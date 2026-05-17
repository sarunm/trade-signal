import pytest
from datetime import datetime, timezone

DEAL_OPEN_PAYLOAD = {
    "transaction_type": "DEAL_ADD",
    "ticket": 123456,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "market",
    "order_state": "filled",
    "open_price": 1950.50,
    "volume": 0.01,
    "tp": 1960.0,
    "sl": None,
    "pending_price": None,
    "open_time": "2026-05-17T09:00:00Z",
    "fill_time": "2026-05-17T09:00:01Z",
    "close_time": None,
    "close_price": None,
    "profit": 0.0,
    "swap": 0.0,
    "commission": -0.5,
}

DEAL_CLOSE_PAYLOAD = {
    "transaction_type": "DEAL_ADD",
    "ticket": 123456,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "market",
    "order_state": "filled",
    "open_price": 1950.50,
    "volume": 0.01,
    "tp": 1960.0,
    "sl": None,
    "pending_price": None,
    "open_time": "2026-05-17T09:00:00Z",
    "fill_time": "2026-05-17T09:00:01Z",
    "close_time": "2026-05-17T09:30:00Z",
    "close_price": 1955.0,
    "profit": 45.0,
    "swap": 0.0,
    "commission": -0.5,
}

PENDING_PAYLOAD = {
    "transaction_type": "ORDER_ADD",
    "ticket": 789012,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "buy_limit",
    "order_state": "pending",
    "pending_price": 1940.0,
    "open_price": None,
    "volume": 0.01,
    "tp": 1960.0,
    "sl": None,
    "open_time": "2026-05-17T10:00:00Z",
    "fill_time": None,
    "close_time": None,
    "close_price": None,
    "profit": 0.0,
    "swap": 0.0,
    "commission": 0.0,
}


@pytest.mark.asyncio
async def test_post_trade_event_returns_201(client):
    response = await client.post("/api/trade-events", json=DEAL_OPEN_PAYLOAD)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_post_trade_event_saves_to_db(client, db_session):
    await client.post("/api/trade-events", json=DEAL_OPEN_PAYLOAD)
    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(select(Trade).where(Trade.ticket == 123456))
    trade = result.scalar_one_or_none()
    assert trade is not None
    assert str(trade.symbol) == "XAUUSD"
    assert float(trade.open_price) == 1950.50


@pytest.mark.asyncio
async def test_post_trade_close_updates_existing(client, db_session):
    await client.post("/api/trade-events", json=DEAL_OPEN_PAYLOAD)
    await client.post("/api/trade-events", json=DEAL_CLOSE_PAYLOAD)
    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(select(Trade).where(Trade.ticket == 123456))
    trades = result.scalars().all()
    assert len(trades) == 1
    assert float(trades[0].profit) == 45.0
    assert trades[0].close_time is not None


@pytest.mark.asyncio
async def test_post_pending_order(client, db_session):
    response = await client.post("/api/trade-events", json=PENDING_PAYLOAD)
    assert response.status_code == 201
    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(select(Trade).where(Trade.ticket == 789012))
    trade = result.scalar_one_or_none()
    assert trade is not None
    assert trade.order_state.value == "pending"


@pytest.mark.asyncio
async def test_invalid_payload_returns_422(client):
    response = await client.post("/api/trade-events", json={"ticket": "not_a_number"})
    assert response.status_code == 422
