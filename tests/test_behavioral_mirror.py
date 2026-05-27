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
        symbol="GOLD#",
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


@pytest.mark.asyncio
async def test_returns_none_when_no_trades(db_session):
    avg = await compute_user_avg_profit(db_session, days=30, min_sample=10)
    assert avg is None


@pytest.mark.asyncio
async def test_returns_none_below_min_sample(db_session):
    now = datetime.now(timezone.utc)
    db_session.add(_snapshot(now))
    db_session.add(_real_winning_trade("100.00", now - timedelta(days=1)))
    db_session.add(_real_winning_trade("200.00", now - timedelta(days=2), ticket=9099))
    await db_session.commit()

    avg = await compute_user_avg_profit(db_session, days=30, min_sample=10)
    assert avg is None


@pytest.mark.asyncio
async def test_excludes_losing_paper_outside_other_account(db_session):
    now = datetime.now(timezone.utc)
    db_session.add(_snapshot(now))
    for i in range(10):
        db_session.add(_real_winning_trade("500.00", now - timedelta(days=1), ticket=9100 + i))
    losing = _real_winning_trade("500.00", now - timedelta(days=1), ticket=9200)
    losing.profit = Decimal("-9999.00")
    paper = _real_winning_trade("500.00", now - timedelta(days=1), ticket=9201)
    paper.is_paper = True
    paper.profit = Decimal("9999.00")
    out_of_window = _real_winning_trade("500.00", now - timedelta(days=60), ticket=9202)
    out_of_window.profit = Decimal("9999.00")
    other_acct = _real_winning_trade("500.00", now - timedelta(days=1), account_id=999999, ticket=9203)
    other_acct.profit = Decimal("9999.00")
    db_session.add_all([losing, paper, out_of_window, other_acct])
    await db_session.commit()

    avg = await compute_user_avg_profit(db_session, days=30, min_sample=10)
    assert avg == Decimal("500.00")
