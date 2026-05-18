import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select

from models.price_bar import PriceBar, Timeframe
from models.alert import Alert
from services.pattern_detector import detect_pin_bar, detect_engulfing, run_pattern_detector
from schemas.price_tick import PriceTickSchema, AccountStateSchema


def make_tick(symbol="XAUUSD"):
    return PriceTickSchema(
        timestamp=datetime.now(timezone.utc),
        symbol=symbol,
        account=AccountStateSchema(
            equity=Decimal("10000"), balance=Decimal("10000"),
            margin=Decimal("0"), free_margin=Decimal("10000"),
            floating_pl=Decimal("0"),
        ),
        bars={},
    )


# --- Pure function tests (no DB) ---

def test_detect_pin_bar_bullish():
    # lower_wick=5.0, body=0.5, range=6.0 → 5.0>=1.0 ✓, 5.0>=3.6 ✓
    bars = [{"open": Decimal("1920.0"), "high": Decimal("1921.0"),
             "low": Decimal("1915.0"), "close": Decimal("1920.5")}]
    assert detect_pin_bar(bars) == "bullish"


def test_detect_pin_bar_bearish():
    # upper_wick=5.5, body=0.5, range=6.5 → 5.5>=1.0 ✓, 5.5>=3.9 ✓
    bars = [{"open": Decimal("1920.0"), "high": Decimal("1926.0"),
             "low": Decimal("1919.5"), "close": Decimal("1920.5")}]
    assert detect_pin_bar(bars) == "bearish"


def test_detect_pin_bar_none_for_normal_candle():
    # body=1.0, range=4.0, wicks both small
    bars = [{"open": Decimal("1920.0"), "high": Decimal("1922.0"),
             "low": Decimal("1918.0"), "close": Decimal("1921.0")}]
    assert detect_pin_bar(bars) is None


def test_detect_engulfing_bullish():
    # prev bearish (1921→1919), curr bullish engulfs: open<1919, close>1921
    bars = [
        {"open": Decimal("1921.0"), "high": Decimal("1922.0"),
         "low": Decimal("1918.0"), "close": Decimal("1919.0")},
        {"open": Decimal("1918.5"), "high": Decimal("1923.0"),
         "low": Decimal("1918.0"), "close": Decimal("1921.5")},
    ]
    assert detect_engulfing(bars) == "bullish"


def test_detect_engulfing_bearish():
    # prev bullish (1919→1921), curr bearish engulfs: open>1921, close<1919
    bars = [
        {"open": Decimal("1919.0"), "high": Decimal("1922.0"),
         "low": Decimal("1918.0"), "close": Decimal("1921.0")},
        {"open": Decimal("1921.5"), "high": Decimal("1922.0"),
         "low": Decimal("1916.0"), "close": Decimal("1918.5")},
    ]
    assert detect_engulfing(bars) == "bearish"


def test_detect_engulfing_requires_two_bars():
    bars = [{"open": Decimal("1920.0"), "high": Decimal("1922.0"),
             "low": Decimal("1918.0"), "close": Decimal("1921.0")}]
    assert detect_engulfing(bars) is None


# --- DB tests ---

@pytest.mark.asyncio
async def test_run_pattern_detector_creates_alert_for_pin_bar(db_session):
    t = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    db_session.add(PriceBar(
        time=t, symbol="XAUUSD", timeframe=Timeframe.H1,
        open=Decimal("1920.0"), high=Decimal("1921.0"),
        low=Decimal("1915.0"), close=Decimal("1920.5"),
    ))
    await db_session.commit()

    await run_pattern_detector(db_session, make_tick())

    result = await db_session.execute(select(Alert).where(Alert.type == "pattern_alert"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].trigger_data["pattern"] == "pin_bar"
    assert alerts[0].trigger_data["direction"] == "bullish"
    assert alerts[0].trigger_data["timeframe"] == "H1"


@pytest.mark.asyncio
async def test_run_pattern_detector_deduplicates_within_4_hours(db_session):
    t = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    db_session.add(PriceBar(
        time=t, symbol="XAUUSD", timeframe=Timeframe.H1,
        open=Decimal("1920.0"), high=Decimal("1921.0"),
        low=Decimal("1915.0"), close=Decimal("1920.5"),
    ))
    db_session.add(Alert(
        type="pattern_alert",
        message="Pin Bar (bullish) detected on H1",
        trigger_data={"pattern": "pin_bar", "direction": "bullish", "timeframe": "H1"},
        sent_at=datetime.now(timezone.utc) - timedelta(hours=1),
        acknowledged=False,
    ))
    await db_session.commit()

    await run_pattern_detector(db_session, make_tick())

    result = await db_session.execute(select(Alert).where(Alert.type == "pattern_alert"))
    alerts = result.scalars().all()
    assert len(alerts) == 1  # no new alert created


@pytest.mark.asyncio
async def test_run_pattern_detector_no_alert_when_no_bars(db_session):
    await run_pattern_detector(db_session, make_tick())
    result = await db_session.execute(select(Alert))
    assert result.scalars().all() == []
