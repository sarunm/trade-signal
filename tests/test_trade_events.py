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
    result = await db_session.execute(
        select(Trade).where(Trade.ticket == 123456, Trade.is_paper == False)
    )
    trade = result.scalar_one_or_none()
    assert trade is not None
    assert str(trade.symbol) == "GOLD#"  # normalized from XAUUSD
    assert float(trade.open_price) == 1950.50


@pytest.mark.asyncio
async def test_post_trade_close_updates_existing(client, db_session):
    await client.post("/api/trade-events", json=DEAL_OPEN_PAYLOAD)
    await client.post("/api/trade-events", json=DEAL_CLOSE_PAYLOAD)
    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(
        select(Trade).where(Trade.ticket == 123456, Trade.is_paper == False)
    )
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


# Mirror what EA actually sends from SyncHistoryDeals when ENTRY_OUT deal is replayed:
# direction=null, open_price=null, open_time=null, fill_time=null — only close fields set.
ENTRY_OUT_CATCHUP_PAYLOAD = {
    "transaction_type": "DEAL_ADD",
    "ticket": 123456,
    "symbol": "XAUUSD",
    "direction": None,
    "order_type": "market",
    "order_state": "filled",
    "pending_price": None,
    "open_price": None,
    "close_price": 1955.0,
    "volume": 0.01,
    "tp": None,
    "sl": None,
    "open_time": None,
    "fill_time": None,
    "close_time": "2026-05-17T09:30:00Z",
    "profit": 45.0,
    "swap": 0.0,
    "commission": -0.5,
}


@pytest.mark.asyncio
async def test_symbol_alias_close_merges_into_existing_open(client, db_session):
    """Regression: trade opened under 'GOLD' (broker rename) must merge with
    close event that arrives under 'GOLD#' — not create an orphan row."""
    open_payload = {**DEAL_OPEN_PAYLOAD, "symbol": "GOLD", "ticket": 999777}
    close_payload = {
        **DEAL_CLOSE_PAYLOAD,
        "symbol": "GOLD#",
        "ticket": 999777,
        "open_price": None,
        "direction": None,
        "open_time": None,
        "fill_time": None,
    }
    await client.post("/api/trade-events", json=open_payload)
    await client.post("/api/trade-events", json=close_payload)

    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(
        select(Trade).where(Trade.ticket == 999777, Trade.is_paper == False)
    )
    trades = result.scalars().all()
    assert len(trades) == 1, f"expected single row after alias merge, got {len(trades)}"
    trade = trades[0]
    assert trade.close_time is not None
    assert float(trade.close_price) == 1955.0
    assert float(trade.open_price) == 1950.50
    assert trade.symbol == "GOLD#"  # canonical


@pytest.mark.asyncio
async def test_entry_out_catchup_closes_existing_open_trade(client, db_session):
    """Regression: EA SyncHistoryDeals replays ENTRY_OUT with most fields null.
    Existing open row must get close_time + close_price merged onto it."""
    await client.post("/api/trade-events", json=DEAL_OPEN_PAYLOAD)
    response = await client.post("/api/trade-events", json=ENTRY_OUT_CATCHUP_PAYLOAD)
    assert response.status_code == 201

    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(
        select(Trade).where(Trade.ticket == 123456, Trade.is_paper == False)
    )
    trades = result.scalars().all()
    assert len(trades) == 1
    trade = trades[0]
    assert trade.close_time is not None
    assert float(trade.close_price) == 1955.0
    assert float(trade.profit) == 45.0
    assert trade.direction.value == "buy"  # preserved from open
    assert float(trade.open_price) == 1950.50  # preserved from open


@pytest.mark.asyncio
async def test_pending_promoted_to_filled_removes_stale_pending_row(client, db_session):
    """Regression: pending order trigger fires DEAL_ADD with new position_id.
    EA passes original order_ticket as `pending_ticket` so backend can remove
    the stale pending row that's keyed under order_ticket."""
    pending = {
        "transaction_type": "ORDER_ADD",
        "ticket": 753764157,
        "symbol": "XAUUSD",
        "direction": "buy",
        "order_type": "buy_limit",
        "order_state": "pending",
        "pending_price": 4496.14,
        "volume": 0.01,
        "tp": 4520.0,
        "sl": None,
        "open_time": "2026-05-20T13:40:38Z",
    }
    await client.post("/api/trade-events", json=pending)

    filled = {
        "transaction_type": "DEAL_ADD",
        "ticket": 999888777,
        "pending_ticket": 753764157,
        "symbol": "XAUUSD",
        "direction": "buy",
        "order_type": "market",
        "order_state": "filled",
        "open_price": 4496.14,
        "volume": 0.01,
        "fill_time": "2026-05-20T14:00:00Z",
    }
    response = await client.post("/api/trade-events", json=filled)
    assert response.status_code == 201

    from sqlalchemy import select
    from models.trade import Trade, OrderState
    result = await db_session.execute(
        select(Trade).where(Trade.is_paper == False, Trade.ticket.in_([753764157, 999888777]))
    )
    trades = result.scalars().all()
    assert len(trades) == 1, f"expected single filled row, got {len(trades)}"
    assert trades[0].ticket == 999888777
    assert trades[0].order_state == OrderState.filled
