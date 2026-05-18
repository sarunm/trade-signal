from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.price_tick import PriceTickSchema
from services.price_handler import save_price_tick
from services.alert_manager import check_equity_buffer
from services.pattern_detector import run_pattern_detector

router = APIRouter(prefix="/api", tags=["price-tick"])


@router.post("/price-tick")
async def receive_price_tick(
    tick: PriceTickSchema,
    session: AsyncSession = Depends(get_session),
):
    await save_price_tick(session, tick)
    await check_equity_buffer(session, tick)
    await run_pattern_detector(session, tick)
    return {"status": "saved", "timestamp": tick.timestamp.isoformat()}
