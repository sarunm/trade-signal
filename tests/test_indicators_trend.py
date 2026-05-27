import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from services import indicator_engine


TREND_SLUGS = {
    "sma",
    "ema",
    "dema",
    "tema",
    "wma",
    "hma",
    "kama",
    "mcgd",
    "t3",
    "zlma",
    "macd",
    "psar",
    "adx",
    "ichimoku",
    "aroon",
    "aroon_osc",
    "supertrend",
    "alligator",
    "vortex",
    "stc",
    "mama",
    "ma_envelopes",
    "ma_ribbon",
    "linreg",
    "special_k",
    "trendscore",
    "zlmacd",
    "tcf",
    "chop",
}


def _trade(direction=Direction.buy):
    return Trade(
        id=uuid.uuid4(),
        ticket=91001,
        symbol="GOLD#",
        direction=direction,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        close_price=None,
        is_paper=False,
    )


def _bars(trend=1, count=260):
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        base = Decimal("3200.00") + Decimal(str(trend * i))
        bars.append(
            PriceBar(
                time=start + timedelta(hours=i),
                symbol="GOLD#",
                timeframe=Timeframe.H1,
                open=base - Decimal("0.30"),
                high=base + Decimal("1.00"),
                low=base - Decimal("1.00"),
                close=base + Decimal("0.30"),
                volume=Decimal("1000.00") + Decimal(i),
            )
        )
    return bars


@pytest.mark.asyncio
async def test_trend_indicators_register_all_slugs_and_return_contract():
    import services.indicators  # noqa: F401

    missing = TREND_SLUGS - set(indicator_engine.REGISTRY)
    assert missing == set()

    results = await indicator_engine.compute_all(_trade(), {"H1": _bars(trend=1)})
    trend_results = [result for result in results if result.slug in TREND_SLUGS]

    assert {result.slug for result in trend_results} == TREND_SLUGS
    for result in trend_results:
        assert result.timeframe == "H1"
        assert result.direction in {"bullish", "bearish", "neutral"}
        assert isinstance(result.matched, bool)
        assert isinstance(result.metadata, dict)
        assert result.matched == indicator_engine.matches_trade(
            result.direction,
            Direction.buy,
        )


@pytest.mark.asyncio
async def test_trend_indicator_match_examples_for_sma_and_macd():
    import services.indicators  # noqa: F401

    buy_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(_trade(Direction.buy), {"H1": _bars(trend=1)})
    }
    sell_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(_trade(Direction.sell), {"H1": _bars(trend=-1)})
    }

    assert buy_results["sma"].direction == "bullish"
    assert buy_results["sma"].matched is True
    assert buy_results["macd"].direction == "bullish"
    assert buy_results["macd"].matched is True
    assert sell_results["sma"].direction == "bearish"
    assert sell_results["sma"].matched is True
    assert sell_results["macd"].direction == "bearish"
    assert sell_results["macd"].matched is True
