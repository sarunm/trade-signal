import pytest
from decimal import Decimal
from datetime import datetime, timezone
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
