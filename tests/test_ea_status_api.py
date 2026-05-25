from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models.ea_status import EAStatus


@pytest.mark.asyncio
async def test_post_heartbeat_inserts_row(client, db_session):
    res = await client.post(
        "/api/ea-heartbeat",
        json={"account_id": 1234567, "version": "1.09", "symbol": "GOLD#"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["account_id"] == 1234567
    assert body["version"] == "1.09"

    rows = (await db_session.execute(select(EAStatus))).scalars().all()
    assert len(rows) == 1
    assert rows[0].version == "1.09"


@pytest.mark.asyncio
async def test_post_heartbeat_upserts(client, db_session):
    await client.post("/api/ea-heartbeat", json={"account_id": 1, "version": "1.0"})
    await client.post("/api/ea-heartbeat", json={"account_id": 1, "version": "1.1"})
    rows = (await db_session.execute(select(EAStatus))).scalars().all()
    assert len(rows) == 1
    assert rows[0].version == "1.1"


@pytest.mark.asyncio
async def test_get_status_returns_connected_when_recent(client, db_session):
    db_session.add(EAStatus(
        account_id=999,
        last_seen_at=datetime.now(timezone.utc),
        version="1.08",
        symbol="GOLD#",
    ))
    await db_session.commit()

    res = await client.get("/api/ea-status?account_id=999")
    assert res.status_code == 200
    body = res.json()
    assert body["connected"] is True
    assert body["seconds_since_last_seen"] >= 0


@pytest.mark.asyncio
async def test_get_status_returns_404_when_no_row(client):
    res = await client.get("/api/ea-status?account_id=42")
    assert res.status_code == 404
