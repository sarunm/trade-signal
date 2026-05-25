from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade import Direction, OrderState, PaperMode, Trade
from schemas.market_tick import MarketTickSchema

XAUUSD_CONTRACT_SIZE = Decimal("100")


async def close_paper_trades_on_tick(
    session: AsyncSession,
    tick: MarketTickSchema,
) -> int:
    result = await session.execute(
        select(Trade).where(
            Trade.symbol == tick.symbol,
            Trade.is_paper == True,
            Trade.paper_mode == PaperMode.independent,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.close_price.is_(None),
        )
    )
    open_papers = result.scalars().all()

    closed = 0
    for trade in open_papers:
        exit_price, exit_reason = _exit_for_tick(trade, tick)
        if exit_price is None:
            continue
        trade.close_price = exit_price
        trade.close_time = tick.timestamp
        trade.profit = _paper_profit(trade, exit_price)
        trade.paper_exit_reason = exit_reason
        closed += 1

    if closed:
        await session.commit()
    return closed


def _exit_for_tick(
    trade: Trade,
    tick: MarketTickSchema,
) -> tuple[Optional[Decimal], Optional[str]]:
    if trade.direction == Direction.buy:
        if trade.sl is not None and tick.bid <= trade.sl:
            return trade.sl, "sl"
        if trade.tp is not None and tick.bid >= trade.tp:
            return trade.tp, "tp"
    elif trade.direction == Direction.sell:
        if trade.sl is not None and tick.ask >= trade.sl:
            return trade.sl, "sl"
        if trade.tp is not None and tick.ask <= trade.tp:
            return trade.tp, "tp"
    return None, None


def _paper_profit(trade: Trade, exit_price: Decimal) -> Optional[Decimal]:
    if trade.open_price is None or trade.volume is None or trade.direction is None:
        return None

    if trade.direction == Direction.buy:
        raw = (exit_price - trade.open_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    else:
        raw = (trade.open_price - exit_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
