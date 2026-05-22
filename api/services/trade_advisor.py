from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.alert import Alert
from models.fib_level import FibLevel
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from schemas.market_tick import MarketTickSchema

_FIB_PROXIMITY_PTS = 5.0
_MIN_SESSION_SAMPLE = 5


def _get_session(dt: datetime) -> str | None:
    h = dt.astimezone(timezone.utc).hour if dt.tzinfo else dt.replace(tzinfo=timezone.utc).hour
    if 1 <= h < 9:
        return "Asian"
    if 8 <= h < 16:
        return "London"
    if 13 <= h < 22:
        return "NY"
    return None


def _peak_hours_score(open_time: datetime) -> int:
    dt = open_time.astimezone(timezone.utc) if open_time.tzinfo else open_time.replace(tzinfo=timezone.utc)
    h = dt.hour
    weekday = dt.weekday()  # 0=Monday, 4=Friday
    if (weekday == 4 and h >= 17) or (weekday == 0 and h < 8):
        return -10
    if (8 <= h < 11) or (13 <= h < 16):
        return 10
    return 0


async def _session_win_rate(session: AsyncSession, trade: Trade) -> float | None:
    if trade.open_time is None:
        return None
    current_session = _get_session(trade.open_time)
    if not current_session:
        return None

    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == trade.symbol,
            Trade.order_state == OrderState.filled,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
            Trade.is_rescue == False,
        ).order_by(Trade.close_time.desc()).limit(50)
    )
    trades = result.scalars().all()
    session_trades = [t for t in trades if t.open_time and _get_session(t.open_time) == current_session]
    if len(session_trades) < _MIN_SESSION_SAMPLE:
        return None
    wins = sum(1 for t in session_trades if float(t.profit) > 0)
    return wins / len(session_trades)


async def _consecutive_setup_losses(session: AsyncSession, trade: Trade) -> int:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == trade.symbol,
            Trade.direction == trade.direction,
            Trade.is_rescue == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
            Trade.id != trade.id,
        ).order_by(Trade.close_time.desc()).limit(10)
    )
    recent = result.scalars().all()
    losses = 0
    for t in recent:
        if float(t.profit) < 0:
            losses += 1
        else:
            break
    return min(losses, 2)


async def _atr_score(session: AsyncSession, trade: Trade) -> int:
    result = await session.execute(
        select(PriceBar).where(
            PriceBar.symbol == trade.symbol,
            PriceBar.timeframe == Timeframe.H4,
        ).order_by(PriceBar.time.desc()).limit(21)
    )
    bars = list(reversed(result.scalars().all()))
    # No data → assume normal ATR (stable market, no evidence of spike)
    if len(bars) < 3:
        return 10
    true_ranges = []
    for i in range(1, len(bars)):
        high = float(bars[i].high)
        low = float(bars[i].low)
        prev_close = float(bars[i - 1].close)
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if not true_ranges:
        return 10
    avg_atr = sum(true_ranges[:-1]) / max(len(true_ranges) - 1, 1)
    current_atr = true_ranges[-1]
    if avg_atr == 0:
        return 10
    return -10 if current_atr > 1.5 * avg_atr else 10


async def compute_entry_score(session: AsyncSession, trade: Trade) -> None:
    if trade.entry_score is not None:
        return
    if trade.open_price is None or trade.direction is None:
        return

    score = 0

    # 1. Fib alignment
    dist = float(trade.fib_distance_pts or 999)
    if trade.near_fib_level == "PP" and dist <= _FIB_PROXIMITY_PTS:
        score += 25
    elif trade.near_fib_level is not None and dist <= _FIB_PROXIMITY_PTS:
        score += 20

    # 2. Session win rate
    win_rate = await _session_win_rate(session, trade)
    if win_rate is not None:
        if win_rate > 0.60:
            score += 20
        elif win_rate < 0.40:
            score -= 15

    # 3. Entry pattern
    candle = trade.entry_candle or ""
    if candle not in ("none", "doji", ""):
        if trade.direction == Direction.buy and "bullish" in candle:
            score += 20
        elif trade.direction == Direction.sell and "bearish" in candle:
            score += 20

    # 4. Rescue placement
    if trade.is_rescue:
        if trade.near_fib_level is not None and dist <= _FIB_PROXIMITY_PTS:
            score += 15
        else:
            score -= 15

    # 5. ATR state
    score += await _atr_score(session, trade)

    # 6. Session peak hours
    if trade.open_time:
        score += _peak_hours_score(trade.open_time)

    # 7. Consecutive setup losses — penalty per loss, small bonus when clean slate
    losses = await _consecutive_setup_losses(session, trade)
    if losses == 0:
        score += 5
    else:
        score -= losses * 15

    trade.entry_score = score
    if score >= 70:
        trade.entry_verdict = "good"
    elif score >= 40:
        trade.entry_verdict = "caution"
    else:
        trade.entry_verdict = "high_risk"


async def compute_recovery_plan(session: AsyncSession, trade: Trade) -> None:
    if trade.recovery_plan is not None:
        return
    if trade.open_price is None or trade.direction is None:
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

    entry = float(trade.open_price)
    direction = trade.direction

    all_r = sorted(
        [(k, float(v)) for k, v in fib.resistance.items()],
        key=lambda x: x[1],
    )
    all_s = sorted(
        [(k, float(v)) for k, v in fib.support.items()],
        key=lambda x: x[1],
        reverse=True,
    )

    def make_zone(label: str, price: float) -> dict:
        return {
            "label": label,
            "price": round(price, 2),
            "pts": round(price - entry, 2),
        }

    if direction == Direction.buy:
        tp_candidates = [(k, v) for k, v in all_r if v > entry]
        add_candidates = [(k, v) for k, v in all_s if v < entry]
        cut_candidates = [(k, v) for k, v in all_s if v < entry]
    else:
        tp_candidates = [(k, v) for k, v in all_s if v < entry]
        add_candidates = [(k, v) for k, v in all_r if v > entry]
        cut_candidates = [(k, v) for k, v in all_r if v > entry]

    tp_zones = [make_zone(k, v) for k, v in tp_candidates[:3]]
    add_zones = [make_zone(k, v) for k, v in add_candidates[:3]]
    cut_tuple = cut_candidates[3] if len(cut_candidates) > 3 else (cut_candidates[-1] if cut_candidates else None)

    if not tp_zones or not add_zones or cut_tuple is None:
        return

    trade.recovery_plan = {
        "entry_price": round(entry, 2),
        "direction": direction.value,
        "tp": tp_zones,
        "add": add_zones,
        "cut": make_zone(cut_tuple[0], cut_tuple[1]),
    }


def _zone_crossed(bid: float, level: float, direction: Direction, side: str) -> bool:
    if direction == Direction.buy:
        return bid >= level if side == "tp" else bid <= level
    else:
        return bid <= level if side == "tp" else bid >= level


async def _already_alerted(session: AsyncSession, trade_id, alert_type: str, label: str) -> bool:
    result = await session.execute(
        select(Alert).where(
            Alert.type == alert_type,
            Alert.trade_id == trade_id,
        )
    )
    existing = result.scalars().all()
    return any(
        a.trigger_data and a.trigger_data.get("label") == label
        for a in existing
    )


async def _fire_alert(
    session: AsyncSession,
    trade: Trade,
    zone: dict,
    alert_type: str,
) -> None:
    if await _already_alerted(session, trade.id, alert_type, zone["label"]):
        return

    messages = {
        "tp_zone_reached": f"Price at {zone['label']} ({zone['price']:.2f}) — TP reached",
        "add_zone_reached": f"Price at {zone['label']} ({zone['price']:.2f}) — Add zone reached",
        "cut_zone_reached": f"WARNING {zone['label']} breached ({zone['price']:.2f}) — consider cutting",
    }
    session.add(Alert(
        type=alert_type,
        message=messages[alert_type],
        trigger_data={**zone, "trade_id": str(trade.id)},
        sent_at=datetime.now(timezone.utc),
        trade_id=trade.id,
    ))


async def check_advisor_zones(session: AsyncSession, tick: MarketTickSchema) -> None:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.symbol == tick.symbol,
            Trade.recovery_plan.isnot(None),
        )
    )
    open_trades = result.scalars().all()

    bid = float(tick.bid)
    for trade in open_trades:
        plan = trade.recovery_plan

        for zone in plan.get("tp", []):
            if _zone_crossed(bid, zone["price"], trade.direction, "tp"):
                await _fire_alert(session, trade, zone, "tp_zone_reached")

        for zone in plan.get("add", []):
            if _zone_crossed(bid, zone["price"], trade.direction, "add"):
                await _fire_alert(session, trade, zone, "add_zone_reached")

        cut = plan.get("cut")
        if cut and _zone_crossed(bid, cut["price"], trade.direction, "cut"):
            await _fire_alert(session, trade, cut, "cut_zone_reached")

    await session.commit()
