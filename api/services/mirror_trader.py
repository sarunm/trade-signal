from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade import OrderState, PaperMode, Trade
from schemas.trade_event import TradeEventSchema


MIRROR_EXIT_STRATEGY = "rule_driven"


async def create_mirror_trade(session: AsyncSession, event: TradeEventSchema) -> None:
    if event.order_state != OrderState.filled:
        return
    if event.close_price is not None:
        return
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

    session.add(Trade(
        ticket=event.ticket,
        symbol=event.symbol,
        direction=event.direction,
        order_type=event.order_type,
        order_state=OrderState.filled,
        open_price=event.open_price,
        volume=event.volume,
        open_time=event.open_time or datetime.now(timezone.utc),
        tp=None,
        sl=None,
        account_id=event.account_id,
        is_paper=True,
        paper_mode=PaperMode.mirror,
        paper_exit_strategy=MIRROR_EXIT_STRATEGY,
    ))
