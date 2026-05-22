from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.account_snapshot import AccountSnapshot
from models.trade import OrderState, Trade
from schemas.account import AccountResponse, DailyPLResponse

router = APIRouter(prefix="/api", tags=["account"])
_ICT = timezone(timedelta(hours=7))


@router.get("/account", response_model=AccountResponse)
async def get_account(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(AccountSnapshot).order_by(AccountSnapshot.timestamp.desc()).limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No account snapshot available")
    return snapshot


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


@router.get("/daily-pl", response_model=List[DailyPLResponse])
async def get_daily_pl(
    days: int = Query(14, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
):
    account_id = await _current_account_id(session)

    trade_query = select(Trade).where(
        Trade.is_paper == False,
        Trade.order_state == OrderState.filled,
        Trade.close_time.isnot(None),
        Trade.profit.isnot(None),
    )
    snapshot_query = select(AccountSnapshot)
    if account_id is not None:
        trade_query = trade_query.where(Trade.account_id == account_id)
        snapshot_query = snapshot_query.where(AccountSnapshot.account_id == account_id)

    trade_result = await session.execute(trade_query)
    trades = trade_result.scalars().all()

    snapshot_result = await session.execute(snapshot_query.order_by(AccountSnapshot.timestamp.asc()))
    snapshots = snapshot_result.scalars().all()

    data_dates = [
        _as_utc(trade.close_time).astimezone(_ICT).date()
        for trade in trades
    ] + [
        _as_utc(snapshot.timestamp).astimezone(_ICT).date()
        for snapshot in snapshots
    ]
    anchor_day = max(data_dates, default=datetime.now(_ICT).date())
    oldest = anchor_day - timedelta(days=days - 1)
    grouped: dict = defaultdict(lambda: {"profit": Decimal("0.00"), "trade_count": 0})
    for trade in trades:
        close_date = _as_utc(trade.close_time).astimezone(_ICT).date()
        if close_date < oldest or close_date > anchor_day:
            continue
        grouped[close_date]["profit"] += trade.profit
        grouped[close_date]["trade_count"] += 1

    base_by_date = {}
    for snapshot in snapshots:
        snapshot_date = _as_utc(snapshot.timestamp).astimezone(_ICT).date()
        if snapshot_date < oldest or snapshot_date > anchor_day:
            continue
        base_by_date.setdefault(snapshot_date, snapshot.balance)

    rows = []
    for day, stats in sorted(grouped.items(), reverse=True):
        base_balance = base_by_date.get(day)
        profit = stats["profit"].quantize(Decimal("0.01"))
        profit_pct = None
        if base_balance is not None and base_balance != 0:
            profit_pct = ((profit / base_balance) * Decimal("100")).quantize(Decimal("0.01"))
        rows.append(DailyPLResponse(
            date=day,
            profit=profit,
            profit_pct=profit_pct,
            base_balance=base_balance,
            trade_count=stats["trade_count"],
        ))

    return rows
