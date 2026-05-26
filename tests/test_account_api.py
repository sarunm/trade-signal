import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from models.account_snapshot import AccountSnapshot


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


