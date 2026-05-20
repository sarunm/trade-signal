import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from models.fib_level import FibLevel
from models.trade import Direction, OrderState, Trade
from services.entry_context import fill_entry_context


def _make_trade(**kwargs) -> Trade:
    defaults = dict(
        id=uuid.uuid4(),
        ticket=1001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        is_paper=False,
    )
    defaults.update(kwargs)
    return Trade(**defaults)


@pytest.mark.asyncio
async def test_fill_fib_proximity_finds_nearest_level(db_session):
    fib = FibLevel(
        symbol="XAUUSD",
        timeframe="D",
        swing_high=2050.0,
        swing_low=1950.0,
        direction="bullish",
        levels={"0.000": 1983.33, "0.236": 2006.93, "0.618": 2045.17},
        extensions={"0.236": 1959.73, "0.618": 1921.50},
        computed_at=datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc),
    )
    db_session.add(fib)
    await db_session.commit()

    trade = _make_trade(open_price=Decimal("1962.00"))
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.near_fib_level == "S0.236"
    assert trade.fib_distance_pts is not None
    assert float(trade.fib_distance_pts) == pytest.approx(2.27, abs=0.1)


@pytest.mark.asyncio
async def test_fill_fib_proximity_labels_pp_correctly(db_session):
    fib = FibLevel(
        symbol="XAUUSD",
        timeframe="D",
        swing_high=2050.0,
        swing_low=1950.0,
        direction="bullish",
        levels={"0.000": 1983.33, "0.236": 2006.93},
        extensions={"0.236": 1959.73},
        computed_at=datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc),
    )
    db_session.add(fib)
    await db_session.commit()

    trade = _make_trade(open_price=Decimal("1984.00"))
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.near_fib_level == "PP"


@pytest.mark.asyncio
async def test_fill_fib_proximity_skips_when_no_fib_data(db_session):
    trade = _make_trade()
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.near_fib_level is None
    assert trade.fib_distance_pts is None
