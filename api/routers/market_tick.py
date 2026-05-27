import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.market_tick import MarketTickSchema
from services.alert_manager import check_large_adverse_move
from services.live_account import push_live_account
from services.mirror_exit_manager import evaluate_mirror_exits
from services.paper_exit_manager import close_paper_trades_on_tick
from services.paper_trader import run_paper_trader
from services.signal_broadcaster import broadcast_status_changes
from services.spread_buffer import push_spread
from services.trade_advisor import check_advisor_zones

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["market-tick"])


@router.post("/market-tick")
async def receive_market_tick(
    tick: MarketTickSchema,
    session: AsyncSession = Depends(get_session),
):
    push_spread(tick.ask - tick.bid)
    if tick.equity is not None and tick.floating_pl is not None and tick.account_id is not None:
        push_live_account(tick.account_id, tick.equity, tick.floating_pl)
    closed_independent = await close_paper_trades_on_tick(session, tick)
    closed_mirror = await evaluate_mirror_exits(session, tick)
    await check_large_adverse_move(session, tick)
    await check_advisor_zones(session, tick)

    signals_emitted = 0
    try:
        result = await run_paper_trader(session, tick)
        evals = result.get("evals", [])
        if evals:
            written = await broadcast_status_changes(session, evals, now=tick.timestamp)
            signals_emitted = len(written)
    except Exception:
        logger.exception("paper trader run failed for tick %s", tick.timestamp)

    return {
        "status": "processed",
        "timestamp": tick.timestamp.isoformat(),
        "closed_paper_trades": closed_independent + closed_mirror,
        "closed_mirror": closed_mirror,
        "closed_independent": closed_independent,
        "signals_emitted": signals_emitted,
    }
