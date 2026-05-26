from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.pattern import PaperTraderRule, Pattern
from models.trade import PaperMode, Trade
from schemas.pattern import (
    PaperTradeResponse,
    PaperTraderRuleResponse,
    PatternResponse,
)

router = APIRouter(prefix="/api", tags=["patterns"])


@router.get("/patterns", response_model=List[PatternResponse])
async def list_patterns(
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Pattern).order_by(Pattern.discovered_at.desc())
    if status:
        stmt = stmt.where(Pattern.status == status)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/paper-trader-rules", response_model=List[PaperTraderRuleResponse])
async def list_paper_trader_rules(
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timezone

    stmt = select(PaperTraderRule).order_by(PaperTraderRule.spawned_at.desc())
    if status:
        stmt = stmt.where(PaperTraderRule.status == status)
    result = await session.execute(stmt)
    rules = result.scalars().all()
    now = datetime.now(timezone.utc)
    out: list[PaperTraderRuleResponse] = []
    for r in rules:
        spawned = r.spawned_at
        if spawned is not None and spawned.tzinfo is None:
            spawned = spawned.replace(tzinfo=timezone.utc)
        age = int((now - spawned).total_seconds()) if spawned else 0
        out.append(
            PaperTraderRuleResponse(
                id=r.id,
                pattern_id=r.pattern_id,
                status=r.status,
                spawned_at=r.spawned_at,
                total_trades=r.total_trades,
                win_count=r.win_count,
                mode=getattr(r, "mode", "strict") or "strict",
                trust_tier=getattr(r, "trust_tier", "experimental") or "experimental",
                age_seconds=age,
                net_ev_per_trade=getattr(r, "net_ev_per_trade", None),
                wilson_lower_95=getattr(r, "wilson_lower_95", None),
                baseline_delta=getattr(r, "baseline_delta", None),
                last_signal_status=getattr(r, "last_signal_status", None),
            )
        )
    return out


@router.get("/paper-trades", response_model=List[PaperTradeResponse])
async def list_paper_trades(
    rule_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None, pattern="^(open|closed)$"),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Trade)
        .where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
        )
        .order_by(Trade.open_time.desc().nullslast())
    )
    if status == "open":
        stmt = stmt.where(Trade.close_time.is_(None))
    elif status == "closed":
        stmt = stmt.where(Trade.close_time.is_not(None))

    result = await session.execute(stmt)
    trades = result.scalars().all()

    out: list[PaperTradeResponse] = []
    for t in trades:
        plan = t.recovery_plan or {}
        rid_str = plan.get("paper_trader_rule_id") if isinstance(plan, dict) else None
        rid: Optional[UUID] = None
        if rid_str:
            try:
                rid = UUID(rid_str)
            except (ValueError, TypeError):
                rid = None
        if rule_id is not None and rid != rule_id:
            continue
        out.append(
            PaperTradeResponse(
                id=t.id,
                ticket=t.ticket,
                symbol=t.symbol,
                direction=t.direction.value if t.direction else None,
                open_price=t.open_price,
                close_price=t.close_price,
                tp=t.tp,
                sl=t.sl,
                volume=t.volume,
                profit=t.profit,
                paper_exit_reason=t.paper_exit_reason,
                open_time=t.open_time,
                close_time=t.close_time,
                rule_id=rid,
                status="closed" if t.close_time is not None else "open",
            )
        )
    return out
