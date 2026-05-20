import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from models.fib_level import FibLevel
from models.price_bar import PriceBar, Timeframe
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


def _make_bar(symbol, tf, time, open_, high, low, close) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        timeframe=tf,
        time=time,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
    )


@pytest.mark.asyncio
async def test_fill_entry_candle_detects_pin_bar_on_h4(db_session):
    open_time = datetime(2026, 5, 19, 10, 30, tzinfo=timezone.utc)
    bar_start = datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc)

    prev = _make_bar(
        "XAUUSD",
        Timeframe.H4,
        datetime(2026, 5, 19, 4, 0, tzinfo=timezone.utc),
        2010,
        2015,
        2005,
        2012,
    )
    bar = _make_bar("XAUUSD", Timeframe.H4, bar_start, 2010, 2015, 1990, 2013)
    db_session.add(prev)
    db_session.add(bar)
    await db_session.commit()

    trade = _make_trade(open_time=open_time)
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.entry_candle in (
        "pin_bar_bullish",
        "pin_bar_bearish",
        "doji",
        "engulfing_bullish",
        "engulfing_bearish",
    )
    assert trade.entry_candle_tf == "H4"


@pytest.mark.asyncio
async def test_fill_entry_candle_falls_back_to_h1_when_no_h4_bar(db_session):
    open_time = datetime(2026, 5, 19, 10, 30, tzinfo=timezone.utc)
    h1_bar_start = datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc)
    bar = _make_bar("XAUUSD", Timeframe.H1, h1_bar_start, 2010, 2015, 1990, 2013)
    db_session.add(bar)
    await db_session.commit()

    trade = _make_trade(open_time=open_time)
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.entry_candle_tf == "H1"
    assert trade.entry_candle is not None


@pytest.mark.asyncio
async def test_fill_entry_candle_returns_none_when_no_pattern_any_tf(db_session):
    open_time = datetime(2026, 5, 19, 10, 30, tzinfo=timezone.utc)
    trade = _make_trade(open_time=open_time)
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.entry_candle == "none"
    assert trade.entry_candle_tf is None
