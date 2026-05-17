import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from models.trade import Trade
from models.alert import Alert


ENTRY_EVENT = {
    "transaction_type": "DEAL_ADD",
    "ticket": 5001,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "market",
    "order_state": "filled",
    "open_price": 1950.00,
    "volume": 1.00,
    "open_time": "2026-05-17T10:00:00Z",
}

PRICE_TICK = {
    "timestamp": "2026-05-17T10:00:00Z",
    "symbol": "XAUUSD",
    "account": {
        "equity": 10000.0,
        "balance": 10000.0,
        "margin": 500.0,
        "free_margin": 500.0,   # intentionally low to trigger equity_buffer
        "floating_pl": 0.0,
    },
    "bars": {
        "H1": {"open": 1950, "high": 1955, "low": 1945, "close": 1952, "volume": 1000},
    },
}


@pytest.mark.asyncio
async def test_trade_event_creates_mirror_trade(client, db_session):
    response = await client.post("/api/trade-events", json=ENTRY_EVENT)
    assert response.status_code == 201

    result = await db_session.execute(select(Trade).where(Trade.is_paper == True))
    papers = result.scalars().all()
    assert len(papers) == 1
    assert papers[0].ticket == 5001


@pytest.mark.asyncio
async def test_price_tick_triggers_equity_buffer_alert(client, db_session):
    # Open a 1-lot position first
    await client.post("/api/trade-events", json=ENTRY_EVENT)

    # Price tick with insufficient free_margin (500 < 10000 required for 1 lot)
    response = await client.post("/api/price-tick", json=PRICE_TICK)
    assert response.status_code == 200

    result = await db_session.execute(select(Alert).where(Alert.type == "equity_buffer"))
    alerts = result.scalars().all()
    assert len(alerts) == 1


@pytest.mark.asyncio
async def test_double_down_alert_from_endpoint(client, db_session):
    # First entry
    await client.post("/api/trade-events", json=ENTRY_EVENT)

    # Second buy entry on same symbol
    second = {**ENTRY_EVENT, "ticket": 5002}
    await client.post("/api/trade-events", json=second)

    result = await db_session.execute(select(Alert).where(Alert.type == "double_down"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "buy" in alerts[0].message
