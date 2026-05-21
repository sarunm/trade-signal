from datetime import timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fib_level import FibLevel
from models.price_bar import PriceBar, Timeframe
from models.trade import OrderState, Trade
from services.pattern_detector import detect_engulfing, detect_pin_bar


async def fill_entry_context(session: AsyncSession, trade: Trade) -> None:
    await _fill_fib_proximity(session, trade)
    await _fill_entry_candle(session, trade)
    await _fill_is_rescue(session, trade)


async def _fill_fib_proximity(session: AsyncSession, trade: Trade) -> None:
    if trade.open_price is None:
        return

    result = await session.execute(
        select(FibLevel)
        .where(FibLevel.symbol == trade.symbol)
        .order_by(FibLevel.computed_at.desc())
        .limit(1)
    )
    fib = result.scalar_one_or_none()
    if fib is None:
        return

    open_price = Decimal(trade.open_price)
    candidates = []
    candidates.append(("PP", Decimal(str(fib.pp))))
    for key, price in fib.resistance.items():
        candidates.append((key, Decimal(str(price))))
    for key, price in fib.support.items():
        candidates.append((key, Decimal(str(price))))

    if not candidates:
        return

    nearest_label, nearest_price = min(
        candidates,
        key=lambda item: abs(open_price - item[1]),
    )
    trade.near_fib_level = nearest_label
    trade.fib_distance_pts = abs(open_price - nearest_price).quantize(Decimal("0.01"))


async def _fill_entry_candle(session: AsyncSession, trade: Trade) -> None:
    if trade.open_time is None:
        return

    open_time = trade.open_time
    if open_time.tzinfo is None:
        open_time = open_time.replace(tzinfo=timezone.utc)

    tf_configs = [
        (
            Timeframe.H4,
            timedelta(hours=4),
            open_time.replace(
                hour=(open_time.hour // 4) * 4,
                minute=0,
                second=0,
                microsecond=0,
            ),
        ),
        (Timeframe.H1, timedelta(hours=1), open_time.replace(minute=0, second=0, microsecond=0)),
        (
            Timeframe.M30,
            timedelta(minutes=30),
            open_time.replace(minute=(open_time.minute // 30) * 30, second=0, microsecond=0),
        ),
        (
            Timeframe.M15,
            timedelta(minutes=15),
            open_time.replace(minute=(open_time.minute // 15) * 15, second=0, microsecond=0),
        ),
    ]

    for tf, duration, bar_start in tf_configs:
        bar_res = await session.execute(
            select(PriceBar).where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == tf,
                PriceBar.time >= bar_start,
                PriceBar.time < bar_start + duration,
            ).order_by(PriceBar.time.desc()).limit(1)
        )
        bar = bar_res.scalar_one_or_none()
        if bar is None:
            continue

        prev_res = await session.execute(
            select(PriceBar).where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == tf,
                PriceBar.time >= bar_start - duration,
                PriceBar.time < bar_start,
            ).order_by(PriceBar.time.desc()).limit(1)
        )
        prev_bar = prev_res.scalar_one_or_none()

        bars = []
        if prev_bar:
            bars.append({
                "open": prev_bar.open,
                "high": prev_bar.high,
                "low": prev_bar.low,
                "close": prev_bar.close,
            })
        bars.append({
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
        })

        pin = detect_pin_bar(bars)
        if pin:
            trade.entry_candle = f"pin_bar_{pin}"
            trade.entry_candle_tf = tf.value
            return

        eng = detect_engulfing(bars)
        if eng:
            trade.entry_candle = f"engulfing_{eng}"
            trade.entry_candle_tf = tf.value
            return

        if bar.open == bar.close:
            trade.entry_candle = "doji"
            trade.entry_candle_tf = tf.value
            return

    trade.entry_candle = "none"
    trade.entry_candle_tf = None


async def _fill_is_rescue(session: AsyncSession, trade: Trade) -> None:
    if trade.symbol is None or trade.direction is None:
        return

    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == trade.symbol,
            Trade.direction == trade.direction,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.ticket != trade.ticket,
        )
    )
    existing = result.scalars().all()
    trade.is_rescue = len(existing) > 0
