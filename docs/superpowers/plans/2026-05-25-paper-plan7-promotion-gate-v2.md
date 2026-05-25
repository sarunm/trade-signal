# Plan 7 — Promotion Gate v2 (Wilson + EV + Baseline) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-25-paper-trade-system-redesign-v2.md` § "Cost-aware Promotion Gates" + § "Trust tier (4-badge UI)"

**Goal:** Replace v1's raw-winrate gate with a 4-gate pipeline that requires (1) sample sufficiency `total_trades ≥ 100`, (2) **performance** = Wilson 95% lower bound ≥ 0.55 + net EV/trade ≥ ฿20 + outperforms baseline by ≥ 5%, (3) stability = 7 consecutive days passing, (4) walk-forward = passes on held-out window. Persist `trust_tier` ∈ `{experimental, validated, live_proven, ea_candidate}` per rule. Cron writes `wilson_lower_95`, `net_ev_per_trade`, `baseline_delta` for the UI.

**Architecture:**
- Migration 016 adds `trust_tier`, `is_baseline`, `spawn_strategy`, `net_ev_per_trade`, `wilson_lower_95`, `baseline_delta` columns to `paper_trader_rules`.
- New `statistics.py` — pure-arithmetic helpers: `wilson_lower(p, n, z=1.96)`, `net_ev(trades, cost) -> Decimal`, `profit_factor(trades) -> Decimal`.
- New `promotion_gate.py` — `evaluate_rule(session, rule) -> GateResult` runs all 4 gates and returns the resulting trust tier.
- New `trust_tier.py` — pure mapping `compute_trust_tier(gate_result) -> str`.
- A cron in `main.py` runs `evaluate_all_active_rules()` daily (00:30 UTC, after pattern discovery's 00:00 cron). It persists tier + cached stats columns and bumps `consecutive_stable_days` when Gate 2 passes again.
- New `/api/patterns/{id}/gates` returns the gate breakdown for UI inspection.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, FastAPI, APScheduler, pytest-asyncio + httpx.

---

## File Structure

| Path | Action | Purpose |
|------|--------|---------|
| `api/alembic/versions/016_v2_promotion_columns.py` | create | Adds tier + cached stat columns |
| `api/models/pattern.py` | modify | Add new columns to `PaperTraderRule` |
| `api/services/statistics.py` | create | Wilson + EV + profit factor helpers |
| `api/services/promotion_gate.py` | create | 4-gate orchestration |
| `api/services/trust_tier.py` | create | Gate result → tier name |
| `api/routers/patterns.py` | modify | New `/api/patterns/{id}/gates` route |
| `api/main.py` | modify | Daily cron `_safe_run_promotion_gate()` |
| `tests/test_migration_016.py` | create | Verifies columns |
| `tests/test_statistics.py` | create | Wilson + EV unit tests |
| `tests/test_promotion_gate.py` | create | Gate logic + integration |
| `tests/test_trust_tier.py` | create | Tier mapping |

---

## Task 1: Migration 016 — promotion columns

**Files:**
- Create: `api/alembic/versions/016_v2_promotion_columns.py`
- Modify: `api/models/pattern.py`
- Test: `tests/test_migration_016.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_migration_016.py
import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_paper_trader_rules_has_v2_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("paper_trader_rules")}
        )
    expected = {
        "trust_tier", "is_baseline", "spawn_strategy",
        "net_ev_per_trade", "wilson_lower_95", "baseline_delta",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_migration_016.py -v"
```

Expected: FAIL — columns missing.

- [ ] **Step 3: Write the migration**

```python
# api/alembic/versions/016_v2_promotion_columns.py
"""v2 promotion columns — trust tier + cached stats"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    additions = [
        ("trust_tier", sa.String(20), "experimental"),
        ("is_baseline", sa.Boolean(), "false"),
        ("spawn_strategy", sa.String(40), None),
        ("net_ev_per_trade", sa.Numeric(10, 2), None),
        ("wilson_lower_95", sa.Numeric(5, 4), None),
        ("baseline_delta", sa.Numeric(5, 4), None),
    ]
    for name, col_type, default in additions:
        if name in cols:
            continue
        kwargs = {"nullable": True}
        if default is not None:
            kwargs["server_default"] = default
        op.add_column("paper_trader_rules", sa.Column(name, col_type, **kwargs))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    for name in [
        "baseline_delta", "wilson_lower_95", "net_ev_per_trade",
        "spawn_strategy", "is_baseline", "trust_tier",
    ]:
        if name in cols:
            op.drop_column("paper_trader_rules", name)
```

- [ ] **Step 4: Mirror columns into the ORM**

Update `api/models/pattern.py` `PaperTraderRule`:

```python
    trust_tier: Mapped[str] = mapped_column(String(20), default="experimental")
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    spawn_strategy: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    net_ev_per_trade: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    wilson_lower_95: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    baseline_delta: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4), nullable=True
    )
```

Imports:

```python
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String
from decimal import Decimal
```

- [ ] **Step 5: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_migration_016.py -v"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/alembic/versions/016_v2_promotion_columns.py \
        api/models/pattern.py tests/test_migration_016.py
git commit -m "feat: migration 016 — v2 promotion gate columns"
```

---

## Task 2: Statistics helpers — Wilson + net EV + profit factor

**Files:**
- Create: `api/services/statistics.py`
- Test: `tests/test_statistics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_statistics.py
from decimal import Decimal

import pytest

from services.statistics import (
    net_ev,
    profit_factor,
    wilson_lower,
)


def test_wilson_lower_balanced_30():
    # 50% winrate over 30 trades — lower bound around 0.33
    assert 0.30 < wilson_lower(0.5, 30) < 0.40


def test_wilson_lower_high_winrate_small_sample():
    # 80% over 10 trades — wider band, lower around 0.49
    assert 0.45 < wilson_lower(0.8, 10) < 0.55


def test_wilson_lower_high_winrate_large_sample():
    # 80% over 200 trades — tighter band, lower above 0.74
    assert wilson_lower(0.8, 200) > 0.74


def test_wilson_lower_zero_n_returns_zero():
    assert wilson_lower(0.5, 0) == 0.0


def test_wilson_lower_clamped():
    # Edge: p=1.0 should return < 1.0 due to CI lower bound
    assert wilson_lower(1.0, 100) < 1.0


def test_net_ev_basic():
    # 5 trades summing to ฿250 minus ฿50 cost across all = ฿200 / 5 = ฿40
    profits = [Decimal("100"), Decimal("-50"), Decimal("150"), Decimal("-50"), Decimal("100")]
    assert net_ev(profits, total_cost=Decimal("50")) == Decimal("40.00")


def test_net_ev_zero_trades():
    assert net_ev([], total_cost=Decimal("0")) == Decimal("0.00")


def test_profit_factor_2_to_1():
    profits = [Decimal("200"), Decimal("-100")]
    assert profit_factor(profits) == Decimal("2.0000")


def test_profit_factor_no_losses_returns_inf():
    profits = [Decimal("200"), Decimal("100")]
    assert profit_factor(profits) > Decimal("999")


def test_profit_factor_no_wins_returns_zero():
    profits = [Decimal("-100"), Decimal("-50")]
    assert profit_factor(profits) == Decimal("0.0000")
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_statistics.py -v"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `statistics.py`**

```python
# api/services/statistics.py
import math
from decimal import Decimal
from typing import Sequence


WILSON_Z_95 = 1.96


def wilson_lower(p: float, n: int, z: float = WILSON_Z_95) -> float:
    """Wilson score interval lower bound for a proportion.

    Returns 0.0 if n == 0. Always clamped to [0.0, 1.0].
    """
    if n <= 0:
        return 0.0
    p = max(0.0, min(1.0, p))
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    lower = (centre - margin) / denom
    return max(0.0, min(1.0, lower))


def net_ev(profits: Sequence[Decimal], total_cost: Decimal) -> Decimal:
    """Net expected value per trade after subtracting total cost."""
    if not profits:
        return Decimal("0.00")
    gross = sum(profits, Decimal("0"))
    net = gross - total_cost
    return (net / Decimal(len(profits))).quantize(Decimal("0.01"))


def profit_factor(profits: Sequence[Decimal]) -> Decimal:
    """Sum of wins / |sum of losses|. ∞ when no losses, 0 when no wins."""
    wins = sum((p for p in profits if p > 0), Decimal("0"))
    losses = sum((p for p in profits if p < 0), Decimal("0"))
    if losses == 0:
        return Decimal("9999.0000") if wins > 0 else Decimal("0.0000")
    return (wins / abs(losses)).quantize(Decimal("0.0001"))
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_statistics.py -v"
```

Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/statistics.py tests/test_statistics.py
git commit -m "feat: Wilson lower CI + net EV + profit factor helpers"
```

---

## Task 3: Trust tier mapping

**Files:**
- Create: `api/services/trust_tier.py`
- Test: `tests/test_trust_tier.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_trust_tier.py
from services.trust_tier import (
    TIER_EA_CANDIDATE,
    TIER_EXPERIMENTAL,
    TIER_LIVE_PROVEN,
    TIER_VALIDATED,
    GateOutcomes,
    compute_trust_tier,
)


def test_experimental_when_no_gate_passed():
    g = GateOutcomes(sample=False, performance=False, stability=False, walk_forward=False)
    assert compute_trust_tier(g) == TIER_EXPERIMENTAL


def test_experimental_when_only_sample_passes():
    g = GateOutcomes(sample=True, performance=False, stability=False, walk_forward=False)
    assert compute_trust_tier(g) == TIER_EXPERIMENTAL


def test_validated_when_sample_and_performance_pass():
    g = GateOutcomes(sample=True, performance=True, stability=False, walk_forward=False)
    assert compute_trust_tier(g) == TIER_VALIDATED


def test_live_proven_when_stability_also_passes():
    g = GateOutcomes(sample=True, performance=True, stability=True, walk_forward=False)
    assert compute_trust_tier(g) == TIER_LIVE_PROVEN


def test_ea_candidate_when_all_pass():
    g = GateOutcomes(sample=True, performance=True, stability=True, walk_forward=True)
    assert compute_trust_tier(g) == TIER_EA_CANDIDATE


def test_walk_forward_alone_does_not_promote():
    g = GateOutcomes(sample=True, performance=False, stability=False, walk_forward=True)
    assert compute_trust_tier(g) == TIER_EXPERIMENTAL
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_trust_tier.py -v"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `trust_tier.py`**

```python
# api/services/trust_tier.py
from dataclasses import dataclass


TIER_EXPERIMENTAL = "experimental"
TIER_VALIDATED = "validated"
TIER_LIVE_PROVEN = "live_proven"
TIER_EA_CANDIDATE = "ea_candidate"


@dataclass
class GateOutcomes:
    sample: bool          # Gate 1 — sufficient sample
    performance: bool     # Gate 2 — Wilson + EV + baseline
    stability: bool       # Gate 3 — N consecutive stable days
    walk_forward: bool    # Gate 4 — passes on held-out window


def compute_trust_tier(outcomes: GateOutcomes) -> str:
    if outcomes.sample and outcomes.performance and outcomes.stability and outcomes.walk_forward:
        return TIER_EA_CANDIDATE
    if outcomes.sample and outcomes.performance and outcomes.stability:
        return TIER_LIVE_PROVEN
    if outcomes.sample and outcomes.performance:
        return TIER_VALIDATED
    return TIER_EXPERIMENTAL
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_trust_tier.py -v"
```

Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/trust_tier.py tests/test_trust_tier.py
git commit -m "feat: trust tier mapping from gate outcomes"
```

---

## Task 4: Promotion gate — Gate 1 (sample sufficiency)

**Files:**
- Create: `api/services/promotion_gate.py`
- Test: `tests/test_promotion_gate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_promotion_gate.py
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.promotion_gate import (
    PROMOTION_MIN_TRADES,
    GateResult,
    evaluate_rule,
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


async def _seed_rule(session, total_trades=0, win_count=0) -> PaperTraderRule:
    pattern = Pattern(
        indicator_slugs=["rsi_14", "ema_50"], timeframe="H1",
        win_rate=0.6, sample_count=20, status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(
        pattern_id=pattern.id, status="active", mode="basket_5k",
        total_trades=total_trades, win_count=win_count,
    )
    session.add(rule)
    await session.commit()
    return rule


@pytest.mark.asyncio
async def test_sample_gate_fails_below_threshold(session):
    rule = await _seed_rule(session, total_trades=PROMOTION_MIN_TRADES - 1)
    result = await evaluate_rule(session, rule)
    assert result.gates.sample is False
    assert result.tier == "experimental"


@pytest.mark.asyncio
async def test_sample_gate_passes_at_threshold(session):
    rule = await _seed_rule(session, total_trades=PROMOTION_MIN_TRADES, win_count=70)
    result = await evaluate_rule(session, rule)
    assert result.gates.sample is True
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_promotion_gate.py -v -k sample_gate"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement skeleton + Gate 1**

```python
# api/services/promotion_gate.py
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models.pattern import PaperTraderRule, Pattern
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


async def evaluate_rule(
    session: AsyncSession, rule: PaperTraderRule
) -> GateResult:
    """Run all 4 gates against a single rule. Persists tier + cached stats."""
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
    return result  # later gates appended in subsequent tasks


async def _persist(
    session: AsyncSession, rule: PaperTraderRule, result: GateResult
) -> None:
    rule.trust_tier = result.tier
    rule.wilson_lower_95 = Decimal(str(round(result.wilson_lower, 4)))
    rule.net_ev_per_trade = result.net_ev
    rule.baseline_delta = Decimal(str(round(result.baseline_delta, 4)))
    await session.commit()
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_promotion_gate.py -v -k sample_gate"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/promotion_gate.py tests/test_promotion_gate.py
git commit -m "feat: promotion gate skeleton + Gate 1 (sample sufficiency)"
```

---

## Task 5: Promotion gate — Gate 2 (Wilson + net EV + baseline delta)

**Files:**
- Modify: `api/services/promotion_gate.py`
- Modify: `tests/test_promotion_gate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_promotion_gate.py`:

```python
async def _seed_baseline_with_winrate(session, winrate: float, trades: int = 50):
    from services.baseline_runner import ensure_baseline_rule
    base = datetime.now(timezone.utc) - timedelta(days=10)
    rule = await ensure_baseline_rule(session)
    for i in range(trades):
        is_win = (i / trades) < winrate
        session.add(Trade(
            ticket=10_000 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_type=OrderType.market, order_state=OrderState.filled,
            open_time=base + timedelta(hours=i),
            close_time=base + timedelta(hours=i, minutes=30),
            open_price=Decimal("1950"),
            close_price=Decimal("1955" if is_win else "1945"),
            volume=Decimal("0.10"),
            profit=Decimal("100" if is_win else "-100"),
            is_paper=True, paper_mode=PaperMode.independent,
            recovery_plan={"paper_trader_rule_id": str(rule.id), "is_baseline": True},
        ))
    await session.commit()


async def _seed_paper_history(session, rule_id, total: int, winrate: float, profit_each_win=Decimal("100"), profit_each_loss=Decimal("-50")):
    base = datetime.now(timezone.utc) - timedelta(days=10)
    for i in range(total):
        is_win = (i / total) < winrate
        session.add(Trade(
            ticket=20_000 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_type=OrderType.market, order_state=OrderState.filled,
            open_time=base + timedelta(hours=i),
            close_time=base + timedelta(hours=i, minutes=30),
            open_price=Decimal("1950"),
            close_price=Decimal("1955" if is_win else "1945"),
            volume=Decimal("0.10"),
            profit=profit_each_win if is_win else profit_each_loss,
            is_paper=True, paper_mode=PaperMode.independent,
            recovery_plan={"paper_trader_rule_id": str(rule_id)},
        ))
    await session.commit()


@pytest.mark.asyncio
async def test_performance_gate_passes_with_strong_stats(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7)
    result = await evaluate_rule(session, rule)
    assert result.gates.performance is True
    assert result.tier == "validated"
    assert result.wilson_lower >= PROMOTION_MIN_WILSON_LOWER
    assert result.baseline_delta >= PROMOTION_MIN_BASELINE_DELTA


@pytest.mark.asyncio
async def test_performance_gate_fails_when_not_beating_baseline(session):
    await _seed_baseline_with_winrate(session, winrate=0.7)  # baseline strong
    rule = await _seed_rule(session, total_trades=100, win_count=72)  # only +2%
    await _seed_paper_history(session, rule.id, total=100, winrate=0.72)
    result = await evaluate_rule(session, rule)
    assert result.gates.performance is False
    assert "baseline" in result.reason


@pytest.mark.asyncio
async def test_performance_gate_fails_when_low_net_ev(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=60)
    # 60 wins x ฿1, 40 losses x -฿2 ⇒ gross = ฿60 - ฿80 = -฿20 (net EV negative)
    await _seed_paper_history(
        session, rule.id, total=100, winrate=0.6,
        profit_each_win=Decimal("1"), profit_each_loss=Decimal("-2"),
    )
    result = await evaluate_rule(session, rule)
    assert result.gates.performance is False
    assert "ev" in result.reason or "profit_factor" in result.reason
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_promotion_gate.py -v -k performance_gate"
```

Expected: FAIL — performance gate not implemented.

- [ ] **Step 3: Implement Gate 2 inside `evaluate_rule()`**

In `api/services/promotion_gate.py`:

```python
async def _load_paper_profits(
    session: AsyncSession, rule_id, days: int = 30
) -> list[Decimal]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_not(None),
            Trade.close_time >= cutoff,
        )
    )
    profits: list[Decimal] = []
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        if plan.get("paper_trader_rule_id") != str(rule_id):
            continue
        if trade.profit is not None:
            profits.append(trade.profit)
    return profits


async def _estimate_total_cost(
    session: AsyncSession, profits_count: int
) -> Decimal:
    # Plan 4 ships cost_model — soft-import to keep this file independent if not yet landed.
    try:
        from services.cost_model import estimate_cost_per_trade  # type: ignore
    except Exception:
        return Decimal("0.00") * Decimal(profits_count)
    per = await estimate_cost_per_trade(session)
    return Decimal(str(per)) * Decimal(profits_count)


async def _gate_performance(
    session: AsyncSession, rule: PaperTraderRule
) -> tuple[bool, str, dict]:
    from services.baseline_stats import get_baseline_winrate

    profits = await _load_paper_profits(session, rule.id)
    if not profits:
        return False, "no_recent_trades", {
            "wilson_lower": 0.0, "net_ev": Decimal("0.00"),
            "profit_factor": Decimal("0"), "baseline_delta": 0.0,
        }

    n = len(profits)
    wins = sum(1 for p in profits if p > 0)
    p_hat = wins / n
    w_low = wilson_lower(p_hat, n)
    cost = await _estimate_total_cost(session, n)
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

    reasons = []
    if w_low < PROMOTION_MIN_WILSON_LOWER:
        reasons.append("wilson")
    if ev < PROMOTION_MIN_NET_EV_THB:
        reasons.append("ev")
    if pf < PROMOTION_MIN_PROFIT_FACTOR_NET:
        reasons.append("profit_factor")
    if delta < PROMOTION_MIN_BASELINE_DELTA:
        reasons.append("baseline")
    return (not reasons), ",".join(reasons), metadata
```

Update `evaluate_rule()`:

```python
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
    if not perf_pass:
        result.reason = perf_reason
        result.tier = compute_trust_tier(gates)
        await _persist(session, rule, result)
        return result

    result.tier = compute_trust_tier(gates)
    return result
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_promotion_gate.py -v"
```

Expected: PASS for performance_gate tests.

- [ ] **Step 5: Commit**

```bash
git add api/services/promotion_gate.py tests/test_promotion_gate.py
git commit -m "feat: Gate 2 — Wilson + net EV + profit factor + baseline delta"
```

---

## Task 6: Promotion gate — Gate 3 (stability) + Gate 4 (walk-forward)

**Files:**
- Modify: `api/services/promotion_gate.py`
- Modify: `tests/test_promotion_gate.py`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_stability_gate_passes_at_threshold(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    rule.consecutive_stable_days_rule = PROMOTION_STABLE_DAYS  # via mapped attribute
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7)
    await session.commit()
    result = await evaluate_rule(session, rule)
    assert result.gates.stability is True
    assert result.tier in ("live_proven", "ea_candidate")


@pytest.mark.asyncio
async def test_stability_gate_fails_below_threshold(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    rule.consecutive_stable_days_rule = PROMOTION_STABLE_DAYS - 1
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7)
    await session.commit()
    result = await evaluate_rule(session, rule)
    assert result.gates.stability is False
    assert result.tier == "validated"


@pytest.mark.asyncio
async def test_walk_forward_passes_with_held_out_window(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    rule.consecutive_stable_days_rule = PROMOTION_STABLE_DAYS
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7)
    # Add a held-out window (last 14 days) with same strong winrate
    await _seed_paper_history(session, rule.id, total=30, winrate=0.7)
    await session.commit()
    result = await evaluate_rule(session, rule)
    assert result.gates.walk_forward is True
    assert result.tier == "ea_candidate"
```

- [ ] **Step 2: Implement Gate 3 + Gate 4**

In `api/services/promotion_gate.py`:

```python
async def _gate_stability(rule: PaperTraderRule) -> bool:
    return (rule.consecutive_stable_days_rule or 0) >= PROMOTION_STABLE_DAYS


async def _gate_walk_forward(
    session: AsyncSession, rule: PaperTraderRule
) -> bool:
    """Pass if the most recent WALK_FORWARD_WINDOW_DAYS slice also has Wilson ≥ 0.55."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=WALK_FORWARD_WINDOW_DAYS)
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_not(None),
            Trade.close_time >= cutoff,
        )
    )
    profits: list[Decimal] = []
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        if plan.get("paper_trader_rule_id") != str(rule.id):
            continue
        if trade.profit is not None:
            profits.append(trade.profit)
    if len(profits) < 20:  # need a minimum walk-forward sample
        return False
    wins = sum(1 for p in profits if p > 0)
    return wilson_lower(wins / len(profits), len(profits)) >= PROMOTION_MIN_WILSON_LOWER
```

Update `evaluate_rule()` after the performance check:

```python
    if perf_pass:
        gates.stability = await _gate_stability(rule)
        if gates.stability:
            gates.walk_forward = await _gate_walk_forward(session, rule)

    result.tier = compute_trust_tier(gates)
    await _persist(session, rule, result)
    return result
```

(Remove the now-redundant `_persist` call in the early-return performance fail branch — leave the single tail-call persist; ensure `_persist` is only called in fail/return branches that didn't already persist. Easiest: persist exactly once at the end. Restructure if needed.)

Cleaned-up version:

```python
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
    else:
        perf_pass, perf_reason, perf_meta = await _gate_performance(session, rule)
        gates.performance = perf_pass
        result.wilson_lower = perf_meta["wilson_lower"]
        result.net_ev = perf_meta["net_ev"]
        result.profit_factor = perf_meta["profit_factor"]
        result.baseline_delta = perf_meta["baseline_delta"]
        result.metadata.update(perf_meta)
        if not perf_pass:
            result.reason = perf_reason
        else:
            gates.stability = await _gate_stability(rule)
            if gates.stability:
                gates.walk_forward = await _gate_walk_forward(session, rule)

    result.tier = compute_trust_tier(gates)
    await _persist(session, rule, result)
    return result
```

- [ ] **Step 3: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_promotion_gate.py -v"
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add api/services/promotion_gate.py tests/test_promotion_gate.py
git commit -m "feat: Gate 3 (stability) + Gate 4 (walk-forward)"
```

---

## Task 7: Daily promotion cron + rule iteration

**Files:**
- Modify: `api/services/promotion_gate.py`
- Modify: `api/main.py`

- [ ] **Step 1: Add `evaluate_all_active_rules()`**

```python
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
            continue  # don't grade the benchmark
        try:
            results.append(await evaluate_rule(session, rule))
        except Exception:
            logger.exception("evaluate_rule failed for rule_id=%s", rule.id)
    return results
```

- [ ] **Step 2: Schedule cron in `api/main.py`**

```python
from services.promotion_gate import evaluate_all_active_rules

PROMOTION_GATE_ENABLED = os.getenv("PROMOTION_GATE_ENABLED", "1") == "1"


async def _safe_run_promotion_gate() -> None:
    try:
        results = await evaluate_all_active_rules()
        logger.info("promotion gate cron evaluated %d rules", len(results))
    except Exception:
        logger.exception("promotion gate cron failed")
```

Inside `lifespan()`:

```python
        if PROMOTION_GATE_ENABLED:
            scheduler.add_job(
                _safe_run_promotion_gate, "cron", hour=0, minute=30,
                id="promotion_gate_daily", replace_existing=True,
            )
```

And update `needs_scheduler` to include it:

```python
    needs_scheduler = (
        PATTERN_DISCOVERY_ENABLED or BASELINE_ENABLED or PROMOTION_GATE_ENABLED
    )
```

- [ ] **Step 3: Smoke test**

```
docker compose up -d
docker compose logs api --tail 20
```

Expect no scheduler exceptions.

```
docker compose down
```

- [ ] **Step 4: Commit**

```bash
git add api/services/promotion_gate.py api/main.py
git commit -m "feat: daily promotion gate cron over all non-baseline rules"
```

---

## Task 8: `/api/patterns/{id}/gates` endpoint

**Files:**
- Modify: `api/routers/patterns.py`
- Test: `tests/test_promotion_gate_api.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_promotion_gate_api.py
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base, get_session
from main import app
from models.pattern import PaperTraderRule, Pattern


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
    async with Session() as setup:
        pattern = Pattern(
            indicator_slugs=["a", "b"], timeframe="H1",
            win_rate=0.6, sample_count=20, status="active",
        )
        setup.add(pattern); await setup.flush()
        rule = PaperTraderRule(pattern_id=pattern.id, status="active",
                               mode="basket_5k", total_trades=50, win_count=30)
        setup.add(rule); await setup.commit()
        rule_id = rule.id
        pattern_id = pattern.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, pattern_id, rule_id

    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_pattern_gates_endpoint_returns_breakdown(client):
    c, pattern_id, _ = client
    res = await c.get(f"/api/patterns/{pattern_id}/gates")
    assert res.status_code == 200
    data = res.json()
    assert "rules" in data
    assert len(data["rules"]) == 1
    rule_summary = data["rules"][0]
    for key in ("rule_id", "tier", "gates", "wilson_lower", "net_ev",
                "profit_factor", "baseline_delta"):
        assert key in rule_summary
    assert set(rule_summary["gates"].keys()) == {
        "sample", "performance", "stability", "walk_forward",
    }
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_promotion_gate_api.py -v"
```

Expected: FAIL with 404.

- [ ] **Step 3: Add the endpoint to `api/routers/patterns.py`**

```python
from services.promotion_gate import evaluate_rule


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
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_promotion_gate_api.py -v"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routers/patterns.py tests/test_promotion_gate_api.py
git commit -m "feat: GET /api/patterns/{id}/gates breakdown"
```

---

## Task 9: Stability counter — auto-bump on performance pass

**Files:**
- Modify: `api/services/promotion_gate.py`
- Modify: `tests/test_promotion_gate.py`

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_stable_days_increments_when_performance_passes(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7)
    await session.commit()
    before = rule.consecutive_stable_days_rule
    await evaluate_rule(session, rule)
    await session.refresh(rule)
    assert rule.consecutive_stable_days_rule == (before or 0) + 1


@pytest.mark.asyncio
async def test_stable_days_resets_when_performance_fails(session):
    await _seed_baseline_with_winrate(session, winrate=0.7)
    rule = await _seed_rule(session, total_trades=100, win_count=72)
    rule.consecutive_stable_days_rule = 5
    await _seed_paper_history(session, rule.id, total=100, winrate=0.72)
    await session.commit()
    await evaluate_rule(session, rule)
    await session.refresh(rule)
    assert rule.consecutive_stable_days_rule == 0
```

- [ ] **Step 2: Add the bump logic** in `evaluate_rule()`

After `gates.performance` is determined:

```python
        if perf_pass:
            rule.consecutive_stable_days_rule = (rule.consecutive_stable_days_rule or 0) + 1
        else:
            rule.consecutive_stable_days_rule = 0
```

- [ ] **Step 3: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_promotion_gate.py -v -k stable_days"
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add api/services/promotion_gate.py tests/test_promotion_gate.py
git commit -m "feat: bump/reset consecutive_stable_days based on Gate 2"
```

---

## Task 10: Full regression

- [ ] **Step 1: Run all tests**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/ -v"
```

Expected: PASS — including all `test_promotion_gate*`, `test_statistics`, `test_trust_tier`, `test_migration_016`.

- [ ] **Step 2: Commit any test fixups**

```bash
git add -A tests/
git commit -m "test: regression sweep after promotion gate v2 rollout"
```

---

## Out of scope for this plan

- Adaptive shadow rules / filters / shadow_of_rule_id — Plan 8.
- UI for the gate breakdown drawer — pull `/api/patterns/{id}/gates` later when wiring the rule detail panel.
- Auto-deactivation of rules whose tier drops to `experimental` — keep them active; only the broadcaster + UI gate decides whether to noti.
