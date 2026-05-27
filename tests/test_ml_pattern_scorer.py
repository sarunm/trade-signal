from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ml.pattern_scorer import score_pattern
from models.pattern import Pattern


@pytest.mark.asyncio
async def test_score_pattern_with_no_classifier_returns_neutral(db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    pattern = Pattern(
        id=uuid4(), indicator_slugs=["ema_cross"], timeframe="H1",
        win_rate=0.6, sample_count=10, consecutive_stable_days=3,
        status="candidate", discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.commit()

    result = await score_pattern(db_session, pattern)
    expected_confidence = min(1.0, 10 / 30) * min(1.0, 3 / 7)
    assert result["confidence_factor"] == pytest.approx(expected_confidence, abs=0.01)
    assert result["sample_count"] == 0
    assert result["model_version"] is None


@pytest.mark.asyncio
async def test_score_pattern_combines_win_prob_and_confidence(db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    pattern = Pattern(
        id=uuid4(), indicator_slugs=["rsi"], timeframe="H1",
        win_rate=0.7, sample_count=50, consecutive_stable_days=10,
        status="candidate", discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.commit()

    result = await score_pattern(db_session, pattern)
    assert result["confidence_factor"] == pytest.approx(1.0, abs=0.001)
