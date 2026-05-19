from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.market_tick import MarketTickSchema
from services.paper_exit_manager import close_paper_trades_on_tick
from services.alert_manager import check_large_adverse_move

router = APIRouter(prefix="/api", tags=["market-tick"])


@router.post("/market-tick")
async def receive_market_tick(
    tick: MarketTickSchema,
    session: AsyncSession = Depends(get_session),
):
    closed = await close_paper_trades_on_tick(session, tick)
    await check_large_adverse_move(session, tick)
    return {
        "status": "processed",
        "timestamp": tick.timestamp.isoformat(),
        "closed_paper_trades": closed,
    }
