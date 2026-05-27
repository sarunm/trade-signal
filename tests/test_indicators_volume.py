import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from services import indicator_engine


VOLUME_SLUGS = {
    "obv",
    "vwap",
    "avwap",
    "ad",
    "cmf",
    "chaikin_osc",
    "mfi",
    "vpt",
    "kvo",
    "eom",
    "pvi",
    "nvi",
    "vrsi",
    "rvol",
    "pvo",
    "tvi",
    "vol_profile",
    "smi_vol",
    "volume_raw",
}


def _trade(direction=Direction.buy):
    return Trade(
        id=uuid.uuid4(),
        ticket=93001,
        symbol="GOLD#",
        direction=direction,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        close_price=None,
        is_paper=False,
    )


def _bars(trend=1, count=320, final_spike=False):
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        base = Decimal("3200.00") + Decimal(str(trend * i))
        volume = Decimal("1000.00") + Decimal(i % 30)
        if final_spike and i == count - 1:
            volume = Decimal("5000.00")
            base = base + Decimal("6.00") if trend > 0 else base - Decimal("6.00")
        bars.append(
            PriceBar(
                time=start + timedelta(hours=i),
                symbol="GOLD#",
                timeframe=Timeframe.H1,
                open=base - Decimal("0.40") if trend > 0 else base + Decimal("0.40"),
                high=base + Decimal("1.20"),
                low=base - Decimal("1.20"),
                close=base + Decimal("0.40") if trend > 0 else base - Decimal("0.40"),
                volume=volume,
            )
        )
    return bars


@pytest.mark.asyncio
async def test_volume_indicators_register_all_slugs_and_return_contract():
    import services.indicators  # noqa: F401

    missing = VOLUME_SLUGS - set(indicator_engine.REGISTRY)
    assert missing == set()

    results = await indicator_engine.compute_all(
        _trade(Direction.buy),
        {"H1": _bars(trend=1, final_spike=True)},
    )
    volume_results = [result for result in results if result.slug in VOLUME_SLUGS]

    assert {result.slug for result in volume_results} == VOLUME_SLUGS
    for result in volume_results:
        assert result.timeframe == "H1"
        assert result.direction in {"bullish", "bearish", "neutral"}
        assert isinstance(result.matched, bool)
        assert isinstance(result.metadata, dict)
        assert result.matched == indicator_engine.matches_trade(
            result.direction,
            Direction.buy,
        )


@pytest.mark.asyncio
async def test_volume_indicator_match_examples_for_obv_vwap_and_spikes():
    import services.indicators  # noqa: F401

    buy_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(
            _trade(Direction.buy),
            {"H1": _bars(trend=1, final_spike=True)},
        )
    }
    sell_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(
            _trade(Direction.sell),
            {"H1": _bars(trend=-1, final_spike=True)},
        )
    }

    assert buy_results["obv"].direction == "bullish"
    assert buy_results["obv"].matched is True
    assert buy_results["vwap"].direction == "bullish"
    assert buy_results["vwap"].matched is True
    assert buy_results["volume_raw"].direction == "bullish"
    assert buy_results["volume_raw"].matched is True
    assert sell_results["obv"].direction == "bearish"
    assert sell_results["obv"].matched is True
    assert sell_results["volume_raw"].direction == "bearish"
    assert sell_results["volume_raw"].matched is True
