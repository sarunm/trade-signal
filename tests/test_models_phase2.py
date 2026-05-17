import pytest
import uuid
from datetime import datetime, timezone
from models.insight import Insight
from models.alert import Alert


@pytest.mark.asyncio
async def test_create_insight(db_session):
    insight = Insight(
        id=uuid.uuid4(),
        type="time_bias",
        description="74% losses after 21:00",
        confidence=0.74,
        sample_size=12,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={"hour": 21, "loss_rate": 0.74},
    )
    db_session.add(insight)
    await db_session.commit()
    await db_session.refresh(insight)
    assert insight.type == "time_bias"
    assert float(insight.confidence) == pytest.approx(0.74)


@pytest.mark.asyncio
async def test_create_alert(db_session):
    alert = Alert(
        id=uuid.uuid4(),
        type="equity_buffer",
        message="Free margin below required buffer",
        trigger_data={"free_margin": 500.0, "required": 1000.0},
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    assert alert.type == "equity_buffer"
    assert alert.acknowledged is False
