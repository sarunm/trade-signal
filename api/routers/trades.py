from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.trade import OrderState, Trade
from models.account_snapshot import AccountSnapshot
from schemas.trade import TradeResponse, TradeTagSchema

router = APIRouter(prefix="/api", tags=["trades"])


async def _current_account_id(session: AsyncSession) -> Optional[int]:
    result = await session.execute(
        select(AccountSnapshot.account_id)
        .where(AccountSnapshot.account_id.isnot(None))
        .order_by(AccountSnapshot.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/trades", response_model=List[TradeResponse])
async def list_trades(
    state: Literal["open", "closed"] = Query("open"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    account_id = await _current_account_id(session)

    query = select(Trade).order_by(Trade.open_time.desc())
    if account_id is not None:
        query = query.where(Trade.account_id == account_id)

    if state == "open":
        query = query.where(
            Trade.order_state == OrderState.filled,
            Trade.open_price.isnot(None),
            Trade.close_price.is_(None),
        ).limit(limit).offset(offset)
    else:
        query = query.where(Trade.close_price.isnot(None)).limit(limit).offset(offset)

    result = await session.execute(query)
    return result.scalars().all()


@router.patch("/trades/{ticket}/tag", response_model=TradeResponse)
async def tag_trade(
    ticket: int,
    body: TradeTagSchema,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Trade).where(Trade.ticket == ticket, Trade.is_paper == False)
    )
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")

    if body.setup_pattern is not None:
        trade.setup_pattern = body.setup_pattern
    if body.trade_bias is not None:
        trade.trade_bias = body.trade_bias

    await session.commit()
    await session.refresh(trade)
    return trade
