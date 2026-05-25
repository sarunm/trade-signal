import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from models.account_snapshot import AccountSnapshot
from models.trade import Direction, OrderState, Trade
import uuid


@pytest.mark.asyncio
async def test_get_account_empty(client):
    response = await client.get("/api/account")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_account_returns_latest(client, db_session):
    t1 = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 5, 18, 10, 1, tzinfo=timezone.utc)
    for t, eq in [(t1, Decimal("1000.00")), (t2, Decimal("2000.00"))]:
        db_session.add(AccountSnapshot(
            timestamp=t,
            equity=eq,
            balance=Decimal("900.00"),
            margin=Decimal("50.00"),
            free_margin=Decimal("950.00"),
            floating_pl=eq - Decimal("900.00"),
        ))
    await db_session.commit()

    response = await client.get("/api/account")
    assert response.status_code == 200
    data = response.json()
    assert float(data["equity"]) == pytest.approx(2000.00)
    assert "timestamp" in data


def _closed_trade(
    ticket: int,
    close_time: datetime,
    profit: str,
    account_id: int = 335297575,
    is_paper: bool = False,
) -> Trade:
    return Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        close_price=Decimal("2010.00"),
        open_time=close_time,
        close_time=close_time,
        profit=Decimal(profit),
        volume=Decimal("0.10"),
        is_paper=is_paper,
        account_id=account_id,
    )


@pytest.mark.asyncio
async def test_get_daily_pl_uses_closed_real_trades_and_ignores_deposits(client, db_session):
    day = datetime(2026, 5, 20, tzinfo=timezone.utc)
    db_session.add_all([
        AccountSnapshot(
            timestamp=day.replace(hour=0, minute=5),
            equity=Decimal("10000.00"),
            balance=Decimal("10000.00"),
            margin=Decimal("0.00"),
            free_margin=Decimal("10000.00"),
            floating_pl=Decimal("0.00"),
            account_id=335297575,
        ),
        # Balance jump simulates a deposit; it must not be counted as daily P/L.
        AccountSnapshot(
            timestamp=day.replace(hour=12, minute=0),
            equity=Decimal("15200.00"),
            balance=Decimal("15200.00"),
            margin=Decimal("0.00"),
            free_margin=Decimal("15200.00"),
            floating_pl=Decimal("0.00"),
            account_id=335297575,
        ),
        _closed_trade(1001, day.replace(hour=10), "300.00"),
        _closed_trade(1002, day.replace(hour=11), "-100.00"),
        _closed_trade(1003, day.replace(hour=11), "999.00", is_paper=True),
        _closed_trade(1004, day.replace(hour=11), "500.00", account_id=999999),
    ])
    await db_session.commit()

    response = await client.get("/api/daily-pl?days=7")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["date"] == "2026-05-20"
    assert float(data[0]["profit"]) == pytest.approx(200.00)
    assert float(data[0]["profit_pct"]) == pytest.approx(2.0)
    assert float(data[0]["base_balance"]) == pytest.approx(10000.00)
    assert data[0]["trade_count"] == 2


@pytest.mark.asyncio
async def test_get_account_snapshots_empty(client):
    response = await client.get("/api/account-snapshots?days=7")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_account_snapshots_filters_by_window_and_account(client, db_session):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        AccountSnapshot(
            timestamp=now - timedelta(hours=1),
            equity=Decimal("1100.00"),
            balance=Decimal("1000.00"),
            margin=Decimal("50.00"),
            free_margin=Decimal("1050.00"),
            floating_pl=Decimal("100.00"),
            account_id=335297575,
        ),
        AccountSnapshot(
            timestamp=now - timedelta(days=20),
            equity=Decimal("900.00"),
            balance=Decimal("900.00"),
            margin=Decimal("0.00"),
            free_margin=Decimal("900.00"),
            floating_pl=Decimal("0.00"),
            account_id=335297575,
        ),
        AccountSnapshot(
            timestamp=now - timedelta(days=1),
            equity=Decimal("500.00"),
            balance=Decimal("500.00"),
            margin=Decimal("0.00"),
            free_margin=Decimal("500.00"),
            floating_pl=Decimal("0.00"),
            account_id=999999,
        ),
    ])
    await db_session.commit()

    response = await client.get("/api/account-snapshots?days=7")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert float(data[0]["equity"]) == pytest.approx(1100.00)
    assert data[0]["account_id"] == 335297575


@pytest.mark.asyncio
async def test_get_daily_pl_anchors_to_latest_trade_date(client, db_session):
    broker_day = datetime.now(timezone.utc) + timedelta(days=1)
    db_session.add_all([
        AccountSnapshot(
            timestamp=broker_day.replace(hour=0, minute=5, second=0, microsecond=0),
            equity=Decimal("10000.00"),
            balance=Decimal("10000.00"),
            margin=Decimal("0.00"),
            free_margin=Decimal("10000.00"),
            floating_pl=Decimal("0.00"),
            account_id=335297575,
        ),
        _closed_trade(
            2001,
            broker_day.replace(hour=10, minute=0, second=0, microsecond=0),
            "150.00",
        ),
    ])
    await db_session.commit()

    response = await client.get("/api/daily-pl?days=1")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert float(data[0]["profit"]) == pytest.approx(150.00)
