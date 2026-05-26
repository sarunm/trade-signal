import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.pattern import PaperTraderRule
from models.trade import Trade
from services.feature_extractor import (
    classify_session,
    day_of_week,
    hour_bucket,
)

logger = logging.getLogger(__name__)

ADAPTIVE_ENABLED = os.getenv("ADAPTIVE_ENABLED", "1") == "1"
ADAPTIVE_LOOKBACK_TRADES = int(os.getenv("ADAPTIVE_LOOKBACK_TRADES", "200"))
ADAPTIVE_MIN_TRADES = int(os.getenv("ADAPTIVE_MIN_TRADES", "30"))
ADAPTIVE_MIN_BUCKET = int(os.getenv("ADAPTIVE_MIN_BUCKET", "10"))
ADAPTIVE_LOSS_DELTA = float(os.getenv("ADAPTIVE_LOSS_DELTA", "0.20"))
ADAPTIVE_PROMOTE_DELTA = float(os.getenv("ADAPTIVE_PROMOTE_DELTA", "0.05"))
ADAPTIVE_SHADOW_AGE_DAYS = int(os.getenv("ADAPTIVE_SHADOW_AGE_DAYS", "30"))

FEATURE_SESSION = "session"
FEATURE_HOUR = "hour_bucket"
FEATURE_DOW = "dow"

_FEATURE_FNS = {
    FEATURE_SESSION: lambda t: classify_session(t.open_time),
    FEATURE_HOUR: lambda t: hour_bucket(t.open_time),
    FEATURE_DOW: lambda t: day_of_week(t.open_time),
}


@dataclass(frozen=True)
class FilterProposal:
    feature: str
    exclude: str
    bucket_n: int
    bucket_loss_rate: float
    other_loss_rate: float

    def to_filter(self) -> dict:
        return {"feature": self.feature, "exclude": self.exclude}


@dataclass
class _BucketStats:
    n: int = 0
    losses: int = 0

    @property
    def loss_rate(self) -> float:
        return self.losses / self.n if self.n else 0.0


async def _load_rule_trades(
    session: AsyncSession, rule: PaperTraderRule, limit: int
) -> list[Trade]:
    """Closed paper trades for this rule, newest first, capped at `limit`."""
    result = await session.execute(
        select(Trade)
        .where(
            Trade.is_paper.is_(True),
            Trade.close_time.is_not(None),
        )
        .order_by(Trade.close_time.desc())
    )
    rule_id_str = str(rule.id)
    matched: list[Trade] = []
    for t in result.scalars().all():
        plan = t.recovery_plan or {}
        if plan.get("paper_trader_rule_id") == rule_id_str:
            matched.append(t)
            if len(matched) >= limit:
                break
    return matched


def _bucket_trades(
    trades: Sequence[Trade], feature_fn
) -> dict[str, _BucketStats]:
    buckets: dict[str, _BucketStats] = defaultdict(_BucketStats)
    for t in trades:
        key = feature_fn(t)
        b = buckets[key]
        b.n += 1
        if t.profit is not None and t.profit < 0:
            b.losses += 1
    return buckets


def _propose_for_feature(
    feature: str, buckets: dict[str, _BucketStats]
) -> list[FilterProposal]:
    proposals: list[FilterProposal] = []
    big = [(k, b) for k, b in buckets.items() if b.n >= ADAPTIVE_MIN_BUCKET]
    if len(big) < 2:
        return proposals
    total_n = sum(b.n for _, b in big)
    total_losses = sum(b.losses for _, b in big)
    for key, bucket in big:
        other_n = total_n - bucket.n
        other_losses = total_losses - bucket.losses
        if other_n < ADAPTIVE_MIN_BUCKET:
            continue
        other_rate = other_losses / other_n
        delta = bucket.loss_rate - other_rate
        if delta >= ADAPTIVE_LOSS_DELTA:
            proposals.append(FilterProposal(
                feature=feature,
                exclude=key,
                bucket_n=bucket.n,
                bucket_loss_rate=bucket.loss_rate,
                other_loss_rate=other_rate,
            ))
    return proposals


async def _existing_shadow_with_filter(
    session: AsyncSession,
    parent_rule_id: UUID,
    filter_clause: dict,
) -> Optional[PaperTraderRule]:
    result = await session.execute(
        select(PaperTraderRule).where(
            PaperTraderRule.shadow_of_rule_id == parent_rule_id,
            PaperTraderRule.status == "shadow",
        )
    )
    for rule in result.scalars().all():
        existing = rule.filters or []
        if filter_clause in existing:
            return rule
    return None


async def spawn_shadow_rule(
    session: AsyncSession,
    parent: PaperTraderRule,
    proposal: FilterProposal,
) -> PaperTraderRule:
    """Create or return a shadow rule that copies the parent and appends the
    proposed filter clause. Idempotent on (parent_id, filter_clause)."""
    clause = proposal.to_filter()
    existing = await _existing_shadow_with_filter(session, parent.id, clause)
    if existing is not None:
        return existing

    parent_filters = list(parent.filters or [])
    shadow_filters = parent_filters + [clause]

    shadow = PaperTraderRule(
        pattern_id=parent.pattern_id,
        status="shadow",
        mode=parent.mode,
        virtual_balance_start=parent.virtual_balance_start,
        virtual_balance_current=parent.virtual_balance_start,
        score_weights=dict(parent.score_weights or {}) or None,
        filters=shadow_filters,
        shadow_of_rule_id=parent.id,
    )
    session.add(shadow)
    await session.flush()
    await session.commit()
    logger.info(
        "adaptive_tuner: spawned shadow %s from parent %s with filter %s",
        shadow.id, parent.id, clause,
    )
    return shadow


def _winrate(trades: Iterable[Trade]) -> tuple[float, int]:
    total = 0
    wins = 0
    for t in trades:
        if t.profit is None:
            continue
        total += 1
        if t.profit > 0:
            wins += 1
    return (wins / total if total else 0.0), total


async def promote_shadow_if_outperforms(
    session: AsyncSession, shadow: PaperTraderRule
) -> bool:
    """Promote shadow when it beats parent winrate by ADAPTIVE_PROMOTE_DELTA
    over the apples-to-apples window since the shadow was spawned. Both sides
    must have ≥ ADAPTIVE_MIN_TRADES."""
    if shadow.shadow_of_rule_id is None:
        return False
    spawned = shadow.spawned_at
    if spawned is not None and spawned.tzinfo is None:
        spawned = spawned.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - spawned
    if age < timedelta(days=ADAPTIVE_SHADOW_AGE_DAYS):
        return False

    parent = await session.get(PaperTraderRule, shadow.shadow_of_rule_id)
    if parent is None or parent.status != "active":
        return False

    shadow_trades = await _load_rule_trades(session, shadow, ADAPTIVE_LOOKBACK_TRADES)
    parent_trades_all = await _load_rule_trades(session, parent, ADAPTIVE_LOOKBACK_TRADES)
    parent_trades = []
    for t in parent_trades_all:
        ct = t.close_time
        if ct is None:
            continue
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        if ct >= spawned:
            parent_trades.append(t)

    shadow_wr, shadow_n = _winrate(shadow_trades)
    parent_wr, parent_n = _winrate(parent_trades)

    if shadow_n < ADAPTIVE_MIN_TRADES or parent_n < ADAPTIVE_MIN_TRADES:
        return False
    if shadow_wr - parent_wr < ADAPTIVE_PROMOTE_DELTA:
        return False

    parent.status = "retired"
    shadow.status = "active"
    shadow.shadow_of_rule_id = None
    await session.commit()
    logger.info(
        "adaptive_tuner: promoted shadow %s (winrate %.3f) over parent %s (winrate %.3f)",
        shadow.id, shadow_wr, parent.id, parent_wr,
    )
    return True


async def propose_filters_for_rule(
    session: AsyncSession, rule: PaperTraderRule
) -> list[FilterProposal]:
    trades = await _load_rule_trades(session, rule, ADAPTIVE_LOOKBACK_TRADES)
    if len(trades) < ADAPTIVE_MIN_TRADES:
        return []
    proposals: list[FilterProposal] = []
    for feature, fn in _FEATURE_FNS.items():
        buckets = _bucket_trades(trades, fn)
        proposals.extend(_propose_for_feature(feature, buckets))
    return proposals


async def _active_non_baseline_rules(session: AsyncSession) -> list[PaperTraderRule]:
    result = await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.status == "active")
    )
    rules: list[PaperTraderRule] = []
    for r in result.scalars().all():
        if getattr(r, "is_baseline", False):
            continue
        rules.append(r)
    return rules


async def _all_shadow_rules(session: AsyncSession) -> list[PaperTraderRule]:
    result = await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.status == "shadow")
    )
    return list(result.scalars().all())


async def run_adaptive_tuner(session: AsyncSession) -> dict:
    """Daily orchestrator: propose filters, spawn shadows, promote winners."""
    summary = {
        "rules_evaluated": 0,
        "proposals_total": 0,
        "shadows_spawned": 0,
        "shadows_promoted": 0,
    }
    if not ADAPTIVE_ENABLED:
        return summary

    active_rules = await _active_non_baseline_rules(session)
    summary["rules_evaluated"] = len(active_rules)

    for rule in active_rules:
        try:
            proposals = await propose_filters_for_rule(session, rule)
        except Exception:
            logger.exception("adaptive_tuner: propose failed for rule %s", rule.id)
            continue
        summary["proposals_total"] += len(proposals)
        for proposal in proposals:
            try:
                await spawn_shadow_rule(session, rule, proposal)
                summary["shadows_spawned"] += 1
            except Exception:
                logger.exception(
                    "adaptive_tuner: spawn failed for rule %s, proposal %s",
                    rule.id, proposal,
                )

    for shadow in await _all_shadow_rules(session):
        try:
            if await promote_shadow_if_outperforms(session, shadow):
                summary["shadows_promoted"] += 1
        except Exception:
            logger.exception("adaptive_tuner: promote failed for shadow %s", shadow.id)

    logger.info("adaptive_tuner: %s", summary)
    return summary
