from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.trade_event import TradeEventSchema
from services.trade_logger import upsert_trade

router = APIRouter(prefix="/api", tags=["trade-events"])


@router.post("/trade-events", status_code=status.HTTP_201_CREATED)
async def receive_trade_event(
    event: TradeEventSchema,
    session: AsyncSession = Depends(get_session),
):
    trade = await upsert_trade(session, event)
    return {"id": str(trade.id), "ticket": trade.ticket}
