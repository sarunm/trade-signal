from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.trade import Trade, OrderState, PaperMode
from schemas.trade_event import TradeEventSchema


async def create_mirror_trade(session: AsyncSession, event: TradeEventSchema) -> None:
    if event.order_state != OrderState.filled:
        return
    if event.close_price is not None:
        return  # exit event, not entry
    if event.open_price is None:
        return

    existing = await session.execute(
        select(Trade).where(
            Trade.ticket == event.ticket,
            Trade.symbol == event.symbol,
            Trade.is_paper == True,
            Trade.paper_mode == PaperMode.mirror,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    paper_tp = await _compute_paper_tp(session, event)
    paper_sl = await _compute_paper_sl(session, event)

    session.add(Trade(
        ticket=event.ticket,
        symbol=event.symbol,
        direction=event.direction,
        order_type=event.order_type,
        order_state=OrderState.filled,
        open_price=event.open_price,
        volume=event.volume,
        open_time=event.open_time or datetime.now(timezone.utc),
        tp=paper_tp,
        sl=paper_sl,
        is_paper=True,
        paper_mode=PaperMode.mirror,
    ))


async def _compute_paper_tp(session: AsyncSession, event: TradeEventSchema) -> Optional[Decimal]:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.direction == event.direction,
            Trade.profit > 0,
            Trade.tp.isnot(None),
            Trade.open_price.isnot(None),
        )
    )
    wins = result.scalars().all()
    offsets = [
        abs(float(t.tp) - float(t.open_price))
        for t in wins
        if t.tp and t.open_price
    ]
    if not offsets:
        return None

    avg_offset = sum(offsets) / len(offsets)
    open_price = float(event.open_price)
    if event.direction and event.direction.value == "buy":
        return Decimal(str(round(open_price + avg_offset, 5)))
    return Decimal(str(round(open_price - avg_offset, 5)))


async def _compute_paper_sl(session: AsyncSession, event: TradeEventSchema) -> Optional[Decimal]:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.direction == event.direction,
            Trade.profit < 0,
            Trade.close_price.isnot(None),
            Trade.open_price.isnot(None),
        )
    )
    losses = result.scalars().all()
    offsets = [
        abs(float(t.close_price) - float(t.open_price))
        for t in losses
        if t.close_price and t.open_price
    ]
    if not offsets:
        return None

    avg_offset = sum(offsets) / len(offsets)
    open_price = float(event.open_price)
    if event.direction and event.direction.value == "buy":
        return Decimal(str(round(open_price - avg_offset, 5)))
    return Decimal(str(round(open_price + avg_offset, 5)))
