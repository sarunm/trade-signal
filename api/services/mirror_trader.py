from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade import Direction, OrderState, PaperMode, Trade
from schemas.trade_event import TradeEventSchema

MIN_CONTEXT_TRADES = 2
PRICE_QUANT = Decimal("0.00001")


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

    paper_tp, tp_strategy = await _compute_paper_tp(session, event)
    paper_sl, sl_strategy = await _compute_paper_sl(session, event)

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
        paper_exit_strategy=_strategy_label(tp_strategy, sl_strategy),
    ))


async def _compute_paper_tp(
    session: AsyncSession,
    event: TradeEventSchema,
) -> tuple[Optional[Decimal], str]:
    avg_offset, strategy = await _average_offset(session, event, profitable=True)
    if avg_offset is None:
        return None, strategy
    open_price = event.open_price
    if event.direction and event.direction == Direction.buy:
        return (open_price + avg_offset).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP), strategy
    return (open_price - avg_offset).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP), strategy


async def _compute_paper_sl(
    session: AsyncSession,
    event: TradeEventSchema,
) -> tuple[Optional[Decimal], str]:
    avg_offset, strategy = await _average_offset(session, event, profitable=False)
    if avg_offset is None:
        return None, strategy
    open_price = event.open_price
    if event.direction and event.direction == Direction.buy:
        return (open_price - avg_offset).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP), strategy
    return (open_price + avg_offset).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP), strategy


async def _average_offset(
    session: AsyncSession,
    event: TradeEventSchema,
    profitable: bool,
) -> tuple[Optional[Decimal], str]:
    profit_filter = Trade.profit > 0 if profitable else Trade.profit < 0
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.direction == event.direction,
            Trade.symbol == event.symbol,
            profit_filter,
            Trade.close_price.isnot(None),
            Trade.open_price.isnot(None),
            Trade.open_time.isnot(None),
        )
    )
    trades = result.scalars().all()
    event_session = _session_for_time(event.open_time or datetime.now(timezone.utc))
    session_trades = [
        trade for trade in trades
        if trade.open_time and _session_for_time(trade.open_time) == event_session
    ]

    if len(session_trades) >= MIN_CONTEXT_TRADES:
        return _mean_offset(session_trades), "session_direction_avg"
    if trades:
        return _mean_offset(trades), "direction_avg"
    return None, "no_history"


def _mean_offset(trades: list[Trade]) -> Decimal:
    offsets = [
        abs(trade.close_price - trade.open_price)
        for trade in trades
        if trade.close_price is not None and trade.open_price is not None
    ]
    return sum(offsets) / len(offsets)


def _session_for_time(value: datetime) -> str:
    hour = value.hour
    if 7 <= hour < 13:
        return "London"
    if 13 <= hour < 22:
        return "NY"
    return "Asia"


def _strategy_label(tp_strategy: str, sl_strategy: str) -> str:
    return f"tp:{tp_strategy};sl:{sl_strategy}"
