from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
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
from services.promotion_gate import evaluate_rule

router = APIRouter(prefix="/api", tags=["patterns"])


async def _open_trades_count_by_rule(session: AsyncSession) -> dict[str, int]:
    """Return {rule_id_str: open_count} for all paper trades currently open."""
    stmt = select(Trade).where(
        Trade.is_paper.is_(True),
        Trade.close_time.is_(None),
    )
    result = await session.execute(stmt)
    counts: dict[str, int] = {}
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        rid = plan.get("paper_trader_rule_id") if isinstance(plan, dict) else None
        if not rid:
            continue
        counts[rid] = counts.get(rid, 0) + 1
    return counts


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
    open_counts = await _open_trades_count_by_rule(session)
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
                filters=list(getattr(r, "filters", None) or []),
                shadow_of_rule_id=getattr(r, "shadow_of_rule_id", None),
                virtual_balance_start=getattr(r, "virtual_balance_start", None),
                virtual_balance_current=getattr(r, "virtual_balance_current", None),
                open_trades_count=open_counts.get(str(r.id), 0),
                last_activity_at=None,
            )
        )
    return out


@router.get("/patterns/{pattern_id}/gates")
async def pattern_gates(
    pattern_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    rules = (await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.pattern_id == pattern_id)
    )).scalars().all()
    summaries = []
    for rule in rules:
        result = await evaluate_rule(session, rule)
        summaries.append({
            "rule_id": str(rule.id),
            "mode": rule.mode,
            "tier": result.tier,
            "gates": {
                "sample": result.gates.sample,
                "performance": result.gates.performance,
                "stability": result.gates.stability,
                "walk_forward": result.gates.walk_forward,
            },
            "wilson_lower": result.wilson_lower,
            "net_ev": float(result.net_ev),
            "profit_factor": float(result.profit_factor),
            "baseline_delta": result.baseline_delta,
            "reason": result.reason,
        })
    return {"pattern_id": str(pattern_id), "rules": summaries}


def _serialize_rule(rule: PaperTraderRule) -> dict:
    return {
        "id": str(rule.id),
        "pattern_id": str(rule.pattern_id),
        "status": rule.status,
        "mode": rule.mode,
        "filters": rule.filters or [],
        "shadow_of_rule_id": (
            str(rule.shadow_of_rule_id) if rule.shadow_of_rule_id else None
        ),
        "spawned_at": rule.spawned_at.isoformat() if rule.spawned_at else None,
        "total_trades": rule.total_trades,
        "win_count": rule.win_count,
    }


async def _rule_winrate(session: AsyncSession, rule_id: UUID) -> tuple[float, int]:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.close_time.is_not(None),
        )
    )
    target = str(rule_id)
    total, wins = 0, 0
    for t in result.scalars().all():
        plan = t.recovery_plan or {}
        if plan.get("paper_trader_rule_id") != target:
            continue
        if t.profit is None:
            continue
        total += 1
        if t.profit > 0:
            wins += 1
    return (wins / total if total else 0.0), total


@router.get("/paper-trader-rules/{rule_id}/shadows")
async def get_rule_shadows(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    parent = await session.get(PaperTraderRule, rule_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="rule not found")

    parent_wr, parent_n = await _rule_winrate(session, parent.id)

    result = await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.shadow_of_rule_id == parent.id)
    )
    shadows = []
    for shadow in result.scalars().all():
        s_wr, s_n = await _rule_winrate(session, shadow.id)
        delta = s_wr - parent_wr if (s_n >= 30 and parent_n >= 30) else None
        shadows.append({
            **_serialize_rule(shadow),
            "winrate": s_wr,
            "trades": s_n,
            "winrate_delta": delta,
        })

    return {
        "parent": {**_serialize_rule(parent), "winrate": parent_wr, "trades": parent_n},
        "shadows": shadows,
    }


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
