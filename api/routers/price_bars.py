from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.price_bar import PriceBar, Timeframe
from schemas.price_bar import PriceBarResponse

router = APIRouter(prefix="/api", tags=["price-bars"])


@router.get("/price-bars", response_model=List[PriceBarResponse])
async def list_price_bars(
    symbol: str = Query("GOLD#"),
    tf: Timeframe = Query(Timeframe.M15),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(PriceBar)
        .where(PriceBar.symbol == symbol, PriceBar.timeframe == tf)
        .order_by(PriceBar.time.desc())
        .limit(limit)
    )
    bars = result.scalars().all()
    return list(reversed(bars))
