from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.trade import Trade, OrderState, Direction
from models.alert import Alert
from schemas.trade_event import TradeEventSchema
from schemas.market_tick import MarketTickSchema
from schemas.price_tick import PriceTickSchema

CONSECUTIVE_LOSS_THRESHOLD = 3
# XAUUSD: 1 std lot = 100 oz. Buffer = 100 oz * $100 adverse move = $10,000 per lot.
# User requires free_margin >= total_open_lots * $10,000.
EQUITY_BUFFER_POINTS = 10000
# XAUUSD: 1 point = 0.01 price unit → 200 pts = 20,000 pips (user's threshold)
LARGE_ADVERSE_MOVE_PTS = 200.0
LARGE_ADVERSE_MOVE_COOLDOWN_MINUTES = 10
ALERT_COOLDOWN_HOURS = 24
LOW_WINRATE_THRESHOLD = 0.40
RESCUE_WINRATE_THRESHOLD = 0.35
RESCUE_DELTA_THRESHOLD = 0.20


async def check_trade_alerts(session: AsyncSession, event: TradeEventSchema) -> None:
    await _check_double_down(session, event)
    await _check_consecutive_loss(session, event)
    await _check_session_loss_streak(session, event)
    await session.commit()


async def check_equity_buffer(session: AsyncSession, tick: PriceTickSchema) -> None:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.symbol == tick.symbol,
        )
    )
    open_trades = result.scalars().all()
    if not open_trades:
        return

    total_volume = sum(float(t.volume) for t in open_trades if t.volume)
    required_usd = total_volume * EQUITY_BUFFER_POINTS
    free_margin = float(tick.account.free_margin)

    if free_margin >= required_usd:
        return

    session.add(Alert(
        type="equity_buffer",
        message=(
            f"Free margin ${free_margin:.2f} is below the required "
            f"${required_usd:.2f} buffer for {total_volume:.2f} lots open"
        ),
        trigger_data={
            "free_margin": free_margin,
            "required_buffer": required_usd,
            "total_volume": total_volume,
        },
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))
    await session.commit()


async def check_insight_alerts(session: AsyncSession, tagged: list, trades: list) -> None:
    await _check_low_winrate_setup(session, tagged)
    await _check_rescue_ineffective(session, trades)
    await session.commit()


async def _check_low_winrate_setup(session: AsyncSession, tagged: list) -> None:
    trades_with_profit = [t for t in tagged if t.profit is not None]
    if not trades_with_profit:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=ALERT_COOLDOWN_HOURS)
    recent_res = await session.execute(
        select(Alert).where(
            Alert.type == "low_winrate_setup",
            Alert.sent_at >= cutoff,
        )
    )
    recently_alerted = {
        (a.trigger_data.get("pattern"), a.trigger_data.get("bias"))
        for a in recent_res.scalars().all()
        if a.trigger_data
    }

    from collections import defaultdict
    groups: dict = defaultdict(list)
    for trade in trades_with_profit:
        groups[(trade.setup_pattern, trade.trade_bias)].append(float(trade.profit))

    for (pattern, bias), profits in groups.items():
        if len(profits) < 5:
            continue
        win_rate = sum(1 for profit in profits if profit > 0) / len(profits)
        if win_rate >= LOW_WINRATE_THRESHOLD:
            continue
        if (pattern, bias) in recently_alerted:
            continue

        session.add(Alert(
            type="low_winrate_setup",
            message=(
                f"{pattern} + {bias or 'any'}: ชนะแค่ {win_rate:.0%} "
                f"({len(profits)} เทรด) - setup นี้ประวัติไม่ดี พิจารณาใหม่"
            ),
            trigger_data={
                "pattern": pattern,
                "bias": bias,
                "win_rate": win_rate,
                "count": len(profits),
            },
            sent_at=datetime.now(timezone.utc),
            acknowledged=False,
        ))


async def _check_rescue_ineffective(session: AsyncSession, trades: list) -> None:
    trades_with_data = [
        t for t in trades
        if t.profit is not None and t.is_rescue is not None
    ]
    rescue = [t for t in trades_with_data if t.is_rescue]
    initial = [t for t in trades_with_data if not t.is_rescue]

    if len(rescue) < 5 or len(initial) < 5:
        return

    rescue_wr = sum(1 for t in rescue if float(t.profit) > 0) / len(rescue)
    initial_wr = sum(1 for t in initial if float(t.profit) > 0) / len(initial)

    if rescue_wr >= RESCUE_WINRATE_THRESHOLD:
        return
    if (initial_wr - rescue_wr) <= RESCUE_DELTA_THRESHOLD:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=ALERT_COOLDOWN_HOURS)
    existing = await session.execute(
        select(Alert).where(
            Alert.type == "rescue_ineffective",
            Alert.sent_at >= cutoff,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    session.add(Alert(
        type="rescue_ineffective",
        message=(
            f"ไม้แก้ชนะแค่ {rescue_wr:.0%} vs ไม้เดิม {initial_wr:.0%}"
            f" - ข้อมูลบอกว่าตัดขาดทุนแล้วเริ่มใหม่ดีกว่า"
        ),
        trigger_data={
            "rescue_win_rate": rescue_wr,
            "initial_win_rate": initial_wr,
            "rescue_count": len(rescue),
        },
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))


async def _check_double_down(session: AsyncSession, event: TradeEventSchema) -> None:
    if event.order_state != OrderState.filled:
        return
    if event.close_price is not None:
        return
    if event.open_price is None or not event.direction:
        return

    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == event.symbol,
            Trade.direction == event.direction,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.ticket != event.ticket,
        )
    )
    existing = result.scalars().all()
    if not existing:
        return

    existing_volume = sum(float(t.volume) for t in existing if t.volume)
    session.add(Alert(
        type="double_down",
        message=(
            f"Adding to existing {event.direction.value} position "
            f"({existing_volume:.2f} lots already open on {event.symbol})"
        ),
        trigger_data={
            "symbol": event.symbol,
            "direction": event.direction.value,
            "existing_volume": existing_volume,
            "new_ticket": event.ticket,
        },
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))


async def check_large_adverse_move(session: AsyncSession, tick: MarketTickSchema) -> None:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == tick.symbol,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.open_price.isnot(None),
        )
    )
    open_trades = result.scalars().all()
    if not open_trades:
        return

    cutoff = tick.timestamp - timedelta(minutes=LARGE_ADVERSE_MOVE_COOLDOWN_MINUTES)
    recent_res = await session.execute(
        select(Alert).where(Alert.type == "large_adverse_move", Alert.sent_at >= cutoff)
    )
    recently_alerted = {
        int(a.trigger_data["ticket"])
        for a in recent_res.scalars().all()
        if a.trigger_data and "ticket" in a.trigger_data
    }

    for trade in open_trades:
        if trade.ticket in recently_alerted:
            continue

        open_price = float(trade.open_price)
        if trade.direction == Direction.buy:
            current = float(tick.bid)
            adverse = open_price - current
        else:
            current = float(tick.ask)
            adverse = current - open_price

        if adverse < LARGE_ADVERSE_MOVE_PTS:
            continue

        session.add(Alert(
            type="large_adverse_move",
            message=(
                f"Price moved {adverse:.1f} pts against #{trade.ticket} "
                f"{trade.direction.value} (entry {open_price:.2f} → now {current:.2f}). "
                f"Avoid doubling down."
            ),
            trigger_data={
                "ticket": trade.ticket,
                "symbol": trade.symbol,
                "direction": trade.direction.value,
                "open_price": open_price,
                "current_price": current,
                "adverse_pts": round(adverse, 2),
            },
            sent_at=tick.timestamp,
            acknowledged=False,
        ))

    await session.commit()


async def _check_consecutive_loss(session: AsyncSession, event: TradeEventSchema) -> None:
    if event.profit is None or event.profit >= 0:
        return

    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == event.symbol,
            Trade.order_state == OrderState.filled,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
        ).order_by(Trade.close_time.desc()).limit(CONSECUTIVE_LOSS_THRESHOLD)
    )
    recent = result.scalars().all()

    if len(recent) < CONSECUTIVE_LOSS_THRESHOLD:
        return
    if not all(t.profit < 0 for t in recent):
        return

    total_loss = float(sum(t.profit for t in recent))
    session.add(Alert(
        type="consecutive_loss",
        message=(
            f"{CONSECUTIVE_LOSS_THRESHOLD} consecutive losses detected "
            f"(total: ${total_loss:.2f}). Consider stepping back."
        ),
        trigger_data={
            "count": CONSECUTIVE_LOSS_THRESHOLD,
            "total_loss": total_loss,
            "tickets": [t.ticket for t in recent],
        },
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))


async def _check_session_loss_streak(session: AsyncSession, event: TradeEventSchema) -> None:
    if event.profit is None or event.profit >= 0:
        return

    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == event.symbol,
            Trade.order_state == OrderState.filled,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
        ).order_by(Trade.close_time.desc()).limit(CONSECUTIVE_LOSS_THRESHOLD)
    )
    recent = result.scalars().all()

    if len(recent) < CONSECUTIVE_LOSS_THRESHOLD:
        return
    if not all(t.profit < 0 for t in recent):
        return

    common_sessions = set(_sessions_for_close_time(recent[0].close_time))
    for trade in recent[1:]:
        common_sessions &= set(_sessions_for_close_time(trade.close_time))
    if not common_sessions:
        return

    total_loss = float(sum(t.profit for t in recent))
    session_name = _pick_session(common_sessions)
    session.add(Alert(
        type="session_loss_streak",
        message=(
            f"{CONSECUTIVE_LOSS_THRESHOLD} consecutive losses in {session_name} "
            f"(total: ${total_loss:.2f}). Stop trading this session today."
        ),
        trigger_data={
            "session": session_name,
            "count": CONSECUTIVE_LOSS_THRESHOLD,
            "total_loss": total_loss,
            "tickets": [t.ticket for t in recent],
        },
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))


def _sessions_for_close_time(value: datetime) -> list[str]:
    hour = value.hour
    sessions = []
    if 7 <= hour < 16:
        sessions.append("London")
    if 13 <= hour < 22:
        sessions.append("NY")
    return sessions or ["Asia"]


def _pick_session(sessions: set[str]) -> str:
    for session_name in ("London", "NY", "Asia"):
        if session_name in sessions:
            return session_name
    return "Asia"
