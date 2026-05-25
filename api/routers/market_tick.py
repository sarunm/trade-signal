import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.market_tick import MarketTickSchema
from services.alert_manager import check_large_adverse_move
from services.mirror_exit_manager import evaluate_mirror_exits
from services.paper_exit_manager import close_paper_trades_on_tick
from services.paper_trader import run_paper_trader
from services.trade_advisor import check_advisor_zones

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["market-tick"])


@router.post("/market-tick")
async def receive_market_tick(
    tick: MarketTickSchema,
    session: AsyncSession = Depends(get_session),
):
    closed_independent = await close_paper_trades_on_tick(session, tick)
    closed_mirror = await evaluate_mirror_exits(session, tick)
    await check_large_adverse_move(session, tick)
    await check_advisor_zones(session, tick)

    try:
        await run_paper_trader(session, tick)
    except Exception:
        logger.exception("paper trader run failed for tick %s", tick.timestamp)

    return {
        "status": "processed",
        "timestamp": tick.timestamp.isoformat(),
        "closed_paper_trades": closed_independent + closed_mirror,
        "closed_mirror": closed_mirror,
        "closed_independent": closed_independent,
    }
