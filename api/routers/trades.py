from typing import List, Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.trade import Trade
from schemas.trade import TradeResponse

router = APIRouter(prefix="/api", tags=["trades"])


@router.get("/trades", response_model=List[TradeResponse])
async def list_trades(
    state: Literal["open", "closed"] = Query("open"),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    query = select(Trade).order_by(Trade.open_time.desc())
    if state == "open":
        query = query.where(Trade.close_price.is_(None))
    else:
        query = query.where(Trade.close_price.isnot(None)).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()
