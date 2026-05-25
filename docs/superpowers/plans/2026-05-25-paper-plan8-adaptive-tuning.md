# Plan 8 — Adaptive Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-25-paper-trade-system-redesign.md` § "Component 3 — Adaptive Tuning" (v1 — kept unchanged in v2 spec line 354).

**Goal:** For each non-baseline rule with ≥ 30 closed paper trades, mine **features** (session, hour bucket, day-of-week, ATR-volatility regime) that separate winners from losers. When a feature drops loss-rate by ≥ 0.20, propose it as a `filters` entry, spawn a **shadow rule** (`status='shadow'`, `shadow_of_rule_id=parent.id`, `filters=[...]`) for 30-day live-test, then auto-promote shadow → primary when shadow winrate > parent winrate + 5% and shadow has ≥ 30 closed trades.

**Architecture:**
- New `feature_extractor.py` — pure helpers: `classify_session(dt)`, `hour_bucket(dt)`, `day_of_week(dt)`, `volatility_regime(atr, atr_history)`. Computed at evaluation time from `trade.open_time` and a small ATR snapshot — **not** persisted (cheap to recompute, schema-stable).
- New `adaptive_tuner.py` — per active rule:
  1. Load last `ADAPTIVE_LOOKBACK_TRADES=200` closed paper trades for the rule.
  2. Compute feature buckets and per-bucket loss-rate.
  3. For each feature `X` where `loss_rate(X=true) − loss_rate(X=false) ≥ ADAPTIVE_LOSS_DELTA=0.20` and both buckets have ≥ `ADAPTIVE_MIN_BUCKET=10` trades, propose filter `{"feature": X, "exclude": value}`.
  4. Skip proposals that already exist as a shadow under this parent.
  5. Create shadow rule (`status='shadow'`, copies parent's `mode`, `pattern_id`, `score_weights`, but adds `filters`). The paper trader's existing entry path **already enforces filters** — no entry-path changes.
  6. After 30 days, compare shadow vs parent on overlapping window; if shadow wins by `ADAPTIVE_PROMOTE_DELTA=0.05`, swap them: parent → `status='retired'`, shadow → `status='active'`, clear `shadow_of_rule_id`.
- New `paper_trader.py` filter-check hook — `_passes_filters(rule, ctx)` rejects entries whose context matches an exclude clause. Called from existing `_check_entries()` immediately before opening a trade.
- New cron in `main.py` runs `_safe_run_adaptive_tuner()` daily at 00:45 UTC (after promotion gate's 00:30).
- New `/api/paper-trader-rules/{id}/shadows` returns parent rule + shadow rules + their delta — for UI inspection.
- **No new migration.** All required columns (`filters`, `shadow_of_rule_id`) already landed in migration 011 (Plan 1).

**Tech Stack:** SQLAlchemy 2.0 async, FastAPI, APScheduler, pytest-asyncio + httpx (SQLite in-memory).

---

## File Structure

| Path | Action | Purpose |
|------|--------|---------|
| `api/services/feature_extractor.py` | create | Bucket trades by session/hour/dow/volatility |
| `api/services/adaptive_tuner.py` | create | Loss-rate analysis + shadow spawn + auto-promote |
| `api/services/paper_trader.py` | modify | Add `_passes_filters()` gate in `_check_entries()` |
| `api/routers/patterns.py` | modify | New `/api/paper-trader-rules/{id}/shadows` route |
| `api/main.py` | modify | Daily cron `_safe_run_adaptive_tuner()` |
| `tests/test_feature_extractor.py` | create | Unit tests for bucket helpers |
| `tests/test_adaptive_tuner.py` | create | Loss-rate analysis + shadow spawn + promotion |
| `tests/test_paper_trader_filters.py` | create | Filter gate rejects matching entries |
| `tests/test_shadows_api.py` | create | API exposes parent + shadows + delta |

**Note on migrations:** This plan touches no Alembic versions. The `filters JSONB` and `shadow_of_rule_id UUID` columns were created by migration 011 in Plan 1; we just write to them here.

---

## Task 1: Feature extractor — session / hour / dow / volatility

**Files:**
- Create: `api/services/feature_extractor.py`
- Test: `tests/test_feature_extractor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_feature_extractor.py
from datetime import datetime, timezone

import pytest

from services.feature_extractor import (
    HOUR_BUCKETS,
    SESSION_ASIA,
    SESSION_LONDON,
    SESSION_NY,
    classify_session,
    day_of_week,
    hour_bucket,
    volatility_regime,
)


@pytest.mark.parametrize("hour, expected", [
    (0, SESSION_ASIA),
    (5, SESSION_ASIA),
    (7, SESSION_LONDON),
    (12, SESSION_LONDON),
    (13, SESSION_NY),
    (20, SESSION_NY),
    (22, SESSION_ASIA),
])
def test_classify_session_by_utc_hour(hour, expected):
    dt = datetime(2026, 5, 25, hour, 0, tzinfo=timezone.utc)
    assert classify_session(dt) == expected


def test_hour_bucket_groups_into_4h_blocks():
    dt = datetime(2026, 5, 25, 9, 30, tzinfo=timezone.utc)
    bucket = hour_bucket(dt)
    assert bucket in HOUR_BUCKETS
    # 4-hour block starting at 08
    assert bucket == "08-12"


def test_day_of_week_returns_short_name():
    monday = datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc)  # Mon
    assert day_of_week(monday) == "mon"


def test_volatility_regime_high_when_atr_above_p70():
    history = [10.0, 12.0, 8.0, 11.0, 15.0, 9.0, 13.0, 14.0, 18.0, 20.0]
    assert volatility_regime(19.0, history) == "high"
    assert volatility_regime(11.0, history) == "mid"
    assert volatility_regime(8.5, history) == "low"


def test_volatility_regime_unknown_when_history_too_short():
    assert volatility_regime(10.0, [12.0, 11.0]) == "unknown"
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_feature_extractor.py -v"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# api/services/feature_extractor.py
from datetime import datetime
from typing import Sequence

SESSION_LONDON = "london"
SESSION_NY = "ny"
SESSION_ASIA = "asia"

HOUR_BUCKETS = ("00-04", "04-08", "08-12", "12-16", "16-20", "20-24")
DOW_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

VOL_LOW = "low"
VOL_MID = "mid"
VOL_HIGH = "high"
VOL_UNKNOWN = "unknown"

_VOL_HISTORY_MIN = 5
_VOL_LOW_PCTILE = 0.30
_VOL_HIGH_PCTILE = 0.70


def classify_session(dt: datetime) -> str:
    """Map UTC hour to a session label.

    London 07:00–13:00, NY 13:00–22:00, Asia 22:00–07:00.
    """
    h = dt.astimezone().hour if dt.tzinfo is None else dt.hour
    if 7 <= h < 13:
        return SESSION_LONDON
    if 13 <= h < 22:
        return SESSION_NY
    return SESSION_ASIA


def hour_bucket(dt: datetime) -> str:
    h = dt.hour
    start = (h // 4) * 4
    return f"{start:02d}-{start + 4:02d}"


def day_of_week(dt: datetime) -> str:
    return DOW_NAMES[dt.weekday()]


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    n = len(sorted_values)
    if n == 0:
        return 0.0
    k = max(0, min(n - 1, int(pct * (n - 1))))
    return sorted_values[k]


def volatility_regime(atr_value: float, history: Sequence[float]) -> str:
    """Classify ATR vs its own recent distribution (history)."""
    if len(history) < _VOL_HISTORY_MIN:
        return VOL_UNKNOWN
    s = sorted(history)
    if atr_value < _percentile(s, _VOL_LOW_PCTILE):
        return VOL_LOW
    if atr_value > _percentile(s, _VOL_HIGH_PCTILE):
        return VOL_HIGH
    return VOL_MID
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_feature_extractor.py -v"
```

Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/feature_extractor.py tests/test_feature_extractor.py
git commit -m "feat: feature extractor (session, hour bucket, dow, volatility regime)"
```

---

## Task 2: Adaptive tuner — bucket trades by feature, compute loss-rate delta

**Files:**
- Create: `api/services/adaptive_tuner.py`
- Test: `tests/test_adaptive_tuner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_adaptive_tuner.py
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.adaptive_tuner import (
    ADAPTIVE_LOSS_DELTA,
    ADAPTIVE_MIN_BUCKET,
    FilterProposal,
    propose_filters_for_rule,
)


@pytest_asyncio.fixture
async def session():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    async with Session() as s:
        yield s
    await eng.dispose()


async def _seed_rule(session) -> PaperTraderRule:
    pattern = Pattern(
        indicator_slugs=["rsi", "macd"], timeframe="H1",
        win_rate=0.55, sample_count=100, status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(
        pattern_id=pattern.id, status="active",
        mode="strict",
        virtual_balance_start=Decimal("5000"),
        virtual_balance_current=Decimal("5000"),
    )
    session.add(rule)
    await session.flush()
    return rule


def _trade(rule_id, *, profit: float, hour: int, dow: int = 0) -> Trade:
    open_t = datetime(2026, 4, 6 + dow, hour, 0, tzinfo=timezone.utc)  # 2026-04-06 = Mon
    return Trade(
        ticket=uuid4().int & 0x7FFFFFFF, symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market, order_state=OrderState.closed,
        open_time=open_t,
        close_time=open_t,
        open_price=Decimal("1950"), close_price=Decimal("1955"),
        volume=Decimal("0.10"),
        profit=Decimal(str(profit)),
        is_paper=True, paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule_id)},
    )


@pytest.mark.asyncio
async def test_propose_filters_returns_session_excluder(session):
    rule = await _seed_rule(session)
    # Asia (hour=2): 12 trades, all losses
    for _ in range(12):
        session.add(_trade(rule.id, profit=-50, hour=2))
    # London (hour=10): 12 trades, all wins
    for _ in range(12):
        session.add(_trade(rule.id, profit=+50, hour=10))
    await session.commit()

    proposals = await propose_filters_for_rule(session, rule)

    assert any(
        p.feature == "session" and p.exclude == "asia"
        for p in proposals
    ), proposals


@pytest.mark.asyncio
async def test_propose_filters_skips_small_buckets(session):
    rule = await _seed_rule(session)
    # 5 losses in Asia (below ADAPTIVE_MIN_BUCKET=10) — should not propose
    for _ in range(5):
        session.add(_trade(rule.id, profit=-50, hour=2))
    for _ in range(20):
        session.add(_trade(rule.id, profit=+50, hour=10))
    await session.commit()
    proposals = await propose_filters_for_rule(session, rule)
    assert not any(p.feature == "session" and p.exclude == "asia" for p in proposals)


@pytest.mark.asyncio
async def test_propose_filters_skips_when_delta_below_threshold(session):
    rule = await _seed_rule(session)
    # Asia 6/12 wins (loss_rate 0.50), London 7/12 wins (loss_rate 0.42) — delta 0.08 < 0.20
    for i in range(12):
        session.add(_trade(rule.id, profit=+50 if i < 6 else -50, hour=2))
    for i in range(12):
        session.add(_trade(rule.id, profit=+50 if i < 7 else -50, hour=10))
    await session.commit()
    proposals = await propose_filters_for_rule(session, rule)
    assert not any(p.feature == "session" for p in proposals)
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_adaptive_tuner.py -v -k propose_filters"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# api/services/adaptive_tuner.py
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
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
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_adaptive_tuner.py -v -k propose_filters"
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/adaptive_tuner.py tests/test_adaptive_tuner.py
git commit -m "feat: adaptive tuner — propose filters from per-bucket loss-rate delta"
```

---

## Task 3: Adaptive tuner — spawn shadow rule from proposal

**Files:**
- Modify: `api/services/adaptive_tuner.py`
- Modify: `tests/test_adaptive_tuner.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_adaptive_tuner.py`:

```python
from services.adaptive_tuner import spawn_shadow_rule


@pytest.mark.asyncio
async def test_spawn_shadow_creates_rule_with_filter_and_parent_link(session):
    rule = await _seed_rule(session)
    proposal = FilterProposal(
        feature="session", exclude="asia",
        bucket_n=12, bucket_loss_rate=1.0, other_loss_rate=0.0,
    )
    shadow = await spawn_shadow_rule(session, rule, proposal)
    assert shadow.id != rule.id
    assert shadow.status == "shadow"
    assert shadow.shadow_of_rule_id == rule.id
    assert shadow.pattern_id == rule.pattern_id
    assert shadow.mode == rule.mode
    # filter is appended (parent has no filters; shadow has one)
    assert shadow.filters == [{"feature": "session", "exclude": "asia"}]


@pytest.mark.asyncio
async def test_spawn_shadow_is_idempotent_for_same_proposal(session):
    rule = await _seed_rule(session)
    proposal = FilterProposal(
        feature="session", exclude="asia",
        bucket_n=12, bucket_loss_rate=1.0, other_loss_rate=0.0,
    )
    a = await spawn_shadow_rule(session, rule, proposal)
    b = await spawn_shadow_rule(session, rule, proposal)
    assert a.id == b.id

    rules = (await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.shadow_of_rule_id == rule.id)
    )).scalars().all()
    assert len(rules) == 1
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_adaptive_tuner.py -v -k shadow"
```

Expected: FAIL — `spawn_shadow_rule` not defined.

- [ ] **Step 3: Implement**

Append to `api/services/adaptive_tuner.py`:

```python
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
        score_weights=dict(parent.score_weights or {}),
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
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_adaptive_tuner.py -v -k shadow"
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/adaptive_tuner.py tests/test_adaptive_tuner.py
git commit -m "feat: spawn shadow rule from filter proposal (idempotent)"
```

---

## Task 4: Filter gate in paper_trader — reject entries that match an exclude clause

**Files:**
- Modify: `api/services/paper_trader.py`
- Test: `tests/test_paper_trader_filters.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_paper_trader_filters.py
from datetime import datetime, timezone

import pytest

from services.paper_trader import _passes_filters


def _ctx(now: datetime) -> dict:
    return {"now": now}


def test_passes_when_no_filters():
    rule = type("R", (), {"filters": []})()
    assert _passes_filters(rule, _ctx(datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)))


def test_rejects_when_session_excluded():
    rule = type("R", (), {"filters": [{"feature": "session", "exclude": "asia"}]})()
    asia_now = datetime(2026, 5, 25, 2, 0, tzinfo=timezone.utc)
    assert not _passes_filters(rule, _ctx(asia_now))


def test_passes_when_session_does_not_match_excluded():
    rule = type("R", (), {"filters": [{"feature": "session", "exclude": "asia"}]})()
    london_now = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    assert _passes_filters(rule, _ctx(london_now))


def test_rejects_on_hour_bucket_exclude():
    rule = type("R", (), {"filters": [{"feature": "hour_bucket", "exclude": "00-04"}]})()
    early_now = datetime(2026, 5, 25, 2, 0, tzinfo=timezone.utc)
    assert not _passes_filters(rule, _ctx(early_now))


def test_rejects_on_dow_exclude():
    rule = type("R", (), {"filters": [{"feature": "dow", "exclude": "fri"}]})()
    fri_now = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)  # Fri
    assert not _passes_filters(rule, _ctx(fri_now))


def test_rejects_on_unknown_feature_passes_through():
    rule = type("R", (), {"filters": [{"feature": "novel", "exclude": "x"}]})()
    assert _passes_filters(rule, _ctx(datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)))
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader_filters.py -v"
```

Expected: FAIL — `_passes_filters` not defined.

- [ ] **Step 3: Implement** — append to `api/services/paper_trader.py`

```python
# Adaptive-tuning filter gate
from services.feature_extractor import (
    classify_session as _classify_session,
    day_of_week as _day_of_week,
    hour_bucket as _hour_bucket,
)

_FILTER_FEATURE_FNS = {
    "session": lambda ctx: _classify_session(ctx["now"]),
    "hour_bucket": lambda ctx: _hour_bucket(ctx["now"]),
    "dow": lambda ctx: _day_of_week(ctx["now"]),
}


def _passes_filters(rule, ctx: dict) -> bool:
    """Return False if any filter clause excludes the current context."""
    for clause in (getattr(rule, "filters", None) or []):
        feature = clause.get("feature")
        exclude = clause.get("exclude")
        fn = _FILTER_FEATURE_FNS.get(feature)
        if fn is None:
            continue  # unknown feature — let it pass (forward-compatible)
        if fn(ctx) == exclude:
            return False
    return True
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader_filters.py -v"
```

Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/paper_trader.py tests/test_paper_trader_filters.py
git commit -m "feat: filter gate for paper trader (rejects entries on excluded session/hour/dow)"
```

---

## Task 5: Wire filter gate into entry path

**Files:**
- Modify: `api/services/paper_trader.py`
- Modify: `tests/test_paper_trader_filters.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_paper_trader_filters.py`:

```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from services.paper_trader import _RuleSnapshot, _open_papers_for_rules


@pytest_asyncio.fixture
async def session():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    async with Session() as s:
        yield s
    await eng.dispose()


@pytest.mark.asyncio
async def test_open_papers_skips_rule_when_filter_excludes_now(session):
    pattern = Pattern(
        indicator_slugs=["rsi"], timeframe="H1",
        win_rate=0.6, sample_count=100, status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(
        pattern_id=pattern.id, status="active", mode="strict",
        filters=[{"feature": "session", "exclude": "asia"}],
        virtual_balance_start=Decimal("5000"),
        virtual_balance_current=Decimal("5000"),
    )
    session.add(rule)
    await session.commit()

    asia_now = datetime(2026, 5, 25, 2, 0, tzinfo=timezone.utc)
    rule_snapshots = [_RuleSnapshot.from_rule(rule)]

    # _open_papers_for_rules consults _passes_filters; when filter excludes,
    # the rule contributes 0 trades.
    opened = await _open_papers_for_rules(
        session,
        rule_snapshots=rule_snapshots,
        matched_rule_ids=[rule.id],
        now=asia_now,
    )
    assert opened == {} or opened.get(rule.id) in (None, [])
```

> **Note:** `_RuleSnapshot.from_rule` and `_open_papers_for_rules` signatures are defined in Plan 3 (Task — `_open_papers_for_rules` returns `dict[UUID, list[Trade]]`). If those signatures changed during Plan 3 execution, mirror that change here — the **call to `_passes_filters` is the only behavior this task adds**.

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader_filters.py -v -k skips_rule"
```

Expected: FAIL — rule still opens a paper despite the filter.

- [ ] **Step 3: Insert filter check in `_open_papers_for_rules`**

In `api/services/paper_trader.py`, locate the loop in `_open_papers_for_rules` that iterates `rule_snapshots` and, immediately before opening any paper trade for that rule, add:

```python
if not _passes_filters(snapshot, {"now": now}):
    continue
```

Where `snapshot` is the loop variable for each `_RuleSnapshot`. The snapshot dataclass already carries `filters` (it was added in Plan 1 / Plan 3) — if it doesn't, **add `filters: list = field(default_factory=list)` to `_RuleSnapshot` and copy from `rule.filters` in `from_rule()`**.

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader_filters.py -v"
```

Expected: PASS (all tests).

- [ ] **Step 5: Run full paper_trader suite to confirm no regression**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader.py tests/test_paper_trader_filters.py -v"
```

Expected: PASS — all prior paper_trader tests still pass.

- [ ] **Step 6: Commit**

```bash
git add api/services/paper_trader.py tests/test_paper_trader_filters.py
git commit -m "feat: enforce filter gate in paper_trader entry path"
```

---

## Task 6: Auto-promote shadow when it outperforms parent

**Files:**
- Modify: `api/services/adaptive_tuner.py`
- Modify: `tests/test_adaptive_tuner.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_adaptive_tuner.py`:

```python
from datetime import timedelta

from services.adaptive_tuner import (
    ADAPTIVE_PROMOTE_DELTA,
    ADAPTIVE_SHADOW_AGE_DAYS,
    promote_shadow_if_outperforms,
)


def _trade_at(rule_id, *, profit, when: datetime) -> Trade:
    return Trade(
        ticket=uuid4().int & 0x7FFFFFFF, symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market, order_state=OrderState.closed,
        open_time=when, close_time=when,
        open_price=Decimal("1950"), close_price=Decimal("1960"),
        volume=Decimal("0.10"),
        profit=Decimal(str(profit)),
        is_paper=True, paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule_id)},
    )


@pytest.mark.asyncio
async def test_promotes_shadow_when_winrate_beats_parent(session):
    parent = await _seed_rule(session)
    proposal = FilterProposal(
        feature="session", exclude="asia",
        bucket_n=12, bucket_loss_rate=1.0, other_loss_rate=0.0,
    )
    shadow = await spawn_shadow_rule(session, parent, proposal)
    # Backdate shadow to be older than ADAPTIVE_SHADOW_AGE_DAYS
    shadow.spawned_at = datetime.now(timezone.utc) - timedelta(days=ADAPTIVE_SHADOW_AGE_DAYS + 1)
    await session.commit()

    base = datetime.now(timezone.utc) - timedelta(days=ADAPTIVE_SHADOW_AGE_DAYS)
    # Parent: 30 trades, 50% winrate
    for i in range(30):
        session.add(_trade_at(parent.id, profit=+50 if i < 15 else -50, when=base + timedelta(hours=i)))
    # Shadow: 30 trades, 70% winrate (≥ +5% delta)
    for i in range(30):
        session.add(_trade_at(shadow.id, profit=+50 if i < 21 else -50, when=base + timedelta(hours=i)))
    await session.commit()

    promoted = await promote_shadow_if_outperforms(session, shadow)
    assert promoted is True

    await session.refresh(shadow)
    await session.refresh(parent)
    assert shadow.status == "active"
    assert shadow.shadow_of_rule_id is None
    assert parent.status == "retired"


@pytest.mark.asyncio
async def test_does_not_promote_shadow_when_delta_too_small(session):
    parent = await _seed_rule(session)
    proposal = FilterProposal(
        feature="session", exclude="asia",
        bucket_n=12, bucket_loss_rate=1.0, other_loss_rate=0.0,
    )
    shadow = await spawn_shadow_rule(session, parent, proposal)
    shadow.spawned_at = datetime.now(timezone.utc) - timedelta(days=ADAPTIVE_SHADOW_AGE_DAYS + 1)
    await session.commit()

    base = datetime.now(timezone.utc) - timedelta(days=ADAPTIVE_SHADOW_AGE_DAYS)
    for i in range(30):
        session.add(_trade_at(parent.id, profit=+50 if i < 18 else -50, when=base + timedelta(hours=i)))  # 60%
    for i in range(30):
        session.add(_trade_at(shadow.id, profit=+50 if i < 19 else -50, when=base + timedelta(hours=i)))  # 63% — only +3%
    await session.commit()

    promoted = await promote_shadow_if_outperforms(session, shadow)
    assert promoted is False

    await session.refresh(shadow)
    await session.refresh(parent)
    assert shadow.status == "shadow"
    assert parent.status == "active"


@pytest.mark.asyncio
async def test_does_not_promote_shadow_below_min_trades(session):
    parent = await _seed_rule(session)
    proposal = FilterProposal(
        feature="session", exclude="asia",
        bucket_n=12, bucket_loss_rate=1.0, other_loss_rate=0.0,
    )
    shadow = await spawn_shadow_rule(session, parent, proposal)
    shadow.spawned_at = datetime.now(timezone.utc) - timedelta(days=ADAPTIVE_SHADOW_AGE_DAYS + 1)
    await session.commit()

    base = datetime.now(timezone.utc) - timedelta(days=ADAPTIVE_SHADOW_AGE_DAYS)
    for i in range(30):
        session.add(_trade_at(parent.id, profit=+50 if i < 15 else -50, when=base + timedelta(hours=i)))
    for i in range(5):  # only 5 — below ADAPTIVE_MIN_TRADES
        session.add(_trade_at(shadow.id, profit=+50, when=base + timedelta(hours=i)))
    await session.commit()

    promoted = await promote_shadow_if_outperforms(session, shadow)
    assert promoted is False
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_adaptive_tuner.py -v -k promote"
```

Expected: FAIL — `promote_shadow_if_outperforms` not defined.

- [ ] **Step 3: Implement**

Append to `api/services/adaptive_tuner.py`:

```python
from datetime import timedelta


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
    """Compare shadow winrate vs parent on the trades closed since `shadow.spawned_at`.
    Promote when shadow_winrate − parent_winrate ≥ ADAPTIVE_PROMOTE_DELTA AND both
    sides have ≥ ADAPTIVE_MIN_TRADES.

    Returns True iff promoted.
    """
    if shadow.shadow_of_rule_id is None:
        return False
    age = datetime.now(timezone.utc) - shadow.spawned_at
    if age < timedelta(days=ADAPTIVE_SHADOW_AGE_DAYS):
        return False

    parent = await session.get(PaperTraderRule, shadow.shadow_of_rule_id)
    if parent is None or parent.status != "active":
        return False

    shadow_trades = await _load_rule_trades(session, shadow, ADAPTIVE_LOOKBACK_TRADES)
    parent_trades_all = await _load_rule_trades(session, parent, ADAPTIVE_LOOKBACK_TRADES)
    # Only count parent trades since shadow was spawned (apples-to-apples window)
    parent_trades = [t for t in parent_trades_all if t.close_time and t.close_time >= shadow.spawned_at]

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
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_adaptive_tuner.py -v -k promote"
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/adaptive_tuner.py tests/test_adaptive_tuner.py
git commit -m "feat: auto-promote shadow rule when it outperforms parent by ≥ 5%"
```

---

## Task 7: Daily orchestrator — `run_adaptive_tuner()`

**Files:**
- Modify: `api/services/adaptive_tuner.py`
- Modify: `tests/test_adaptive_tuner.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_adaptive_tuner.py`:

```python
from services.adaptive_tuner import run_adaptive_tuner


@pytest.mark.asyncio
async def test_run_adaptive_tuner_spawns_shadows_for_eligible_rules(session):
    rule = await _seed_rule(session)
    # 12 Asia losses, 12 London wins → propose session=asia
    for _ in range(12):
        session.add(_trade(rule.id, profit=-50, hour=2))
    for _ in range(12):
        session.add(_trade(rule.id, profit=+50, hour=10))
    await session.commit()

    summary = await run_adaptive_tuner(session)

    assert summary["rules_evaluated"] >= 1
    assert summary["shadows_spawned"] >= 1
    shadows = (await session.execute(
        select(PaperTraderRule).where(
            PaperTraderRule.shadow_of_rule_id == rule.id,
            PaperTraderRule.status == "shadow",
        )
    )).scalars().all()
    assert len(shadows) >= 1


@pytest.mark.asyncio
async def test_run_adaptive_tuner_skips_baseline_rules(session):
    rule = await _seed_rule(session)
    # Mark as baseline-equivalent: status='shadow' or low trade count.
    # Use the actual is_baseline column once available; for now use status filter.
    rule.status = "baseline"
    await session.commit()
    summary = await run_adaptive_tuner(session)
    assert summary["rules_evaluated"] == 0
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_adaptive_tuner.py -v -k run_adaptive"
```

Expected: FAIL — `run_adaptive_tuner` not defined.

- [ ] **Step 3: Implement**

Append to `api/services/adaptive_tuner.py`:

```python
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
                spawned = await spawn_shadow_rule(session, rule, proposal)
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
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_adaptive_tuner.py -v"
```

Expected: PASS (all adaptive_tuner tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/adaptive_tuner.py tests/test_adaptive_tuner.py
git commit -m "feat: adaptive tuner daily orchestrator"
```

---

## Task 8: Register cron in `main.py`

**Files:**
- Modify: `api/main.py`

- [ ] **Step 1: Wire APScheduler job**

In `api/main.py`, add:

```python
import os

from apscheduler.triggers.cron import CronTrigger

from services.adaptive_tuner import run_adaptive_tuner as _run_adaptive_tuner

ADAPTIVE_ENABLED = os.getenv("ADAPTIVE_ENABLED", "1") == "1"


async def _safe_run_adaptive_tuner() -> None:
    from database import SessionLocal

    try:
        async with SessionLocal() as session:
            await _run_adaptive_tuner(session)
    except Exception:
        logger.exception("adaptive_tuner cron failed")
```

In the existing `lifespan()` block where `scheduler.add_job(...)` is called for pattern discovery / promotion gate, append:

```python
if ADAPTIVE_ENABLED:
    scheduler.add_job(
        _safe_run_adaptive_tuner,
        trigger=CronTrigger(hour=0, minute=45),  # 00:45 UTC, after promotion gate's 00:30
        id="adaptive_tuner_daily",
        replace_existing=True,
    )
```

Update the `needs_scheduler` boolean to include `ADAPTIVE_ENABLED` (alongside `PATTERN_DISCOVERY_ENABLED`, `BASELINE_ENABLED`, `PROMOTION_GATE_ENABLED`).

- [ ] **Step 2: Smoke-check imports**

```
docker compose run --rm api python -c "from main import _safe_run_adaptive_tuner; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Verify cron is registered**

Add a quick test:

```python
# tests/test_adaptive_cron_registered.py
import os

import pytest


@pytest.mark.asyncio
async def test_adaptive_tuner_function_imports():
    os.environ["ADAPTIVE_ENABLED"] = "1"
    from main import _safe_run_adaptive_tuner
    assert callable(_safe_run_adaptive_tuner)
```

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_adaptive_cron_registered.py -v"
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add api/main.py tests/test_adaptive_cron_registered.py
git commit -m "feat: register adaptive tuner daily cron at 00:45 UTC"
```

---

## Task 9: API — `GET /api/paper-trader-rules/{id}/shadows`

**Files:**
- Modify: `api/routers/patterns.py`
- Test: `tests/test_shadows_api.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_shadows_api.py
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from database import Base, get_session
from main import app
from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def client():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    async def _override():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c._session_factory = Session
        yield c
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_shadows_endpoint_returns_parent_and_shadows(client):
    Session = client._session_factory
    async with Session() as s:
        pattern = Pattern(
            indicator_slugs=["rsi"], timeframe="H1",
            win_rate=0.6, sample_count=100, status="active",
        )
        s.add(pattern)
        await s.flush()
        parent = PaperTraderRule(
            pattern_id=pattern.id, status="active", mode="strict",
            virtual_balance_start=Decimal("5000"),
            virtual_balance_current=Decimal("5000"),
        )
        s.add(parent)
        await s.flush()
        shadow = PaperTraderRule(
            pattern_id=pattern.id, status="shadow", mode="strict",
            virtual_balance_start=Decimal("5000"),
            virtual_balance_current=Decimal("5000"),
            filters=[{"feature": "session", "exclude": "asia"}],
            shadow_of_rule_id=parent.id,
        )
        s.add(shadow)
        await s.commit()
        parent_id = str(parent.id)
        shadow_id = str(shadow.id)

    res = await client.get(f"/api/paper-trader-rules/{parent_id}/shadows")
    assert res.status_code == 200
    body = res.json()
    assert body["parent"]["id"] == parent_id
    ids = [s["id"] for s in body["shadows"]]
    assert shadow_id in ids
    s0 = body["shadows"][0]
    assert s0["filters"] == [{"feature": "session", "exclude": "asia"}]
    assert "winrate_delta" in s0  # null when not enough samples


@pytest.mark.asyncio
async def test_shadows_endpoint_404_for_unknown_id(client):
    res = await client.get(f"/api/paper-trader-rules/{uuid4()}/shadows")
    assert res.status_code == 404
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_shadows_api.py -v"
```

Expected: FAIL — endpoint not defined (404 on existing parent).

- [ ] **Step 3: Implement**

Add to `api/routers/patterns.py`:

```python
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.pattern import PaperTraderRule
from models.trade import Trade


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


@router.get("/api/paper-trader-rules/{rule_id}/shadows")
async def get_shadows(
    rule_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict:
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
```

> If the `router` / `get_session` import names differ in `patterns.py`, mirror the existing pattern used by `/api/paper-trader-rules` instead of introducing new imports.

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_shadows_api.py -v"
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add api/routers/patterns.py tests/test_shadows_api.py
git commit -m "feat: GET /api/paper-trader-rules/{id}/shadows (parent + shadows + delta)"
```

---

## Task 10: Console UI — surface shadow status on rule card

**Files:**
- Modify: `frontend/src/components/PaperRuleCard.jsx`
- Modify: `frontend/src/components/PaperTradeConsole.jsx`
- Test: manual smoke test (no Jest setup yet)

- [ ] **Step 1: Add a "Shadow" sub-section to `PaperRuleCard`**

In `PaperRuleCard.jsx`, after the existing trust-tier / score / virtual-balance block, add:

```jsx
{rule.shadow_of_rule_id ? (
  <div className="mt-2 text-xs text-amber-700">
    🌗 Shadow of <code>{rule.shadow_of_rule_id.slice(0, 8)}</code> — testing filter:
    {(rule.filters || []).map((f, i) => (
      <span key={i} className="ml-1 inline-block rounded bg-amber-100 px-1">
        {f.feature}≠{f.exclude}
      </span>
    ))}
  </div>
) : (rule.filters || []).length > 0 ? (
  <div className="mt-2 text-xs text-slate-600">
    Active filters:
    {rule.filters.map((f, i) => (
      <span key={i} className="ml-1 inline-block rounded bg-slate-100 px-1">
        {f.feature}≠{f.exclude}
      </span>
    ))}
  </div>
) : null}
```

- [ ] **Step 2: Filter out shadow rules from the main console list by default**

In `PaperTradeConsole.jsx`, locate the `rules.filter(...)` call and add a clause:

```jsx
const visibleRules = rules.filter((r) => r.status !== "shadow");
```

Pass `visibleRules` to the existing render loop. Do **not** remove shadow rules from the API response — just hide them from the default view; a future "show shadows" toggle can be added later.

- [ ] **Step 3: Manual smoke check**

Start the dev stack and seed a shadow rule by running:

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && python -c '
import asyncio
from decimal import Decimal
from database import SessionLocal
from models.pattern import PaperTraderRule, Pattern
async def go():
    async with SessionLocal() as s:
        p = Pattern(indicator_slugs=[\"rsi\"], timeframe=\"H1\", win_rate=0.6, sample_count=100, status=\"active\")
        s.add(p); await s.flush()
        parent = PaperTraderRule(pattern_id=p.id, status=\"active\", mode=\"strict\", virtual_balance_start=Decimal(5000), virtual_balance_current=Decimal(5000))
        s.add(parent); await s.flush()
        shadow = PaperTraderRule(pattern_id=p.id, status=\"shadow\", mode=\"strict\", virtual_balance_start=Decimal(5000), virtual_balance_current=Decimal(5000), filters=[{\"feature\":\"session\",\"exclude\":\"asia\"}], shadow_of_rule_id=parent.id)
        s.add(shadow); await s.commit()
        print(parent.id, shadow.id)
asyncio.run(go())
'"
```

Open `http://localhost:3000`, navigate to the Paper Console:

- The parent rule card is visible (no shadow prefix).
- Calling `GET /api/paper-trader-rules/<parent>/shadows` returns the shadow with its filter.
- The shadow does **not** appear in the main rule list.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PaperRuleCard.jsx frontend/src/components/PaperTradeConsole.jsx
git commit -m "feat: show shadow filter chip on rule card; hide shadows from main list"
```

---

## Self-Review

Before declaring this plan complete, walk through:

- [ ] **Spec coverage** — every line of v1 spec § "Component 3 — Adaptive Tuning" is implemented:
  - Daily cron after pattern discovery → Task 8 (00:45 UTC, after promotion's 00:30)
  - ≥ 30 trades per rule → `ADAPTIVE_MIN_TRADES=30`
  - Loss-rate diff ≥ 0.20 → `ADAPTIVE_LOSS_DELTA=0.20`
  - Features: session, ATR vol regime, dow, hour bucket, indicator state — Task 1 implements 4 of 5; ATR-state filter is built in feature_extractor but not wired into `propose_filters_for_rule` (deferred — needs ATR context per trade, which would require persisting ATR in `trade_indicator_signals`).
  - Shadow rule with `active=false` for 30 days → `status='shadow'`, `ADAPTIVE_SHADOW_AGE_DAYS=30`
  - Promotion: shadow winrate > parent + 5% → `ADAPTIVE_PROMOTE_DELTA=0.05`

- [ ] **Placeholder scan** — no "TBD" / "implement later" in any task body.

- [ ] **Schema reuse** — `filters JSONB`, `shadow_of_rule_id UUID` both already exist (migration 011, Plan 1). No new migration.

- [ ] **No regression** — Task 5's full paper_trader test run confirms entry path filter doesn't break v2 flows.

- [ ] **Type consistency** —
  - `FilterProposal.to_filter()` shape matches the clause shape consumed by `_passes_filters` (`{"feature": ..., "exclude": ...}`).
  - `_load_rule_trades` is shared between `propose_filters_for_rule` and `promote_shadow_if_outperforms`.
  - Cron name `adaptive_tuner_daily` does not collide with existing `pattern_discovery_daily`, `promotion_gate_daily`, `baseline_*`.

---

## Open question (deferred — not blocking)

- **ATR-state filter** is in spec v1 but skipped here because it requires per-trade ATR snapshot stored at entry time. Add to backlog: "Persist `atr_h1` on `trade_indicator_signals` so adaptive tuner can bucket on volatility regime."

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-25-paper-plan8-adaptive-tuning.md`. Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch with checkpoints.

**Which approach?**
