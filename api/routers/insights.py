from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.insight import Insight
from schemas.insight import InsightResponse

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/insights", response_model=List[InsightResponse])
async def list_insights(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Insight)
        .where(Insight.is_active == True)
        .order_by(Insight.discovered_at.desc())
    )
    return result.scalars().all()
