from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.account_snapshot import AccountSnapshot
from models.ea_status import EAStatus
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade

_BKK = timezone(timedelta(hours=7))


@pytest.mark.asyncio
async def test_header_snapshot_empty(client):
    res = await client.get("/api/header-snapshot")
    assert res.status_code == 200
    body = res.json()
    assert body["account_id"] is None
    assert body["balance"] is None
    assert body["equity"] is None
    assert body["floating_pl"] is None
    assert body["xau_price"] is None
    assert body["today_pnl_baht"] is None
    assert body["today_pnl_pct"] is None
    assert body["ea_online"] is False


@pytest.mark.asyncio
async def test_header_snapshot_returns_latest_account_and_price(client, db_session):
    now = datetime.now(timezone.utc)
    db_session.add(AccountSnapshot(
        timestamp=now - timedelta(seconds=10),
        equity=Decimal("4500.00"), balance=Decimal("5000.00"),
        margin=Decimal("400.00"), free_margin=Decimal("4100.00"),
        floating_pl=Decimal("-500.00"), account_id=335297575,
    ))
    db_session.add(PriceBar(
        time=now, symbol="GOLD#", timeframe=Timeframe.M5,
        open=Decimal("4570"), high=Decimal("4580"),
        low=Decimal("4565"), close=Decimal("4577.37"),
        volume=Decimal("100"),
    ))
    await db_session.commit()

    res = await client.get("/api/header-snapshot")
    assert res.status_code == 200
    body = res.json()
    assert body["account_id"] == 335297575
    assert float(body["balance"]) == pytest.approx(5000.00)
    assert float(body["equity"]) == pytest.approx(4500.00)
    assert float(body["floating_pl"]) == pytest.approx(-500.00)
    assert float(body["xau_price"]) == pytest.approx(4577.37)


@pytest.mark.asyncio
async def test_header_snapshot_today_pnl_pct(client, db_session):
    today_bkk = datetime.now(_BKK).date()
    close_at = datetime(today_bkk.year, today_bkk.month, today_bkk.day, 5, 0, tzinfo=_BKK)
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("5050.00"), balance=Decimal("5000.00"),
        margin=Decimal("0"), free_margin=Decimal("5050.00"),
        floating_pl=Decimal("50.00"), account_id=42,
    ))
    db_session.add(Trade(
        ticket=1, symbol="GOLD#", direction=Direction.buy,
        order_state=OrderState.filled, is_paper=False,
        open_time=close_at - timedelta(hours=1),
        open_price=Decimal("4500"), close_time=close_at,
        close_price=Decimal("4520"), volume=Decimal("0.10"),
        profit=Decimal("100.00"), account_id=42,
    ))
    await db_session.commit()

    res = await client.get("/api/header-snapshot")
    body = res.json()
    assert float(body["today_pnl_baht"]) == pytest.approx(100.00)
    assert float(body["today_pnl_pct"]) == pytest.approx(2.00)


@pytest.mark.asyncio
async def test_header_snapshot_ea_online_when_recent(client, db_session):
    now = datetime.now(timezone.utc)
    db_session.add(AccountSnapshot(
        timestamp=now, equity=Decimal("100"), balance=Decimal("100"),
        margin=Decimal("0"), free_margin=Decimal("100"),
        floating_pl=Decimal("0"), account_id=42,
    ))
    db_session.add(EAStatus(
        account_id=42, last_seen_at=now - timedelta(seconds=5), symbol="GOLD#",
    ))
    await db_session.commit()

    res = await client.get("/api/header-snapshot")
    assert res.json()["ea_online"] is True


@pytest.mark.asyncio
async def test_header_snapshot_ea_offline_when_stale(client, db_session):
    now = datetime.now(timezone.utc)
    db_session.add(AccountSnapshot(
        timestamp=now, equity=Decimal("100"), balance=Decimal("100"),
        margin=Decimal("0"), free_margin=Decimal("100"),
        floating_pl=Decimal("0"), account_id=42,
    ))
    db_session.add(EAStatus(
        account_id=42, last_seen_at=now - timedelta(minutes=10), symbol="GOLD#",
    ))
    await db_session.commit()

    res = await client.get("/api/header-snapshot")
    assert res.json()["ea_online"] is False
