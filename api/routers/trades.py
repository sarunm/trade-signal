from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Literal, Optional

from database import get_session
from fastapi import APIRouter, Depends, HTTPException, Query
from models.account_snapshot import AccountSnapshot
from models.trade import OrderState, Trade
from schemas.trade import PnlHistoryPoint, TradeResponse, TradeTagSchema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api", tags=["trades"])


async def _current_account_id(session: AsyncSession) -> Optional[int]:
    result = await session.execute(
        select(AccountSnapshot.account_id)
        .where(AccountSnapshot.account_id.isnot(None))
        .order_by(AccountSnapshot.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
        query = (
            query.where(
                Trade.order_state == OrderState.filled,
                Trade.open_price.isnot(None),
                Trade.close_price.is_(None),
            )
            .limit(limit)
            .offset(offset)
        )
    else:
        query = query.where(Trade.close_price.isnot(None)).limit(limit).offset(offset)

    result = await session.execute(query)
    return result.scalars().all()


@router.get("/trades/pnl-history", response_model=List[PnlHistoryPoint])
async def get_pnl_history(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    account_id = await _current_account_id(session)

    query = (
        select(Trade)
        .where(
            Trade.is_paper == False,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
        )
        .order_by(Trade.close_time.asc())
    )
    if account_id is not None:
        query = query.where(Trade.account_id == account_id)

    result = await session.execute(query)
    trades = result.scalars().all()
    if not trades:
        return []

    anchor_day = datetime.now(timezone.utc).date()
    oldest = anchor_day - timedelta(days=days - 1)

    grouped = defaultdict(lambda: Decimal("0.00"))
    for trade in trades:
        close_date = _as_utc(trade.close_time).date()
        if close_date < oldest or close_date > anchor_day:
            continue
        grouped[close_date] += trade.profit

    cumulative = Decimal("0.00")
    rows = []
    for close_date, profit in sorted(grouped.items()):
        cumulative += profit
        rows.append(
            PnlHistoryPoint(
                date=close_date,
                cumulative_pnl=float(cumulative),
            )
        )
    return rows


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
