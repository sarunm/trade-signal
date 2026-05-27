from datetime import datetime, timezone
from uuid import uuid4

import pytest

from models.pattern import Pattern


@pytest.mark.asyncio
async def test_retrain_below_threshold_returns_skipped(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    res = await client.post("/api/ml/retrain")
    assert res.status_code == 200
    assert res.json()["status"] == "skipped"


@pytest.mark.asyncio
async def test_pattern_scores_lists_candidates(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    pattern = Pattern(
        id=uuid4(), indicator_slugs=["rsi"], timeframe="H1",
        win_rate=0.6, sample_count=15, consecutive_stable_days=3,
        status="candidate", discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.commit()

    res = await client.get("/api/ml/pattern-scores")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert "score" in body[0]
    assert body[0]["pattern_id"] == str(pattern.id)


@pytest.mark.asyncio
async def test_training_status_when_no_artifact(client, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    res = await client.get("/api/ml/training-status")
    assert res.status_code == 200
    body = res.json()
    assert body["model_version"] is None
    assert body["mode"] in ("shadow", "active")
