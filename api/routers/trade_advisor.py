from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.trade import Trade, OrderState

router = APIRouter(prefix="/api", tags=["trade-advisor"])


@router.get("/trade-advisor")
async def get_trade_advisor(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
        )
    )
    trades = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "ticket": t.ticket,
            "symbol": t.symbol,
            "direction": t.direction.value if t.direction else None,
            "open_price": float(t.open_price) if t.open_price else None,
            "entry_score": t.entry_score,
            "entry_verdict": t.entry_verdict,
            "recovery_plan": t.recovery_plan,
        }
        for t in trades
    ]
