import itertools
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models.indicator_signal import TradeIndicatorSignal
from models.pattern import PaperTraderRule, Pattern
from models.trade import Trade

logger = logging.getLogger(__name__)

DISCOVERY_WINDOW_TRADES = int(os.getenv("DISCOVERY_WINDOW_TRADES", 50))
DISCOVERY_WINDOW_MAX_DAYS = int(os.getenv("DISCOVERY_WINDOW_MAX_DAYS", 30))
DISCOVERY_MIN_SAMPLE = int(os.getenv("DISCOVERY_MIN_SAMPLE", 10))
DISCOVERY_MIN_WIN_RATE = float(os.getenv("DISCOVERY_MIN_WIN_RATE", 0.60))
DISCOVERY_STABLE_DAYS = int(os.getenv("DISCOVERY_STABLE_DAYS", 3))
DEDUP_JACCARD_THRESHOLD = 0.8
COMBINATION_SIZES = (2, 3, 4, 5)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _ensure_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _window_cutoff(session: AsyncSession, now: datetime) -> datetime:
    age_cutoff = now - timedelta(days=DISCOVERY_WINDOW_MAX_DAYS)
    result = await session.execute(
        select(Trade.close_time)
        .where(Trade.is_paper.is_(False), Trade.close_time.is_not(None))
        .order_by(Trade.close_time.desc())
        .limit(DISCOVERY_WINDOW_TRADES)
    )
    times = [_ensure_aware(t) for t in result.scalars().all() if t is not None]
    if len(times) < DISCOVERY_WINDOW_TRADES:
        return age_cutoff
    return max(age_cutoff, times[-1])


async def _load_window(
    session: AsyncSession, cutoff: datetime
) -> list[tuple[Trade, set[str]]]:
    trade_q = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(False),
            Trade.close_time.is_not(None),
            Trade.close_time >= cutoff,
            Trade.profit.is_not(None),
        )
    )
    trades = trade_q.scalars().all()
    if not trades:
        return []

    sig_q = await session.execute(
        select(TradeIndicatorSignal).where(
            TradeIndicatorSignal.trade_id.in_([t.id for t in trades]),
            TradeIndicatorSignal.matched.is_(True),
        )
    )
    matched_by_trade: dict = {}
    for sig in sig_q.scalars().all():
        matched_by_trade.setdefault(sig.trade_id, set()).add(sig.indicator_slug)

    return [(t, matched_by_trade.get(t.id, set())) for t in trades]


def _score_combinations(
    population: list[tuple[Trade, set[str]]]
) -> dict[frozenset[str], tuple[int, int]]:
    """Return {combo: (sample_count, win_count)}."""
    scores: dict[frozenset[str], list[int]] = {}
    for trade, slugs in population:
        if len(slugs) < 2:
            continue
        is_win = trade.profit is not None and float(trade.profit) > 0
        ordered = sorted(slugs)
        for size in COMBINATION_SIZES:
            if size > len(ordered):
                break
            for combo in itertools.combinations(ordered, size):
                key = frozenset(combo)
                bucket = scores.setdefault(key, [0, 0])
                bucket[0] += 1
                if is_win:
                    bucket[1] += 1
    return {k: (v[0], v[1]) for k, v in scores.items()}


async def _existing_patterns(session: AsyncSession) -> dict[frozenset[str], Pattern]:
    result = await session.execute(select(Pattern))
    return {frozenset(p.indicator_slugs): p for p in result.scalars().all()}


async def _existing_active_rule_slugs(session: AsyncSession) -> list[set[str]]:
    result = await session.execute(
        select(Pattern)
        .join(PaperTraderRule, PaperTraderRule.pattern_id == Pattern.id)
        .where(PaperTraderRule.status == "active")
    )
    return [set(p.indicator_slugs) for p in result.scalars().all()]


def _passes_filter(sample: int, win_rate: float) -> bool:
    return sample >= DISCOVERY_MIN_SAMPLE and win_rate >= DISCOVERY_MIN_WIN_RATE


async def run_pattern_discovery(
    session: Optional[AsyncSession] = None, now: Optional[datetime] = None
) -> None:
    now = now or datetime.now(timezone.utc)
    if session is None:
        async with SessionLocal() as owned_session:
            await _run(owned_session, now)
            await owned_session.commit()
        return
    await _run(session, now)
    await session.commit()


async def _run(session: AsyncSession, now: datetime) -> None:
    cutoff = await _window_cutoff(session, now)
    population = await _load_window(session, cutoff)
    if not population:
        logger.info("pattern_discovery: no trades in window")
        return

    scores = _score_combinations(population)
    existing = await _existing_patterns(session)
    active_rule_slugs = await _existing_active_rule_slugs(session)

    passing_keys: set[frozenset[str]] = set()

    for combo_key, (sample, win_count) in scores.items():
        win_rate = win_count / sample if sample else 0.0
        if not _passes_filter(sample, win_rate):
            continue
        passing_keys.add(combo_key)

        pattern = existing.get(combo_key)
        if pattern is None:
            pattern = Pattern(
                indicator_slugs=sorted(combo_key),
                timeframe="H1",
                win_rate=win_rate,
                sample_count=sample,
                consecutive_stable_days=1,
                status="candidate",
            )
            session.add(pattern)
            existing[combo_key] = pattern
        else:
            pattern.win_rate = win_rate
            pattern.sample_count = sample
            if pattern.status == "candidate":
                pattern.consecutive_stable_days += 1

        if pattern.status == "candidate" and pattern.consecutive_stable_days >= DISCOVERY_STABLE_DAYS:
            if _is_duplicate(set(combo_key), active_rule_slugs):
                continue
            pattern.status = "active"
            pattern.promoted_at = now
            await session.flush()
            session.add(PaperTraderRule(pattern_id=pattern.id, status="active"))
            active_rule_slugs.append(set(combo_key))

    for key, pattern in existing.items():
        if key in passing_keys:
            continue
        if pattern.status == "candidate":
            pattern.consecutive_stable_days = 0


def _is_duplicate(combo: set[str], existing_active: Iterable[set[str]]) -> bool:
    for other in existing_active:
        if jaccard(combo, other) > DEDUP_JACCARD_THRESHOLD:
            return True
    return False
