from decimal import Decimal

import pytest

from services.statistics import (
    net_ev,
    profit_factor,
    wilson_lower,
)


def test_wilson_lower_balanced_30():
    assert 0.30 < wilson_lower(0.5, 30) < 0.40


def test_wilson_lower_high_winrate_small_sample():
    assert 0.45 < wilson_lower(0.8, 10) < 0.55


def test_wilson_lower_high_winrate_large_sample():
    assert wilson_lower(0.8, 200) > 0.73


def test_wilson_lower_zero_n_returns_zero():
    assert wilson_lower(0.5, 0) == 0.0


def test_wilson_lower_clamped():
    assert wilson_lower(1.0, 100) < 1.0


def test_net_ev_basic():
    profits = [Decimal("100"), Decimal("-50"), Decimal("150"), Decimal("-50"), Decimal("100")]
    assert net_ev(profits, total_cost=Decimal("50")) == Decimal("40.00")


def test_net_ev_zero_trades():
    assert net_ev([], total_cost=Decimal("0")) == Decimal("0.00")


def test_profit_factor_2_to_1():
    profits = [Decimal("200"), Decimal("-100")]
    assert profit_factor(profits) == Decimal("2.0000")


def test_profit_factor_no_losses_returns_inf():
    profits = [Decimal("200"), Decimal("100")]
    assert profit_factor(profits) > Decimal("999")


def test_profit_factor_no_wins_returns_zero():
    profits = [Decimal("-100"), Decimal("-50")]
    assert profit_factor(profits) == Decimal("0.0000")
