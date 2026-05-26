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
