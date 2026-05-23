from dataclasses import dataclass, field
from typing import Awaitable, Callable, Mapping, Optional, Sequence, Union

from models.price_bar import PriceBar
from models.trade import Direction, Trade


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
