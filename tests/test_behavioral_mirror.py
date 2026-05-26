import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from models.account_snapshot import AccountSnapshot
from models.trade import Direction, OrderState, Trade
from services.behavioral_mirror import compute_user_avg_profit


def _real_winning_trade(
    profit: str,
    close_time: datetime,
    account_id: int = 335297575,
    ticket: int = 9001,
) -> Trade:
    return Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("1950.00"),
        close_price=Decimal("1955.00"),
        open_time=close_time - timedelta(hours=1),
        close_time=close_time,
        profit=Decimal(profit),
        volume=Decimal("0.10"),
        is_paper=False,
        account_id=account_id,
    )


def _snapshot(ts: datetime, account_id: int = 335297575) -> AccountSnapshot:
    return AccountSnapshot(
        timestamp=ts,
        equity=Decimal("10000.00"),
        balance=Decimal("10000.00"),
        margin=Decimal("0.00"),
        free_margin=Decimal("10000.00"),
        floating_pl=Decimal("0.00"),
        account_id=account_id,
    )


@pytest.mark.asyncio
async def test_returns_avg_of_winning_trades(db_session):
    now = datetime.now(timezone.utc)
    db_session.add(_snapshot(now))
    for i, profit in enumerate(["100.00", "200.00", "300.00", "400.00", "500.00",
                                 "600.00", "700.00", "800.00", "900.00", "1000.00"]):
        db_session.add(_real_winning_trade(profit, now - timedelta(days=1), ticket=9000 + i))
    await db_session.commit()

    avg = await compute_user_avg_profit(db_session, days=30, min_sample=10)

    assert avg == Decimal("550.00")
