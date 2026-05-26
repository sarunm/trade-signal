from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.paper_signal import PaperSignal
from schemas.paper_signal import PaperSignalResponse

router = APIRouter(prefix="/api", tags=["paper-signals"])

DEFAULT_LIMIT = 200


@router.get("/paper-signals", response_model=list[PaperSignalResponse])
async def list_paper_signals(
    rule_id: Optional[UUID] = Query(None),
    since: Optional[datetime] = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(PaperSignal).order_by(PaperSignal.emitted_at.desc()).limit(limit)
    if rule_id is not None:
        stmt = stmt.where(PaperSignal.rule_id == rule_id)
    if since is not None:
        stmt = stmt.where(PaperSignal.emitted_at > since)
    result = await session.execute(stmt)
    return result.scalars().all()
