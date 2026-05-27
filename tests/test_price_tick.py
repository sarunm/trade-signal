import pytest

PRICE_TICK_PAYLOAD = {
    "timestamp": "2026-05-17T09:00:00Z",
    "account": {
        "equity": 10500.00,
        "balance": 10000.00,
        "margin": 450.00,
        "free_margin": 10050.00,
        "floating_pl": 500.00,
    },
    "bars": {
        "M5":  {"open": 1950.1, "high": 1951.2, "low": 1949.8, "close": 1950.9, "volume": 1200},
        "M15": {"open": 1948.5, "high": 1951.5, "low": 1948.0, "close": 1950.9, "volume": 3600},
        "M30": {"open": 1947.0, "high": 1952.0, "low": 1946.5, "close": 1950.9, "volume": 7200},
        "H1":  {"open": 1945.0, "high": 1953.0, "low": 1944.5, "close": 1950.9, "volume": 14400},
        "H4":  {"open": 1940.0, "high": 1955.0, "low": 1939.0, "close": 1950.9, "volume": 57600},
        "D":   {"open": 1930.0, "high": 1960.0, "low": 1928.0, "close": 1950.9, "volume": 86400},
        "W1":  {"open": 1920.0, "high": 1965.0, "low": 1918.0, "close": 1950.9, "volume": 604800},
    },
    "symbol": "GOLD#",
}


@pytest.mark.asyncio
async def test_post_price_tick_returns_200(client):
    response = await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_price_tick_saves_bars(client, db_session):
    await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    from sqlalchemy import select
    from models.price_bar import PriceBar
    result = await db_session.execute(select(PriceBar))
    bars = result.scalars().all()
    assert len(bars) == 7


@pytest.mark.asyncio
async def test_price_tick_saves_account_snapshot(client, db_session):
    await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    from sqlalchemy import select
    from models.account_snapshot import AccountSnapshot
    result = await db_session.execute(select(AccountSnapshot))
    snapshots = result.scalars().all()
    assert len(snapshots) == 1
    assert float(snapshots[0].equity) == 10500.00


@pytest.mark.asyncio
async def test_price_tick_deduplicates_bars(client, db_session):
    await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    from sqlalchemy import select
    from models.price_bar import PriceBar
    result = await db_session.execute(select(PriceBar))
    bars = result.scalars().all()
    assert len(bars) == 7  # no duplicates on same timestamp+symbol+timeframe
