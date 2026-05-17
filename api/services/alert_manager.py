from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.trade import Trade, OrderState, Direction
from models.alert import Alert
from schemas.trade_event import TradeEventSchema
from schemas.price_tick import PriceTickSchema

CONSECUTIVE_LOSS_THRESHOLD = 3
# XAUUSD: 1 std lot = 100 oz. Buffer = 100 oz * $100 adverse move = $10,000 per lot.
# User requires free_margin >= total_open_lots * $10,000.
EQUITY_BUFFER_POINTS = 10000


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
