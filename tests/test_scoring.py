from decimal import Decimal

import pytest

from services.scoring import (
    LOT_TIER_FLOOR,
    LOT_TIER_LOW,
    LOT_TIER_MID,
    LOT_TIER_HIGH,
    SignalQualityInputs,
    compute_score,
    score_to_lot,
)


def test_score_perfect_is_100():
    inputs = SignalQualityInputs(
        matched_count=5,
        total_count=5,
        avg_indicator_strength=1.0,
        rule_winrate=1.0,
    )
    assert compute_score(inputs) == pytest.approx(100.0)


def test_score_no_match_is_zero():
    inputs = SignalQualityInputs(
        matched_count=0, total_count=5, avg_indicator_strength=0.0, rule_winrate=0.0,
    )
    assert compute_score(inputs) == pytest.approx(0.0)


def test_score_balanced_components():
    inputs = SignalQualityInputs(
        matched_count=3,
        total_count=5,
        avg_indicator_strength=0.5,
        rule_winrate=0.6,
    )
    s = compute_score(inputs)
    # 0.25*60 + 0.40*60 + 0.20*50 + 0.15*60 ≈ 58
    assert 50.0 <= s <= 65.0


def test_lot_tier_mapping_floor():
    assert score_to_lot(0) == LOT_TIER_FLOOR
    assert score_to_lot(39.9) == LOT_TIER_FLOOR


def test_lot_tier_mapping_low():
    assert score_to_lot(40) == LOT_TIER_LOW
    assert score_to_lot(69.9) == LOT_TIER_LOW


def test_lot_tier_mapping_mid():
    assert score_to_lot(70) == LOT_TIER_MID
    assert score_to_lot(89.9) == LOT_TIER_MID


def test_lot_tier_mapping_high():
    assert score_to_lot(90) == LOT_TIER_HIGH
    assert score_to_lot(100) == LOT_TIER_HIGH
