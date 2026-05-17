import pytest
import uuid
from datetime import datetime, timezone
from models.insight import Insight


@pytest.mark.asyncio
async def test_get_insights_empty(client):
    response = await client.get("/api/insights")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_insights_returns_active_only(client, db_session):
    active = Insight(
        id=uuid.uuid4(),
        type="time_bias",
        description="80% loss at hour 21",
        confidence=0.8,
        sample_size=15,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data=None,
    )
    inactive = Insight(
        id=uuid.uuid4(),
        type="session_bias",
        description="Old insight",
        confidence=0.7,
        sample_size=12,
        discovered_at=datetime.now(timezone.utc),
        is_active=False,
        data=None,
    )
    db_session.add(active)
    db_session.add(inactive)
    await db_session.commit()

    response = await client.get("/api/insights")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "time_bias"
    assert data[0]["confidence"] == pytest.approx(0.8)
