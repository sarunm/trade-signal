import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from models.trade import Trade, Direction, OrderState, OrderType


def make_trade(ticket, is_paper=False, close_price=None, profit=None):
    return Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_price=Decimal("1920.00000"),
        close_price=close_price,
        profit=profit,
        volume=Decimal("0.10"),
        is_paper=is_paper,
        open_time=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        close_time=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc) if close_price else None,
    )


@pytest.mark.asyncio
async def test_list_open_trades(client, db_session):
    db_session.add(make_trade(1001))
    db_session.add(make_trade(1002, close_price=Decimal("1930.00000"), profit=Decimal("100.00")))
    await db_session.commit()

    response = await client.get("/api/trades?state=open")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticket"] == 1001
    assert data[0]["close_price"] is None


@pytest.mark.asyncio
async def test_list_closed_trades(client, db_session):
    db_session.add(make_trade(1001))
    db_session.add(make_trade(1002, close_price=Decimal("1930.00000"), profit=Decimal("100.00")))
    await db_session.commit()

    response = await client.get("/api/trades?state=closed")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticket"] == 1002


@pytest.mark.asyncio
async def test_list_trades_returns_both_real_and_paper(client, db_session):
    db_session.add(make_trade(1001, is_paper=False))
    db_session.add(make_trade(1001, is_paper=True))
    await db_session.commit()

    response = await client.get("/api/trades?state=open")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_list_closed_trades_limit(client, db_session):
    for i in range(5):
        db_session.add(make_trade(2000 + i, close_price=Decimal("1930.00000"), profit=Decimal("10.00")))
    await db_session.commit()

    response = await client.get("/api/trades?state=closed&limit=3")
    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.asyncio
async def test_invalid_state_returns_422(client):
    response = await client.get("/api/trades?state=invalid")
    assert response.status_code == 422
