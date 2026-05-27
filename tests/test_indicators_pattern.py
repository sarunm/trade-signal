import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from services import indicator_engine


PATTERN_SLUGS = {
    "fractals",
    "heikinashi",
    "candle_pattern",
    "bw_mfi",
    "renko",
    "pnf",
    "kagi",
    "tlb",
    "rei_pattern",
}


def _trade(direction=Direction.buy):
    return Trade(
        id=uuid.uuid4(),
        ticket=94001,
        symbol="GOLD#",
        direction=direction,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        close_price=None,
        is_paper=False,
    )


def _bars(trend=1, count=120):
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        base = Decimal("3200.00") + Decimal(str(trend * i))
        bars.append(
            PriceBar(
                time=start + timedelta(hours=i),
                symbol="GOLD#",
                timeframe=Timeframe.H1,
                open=base - Decimal("0.40") if trend > 0 else base + Decimal("0.40"),
                high=base + Decimal("1.20"),
                low=base - Decimal("1.20"),
                close=base + Decimal("0.40") if trend > 0 else base - Decimal("0.40"),
                volume=Decimal("1000.00") + Decimal(i % 30),
            )
        )
    return bars


def _bars_with_engulfing(direction="bullish", count=120):
    """Build a clean uptrend/downtrend then a final engulfing candle of the requested direction."""
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = []
    if direction == "bullish":
        # Downtrend leading to bullish engulfing
        for i in range(count - 2):
            base = Decimal("3300.00") - Decimal(str(i * 0.5))
            bars.append(
                PriceBar(
                    time=start + timedelta(hours=i),
                    symbol="GOLD#",
                    timeframe=Timeframe.H1,
                    open=base + Decimal("0.40"),
                    high=base + Decimal("0.60"),
                    low=base - Decimal("0.60"),
                    close=base - Decimal("0.40"),
                    volume=Decimal("1000.00") + Decimal(i % 30),
                )
            )
        # Penultimate bar: small bearish candle
        prev_base = Decimal("3300.00") - Decimal(str((count - 2) * 0.5))
        prev_open = prev_base + Decimal("0.50")
        prev_close = prev_base - Decimal("0.50")
        bars.append(
            PriceBar(
                time=start + timedelta(hours=count - 2),
                symbol="GOLD#",
                timeframe=Timeframe.H1,
                open=prev_open,
                high=prev_open + Decimal("0.20"),
                low=prev_close - Decimal("0.20"),
                close=prev_close,
                volume=Decimal("1100"),
            )
        )
        # Last bar: bullish candle that engulfs the previous body
        last_open = prev_close - Decimal("0.10")
        last_close = prev_open + Decimal("0.20")
        bars.append(
            PriceBar(
                time=start + timedelta(hours=count - 1),
                symbol="GOLD#",
                timeframe=Timeframe.H1,
                open=last_open,
                high=last_close + Decimal("0.30"),
                low=last_open - Decimal("0.30"),
                close=last_close,
                volume=Decimal("2000"),
            )
        )
    else:
        # Uptrend leading to bearish engulfing
        for i in range(count - 2):
            base = Decimal("3200.00") + Decimal(str(i * 0.5))
            bars.append(
                PriceBar(
                    time=start + timedelta(hours=i),
                    symbol="GOLD#",
                    timeframe=Timeframe.H1,
                    open=base - Decimal("0.40"),
                    high=base + Decimal("0.60"),
                    low=base - Decimal("0.60"),
                    close=base + Decimal("0.40"),
                    volume=Decimal("1000.00") + Decimal(i % 30),
                )
            )
        prev_base = Decimal("3200.00") + Decimal(str((count - 2) * 0.5))
        prev_open = prev_base - Decimal("0.50")
        prev_close = prev_base + Decimal("0.50")
        bars.append(
            PriceBar(
                time=start + timedelta(hours=count - 2),
                symbol="GOLD#",
                timeframe=Timeframe.H1,
                open=prev_open,
                high=prev_close + Decimal("0.20"),
                low=prev_open - Decimal("0.20"),
                close=prev_close,
                volume=Decimal("1100"),
            )
        )
        last_open = prev_close + Decimal("0.10")
        last_close = prev_open - Decimal("0.20")
        bars.append(
            PriceBar(
                time=start + timedelta(hours=count - 1),
                symbol="GOLD#",
                timeframe=Timeframe.H1,
                open=last_open,
                high=last_open + Decimal("0.30"),
                low=last_close - Decimal("0.30"),
                close=last_close,
                volume=Decimal("2000"),
            )
        )
    return bars


@pytest.mark.asyncio
async def test_pattern_indicators_register_all_slugs_and_return_contract():
    import services.indicators  # noqa: F401

    missing = PATTERN_SLUGS - set(indicator_engine.REGISTRY)
    assert missing == set()

    results = await indicator_engine.compute_all(
        _trade(Direction.buy),
        {"H1": _bars(trend=1)},
    )
    pattern_results = [result for result in results if result.slug in PATTERN_SLUGS]

    assert {result.slug for result in pattern_results} == PATTERN_SLUGS
    for result in pattern_results:
        assert result.timeframe == "H1"
        assert result.direction in {"bullish", "bearish", "neutral"}
        assert isinstance(result.matched, bool)
        assert isinstance(result.metadata, dict)
        assert result.matched == indicator_engine.matches_trade(
            result.direction,
            Direction.buy,
        )


@pytest.mark.asyncio
async def test_pattern_candle_engulfing_detects_bullish_and_bearish():
    import services.indicators  # noqa: F401

    bullish_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(
            _trade(Direction.buy),
            {"H1": _bars_with_engulfing("bullish")},
        )
    }
    bearish_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(
            _trade(Direction.sell),
            {"H1": _bars_with_engulfing("bearish")},
        )
    }

    assert bullish_results["candle_pattern"].direction == "bullish"
    assert bullish_results["candle_pattern"].matched is True
    assert "bullish_engulfing" in bullish_results["candle_pattern"].metadata["patterns"]

    assert bearish_results["candle_pattern"].direction == "bearish"
    assert bearish_results["candle_pattern"].matched is True
    assert "bearish_engulfing" in bearish_results["candle_pattern"].metadata["patterns"]


@pytest.mark.asyncio
async def test_pattern_renko_and_kagi_track_trend_direction():
    import services.indicators  # noqa: F401

    up_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(
            _trade(Direction.buy),
            {"H1": _bars(trend=1)},
        )
    }
    down_results = {
        result.slug: result
        for result in await indicator_engine.compute_all(
            _trade(Direction.sell),
            {"H1": _bars(trend=-1)},
        )
    }

    assert up_results["renko"].direction == "bullish"
    assert up_results["renko"].matched is True
    assert up_results["kagi"].direction == "bullish"
    assert up_results["kagi"].matched is True
    assert down_results["renko"].direction == "bearish"
    assert down_results["renko"].matched is True
    assert down_results["kagi"].direction == "bearish"
    assert down_results["kagi"].matched is True
