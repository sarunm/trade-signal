import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models.pattern import PaperTraderRule
from models.trade import PaperMode, Trade
from services.statistics import net_ev, profit_factor, wilson_lower
from services.trust_tier import GateOutcomes, compute_trust_tier

logger = logging.getLogger(__name__)

PROMOTION_MIN_TRADES = int(os.getenv("PROMOTION_MIN_TRADES", "100"))
PROMOTION_MIN_WILSON_LOWER = float(os.getenv("PROMOTION_MIN_WILSON_LOWER", "0.55"))
PROMOTION_MIN_NET_EV_THB = Decimal(os.getenv("PROMOTION_MIN_NET_EV_THB", "20"))
PROMOTION_MIN_PROFIT_FACTOR_NET = Decimal(os.getenv("PROMOTION_MIN_PROFIT_FACTOR_NET", "1.3"))
PROMOTION_MIN_BASELINE_DELTA = float(os.getenv("PROMOTION_MIN_BASELINE_DELTA", "0.05"))
PROMOTION_STABLE_DAYS = int(os.getenv("PROMOTION_STABLE_DAYS", "7"))
WALK_FORWARD_WINDOW_DAYS = int(os.getenv("WALK_FORWARD_WINDOW_DAYS", "14"))
WALK_FORWARD_MIN_SAMPLE = int(os.getenv("WALK_FORWARD_MIN_SAMPLE", "20"))
PROMOTION_HISTORY_DAYS = int(os.getenv("PROMOTION_HISTORY_DAYS", "30"))


@dataclass
class GateResult:
    rule_id: str
    gates: GateOutcomes
    tier: str
    wilson_lower: float
    net_ev: Decimal
    profit_factor: Decimal
    baseline_delta: float
    reason: str = ""
    metadata: dict = field(default_factory=dict)


async def _gate_sample(rule: PaperTraderRule) -> bool:
    return (rule.total_trades or 0) >= PROMOTION_MIN_TRADES


async def _load_paper_trades_in_window(
    session: AsyncSession, rule_id, days: int
) -> list[Trade]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_not(None),
            Trade.close_time >= cutoff,
        )
    )
    rule_id_str = str(rule_id)
    matched: list[Trade] = []
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        if plan.get("paper_trader_rule_id") != rule_id_str:
            continue
        if trade.profit is None:
            continue
        matched.append(trade)
    return matched


async def _estimate_total_cost(
    session: AsyncSession, trades: list[Trade]
) -> Decimal:
    try:
        from services.cost_model import estimate_cost
    except Exception:
        return Decimal("0.00")
    total = Decimal("0.00")
    for trade in trades:
        try:
            cost = await estimate_cost(session, trade.volume or Decimal("0.10"))
            total += cost.total_thb
        except Exception:
            continue
    return total


async def _gate_performance(
    session: AsyncSession, rule: PaperTraderRule
) -> tuple[bool, str, dict]:
    from services.baseline_stats import get_baseline_winrate

    trades = await _load_paper_trades_in_window(
        session, rule.id, days=PROMOTION_HISTORY_DAYS
    )
    if not trades:
        return False, "no_recent_trades", {
            "wilson_lower": 0.0, "net_ev": Decimal("0.00"),
            "profit_factor": Decimal("0"), "baseline_delta": 0.0,
            "winrate": 0.0,
        }

    profits = [t.profit for t in trades]
    n = len(profits)
    wins = sum(1 for p in profits if p > 0)
    p_hat = wins / n
    w_low = wilson_lower(p_hat, n)
    cost = await _estimate_total_cost(session, trades)
    ev = net_ev(profits, cost)
    pf = profit_factor(profits)
    baseline = await get_baseline_winrate(session)
    delta = p_hat - baseline

    metadata = {
        "wilson_lower": w_low,
        "net_ev": ev,
        "profit_factor": pf,
        "baseline_delta": delta,
        "winrate": p_hat,
    }

    reasons: list[str] = []
    if w_low < PROMOTION_MIN_WILSON_LOWER:
        reasons.append("wilson")
    if ev < PROMOTION_MIN_NET_EV_THB:
        reasons.append("ev")
    if pf < PROMOTION_MIN_PROFIT_FACTOR_NET:
        reasons.append("profit_factor")
    if delta < PROMOTION_MIN_BASELINE_DELTA:
        reasons.append("baseline")
    return (not reasons), ",".join(reasons), metadata


async def _gate_stability(rule: PaperTraderRule) -> bool:
    return (rule.consecutive_stable_days_rule or 0) >= PROMOTION_STABLE_DAYS


async def _gate_walk_forward(
    session: AsyncSession, rule: PaperTraderRule
) -> bool:
    trades = await _load_paper_trades_in_window(
        session, rule.id, days=WALK_FORWARD_WINDOW_DAYS
    )
    if len(trades) < WALK_FORWARD_MIN_SAMPLE:
        return False
    profits = [t.profit for t in trades]
    wins = sum(1 for p in profits if p > 0)
    return wilson_lower(wins / len(profits), len(profits)) >= PROMOTION_MIN_WILSON_LOWER


async def _persist(
    session: AsyncSession, rule: PaperTraderRule, result: GateResult
) -> None:
    rule.trust_tier = result.tier
    rule.wilson_lower_95 = Decimal(str(round(result.wilson_lower, 4)))
    rule.net_ev_per_trade = result.net_ev
    rule.baseline_delta = Decimal(str(round(result.baseline_delta, 4)))
    await session.commit()


async def evaluate_rule(
    session: AsyncSession, rule: PaperTraderRule
) -> GateResult:
    sample_pass = await _gate_sample(rule)
    gates = GateOutcomes(
        sample=sample_pass,
        performance=False,
        stability=False,
        walk_forward=False,
    )
    result = GateResult(
        rule_id=str(rule.id),
        gates=gates,
        tier=compute_trust_tier(gates),
        wilson_lower=0.0,
        net_ev=Decimal("0.00"),
        profit_factor=Decimal("0.0000"),
        baseline_delta=0.0,
    )

    if not sample_pass:
        result.reason = "insufficient_sample"
        await _persist(session, rule, result)
        return result

    perf_pass, perf_reason, perf_meta = await _gate_performance(session, rule)
    gates.performance = perf_pass
    result.wilson_lower = perf_meta["wilson_lower"]
    result.net_ev = perf_meta["net_ev"]
    result.profit_factor = perf_meta["profit_factor"]
    result.baseline_delta = perf_meta["baseline_delta"]
    result.metadata.update(perf_meta)

    if perf_pass:
        rule.consecutive_stable_days_rule = (rule.consecutive_stable_days_rule or 0) + 1
    else:
        rule.consecutive_stable_days_rule = 0
        result.reason = perf_reason

    if perf_pass:
        gates.stability = await _gate_stability(rule)
        if gates.stability:
            gates.walk_forward = await _gate_walk_forward(session, rule)

    result.tier = compute_trust_tier(gates)
    await _persist(session, rule, result)
    return result


async def evaluate_all_active_rules(
    session: Optional[AsyncSession] = None,
) -> list[GateResult]:
    if session is None:
        async with SessionLocal() as owned:
            return await _evaluate_all(owned)
    return await _evaluate_all(session)


async def _evaluate_all(session: AsyncSession) -> list[GateResult]:
    rules = (await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.status == "active")
    )).scalars().all()
    results: list[GateResult] = []
    for rule in rules:
        if getattr(rule, "is_baseline", False):
            continue
        try:
            results.append(await evaluate_rule(session, rule))
        except Exception:
            logger.exception("evaluate_rule failed for rule_id=%s", rule.id)
    return results
