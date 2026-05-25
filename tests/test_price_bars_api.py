from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.price_bar import PriceBar, Timeframe


def _bar(time, symbol="XAUUSD", tf=Timeframe.M15, close="1900.0"):
    return PriceBar(
        time=time,
        symbol=symbol,
        timeframe=tf,
        open=Decimal("1900.0"),
        high=Decimal("1901.0"),
        low=Decimal("1899.0"),
        close=Decimal(close),
        volume=Decimal("100"),
    )


@pytest.mark.asyncio
async def test_price_bars_empty(client):
    response = await client.get("/api/price-bars?symbol=XAUUSD&tf=M15&limit=10")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_price_bars_returns_ascending_within_limit(client, db_session):
    base = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    for i in range(5):
        db_session.add(_bar(base - timedelta(minutes=15 * i), close=str(1900 + i)))
    await db_session.commit()

    response = await client.get("/api/price-bars?symbol=XAUUSD&tf=M15&limit=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    times = [row["time"] for row in data]
    assert times == sorted(times)


@pytest.mark.asyncio
async def test_price_bars_filters_by_symbol_and_timeframe(client, db_session):
    base = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    db_session.add_all([
        _bar(base, symbol="XAUUSD", tf=Timeframe.M15, close="1900"),
        _bar(base, symbol="EURUSD", tf=Timeframe.M15, close="1.10"),
        _bar(base, symbol="XAUUSD", tf=Timeframe.H1, close="1905"),
    ])
    await db_session.commit()

    response = await client.get("/api/price-bars?symbol=XAUUSD&tf=M15&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "XAUUSD"
    assert data[0]["timeframe"] == "M15"
