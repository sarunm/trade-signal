import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade import OrderState, Trade
from schemas.trade_event import TradeEventSchema
from services.entry_context import fill_entry_context
from services.indicator_engine import recompute_trade_indicators_by_id
from services.trade_advisor import compute_entry_score, compute_recovery_plan


async def upsert_trade(session: AsyncSession, event: TradeEventSchema) -> Trade:
    result = await session.execute(
        select(Trade).where(
            Trade.ticket == event.ticket,
            Trade.symbol == event.symbol,
            Trade.is_paper == False,
        )
    )
    trade = result.scalar_one_or_none()

    if trade is None:
        trade = Trade(
            ticket=event.ticket,
            symbol=event.symbol,
            is_paper=False,
        )
        session.add(trade)

    fields = [
        "direction", "order_type", "order_state", "pending_price",
        "open_time", "fill_time", "close_time", "open_price", "close_price",
        "volume", "tp", "sl", "profit", "swap", "commission",
    ]
    for field in fields:
        value = getattr(event, field)
        if value is not None:
            setattr(trade, field, value)

    if event.account_id is not None:
        trade.account_id = event.account_id

    if event.open_price is not None and event.close_price is None:
        await fill_entry_context(session, trade)
        await compute_entry_score(session, trade)
        await compute_recovery_plan(session, trade)

    should_compute_indicators = (
        event.order_state == OrderState.filled
        and event.open_price is not None
        and event.close_price is None
    )

    await session.commit()
    await session.refresh(trade)
    if should_compute_indicators:
        asyncio.create_task(recompute_trade_indicators_by_id(trade.id))
    return trade
