import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from services import indicator_engine


SR_SLUGS = {
    "pivot_std",
    "pivot_woodie",
    "pivot_camarilla",
    "pivot_fib",
    "pivot_demark",
    "fib_retracement",
    "fib_extension",
    "fib_fan",
    "fib_time",
    "murrey",
    "gann_hilo",
    "price_channel",
    "zigzag",
    "vbp",
    "chandelier",
    "rei",
    "se_bands",
    "demark_proj",
}


def _trade(direction=Direction.buy):
    return Trade(
        id=uuid.uuid4(),
        ticket=95001,
        symbol="XAUUSD",
        direction=direction,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        close_price=None,
        is_paper=False,
    )


def _bars(trend=1, count=320, breakout=False):
    """Generate synthetic H1 bars. breakout=True pushes the final close beyond range."""
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        base = Decimal("3200.00") + Decimal(str(trend * i * 0.5))
        if breakout and i == count - 1:
            base = base + Decimal("40.00") if trend > 0 else base - Decimal("40.00")
        if trend > 0:
            open_p = base - Decimal("0.40")
            close_p = base + Decimal("0.40")
        else:
            open_p = base + Decimal("0.40")
            close_p = base - Decimal("0.40")
        high_p = max(open_p, close_p) + Decimal("1.20")
        low_p = min(open_p, close_p) - Decimal("1.20")
        bars.append(
            PriceBar(
                time=start + timedelta(hours=i),
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=Decimal("1000.00") + Decimal(i % 30),
            )
        )
    return bars


def _support_dip_bars(count=320):
    """Generate downtrending bars so the latest close sits well below S1 (pivot support)."""
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        base = Decimal("3400.00") - Decimal(str(i * 0.6))
        if i == count - 1:
            base = base - Decimal("60.00")
        open_p = base + Decimal("0.40")
        close_p = base - Decimal("0.40")
        high_p = max(open_p, close_p) + Decimal("1.20")
        low_p = min(open_p, close_p) - Decimal("1.20")
        bars.append(
            PriceBar(
                time=start + timedelta(hours=i),
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=Decimal("1000.00") + Decimal(i % 30),
            )
        )
    return bars


@pytest.mark.asyncio
async def test_sr_indicators_register_all_slugs_and_return_contract():
    import services.indicators  # noqa: F401

    missing = SR_SLUGS - set(indicator_engine.REGISTRY)
    assert missing == set()

    results = await indicator_engine.compute_all(
        _trade(Direction.buy),
        {"H1": _bars(trend=1, breakout=True)},
    )
    sr_results = [r for r in results if r.slug in SR_SLUGS]

    assert {r.slug for r in sr_results} == SR_SLUGS
    for result in sr_results:
        assert result.timeframe == "H1"
        assert result.direction in {"bullish", "bearish", "neutral"}
        assert isinstance(result.matched, bool)
        assert isinstance(result.metadata, dict)
        assert result.matched == indicator_engine.matches_trade(
            result.direction, Direction.buy
        )


@pytest.mark.asyncio
async def test_sr_pivot_std_emits_bullish_when_close_below_s1():
    import services.indicators  # noqa: F401

    results = {
        r.slug: r
        for r in await indicator_engine.compute_all(
            _trade(Direction.buy),
            {"H1": _support_dip_bars()},
        )
    }
    pivot = results["pivot_std"]
    assert pivot.direction == "bullish"
    assert pivot.matched is True
    assert "s1" in pivot.metadata
    assert pivot.metadata["close"] <= pivot.metadata["s1"]


@pytest.mark.asyncio
async def test_sr_price_channel_breakout_directions():
    import services.indicators  # noqa: F401

    buy_results = {
        r.slug: r
        for r in await indicator_engine.compute_all(
            _trade(Direction.buy),
            {"H1": _bars(trend=1, breakout=True)},
        )
    }
    sell_results = {
        r.slug: r
        for r in await indicator_engine.compute_all(
            _trade(Direction.sell),
            {"H1": _bars(trend=-1, breakout=True)},
        )
    }

    assert buy_results["price_channel"].direction == "bullish"
    assert buy_results["price_channel"].matched is True
    assert sell_results["price_channel"].direction == "bearish"
    assert sell_results["price_channel"].matched is True
