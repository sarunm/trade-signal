from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.basket_recovery import (
    RECOVERY_COOLDOWN_SEC,
    RECOVERY_FLOATING_LOSS_PCT,
    should_open_recovery,
)


def _open_paper(open_time: datetime, open_price: float, volume: float) -> Trade:
    return Trade(
        ticket=1,
        symbol="GOLD#",
        direction=Direction.buy,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=open_time,
        open_price=Decimal(str(open_price)),
        volume=Decimal(str(volume)),
        is_paper=True,
        paper_mode=PaperMode.independent,
    )


NOW = datetime(2026, 5, 25, 12, 30, tzinfo=timezone.utc)


def test_no_recovery_when_no_open_paper():
    assert not should_open_recovery(
        existing=None, current_bid=Decimal("1950"),
        virtual_balance=Decimal("5000"), now=NOW, mode="basket_5k",
    )


def test_no_recovery_when_loss_below_floor():
    existing = _open_paper(NOW - timedelta(hours=1), open_price=1950.0, volume=0.10)
    # Loss = (1950-1948)*0.1*100 = ฿20 → below 30% of 5000
    assert not should_open_recovery(
        existing=existing, current_bid=Decimal("1948"),
        virtual_balance=Decimal("5000"), now=NOW, mode="basket_5k",
    )


def test_no_recovery_when_strict_mode():
    existing = _open_paper(NOW - timedelta(hours=1), open_price=1950.0, volume=0.10)
    assert not should_open_recovery(
        existing=existing, current_bid=Decimal("1900"),
        virtual_balance=Decimal("5000"), now=NOW, mode="strict",
    )


def test_recovery_when_loss_exceeds_floor_and_cooldown_passed():
    existing = _open_paper(NOW - timedelta(hours=1), open_price=1950.0, volume=0.10)
    # Loss ≈ ฿2000 → >30% of 5000 (฿1500)
    assert should_open_recovery(
        existing=existing, current_bid=Decimal("1750"),
        virtual_balance=Decimal("5000"), now=NOW, mode="basket_5k",
    )


def test_no_recovery_within_cooldown():
    open_time = NOW - timedelta(seconds=RECOVERY_COOLDOWN_SEC - 60)
    existing = _open_paper(open_time, open_price=1950.0, volume=0.10)
    assert not should_open_recovery(
        existing=existing, current_bid=Decimal("1750"),
        virtual_balance=Decimal("5000"), now=NOW, mode="basket_5k",
    )
