from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from models.ml_pattern_score import MLPatternScore
from models.pattern import Pattern


@pytest.mark.asyncio
async def test_ml_pattern_score_roundtrip(db_session):
    pattern = Pattern(
        id=uuid4(),
        indicator_slugs=["ema_cross", "rsi"],
        timeframe="H1",
        win_rate=0.6,
        sample_count=10,
        consecutive_stable_days=3,
        status="candidate",
        discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.flush()

    row = MLPatternScore(
        id=uuid4(),
        pattern_id=pattern.id,
        score=Decimal("0.7234"),
        model_version="v1-2026-05-27",
        features={"entry_score": 70, "rsi": 55.2},
        spawn_decision="spawn",
        ml_decision="spawn",
        computed_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    await db_session.commit()

    fetched = await db_session.get(MLPatternScore, row.id)
    assert fetched.score == Decimal("0.7234")
    assert fetched.model_version == "v1-2026-05-27"
    assert fetched.features["rsi"] == 55.2
    assert fetched.spawn_decision == "spawn"
