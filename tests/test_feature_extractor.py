from datetime import datetime, timezone

import pytest

from services.feature_extractor import (
    HOUR_BUCKETS,
    SESSION_ASIA,
    SESSION_LONDON,
    SESSION_NY,
    classify_session,
    day_of_week,
    hour_bucket,
    volatility_regime,
)


@pytest.mark.parametrize("hour, expected", [
    (0, SESSION_ASIA),
    (5, SESSION_ASIA),
    (7, SESSION_LONDON),
    (12, SESSION_LONDON),
    (13, SESSION_NY),
    (20, SESSION_NY),
    (22, SESSION_ASIA),
])
def test_classify_session_by_utc_hour(hour, expected):
    dt = datetime(2026, 5, 25, hour, 0, tzinfo=timezone.utc)
    assert classify_session(dt) == expected


def test_hour_bucket_groups_into_4h_blocks():
    dt = datetime(2026, 5, 25, 9, 30, tzinfo=timezone.utc)
    bucket = hour_bucket(dt)
    assert bucket in HOUR_BUCKETS
    assert bucket == "08-12"


def test_day_of_week_returns_short_name():
    monday = datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc)  # Mon
    assert day_of_week(monday) == "mon"


def test_volatility_regime_high_when_atr_above_p70():
    history = [10.0, 12.0, 8.0, 11.0, 15.0, 9.0, 13.0, 14.0, 18.0, 20.0]
    assert volatility_regime(19.0, history) == "high"
    assert volatility_regime(11.0, history) == "mid"
    assert volatility_regime(8.5, history) == "low"


def test_volatility_regime_unknown_when_history_too_short():
    assert volatility_regime(10.0, [12.0, 11.0]) == "unknown"
