from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.pattern import PaperTraderRule, Pattern
from schemas.pattern import PaperTraderRuleResponse, PatternResponse

router = APIRouter(prefix="/api", tags=["patterns"])


@router.get("/patterns", response_model=List[PatternResponse])
async def list_patterns(
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Pattern).order_by(Pattern.discovered_at.desc())
    if status:
        stmt = stmt.where(Pattern.status == status)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/paper-trader-rules", response_model=List[PaperTraderRuleResponse])
async def list_paper_trader_rules(
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(PaperTraderRule).order_by(PaperTraderRule.spawned_at.desc())
    if status:
        stmt = stmt.where(PaperTraderRule.status == status)
    result = await session.execute(stmt)
    return result.scalars().all()
