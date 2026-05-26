from datetime import datetime, timezone

import pytest

from services.paper_trader import _passes_filters


def _ctx(now: datetime) -> dict:
    return {"now": now}


def test_passes_when_no_filters():
    rule = type("R", (), {"filters": []})()
    assert _passes_filters(rule, _ctx(datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)))


def test_rejects_when_session_excluded():
    rule = type("R", (), {"filters": [{"feature": "session", "exclude": "asia"}]})()
    asia_now = datetime(2026, 5, 25, 2, 0, tzinfo=timezone.utc)
    assert not _passes_filters(rule, _ctx(asia_now))


def test_passes_when_session_does_not_match_excluded():
    rule = type("R", (), {"filters": [{"feature": "session", "exclude": "asia"}]})()
    london_now = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    assert _passes_filters(rule, _ctx(london_now))


def test_rejects_on_hour_bucket_exclude():
    rule = type("R", (), {"filters": [{"feature": "hour_bucket", "exclude": "00-04"}]})()
    early_now = datetime(2026, 5, 25, 2, 0, tzinfo=timezone.utc)
    assert not _passes_filters(rule, _ctx(early_now))


def test_rejects_on_dow_exclude():
    rule = type("R", (), {"filters": [{"feature": "dow", "exclude": "fri"}]})()
    fri_now = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)  # Fri
    assert not _passes_filters(rule, _ctx(fri_now))


def test_rejects_on_unknown_feature_passes_through():
    rule = type("R", (), {"filters": [{"feature": "novel", "exclude": "x"}]})()
    assert _passes_filters(rule, _ctx(datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)))
