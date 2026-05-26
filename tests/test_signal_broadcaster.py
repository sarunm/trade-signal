from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.signal_broadcaster import (
    SignalEvalInputs,
    STATUS_ACTIVE,
    STATUS_NEAR,
    STATUS_FAR,
    STATUS_IDLE,
    compute_status,
)


def test_status_active_when_all_match():
    inputs = SignalEvalInputs(matched_count=4, total_count=4, has_open_paper=False)
    assert compute_status(inputs) == STATUS_ACTIVE


def test_status_near_when_one_missing_of_three_or_more():
    inputs = SignalEvalInputs(matched_count=3, total_count=4, has_open_paper=False)
    assert compute_status(inputs) == STATUS_NEAR


def test_status_far_when_some_match_but_not_near():
    inputs = SignalEvalInputs(matched_count=2, total_count=5, has_open_paper=False)
    assert compute_status(inputs) == STATUS_FAR


def test_status_idle_when_no_match():
    inputs = SignalEvalInputs(matched_count=0, total_count=4, has_open_paper=False)
    assert compute_status(inputs) == STATUS_IDLE


def test_status_active_when_open_paper_overrides():
    inputs = SignalEvalInputs(matched_count=1, total_count=5, has_open_paper=True)
    assert compute_status(inputs) == STATUS_ACTIVE
