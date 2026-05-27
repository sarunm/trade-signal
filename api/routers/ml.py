import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from ml.classifier import load_classifier, train_classifier
from ml.pattern_scorer import score_pattern
from models.pattern import Pattern

router = APIRouter(prefix="/api/ml", tags=["ml"])


class ScorePatternRequest(BaseModel):
    pattern_id: UUID


@router.post("/retrain")
async def retrain(session: AsyncSession = Depends(get_session)):
    return await train_classifier(session)


@router.get("/pattern-scores")
async def pattern_scores(
    status: Optional[str] = "candidate",
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Pattern)
    if status:
        stmt = stmt.where(Pattern.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    out = []
    for p in rows:
        s = await score_pattern(session, p)
        out.append({
            "pattern_id": str(p.id),
            "indicator_slugs": p.indicator_slugs,
            "timeframe": p.timeframe,
            "win_rate": p.win_rate,
            "sample_count": p.sample_count,
            "stable_days": p.consecutive_stable_days,
            **s,
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


@router.get("/training-status")
async def training_status():
    artifact = load_classifier()
    return {
        "model_version": artifact["version"] if artifact else None,
        "trained_at": artifact["trained_at"] if artifact else None,
        "samples": artifact["samples"] if artifact else 0,
        "train_acc": artifact["train_acc"] if artifact else None,
        "val_acc": artifact["val_acc"] if artifact else None,
        "mode": os.getenv("ML_SCORER_MODE", "shadow"),
    }


@router.post("/score-pattern")
async def score_one(
    body: ScorePatternRequest,
    session: AsyncSession = Depends(get_session),
):
    pattern = await session.get(Pattern, body.pattern_id)
    if pattern is None:
        return {"error": "pattern not found"}
    return await score_pattern(session, pattern)
