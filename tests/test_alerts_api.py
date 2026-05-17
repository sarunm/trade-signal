import pytest
import uuid
from datetime import datetime, timezone
from models.alert import Alert


@pytest.mark.asyncio
async def test_get_alerts_empty(client):
    response = await client.get("/api/alerts")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_alerts_returns_all(client, db_session):
    for i in range(2):
        db_session.add(Alert(
            id=uuid.uuid4(),
            type="double_down",
            message=f"Alert {i}",
            trigger_data={"index": i},
            sent_at=datetime.now(timezone.utc),
            acknowledged=False,
        ))
    await db_session.commit()

    response = await client.get("/api/alerts")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_get_alerts_unacknowledged_filter(client, db_session):
    for ack in [True, False]:
        db_session.add(Alert(
            id=uuid.uuid4(),
            type="equity_buffer",
            message="Alert",
            sent_at=datetime.now(timezone.utc),
            acknowledged=ack,
        ))
    await db_session.commit()

    response = await client.get("/api/alerts?unacknowledged_only=true")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["acknowledged"] is False


@pytest.mark.asyncio
async def test_acknowledge_alert(client, db_session):
    alert_id = uuid.uuid4()
    db_session.add(Alert(
        id=alert_id,
        type="double_down",
        message="Test alert",
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))
    await db_session.commit()

    response = await client.patch(f"/api/alerts/{alert_id}/acknowledge")
    assert response.status_code == 200
    assert response.json()["acknowledged"] is True


@pytest.mark.asyncio
async def test_acknowledge_alert_not_found(client):
    fake_id = uuid.uuid4()
    response = await client.patch(f"/api/alerts/{fake_id}/acknowledge")
    assert response.status_code == 404
