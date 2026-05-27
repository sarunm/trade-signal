import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from math import ceil
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.account_snapshot import AccountSnapshot
from models.ea_status import EAStatus
from models.price_bar import PriceBar
from models.trade import OrderState, Trade
from services.live_account import get_live_account
from schemas.account import (
    AccountResponse,
    AccountSnapshotResponse,
    HeaderSnapshotResponse,
    PnlHistoryItem,
    PnlHistoryResponse,
)

router = APIRouter(prefix="/api", tags=["account"])
_ICT = timezone(timedelta(hours=7))
EA_DISCONNECT_UI_THRESHOLD_SEC = int(os.getenv("EA_DISCONNECT_UI_THRESHOLD_SEC", 120))
HEADER_SYMBOL = os.getenv("HEADER_PRICE_SYMBOL", "GOLD#")


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


@router.get("/header-snapshot", response_model=HeaderSnapshotResponse)
async def get_header_snapshot(session: AsyncSession = Depends(get_session)):
    snap_res = await session.execute(
        select(AccountSnapshot).order_by(AccountSnapshot.timestamp.desc()).limit(1)
    )
    snapshot = snap_res.scalar_one_or_none()

    price_res = await session.execute(
        select(PriceBar.close)
        .where(PriceBar.symbol == HEADER_SYMBOL)
        .order_by(PriceBar.time.desc())
        .limit(1)
    )
    xau_price = price_res.scalar_one_or_none()

    today_baht: Optional[Decimal] = None
    today_pct: Optional[Decimal] = None
    if snapshot is not None:
        today = datetime.now(_ICT).date()
        trade_stmt = select(Trade.profit).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
        )
        if snapshot.account_id is not None:
            trade_stmt = trade_stmt.where(Trade.account_id == snapshot.account_id)
        trade_res = await session.execute(
            trade_stmt.where(Trade.close_time >= datetime.combine(today, datetime.min.time(), tzinfo=_ICT))
        )
        today_baht = sum((p for p in trade_res.scalars().all()), Decimal("0.00"))
        if snapshot.balance and snapshot.balance != 0:
            today_pct = (today_baht / snapshot.balance * Decimal("100")).quantize(Decimal("0.01"))
        today_baht = today_baht.quantize(Decimal("0.01"))

    ea_online = False
    if snapshot is not None and snapshot.account_id is not None:
        ea = await session.get(EAStatus, snapshot.account_id)
        if ea is not None:
            last = ea.last_seen_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            seconds = (datetime.now(timezone.utc) - last).total_seconds()
            ea_online = seconds <= EA_DISCONNECT_UI_THRESHOLD_SEC

    live = get_live_account(snapshot.account_id) if snapshot is not None else None
    equity = live.equity if live else (snapshot.equity if snapshot else None)
    floating_pl = live.floating_pl if live else (snapshot.floating_pl if snapshot else None)

    return HeaderSnapshotResponse(
        account_id=snapshot.account_id if snapshot else None,
        balance=snapshot.balance if snapshot else None,
        equity=equity,
        floating_pl=floating_pl,
        today_pnl_baht=today_baht,
        today_pnl_pct=today_pct,
        xau_price=xau_price.quantize(Decimal("0.01")) if xau_price is not None else None,
        ea_online=ea_online,
    )


@router.get("/account-snapshots", response_model=List[AccountSnapshotResponse])
async def get_account_snapshots(
    days: int = Query(7, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
):
    account_id = await _current_account_id(session)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(AccountSnapshot)
        .where(AccountSnapshot.timestamp >= cutoff)
        .order_by(AccountSnapshot.timestamp.desc())
    )
    if account_id is not None:
        stmt = stmt.where(AccountSnapshot.account_id == account_id)

    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/pnl-history", response_model=PnlHistoryResponse)
async def get_pnl_history(
    granularity: str = Query("daily", pattern="^(all|daily|weekly|monthly)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    account_id = await _current_account_id(session)
    stmt = select(Trade).where(
        Trade.is_paper == False,
        Trade.order_state == OrderState.filled,
        Trade.close_time.isnot(None),
        Trade.profit.isnot(None),
    )
    if account_id is not None:
        stmt = stmt.where(Trade.account_id == account_id)
    result = await session.execute(stmt)
    trades = result.scalars().all()

    snapshot_stmt = select(AccountSnapshot)
    if account_id is not None:
        snapshot_stmt = snapshot_stmt.where(AccountSnapshot.account_id == account_id)
    snap_result = await session.execute(snapshot_stmt.order_by(AccountSnapshot.timestamp.asc()))
    snapshots = snap_result.scalars().all()

    if granularity == "daily":
        rows = _group_pnl_daily(trades, snapshots)
    elif granularity == "weekly":
        rows = _group_pnl_weekly(trades, snapshots)
    elif granularity == "monthly":
        rows = _group_pnl_monthly(trades, snapshots)
    else:  # all
        rows = _group_pnl_all(trades)

    total_count = len(rows)
    total_pages = max(1, ceil(total_count / page_size)) if total_count else 0
    start = (page - 1) * page_size
    page_items = rows[start:start + page_size]
    return PnlHistoryResponse(
        items=page_items,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_count=total_count,
    )


def _group_pnl_daily(trades, snapshots):
    grouped: dict = defaultdict(lambda: {"profit": Decimal("0.00"), "trade_count": 0})
    for trade in trades:
        d = _as_utc(trade.close_time).astimezone(_ICT).date()
        grouped[d]["profit"] += trade.profit
        grouped[d]["trade_count"] += 1
    base_by_date = _base_balance_by_date(snapshots)
    rows: list[PnlHistoryItem] = []
    for d in sorted(grouped.keys(), reverse=True):
        profit = grouped[d]["profit"].quantize(Decimal("0.01"))
        base = base_by_date.get(d)
        pct = ((profit / base) * Decimal("100")).quantize(Decimal("0.01")) if base else None
        rows.append(PnlHistoryItem(
            period=d.isoformat(),
            profit=profit,
            profit_pct=pct,
            trade_count=grouped[d]["trade_count"],
        ))
    return rows


def _base_balance_by_date(snapshots) -> dict:
    first_per_day = {}
    for s in snapshots:
        d = _as_utc(s.timestamp).astimezone(_ICT).date()
        first_per_day.setdefault(d, s.balance)
    return first_per_day


def _iso_week_monday(d):
    return d - timedelta(days=d.isoweekday() - 1)


def _group_pnl_weekly(trades, snapshots):
    grouped: dict = defaultdict(lambda: {"profit": Decimal("0.00"), "trade_count": 0})
    for trade in trades:
        d = _as_utc(trade.close_time).astimezone(_ICT).date()
        key = _iso_week_monday(d)
        grouped[key]["profit"] += trade.profit
        grouped[key]["trade_count"] += 1
    base_by_date = _base_balance_by_date(snapshots)
    rows: list[PnlHistoryItem] = []
    for key in sorted(grouped.keys(), reverse=True):
        profit = grouped[key]["profit"].quantize(Decimal("0.01"))
        base = base_by_date.get(key)
        pct = ((profit / base) * Decimal("100")).quantize(Decimal("0.01")) if base else None
        rows.append(PnlHistoryItem(
            period=key.isoformat(),
            profit=profit,
            profit_pct=pct,
            trade_count=grouped[key]["trade_count"],
        ))
    return rows


def _group_pnl_monthly(trades, snapshots):
    grouped: dict = defaultdict(lambda: {"profit": Decimal("0.00"), "trade_count": 0})
    for trade in trades:
        d = _as_utc(trade.close_time).astimezone(_ICT).date()
        key = d.replace(day=1)
        grouped[key]["profit"] += trade.profit
        grouped[key]["trade_count"] += 1
    base_by_date = _base_balance_by_date(snapshots)
    rows: list[PnlHistoryItem] = []
    for key in sorted(grouped.keys(), reverse=True):
        profit = grouped[key]["profit"].quantize(Decimal("0.01"))
        base = base_by_date.get(key)
        pct = ((profit / base) * Decimal("100")).quantize(Decimal("0.01")) if base else None
        rows.append(PnlHistoryItem(
            period=key.isoformat(),
            profit=profit,
            profit_pct=pct,
            trade_count=grouped[key]["trade_count"],
        ))
    return rows


def _group_pnl_all(trades):
    sorted_trades = sorted(trades, key=lambda t: _as_utc(t.close_time), reverse=True)
    rows: list[PnlHistoryItem] = []
    for t in sorted_trades:
        rows.append(PnlHistoryItem(
            period=_as_utc(t.close_time).isoformat(),
            profit=t.profit.quantize(Decimal("0.01")) if t.profit is not None else Decimal("0.00"),
            profit_pct=None,
            trade_count=1,
        ))
    return rows
