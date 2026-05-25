from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Mapping, Optional, Sequence, Union
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models.indicator_signal import TradeIndicatorSignal
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, Trade

BAR_LOOKBACK_LIMIT = 300


@dataclass
class IndicatorResult:
    slug: str
    value: Optional[float]
    direction: Optional[str]
    matched: bool
    timeframe: str
    metadata: dict = field(default_factory=dict)


IndicatorFn = Callable[
    [Trade, Mapping[str, Sequence[PriceBar]]],
    Union[IndicatorResult, Awaitable[IndicatorResult], None],
]
REGISTRY: dict[str, IndicatorFn] = {}


def register(slug: str):
    def decorator(fn: IndicatorFn):
        REGISTRY[slug] = fn
        return fn

    return decorator


def matches_trade(signal_direction: Optional[str], trade_direction: Union[Direction, str, None]) -> bool:
    if signal_direction is None or trade_direction is None:
        return False
    direction_value = trade_direction.value if isinstance(trade_direction, Direction) else trade_direction
    expected = "bullish" if direction_value == Direction.buy.value else "bearish"
    return signal_direction == expected


async def compute_all(
    trade: Trade,
    bars_by_tf: Mapping[str, Sequence[PriceBar]],
) -> list[IndicatorResult]:
    results: list[IndicatorResult] = []
    for fn in REGISTRY.values():
        result = fn(trade, bars_by_tf)
        if hasattr(result, "__await__"):
            result = await result
        if result is not None:
            results.append(result)
    return results


def select_trade_indicator_signals(trade_id: UUID):
    return (
        select(TradeIndicatorSignal)
        .where(TradeIndicatorSignal.trade_id == trade_id)
        .order_by(TradeIndicatorSignal.calculated_at.asc())
    )


async def fetch_bars_by_timeframe(
    session: AsyncSession,
    trade: Trade,
    limit: int = BAR_LOOKBACK_LIMIT,
) -> dict[str, list[PriceBar]]:
    if trade.open_time is None:
        return {}

    bars_by_tf: dict[str, list[PriceBar]] = {}
    for timeframe in Timeframe:
        result = await session.execute(
            select(PriceBar)
            .where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == timeframe,
                PriceBar.time <= trade.open_time,
            )
            .order_by(PriceBar.time.desc())
            .limit(limit)
        )
        bars = list(reversed(result.scalars().all()))
        if bars:
            bars_by_tf[timeframe.value] = bars
    return bars_by_tf


async def recompute_trade_indicators(
    session: AsyncSession,
    trade: Trade,
) -> list[IndicatorResult]:
    bars_by_tf = await fetch_bars_by_timeframe(session, trade)
    results = await compute_all(trade, bars_by_tf)

    await session.execute(
        delete(TradeIndicatorSignal).where(TradeIndicatorSignal.trade_id == trade.id)
    )
    for result in results:
        session.add(
            TradeIndicatorSignal(
                trade_id=trade.id,
                indicator_slug=result.slug,
                timeframe=result.timeframe,
                value=result.value,
                direction=result.direction,
                matched=result.matched,
                metadata=result.metadata,
                calculated_at=datetime.now(timezone.utc),
            )
        )
    await session.flush()
    return results


async def recompute_trade_indicators_by_id(trade_id: UUID) -> list[IndicatorResult]:
    async with SessionLocal() as session:
        trade = await session.get(Trade, trade_id)
        if trade is None:
            return []
        results = await recompute_trade_indicators(session, trade)
        await session.commit()
        return results


from services import indicators as _indicators  # noqa: E402,F401
