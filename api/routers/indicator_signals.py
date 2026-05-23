from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.indicator_signal import TradeIndicatorSignal
from schemas.indicator_signal import IndicatorSignalResponse

router = APIRouter(prefix="/api", tags=["indicator-signals"])


@router.get("/indicator-signals/{trade_id}", response_model=List[IndicatorSignalResponse])
async def get_indicator_signals(
    trade_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(TradeIndicatorSignal)
        .where(TradeIndicatorSignal.trade_id == trade_id)
        .order_by(TradeIndicatorSignal.calculated_at.asc())
    )
    return result.scalars().all()
