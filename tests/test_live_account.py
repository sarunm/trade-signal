from decimal import Decimal

import pytest

from services.live_account import push_live_account, get_live_account, clear_live_account


def setup_function(_):
    clear_live_account()


def test_returns_none_when_empty():
    assert get_live_account(123) is None


def test_push_and_read_per_account():
    push_live_account(account_id=42, equity=Decimal("5000.00"), floating_pl=Decimal("-120.50"))
    snap = get_live_account(42)
    assert snap is not None
    assert snap.equity == Decimal("5000.00")
    assert snap.floating_pl == Decimal("-120.50")
    assert get_live_account(99) is None


def test_push_overwrites():
    push_live_account(account_id=42, equity=Decimal("5000.00"), floating_pl=Decimal("-100"))
    push_live_account(account_id=42, equity=Decimal("5050.00"), floating_pl=Decimal("-50"))
    snap = get_live_account(42)
    assert snap.equity == Decimal("5050.00")
    assert snap.floating_pl == Decimal("-50")


@pytest.mark.asyncio
async def test_market_tick_with_equity_updates_cache(client):
    payload = {
        "timestamp": "2026-05-27T10:00:00Z",
        "symbol": "GOLD#",
        "account_id": 777,
        "bid": 4500.10,
        "ask": 4500.30,
        "equity": 5234.55,
        "floating_pl": -42.10,
    }
    response = await client.post("/api/market-tick", json=payload)
    assert response.status_code == 200
    snap = get_live_account(777)
    assert snap is not None
    assert snap.equity == Decimal("5234.55")
    assert snap.floating_pl == Decimal("-42.10")


@pytest.mark.asyncio
async def test_header_snapshot_uses_live_overlay(client, db_session):
    from datetime import datetime, timezone
    from models.account_snapshot import AccountSnapshot

    db_session.add(AccountSnapshot(
        timestamp=datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc),
        equity=Decimal("5000.00"),
        balance=Decimal("5100.00"),
        margin=Decimal("100.00"),
        free_margin=Decimal("4900.00"),
        floating_pl=Decimal("-100.00"),
        account_id=555,
    ))
    await db_session.commit()

    push_live_account(account_id=555, equity=Decimal("5234.55"), floating_pl=Decimal("-42.10"))

    response = await client.get("/api/header-snapshot")
    assert response.status_code == 200
    body = response.json()
    assert float(body["equity"]) == 5234.55
    assert float(body["floating_pl"]) == -42.10
    assert float(body["balance"]) == 5100.00
