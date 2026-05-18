from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.price_bar import PriceBar, Timeframe
from models.alert import Alert
from schemas.price_tick import PriceTickSchema

PATTERN_ALERT_COOLDOWN_HOURS = 4


def detect_pin_bar(bars: list) -> Optional[str]:
    """Returns 'bullish', 'bearish', or None. bars: list of dicts with Decimal open/high/low/close."""
    if not bars:
        return None
    b = bars[-1]
    open_, high, low, close = b["open"], b["high"], b["low"], b["close"]
    body = abs(close - open_)
    candle_range = high - low
    if candle_range == 0:
        return None
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    if lower_wick >= 2 * body and lower_wick >= Decimal("0.6") * candle_range:
        return "bullish"
    if upper_wick >= 2 * body and upper_wick >= Decimal("0.6") * candle_range:
        return "bearish"
    return None


def detect_engulfing(bars: list) -> Optional[str]:
    """Returns 'bullish', 'bearish', or None. Requires at least 2 bars."""
    if len(bars) < 2:
        return None
    prev, curr = bars[-2], bars[-1]
    prev_open, prev_close = prev["open"], prev["close"]
    curr_open, curr_close = curr["open"], curr["close"]
    if prev_close < prev_open and curr_close > prev_open and curr_open < prev_close:
        return "bullish"
    if prev_close > prev_open and curr_close < prev_open and curr_open > prev_close:
        return "bearish"
    return None


async def run_pattern_detector(session: AsyncSession, tick: PriceTickSchema) -> None:
    for tf in [Timeframe.H1, Timeframe.H4]:
        await _check_timeframe(session, tick.symbol, tf)
    await session.commit()


async def _check_timeframe(session: AsyncSession, symbol: str, tf: Timeframe) -> None:
    result = await session.execute(
        select(PriceBar)
        .where(PriceBar.symbol == symbol, PriceBar.timeframe == tf)
        .order_by(PriceBar.time.desc())
        .limit(2)
    )
    rows = list(reversed(result.scalars().all()))
    if not rows:
        return
    bars = [{"open": r.open, "high": r.high, "low": r.low, "close": r.close} for r in rows]

    for pattern_name, direction in [("pin_bar", detect_pin_bar(bars)), ("engulfing", detect_engulfing(bars))]:
        if direction is None:
            continue
        if await _is_duplicate(session, tf.value, pattern_name, direction):
            continue
        session.add(Alert(
            type="pattern_alert",
            message=f"{pattern_name.replace('_', ' ').title()} ({direction}) detected on {tf.value}",
            trigger_data={
                "pattern": pattern_name,
                "direction": direction,
                "timeframe": tf.value,
                "open": str(rows[-1].open),
                "high": str(rows[-1].high),
                "low": str(rows[-1].low),
                "close": str(rows[-1].close),
            },
            sent_at=datetime.now(timezone.utc),
            acknowledged=False,
        ))


async def _is_duplicate(session: AsyncSession, timeframe: str, pattern: str, direction: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PATTERN_ALERT_COOLDOWN_HOURS)
    result = await session.execute(
        select(Alert).where(Alert.type == "pattern_alert", Alert.sent_at >= cutoff)
    )
    for alert in result.scalars().all():
        td = alert.trigger_data or {}
        if (td.get("pattern") == pattern and
                td.get("direction") == direction and
                td.get("timeframe") == timeframe):
            return True
    return False
