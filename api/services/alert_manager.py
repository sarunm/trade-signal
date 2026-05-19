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


async def check_trade_alerts(session: AsyncSession, event: TradeEventSchema) -> None:
    await _check_double_down(session, event)
    await _check_consecutive_loss(session, event)
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
