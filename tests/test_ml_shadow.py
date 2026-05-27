from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from models.ml_pattern_score import MLPatternScore
from models.pattern import Pattern
from services.ml_shadow import log_shadow_decision


@pytest.mark.asyncio
async def test_log_shadow_decision_writes_score_row(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    pattern = Pattern(
        id=uuid4(), indicator_slugs=["rsi"], timeframe="H1",
        win_rate=0.6, sample_count=10, consecutive_stable_days=3,
        status="candidate", discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.flush()

    await log_shadow_decision(db_session, pattern, rule_based_decision="spawn")
    await db_session.commit()

    rows = (await db_session.execute(
        select(MLPatternScore).where(MLPatternScore.pattern_id == pattern.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].spawn_decision == "spawn"
    assert rows[0].ml_decision in ("spawn", "skip")
