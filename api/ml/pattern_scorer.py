from sqlalchemy.ext.asyncio import AsyncSession

from ml.classifier import load_classifier, predict_proba
from models.pattern import Pattern

CONFIDENCE_SAMPLE_FLOOR = 30
CONFIDENCE_STABLE_DAYS_FLOOR = 7


async def score_pattern(session: AsyncSession, pattern: Pattern) -> dict:
    artifact = load_classifier()
    confidence = (
        min(1.0, (pattern.sample_count or 0) / CONFIDENCE_SAMPLE_FLOOR)
        * min(1.0, (pattern.consecutive_stable_days or 0) / CONFIDENCE_STABLE_DAYS_FLOOR)
    )

    if artifact is None:
        win_prob = float(pattern.win_rate or 0.5)
    else:
        feats = {
            "entry_score": 50, "direction_buy": 1,
            "hour_of_day_utc": 12, "day_of_week": 2,
            "signal_match_count": pattern.sample_count or 0, "signal_density": 1.0,
            "rsi_value": 0.0, "ema_alignment": 0.0,
        }
        win_prob = predict_proba(artifact, feats)

    score = win_prob * confidence + 0.5 * (1 - confidence)
    return {
        "score": round(score, 4),
        "win_prob": round(win_prob, 4),
        "confidence_factor": round(confidence, 4),
        "sample_count": 0,
        "model_version": artifact["version"] if artifact else None,
    }
