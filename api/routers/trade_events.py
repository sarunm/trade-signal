from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.trade_event import TradeEventSchema
from services.trade_logger import upsert_trade
from services.mirror_trader import create_mirror_trade
from services.alert_manager import check_trade_alerts
from services.insight_engine import run_insight_engine

router = APIRouter(prefix="/api", tags=["trade-events"])


@router.post("/trade-events", status_code=status.HTTP_201_CREATED)
async def receive_trade_event(
    event: TradeEventSchema,
    session: AsyncSession = Depends(get_session),
):
    trade = await upsert_trade(session, event)
    await create_mirror_trade(session, event)
    await session.commit()
    await check_trade_alerts(session, event)
    await run_insight_engine(session)
    return {"id": str(trade.id), "ticket": trade.ticket}
