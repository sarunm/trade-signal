import math
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from services import indicator_engine


CYCLE_SLUGS = {
    "correlation",
    "r_squared",
    "linreg_slope",
    "kaufman_er",
    "price_relative",
    "rmo",
    "vidya",
    "ravi",
    "dpo_cycle",
    "kurtosis",
    "hv_percentile",
    "zscore",
    "hurst",
}


def _trade(direction=Direction.buy):
    return Trade(
        id=uuid.uuid4(),
        ticket=94001,
        symbol="XAUUSD",
        direction=direction,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        close_price=None,
        is_paper=False,
    )


def _bars(trend=1, count=320):
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        base = Decimal("3200.00") + Decimal(str(trend * i * 0.5))
        volume = Decimal("1000.00") + Decimal(i % 30)
        bars.append(
            PriceBar(
                time=start + timedelta(hours=i),
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                open=base - (Decimal("0.40") if trend > 0 else Decimal("-0.40")),
                high=base + Decimal("1.20"),
                low=base - Decimal("1.20"),
                close=base + (Decimal("0.40") if trend > 0 else Decimal("-0.40")),
                volume=volume,
            )
        )
    return bars


def _flat_bars(count=320, base_price=3300.0):
    """Bars that oscillate tightly around a constant — used to test mean-reversion / low-volatility behavior."""
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        wiggle = math.sin(i / 5.0) * 0.5
        close = Decimal(str(round(base_price + wiggle, 2)))
        bars.append(
            PriceBar(
                time=start + timedelta(hours=i),
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                open=close,
                high=close + Decimal("0.20"),
                low=close - Decimal("0.20"),
                close=close,
                volume=Decimal("1000.00"),
            )
        )
    return bars


@pytest.mark.asyncio
async def test_cycle_indicators_register_all_slugs_and_return_contract():
    import services.indicators  # noqa: F401

    missing = CYCLE_SLUGS - set(indicator_engine.REGISTRY)
    assert missing == set()

    results = await indicator_engine.compute_all(
        _trade(Direction.buy),
        {"H1": _bars(trend=1)},
    )
    cycle_results = [result for result in results if result.slug in CYCLE_SLUGS]

    assert {result.slug for result in cycle_results} == CYCLE_SLUGS
    for result in cycle_results:
        assert result.timeframe == "H1"
        assert result.direction in {"bullish", "bearish", "neutral"}
        assert isinstance(result.matched, bool)
        assert isinstance(result.metadata, dict)
        assert result.metadata.get("group") == "cycle"
        assert result.matched == indicator_engine.matches_trade(
            result.direction,
            Direction.buy,
        )


@pytest.mark.asyncio
async def test_cycle_linreg_slope_and_correlation_match_uptrend():
    import services.indicators  # noqa: F401

    buy_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(
            _trade(Direction.buy),
            {"H1": _bars(trend=1)},
        )
    }
    sell_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(
            _trade(Direction.sell),
            {"H1": _bars(trend=-1)},
        )
    }

    assert buy_results["linreg_slope"].direction == "bullish"
    assert buy_results["linreg_slope"].matched is True
    assert buy_results["correlation"].direction == "bullish"
    assert buy_results["correlation"].matched is True
    assert buy_results["price_relative"].direction == "bullish"
    assert buy_results["price_relative"].matched is True
    assert buy_results["r_squared"].direction == "bullish"
    assert buy_results["r_squared"].matched is True

    assert sell_results["linreg_slope"].direction == "bearish"
    assert sell_results["linreg_slope"].matched is True
    assert sell_results["price_relative"].direction == "bearish"
    assert sell_results["price_relative"].matched is True
    assert sell_results["r_squared"].direction == "bearish"
    assert sell_results["r_squared"].matched is True


@pytest.mark.asyncio
async def test_cycle_indicators_handle_insufficient_bars():
    import services.indicators  # noqa: F401

    # Only 5 bars — well under the minimum window for most cycle indicators.
    results = await indicator_engine.compute_all(
        _trade(Direction.buy),
        {"H1": _bars(trend=1, count=5)},
    )
    cycle_results = {result.slug: result for result in results if result.slug in CYCLE_SLUGS}

    for slug, result in cycle_results.items():
        # All cycle indicators should degrade gracefully — no crashes, neutral default.
        assert result.direction in {"bullish", "bearish", "neutral"}
        assert isinstance(result.metadata, dict)
