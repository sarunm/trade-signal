import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from services import indicator_engine


VOLATILITY_SLUGS = {
    "bbands",
    "bbw",
    "atr",
    "kc",
    "donchian",
    "stdev",
    "chaikin_vol",
    "starc",
    "adr",
    "hv",
    "ulcer",
    "ttm_squeeze",
    "pctb",
    "adr_pct",
    "linreg_channel",
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


def _bars(trend=1, count=320, breakout=False):
    """Generate synthetic bars. breakout=True → push final close beyond expected upper band."""
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


@pytest.mark.asyncio
async def test_volatility_indicators_register_all_slugs_and_return_contract():
    import services.indicators  # noqa: F401

    missing = VOLATILITY_SLUGS - set(indicator_engine.REGISTRY)
    assert missing == set()

    results = await indicator_engine.compute_all(
        _trade(Direction.buy),
        {"H1": _bars(trend=1, breakout=True)},
    )
    vlt_results = [r for r in results if r.slug in VOLATILITY_SLUGS]

    assert {r.slug for r in vlt_results} == VOLATILITY_SLUGS
    for result in vlt_results:
        assert result.timeframe == "H1"
        assert result.direction in {"bullish", "bearish", "neutral"}
        assert isinstance(result.matched, bool)
        assert isinstance(result.metadata, dict)
        assert result.matched == indicator_engine.matches_trade(
            result.direction, Direction.buy
        )


@pytest.mark.asyncio
async def test_volatility_donchian_breakout_directions():
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

    assert buy_results["donchian"].direction == "bullish"
    assert buy_results["donchian"].matched is True
    assert sell_results["donchian"].direction == "bearish"
    assert sell_results["donchian"].matched is True


@pytest.mark.asyncio
async def test_volatility_bbands_and_pctb_overshoot_signals_sell_for_long_breakout():
    import services.indicators  # noqa: F401

    results = {
        r.slug: r
        for r in await indicator_engine.compute_all(
            _trade(Direction.sell),
            {"H1": _bars(trend=1, breakout=True)},
        )
    }

    assert results["bbands"].direction == "bearish"
    assert results["bbands"].matched is True
    assert results["pctb"].direction == "bearish"
    assert results["pctb"].matched is True
