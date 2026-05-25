import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from services import indicator_engine


MOMENTUM_SLUGS = {
    "rsi",
    "stoch",
    "stochrsi",
    "smi",
    "willr",
    "cci",
    "mom",
    "roc",
    "uo",
    "demarker",
    "ao",
    "ac",
    "trix",
    "tsi",
    "coppock",
    "kst",
    "pmo",
    "cmo",
    "rmi",
    "elder_ray",
    "force_index",
    "bop",
    "dpo",
    "fisher",
    "rvi",
    "laguerre_rsi",
    "double_stoch",
    "crsi",
    "mass_index",
    "pfe",
    "disparity",
    "inertia",
    "tti",
    "ewo",
    "gator",
    "qqe",
    "cdmi",
    "rainbow",
    "gann_swing",
}


def _trade(direction=Direction.buy):
    return Trade(
        id=uuid.uuid4(),
        ticket=92001,
        symbol="XAUUSD",
        direction=direction,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        close_price=None,
        is_paper=False,
    )


def _bars(trend=1, count=260, final_drop=False):
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        offset = trend * i
        if final_drop and i >= count - 20:
            offset = trend * (count - 20) - (i - (count - 20)) * 4
        base = Decimal("3200.00") + Decimal(str(offset))
        bars.append(
            PriceBar(
                time=start + timedelta(hours=i),
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                open=base - Decimal("0.40"),
                high=base + Decimal("1.20"),
                low=base - Decimal("1.20"),
                close=base + Decimal("0.40"),
                volume=Decimal("1000.00") + Decimal(i),
            )
        )
    return bars


@pytest.mark.asyncio
async def test_momentum_indicators_register_all_slugs_and_return_contract():
    import services.indicators  # noqa: F401

    missing = MOMENTUM_SLUGS - set(indicator_engine.REGISTRY)
    assert missing == set()

    results = await indicator_engine.compute_all(_trade(), {"H1": _bars(trend=1)})
    momentum_results = [result for result in results if result.slug in MOMENTUM_SLUGS]

    assert {result.slug for result in momentum_results} == MOMENTUM_SLUGS
    for result in momentum_results:
        assert result.timeframe == "H1"
        assert result.direction in {"bullish", "bearish", "neutral"}
        assert isinstance(result.matched, bool)
        assert isinstance(result.metadata, dict)
        assert result.matched == indicator_engine.matches_trade(
            result.direction,
            Direction.buy,
        )


@pytest.mark.asyncio
async def test_momentum_indicator_match_examples_for_rsi_and_mom():
    import services.indicators  # noqa: F401

    buy_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(
            _trade(Direction.buy),
            {"H1": _bars(trend=1, final_drop=True)},
        )
    }
    sell_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(_trade(Direction.sell), {"H1": _bars(trend=-1)})
    }

    assert buy_results["rsi"].direction == "bullish"
    assert buy_results["rsi"].matched is True
    assert sell_results["mom"].direction == "bearish"
    assert sell_results["mom"].matched is True
