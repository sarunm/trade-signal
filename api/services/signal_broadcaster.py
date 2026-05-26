import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.paper_signal import PaperSignal
from models.pattern import PaperTraderRule

logger = logging.getLogger(__name__)

STATUS_ACTIVE = "active"
STATUS_NEAR = "near"
STATUS_FAR = "far"
STATUS_IDLE = "idle"

NEAR_MISSING_MAX = int(os.getenv("BROADCASTER_NEAR_MISSING_MAX", "1"))
NEAR_MIN_TOTAL = int(os.getenv("BROADCASTER_NEAR_MIN_TOTAL", "3"))


@dataclass
class SignalEvalInputs:
    matched_count: int
    total_count: int
    has_open_paper: bool


def compute_status(inputs: SignalEvalInputs) -> str:
    if inputs.has_open_paper:
        return STATUS_ACTIVE
    if inputs.total_count == 0:
        return STATUS_IDLE
    if inputs.matched_count == 0:
        return STATUS_IDLE
    if inputs.matched_count == inputs.total_count:
        return STATUS_ACTIVE
    missing = inputs.total_count - inputs.matched_count
    if inputs.total_count >= NEAR_MIN_TOTAL and missing <= NEAR_MISSING_MAX:
        return STATUS_NEAR
    return STATUS_FAR


@dataclass
class RuleEval:
    rule_id: UUID
    inputs: SignalEvalInputs
    matched_conditions: list[str]
    missing_conditions: list[str]
    score: Optional[float] = None
    suggested_lot: Optional[Decimal] = None


_last_status: dict[UUID, str] = {}


def reset_broadcaster_state() -> None:
    global _last_status
    _last_status = {}


async def _seed_state_from_db(session: AsyncSession, rule_ids: Iterable[UUID]) -> None:
    """Populate the in-memory cache from `paper_trader_rules.last_signal_status`
    so a process restart doesn't trigger a flood of false 'change' rows."""
    missing = [rid for rid in rule_ids if rid not in _last_status]
    if not missing:
        return
    result = await session.execute(
        select(PaperTraderRule.id, PaperTraderRule.last_signal_status).where(
            PaperTraderRule.id.in_(missing)
        )
    )
    for rid, status in result.all():
        _last_status[rid] = status or STATUS_IDLE


async def broadcast_status_changes(
    session: AsyncSession,
    evals: list[RuleEval],
    now: Optional[datetime] = None,
) -> list[PaperSignal]:
    if not evals:
        return []
    now = now or datetime.now(timezone.utc)
    await _seed_state_from_db(session, [e.rule_id for e in evals])

    written: list[PaperSignal] = []
    for ev in evals:
        new_status = compute_status(ev.inputs)
        old_status = _last_status.get(ev.rule_id, STATUS_IDLE)
        if new_status == old_status:
            continue
        match_pct = (
            Decimal(ev.inputs.matched_count) / Decimal(ev.inputs.total_count)
            if ev.inputs.total_count
            else Decimal("0")
        )
        sig = PaperSignal(
            rule_id=ev.rule_id,
            status=new_status,
            match_pct=match_pct.quantize(Decimal("0.0001")),
            matched_conditions=list(ev.matched_conditions),
            missing_conditions=list(ev.missing_conditions),
            score=Decimal(str(ev.score)) if ev.score is not None else None,
            suggested_lot=ev.suggested_lot,
            emitted_at=now,
        )
        session.add(sig)
        rule = await session.get(PaperTraderRule, ev.rule_id)
        if rule is not None:
            rule.last_signal_status = new_status
        _last_status[ev.rule_id] = new_status
        written.append(sig)

    if written:
        await session.commit()
    return written
