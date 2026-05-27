import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ml.pattern_scorer import score_pattern
from models.ml_pattern_score import MLPatternScore
from models.pattern import Pattern

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.55


async def log_shadow_decision(
    session: AsyncSession,
    pattern: Pattern,
    rule_based_decision: str,
) -> MLPatternScore | None:
    try:
        s = await score_pattern(session, pattern)
    except Exception:
        logger.exception("ml_shadow: score_pattern failed for pattern %s", pattern.id)
        return None

    threshold = float(os.getenv("ML_SPAWN_THRESHOLD", DEFAULT_THRESHOLD))
    ml_decision = "spawn" if s["score"] >= threshold else "skip"

    row = MLPatternScore(
        id=uuid4(),
        pattern_id=pattern.id,
        score=Decimal(str(s["score"])),
        model_version=s["model_version"] or "no-model",
        features=s,
        spawn_decision=rule_based_decision,
        ml_decision=ml_decision,
        computed_at=datetime.now(timezone.utc),
    )
    session.add(row)
    return row
