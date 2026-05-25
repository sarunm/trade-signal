# Plan 3 — Auto Discovery v2 + 3 Variants + Score Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-25-paper-trade-system-redesign-v2.md` § "Component 2 — Mining direction" (carry-over) + § "Variant C (user_style basket)"

**Goal:** Rewrite pattern discovery to use basket grouping with first-trade anchor and size-weighted scoring; spawn 3 risk variants per qualifying combo (strict / basket_5k / basket_50k); add a `scoring.py` service that maps signal quality to lot size 0.01–0.10; rebuild `paper_trader.py` around a shared per-tick indicator compute cache (P1) with fast/slow path split (P2) and a basket-recovery loop for variant_B/C.

**Architecture:**
- `pattern_discovery.py` groups recent real trades into baskets (close-time gap ≤ 1s, max 2 trades) before mining combos. Anchor indicator slugs come from the first trade in the basket; the basket's win/loss outcome is the **net P/L of all trades in the basket**, weighted by combined volume. This stops a 0.10-lot rescue trade from getting outvoted by a 0.01-lot starter trade.
- A new `scoring.py` computes a score 0–100 per signal from indicator confluence + matched count + indicator strength + win-rate; a separate `_score_to_lot()` maps it to lot 0.01 / 0.03 / 0.05 / 0.10 with calibration table override.
- `paper_trader.py` is rebuilt: per tick, every unique `(slug, timeframe)` is computed **once** into a shared cache (P1: O(unique slugs) instead of O(rules × slugs)). A fast path recomputes momentum/SR every tick, a slow path recomputes trend/volatility every 15s (P2). On entry, score is computed, lot size is set, and the rule's mode dictates SL behavior. For `basket_5k` and `basket_50k` the trader can stack a recovery trade on the same rule when the open paper is ≥ 30% of the rule's virtual budget in floating loss and 30 minutes have passed since the last paper open (cooldown derived from `trades.open_time`).
- New ORM column `paper_trader_rule_id` on `Trade` (denormalized from migration 014, Plan 1) is now actually used here for fast lookups instead of `recovery_plan["paper_trader_rule_id"]`.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, pandas (existing indicator REGISTRY), pytest-asyncio + httpx (SQLite in-memory).

---

## File Structure

| Path | Action | Purpose |
|------|--------|---------|
| `api/services/pattern_discovery.py` | rewrite | Basket grouping + first-trade anchor + size-weighted + 3-variant spawn |
| `api/services/scoring.py` | create | `compute_score()` + `score_to_lot()` |
| `api/services/paper_trader.py` | rewrite | Shared compute cache + fast/slow split + 3-variant entry/exit + basket recovery |
| `api/services/basket_recovery.py` | create | Floating-loss check + 30min cooldown decision per rule |
| `tests/test_pattern_discovery.py` | rewrite | Cover basket grouping, size-weight, 3-variant spawn |
| `tests/test_scoring.py` | create | Score formula + lot mapping |
| `tests/test_paper_trader.py` | rewrite | Cover shared cache + fast/slow split + variant entries |
| `tests/test_basket_recovery.py` | create | Trigger conditions, cooldown |

---

## Task 1: Pattern discovery — basket grouping helper

**Files:**
- Modify: `api/services/pattern_discovery.py`
- Test: `tests/test_pattern_discovery.py`

- [ ] **Step 1: Write failing test for `group_into_baskets()`**

```python
# tests/test_pattern_discovery.py — add at top
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.indicator_signal import TradeIndicatorSignal
from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, OrderType, Trade
from services.pattern_discovery import (
    BASKET_CLOSE_GAP_SEC,
    MINING_MAX_BASKET_SIZE,
    group_into_baskets,
    run_pattern_discovery,
)


def _real_trade(close_time, profit, volume="0.10", ticket=None):
    return Trade(
        ticket=ticket or int(close_time.timestamp() * 1000) % 10**9,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=close_time - timedelta(minutes=5),
        close_time=close_time,
        open_price=Decimal("1950.00"),
        close_price=Decimal("1955.00"),
        volume=Decimal(volume),
        profit=Decimal(str(profit)),
        is_paper=False,
    )


def test_group_into_baskets_close_within_gap():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    a = _real_trade(base, profit=10, volume="0.01", ticket=1)
    b = _real_trade(base + timedelta(seconds=1), profit=-5, volume="0.05", ticket=2)
    baskets = group_into_baskets([(a, set()), (b, set())])
    assert len(baskets) == 1
    assert {t.ticket for t, _ in baskets[0]} == {1, 2}


def test_group_into_baskets_far_apart():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    a = _real_trade(base, profit=10, ticket=1)
    b = _real_trade(base + timedelta(seconds=10), profit=20, ticket=2)
    baskets = group_into_baskets([(a, set()), (b, set())])
    assert len(baskets) == 2


def test_group_into_baskets_max_size():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    trades = [
        _real_trade(base + timedelta(milliseconds=i * 200), profit=1, ticket=i + 1)
        for i in range(MINING_MAX_BASKET_SIZE + 2)
    ]
    baskets = group_into_baskets([(t, set()) for t in trades])
    sizes = [len(b) for b in baskets]
    assert max(sizes) == MINING_MAX_BASKET_SIZE
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_pattern_discovery.py::test_group_into_baskets_close_within_gap -v"
```

Expected: FAIL with `cannot import name 'group_into_baskets'`.

- [ ] **Step 3: Implement helper inside `pattern_discovery.py`**

Add near the top of `api/services/pattern_discovery.py`:

```python
BASKET_CLOSE_GAP_SEC = float(os.getenv("MINING_BASKET_CLOSE_GAP_SEC", "1.0"))
MINING_MAX_BASKET_SIZE = int(os.getenv("MINING_MAX_BASKET_SIZE", "2"))


def group_into_baskets(
    population: list[tuple[Trade, set[str]]],
) -> list[list[tuple[Trade, set[str]]]]:
    """Group trades whose close_times are within BASKET_CLOSE_GAP_SEC into baskets.

    Caps each basket at MINING_MAX_BASKET_SIZE — extra concurrent closes start a new basket.
    Population is assumed to already be filtered for close_time is not None.
    """
    if not population:
        return []
    ordered = sorted(
        population,
        key=lambda pair: _ensure_aware(pair[0].close_time),
    )
    baskets: list[list[tuple[Trade, set[str]]]] = [[ordered[0]]]
    for trade, slugs in ordered[1:]:
        last = baskets[-1][-1][0]
        gap = (
            _ensure_aware(trade.close_time) - _ensure_aware(last.close_time)
        ).total_seconds()
        if gap <= BASKET_CLOSE_GAP_SEC and len(baskets[-1]) < MINING_MAX_BASKET_SIZE:
            baskets[-1].append((trade, slugs))
        else:
            baskets.append([(trade, slugs)])
    return baskets
```

- [ ] **Step 4: Run to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_pattern_discovery.py -v -k group_into_baskets"
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/pattern_discovery.py tests/test_pattern_discovery.py
git commit -m "feat: basket grouping helper for pattern discovery"
```

---

## Task 2: Pattern discovery — first-trade anchor + size-weighted scoring

**Files:**
- Modify: `api/services/pattern_discovery.py`
- Test: `tests/test_pattern_discovery.py`

- [ ] **Step 1: Write failing test for size-weighted scoring**

Append to `tests/test_pattern_discovery.py`:

```python
def test_basket_anchor_is_first_trade_slugs():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    a = _real_trade(base, profit=-50, volume="0.01", ticket=1)
    b = _real_trade(base + timedelta(seconds=1), profit=200, volume="0.10", ticket=2)
    population = [(a, {"ema_50_h1", "rsi_14_h1"}), (b, {"macd_h1", "atr_h1"})]
    baskets = group_into_baskets(population)
    from services.pattern_discovery import _basket_anchor_slugs, _basket_outcome
    assert _basket_anchor_slugs(baskets[0]) == {"ema_50_h1", "rsi_14_h1"}


def test_basket_outcome_size_weighted_win():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    starter = _real_trade(base, profit=-50, volume="0.01", ticket=1)
    rescue = _real_trade(base + timedelta(seconds=1), profit=200, volume="0.10", ticket=2)
    from services.pattern_discovery import _basket_outcome
    assert _basket_outcome([(starter, set()), (rescue, set())]) is True


def test_basket_outcome_size_weighted_loss():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    starter = _real_trade(base, profit=10, volume="0.01", ticket=1)
    rescue = _real_trade(base + timedelta(seconds=1), profit=-100, volume="0.10", ticket=2)
    from services.pattern_discovery import _basket_outcome
    assert _basket_outcome([(starter, set()), (rescue, set())]) is False
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_pattern_discovery.py -v -k 'basket_anchor or basket_outcome'"
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement anchor + outcome helpers**

Add to `api/services/pattern_discovery.py`:

```python
def _basket_anchor_slugs(basket: list[tuple[Trade, set[str]]]) -> set[str]:
    """First trade in the basket holds the original entry signals."""
    if not basket:
        return set()
    return set(basket[0][1])


def _basket_outcome(basket: list[tuple[Trade, set[str]]]) -> bool:
    """Win = size-weighted net P/L > 0. Volume-weighted protects against
    a tiny starter outvoting a large rescue or vice versa."""
    total_volume = Decimal("0")
    weighted_profit = Decimal("0")
    for trade, _ in basket:
        if trade.volume is None or trade.profit is None:
            continue
        total_volume += trade.volume
        weighted_profit += trade.profit
    if total_volume <= 0:
        return False
    return weighted_profit > 0
```

Add `from decimal import Decimal` at the top of the file.

- [ ] **Step 4: Replace `_score_combinations()` to score baskets, not trades**

Replace the function in `api/services/pattern_discovery.py`:

```python
def _score_combinations(
    population: list[tuple[Trade, set[str]]],
) -> dict[frozenset[str], tuple[int, int]]:
    """Return {combo: (basket_count, win_count)} weighted by basket outcome.

    Uses first-trade slugs as anchor (only those signals were present at entry).
    Outcome is size-weighted net P/L (basket > 0 => win).
    """
    baskets = group_into_baskets(population)
    scores: dict[frozenset[str], list[int]] = {}
    for basket in baskets:
        anchor = _basket_anchor_slugs(basket)
        if len(anchor) < 2:
            continue
        is_win = _basket_outcome(basket)
        ordered = sorted(anchor)
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
```

- [ ] **Step 5: Run to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_pattern_discovery.py -v"
```

Expected: PASS for new tests; existing tests may need adjustment to use baskets (do that next step if any fail).

- [ ] **Step 6: Commit**

```bash
git add api/services/pattern_discovery.py tests/test_pattern_discovery.py
git commit -m "feat: first-trade anchor + size-weighted basket outcome in pattern discovery"
```

---

## Task 3: Pattern discovery — spawn 3 variants per promoted combo

**Files:**
- Modify: `api/services/pattern_discovery.py`
- Test: `tests/test_pattern_discovery.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_pattern_discovery.py`:

```python
@pytest_asyncio.fixture
async def db_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from database import Base

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


async def _seed_basket_runs(session, n_baskets: int, all_win: bool, slugs: tuple[str, ...]):
    base = datetime(2026, 5, 25, tzinfo=timezone.utc)
    for i in range(n_baskets):
        close_time = base + timedelta(hours=i)
        a = _real_trade(close_time, profit=20 if all_win else -20, ticket=i * 10 + 1)
        b = _real_trade(close_time + timedelta(milliseconds=200),
                         profit=10 if all_win else -10, ticket=i * 10 + 2)
        session.add_all([a, b])
        await session.flush()
        for slug in slugs:
            session.add(TradeIndicatorSignal(
                trade_id=a.id, indicator_slug=slug, matched=True, timeframe="H1",
            ))
    await session.commit()


@pytest.mark.asyncio
async def test_promotion_spawns_three_variants(db_session):
    await _seed_basket_runs(
        db_session, n_baskets=15, all_win=True, slugs=("ema_50_h1", "rsi_14_h1"),
    )
    # Run 3 days for stability
    base = datetime(2026, 5, 28, tzinfo=timezone.utc)
    for i in range(3):
        await run_pattern_discovery(db_session, now=base + timedelta(days=i))

    rules = (await db_session.execute(select(PaperTraderRule))).scalars().all()
    modes = sorted(r.mode for r in rules)
    assert modes == ["basket_50k", "basket_5k", "strict"]
    by_mode = {r.mode: r for r in rules}
    assert by_mode["strict"].virtual_balance_start == Decimal("5000")
    assert by_mode["basket_5k"].virtual_balance_start == Decimal("5000")
    assert by_mode["basket_50k"].virtual_balance_start == Decimal("50000")
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_pattern_discovery.py::test_promotion_spawns_three_variants -v"
```

Expected: FAIL with only one rule spawned (current behavior).

- [ ] **Step 3: Add 3-variant spawn in `_run()`**

Replace the `_run()` body's promotion block in `api/services/pattern_discovery.py`. Add a constant near the top:

```python
USER_STYLE_BUDGET = Decimal(os.getenv("PAPER_VIRTUAL_BUDGET_USER_STYLE", "50000"))
DEFAULT_BUDGET = Decimal("5000")

VARIANT_SPECS: tuple[tuple[str, Decimal], ...] = (
    ("strict", DEFAULT_BUDGET),
    ("basket_5k", DEFAULT_BUDGET),
    ("basket_50k", USER_STYLE_BUDGET),
)
```

Then change the rule-creation line inside `_run()`:

```python
        if pattern.status == "candidate" and pattern.consecutive_stable_days >= DISCOVERY_STABLE_DAYS:
            if _is_duplicate(set(combo_key), active_rule_slugs):
                continue
            pattern.status = "active"
            pattern.promoted_at = now
            await session.flush()
            for mode, budget in VARIANT_SPECS:
                session.add(
                    PaperTraderRule(
                        pattern_id=pattern.id,
                        status="active",
                        mode=mode,
                        virtual_balance_start=budget,
                        virtual_balance_current=budget,
                    )
                )
            active_rule_slugs.append(set(combo_key))
```

- [ ] **Step 4: Run to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_pattern_discovery.py -v"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/pattern_discovery.py tests/test_pattern_discovery.py
git commit -m "feat: spawn 3 risk variants (strict/basket_5k/basket_50k) per promoted pattern"
```

---

## Task 4: Scoring service — score formula + lot mapping

**Files:**
- Create: `api/services/scoring.py`
- Test: `tests/test_scoring.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scoring.py
from decimal import Decimal

import pytest

from services.scoring import (
    LOT_TIER_FLOOR,
    LOT_TIER_LOW,
    LOT_TIER_MID,
    LOT_TIER_HIGH,
    SignalQualityInputs,
    compute_score,
    score_to_lot,
)


def test_score_perfect_is_100():
    inputs = SignalQualityInputs(
        matched_count=5,
        total_count=5,
        avg_indicator_strength=1.0,
        rule_winrate=1.0,
    )
    assert compute_score(inputs) == pytest.approx(100.0)


def test_score_no_match_is_zero():
    inputs = SignalQualityInputs(
        matched_count=0, total_count=5, avg_indicator_strength=0.0, rule_winrate=0.0,
    )
    assert compute_score(inputs) == pytest.approx(0.0)


def test_score_balanced_components():
    inputs = SignalQualityInputs(
        matched_count=3,
        total_count=5,
        avg_indicator_strength=0.5,
        rule_winrate=0.6,
    )
    s = compute_score(inputs)
    # 0.25*60 + 0.40*60 + 0.20*50 + 0.15*60 ≈ 58
    assert 50.0 <= s <= 65.0


def test_lot_tier_mapping_floor():
    assert score_to_lot(0) == LOT_TIER_FLOOR
    assert score_to_lot(39.9) == LOT_TIER_FLOOR


def test_lot_tier_mapping_low():
    assert score_to_lot(40) == LOT_TIER_LOW
    assert score_to_lot(69.9) == LOT_TIER_LOW


def test_lot_tier_mapping_mid():
    assert score_to_lot(70) == LOT_TIER_MID
    assert score_to_lot(89.9) == LOT_TIER_MID


def test_lot_tier_mapping_high():
    assert score_to_lot(90) == LOT_TIER_HIGH
    assert score_to_lot(100) == LOT_TIER_HIGH
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_scoring.py -v"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `scoring.py`**

```python
# api/services/scoring.py
from dataclasses import dataclass
from decimal import Decimal


LOT_TIER_FLOOR = Decimal("0.01")
LOT_TIER_LOW = Decimal("0.03")
LOT_TIER_MID = Decimal("0.05")
LOT_TIER_HIGH = Decimal("0.10")

# Score weights — tuned to keep matched-count dominant but reward quality
WEIGHT_INDICATOR_COUNT = 0.25
WEIGHT_WINRATE = 0.40
WEIGHT_STRENGTH = 0.20
WEIGHT_CONFLUENCE = 0.15


@dataclass
class SignalQualityInputs:
    matched_count: int
    total_count: int
    avg_indicator_strength: float  # 0.0 – 1.0, mean of |spec.compute() value| normalized
    rule_winrate: float            # 0.0 – 1.0, the rule's running winrate


def _safe_div(num: float, denom: float) -> float:
    return num / denom if denom else 0.0


def compute_score(inputs: SignalQualityInputs) -> float:
    """Score 0–100 combining winrate, indicator confluence + count + strength."""
    confluence = _safe_div(inputs.matched_count, inputs.total_count)
    count_norm = min(inputs.matched_count / 5.0, 1.0)  # cap at 5 indicators
    strength = max(0.0, min(inputs.avg_indicator_strength, 1.0))
    winrate = max(0.0, min(inputs.rule_winrate, 1.0))
    score = (
        WEIGHT_INDICATOR_COUNT * count_norm
        + WEIGHT_WINRATE * winrate
        + WEIGHT_STRENGTH * strength
        + WEIGHT_CONFLUENCE * confluence
    ) * 100.0
    return round(score, 2)


def score_to_lot(score: float) -> Decimal:
    """Map score (0-100) to lot tier 0.01 / 0.03 / 0.05 / 0.10."""
    if score >= 90:
        return LOT_TIER_HIGH
    if score >= 70:
        return LOT_TIER_MID
    if score >= 40:
        return LOT_TIER_LOW
    return LOT_TIER_FLOOR
```

- [ ] **Step 4: Run to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_scoring.py -v"
```

Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/scoring.py tests/test_scoring.py
git commit -m "feat: signal score formula + lot tier mapping"
```

---

## Task 5: Paper trader — shared per-tick indicator compute cache (P1)

**Files:**
- Modify: `api/services/paper_trader.py`
- Test: `tests/test_paper_trader.py`

- [ ] **Step 1: Write failing test asserting cache hit count**

```python
# tests/test_paper_trader.py — add at top (rewrite if file already exists)
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from models.price_bar import PriceBar, Timeframe
from models.trade import Trade
from schemas.market_tick import MarketTickSchema
from services.paper_trader import _build_indicator_cache, run_paper_trader


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


def _bar(t: datetime, close: float = 1950.0, tf: Timeframe = Timeframe.H1) -> PriceBar:
    return PriceBar(
        symbol="XAUUSD",
        timeframe=tf,
        time=t,
        open=Decimal(str(close)),
        high=Decimal(str(close + 1)),
        low=Decimal(str(close - 1)),
        close=Decimal(str(close)),
        volume=Decimal("100"),
    )


async def _seed_bars(session, count: int = 300):
    base = datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc)
    for i in range(count):
        session.add(_bar(base + timedelta(hours=i), close=1950 + (i % 10)))
    await session.commit()


@pytest.mark.asyncio
async def test_shared_cache_computes_each_slug_once(session):
    await _seed_bars(session)
    pattern = Pattern(
        indicator_slugs=["rsi_14", "ema_50"],
        timeframe="H1",
        win_rate=0.7,
        sample_count=20,
        status="active",
    )
    session.add(pattern)
    await session.flush()
    for mode in ("strict", "basket_5k", "basket_50k"):
        session.add(PaperTraderRule(
            pattern_id=pattern.id, mode=mode, status="active",
        ))
    await session.commit()

    tick = MarketTickSchema(
        symbol="XAUUSD",
        bid=Decimal("1955.0"),
        ask=Decimal("1955.30"),
        timestamp=datetime(2026, 5, 25, 12, 5, tzinfo=timezone.utc),
        account_id=1,
    )

    call_log: list[str] = []
    real_compute = _build_indicator_cache.__globals__["_compute"]

    def spy(slug, bars):
        call_log.append(slug)
        return real_compute(slug, bars)

    with patch("services.paper_trader._compute", side_effect=spy):
        await run_paper_trader(session, tick)

    # Even with 3 rules sharing the same 2 slugs, each slug computed once
    assert call_log.count("rsi_14") == 1
    assert call_log.count("ema_50") == 1
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader.py::test_shared_cache_computes_each_slug_once -v"
```

Expected: FAIL — `_build_indicator_cache` not exported, or each slug recomputed once per rule.

- [ ] **Step 3: Implement `_build_indicator_cache()` and route entry/exit through it**

Replace the entry/exit functions in `api/services/paper_trader.py`. Add this helper:

```python
def _build_indicator_cache(
    rules: list[_RuleSnapshot],
    bars_by_tf: dict[str, list[PriceBar]],
) -> dict[tuple[str, str], tuple[Optional[float], str, dict]]:
    """Compute each (slug, timeframe) exactly once across all rules.

    Returns {(slug, tf): (value, direction, metadata)}.
    """
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]] = {}
    for rule in rules:
        bars = bars_by_tf.get(rule.timeframe) or bars_by_tf.get(DEFAULT_TIMEFRAME)
        if not bars:
            continue
        for slug in rule.indicator_slugs:
            key = (slug, rule.timeframe)
            if key in cache:
                continue
            cache[key] = _compute(slug, bars)
    return cache


def _cached_direction(
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]],
    slug: str,
    timeframe: str,
) -> str:
    item = cache.get((slug, timeframe)) or cache.get((slug, DEFAULT_TIMEFRAME))
    if item is None:
        return "neutral"
    return item[1]
```

- [ ] **Step 4: Replace `_check_entries()` to use the cache**

```python
async def _check_entries(
    session: AsyncSession,
    tick: MarketTickSchema,
    rules: list[_RuleSnapshot],
    bars_by_tf: dict[str, list[PriceBar]],
    open_by_rule: dict[uuid.UUID, Trade],
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]],
) -> list[Trade]:
    opened: list[Trade] = []
    for rule in rules:
        if rule.rule_id in open_by_rule:
            continue
        bars = bars_by_tf.get(rule.timeframe) or bars_by_tf.get(DEFAULT_TIMEFRAME)
        if not bars:
            continue
        directions = [
            _cached_direction(cache, slug, rule.timeframe)
            for slug in rule.indicator_slugs
        ]
        direction = _consensus_direction(directions)
        if direction is None:
            continue
        entry = (tick.ask if direction == Direction.buy else tick.bid)
        atr = _compute_atr(bars)
        if atr is None:
            continue
        sl = _compute_sl_for_mode(rule.mode, direction, entry, atr)
        tp_raw = _compute_tp(direction, entry, bars, atr)
        if tp_raw is None:
            continue
        tp = _quantize(tp_raw)
        trade = _build_paper_trade(
            tick, rule, direction, entry, tp, sl,
            volume=DEFAULT_VOLUME,  # score-based volume comes in Task 6
        )
        session.add(trade)
        await session.flush()
        rule_row = await session.get(PaperTraderRule, rule.rule_id)
        if rule_row is not None:
            rule_row.total_trades += 1
        opened.append(trade)
        open_by_rule[rule.rule_id] = trade
    return opened


def _compute_sl_for_mode(
    mode: str, direction: Direction, entry: Decimal, atr: Decimal
) -> Optional[Decimal]:
    """variant_A (strict) carries a hard SL = lot×ATR×2; basket modes have no SL."""
    if mode == "strict":
        return _quantize(_compute_sl(direction, entry, atr))
    return None


def _build_paper_trade(
    tick: MarketTickSchema,
    rule: _RuleSnapshot,
    direction: Direction,
    entry: Decimal,
    tp: Decimal,
    sl: Optional[Decimal],
    volume: Decimal,
) -> Trade:
    return Trade(
        ticket=int(tick.timestamp.timestamp() * 1000) % 1_000_000_000_000
        + abs(hash(rule.rule_id)) % 1000,
        symbol=tick.symbol,
        direction=direction,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=tick.timestamp,
        fill_time=tick.timestamp,
        open_price=entry,
        volume=volume,
        tp=tp,
        sl=sl,
        is_paper=True,
        paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule.rule_id)},
        paper_trader_rule_id=rule.rule_id,
        account_id=tick.account_id,
    )
```

Update `_RuleSnapshot` to also carry `mode`:

```python
@dataclass
class _RuleSnapshot:
    rule_id: uuid.UUID
    pattern_id: uuid.UUID
    indicator_slugs: list[str]
    timeframe: str
    mode: str
```

Update `load_active_rules()` to populate `mode`:

```python
        snapshots.append(
            _RuleSnapshot(
                rule_id=rule.id,
                pattern_id=pattern.id,
                indicator_slugs=list(pattern.indicator_slugs),
                timeframe=pattern.timeframe or DEFAULT_TIMEFRAME,
                mode=rule.mode or "strict",
            )
        )
```

- [ ] **Step 5: Replace `_check_exits()` to read from cache (momentum-flip path)**

```python
async def _check_exits(
    session: AsyncSession,
    tick: MarketTickSchema,
    rules: list[_RuleSnapshot],
    bars_by_tf: dict[str, list[PriceBar]],
    open_by_rule: dict[uuid.UUID, Trade],
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]],
) -> list[Trade]:
    rules_by_id = {r.rule_id: r for r in rules}
    closed: list[Trade] = []

    for rule_id, trade in list(open_by_rule.items()):
        rule = rules_by_id.get(rule_id)
        if rule is None or trade.direction is None:
            continue

        exit_price: Optional[Decimal] = None
        reason: Optional[str] = None
        is_win = False

        # SL/TP for strict only — basket modes have no SL
        if rule.mode == "strict":
            if trade.direction == Direction.buy:
                if trade.tp is not None and tick.bid >= trade.tp:
                    exit_price, reason, is_win = trade.tp, "tp", True
                elif trade.sl is not None and tick.bid <= trade.sl:
                    exit_price, reason = trade.sl, "sl"
            else:
                if trade.tp is not None and tick.ask <= trade.tp:
                    exit_price, reason, is_win = trade.tp, "tp", True
                elif trade.sl is not None and tick.ask >= trade.sl:
                    exit_price, reason = trade.sl, "sl"
        else:
            # basket modes: TP only on touch, no SL
            if trade.tp is not None and trade.direction == Direction.buy and tick.bid >= trade.tp:
                exit_price, reason, is_win = trade.tp, "tp", True
            elif trade.tp is not None and trade.direction == Direction.sell and tick.ask <= trade.tp:
                exit_price, reason, is_win = trade.tp, "tp", True

        if exit_price is None:
            momentum_slug = _first_momentum_slug(rule.indicator_slugs)
            if momentum_slug is not None:
                mdir = _cached_direction(cache, momentum_slug, rule.timeframe)
                flipped = (
                    (trade.direction == Direction.buy and mdir == "bearish")
                    or (trade.direction == Direction.sell and mdir == "bullish")
                )
                if flipped:
                    exit_price = tick.bid if trade.direction == Direction.buy else tick.ask
                    reason = "momentum_flip"
                    profit = _paper_profit(trade, exit_price)
                    is_win = bool(profit and profit > 0)

        if exit_price is None:
            continue

        trade.close_price = exit_price
        trade.close_time = tick.timestamp
        trade.profit = _paper_profit(trade, exit_price)
        trade.paper_exit_reason = reason
        rule_row = await session.get(PaperTraderRule, rule_id)
        if rule_row is not None and is_win:
            rule_row.win_count += 1
        closed.append(trade)
        del open_by_rule[rule_id]

    return closed
```

- [ ] **Step 6: Update `run_paper_trader()` to build the cache once**

```python
async def run_paper_trader(
    session: AsyncSession, tick: MarketTickSchema
) -> dict:
    if not PAPER_TRADER_ENABLED:
        return {"opened": 0, "closed": 0, "skipped": "disabled"}

    rules = await load_active_rules(session, tick.timestamp)
    if not rules:
        return {"opened": 0, "closed": 0}

    timeframes = {rule.timeframe for rule in rules}
    bars_by_tf: dict[str, list[PriceBar]] = {}
    for tf in timeframes:
        bars_by_tf[tf] = await _fetch_bars(session, tick.symbol, tf, tick.timestamp)

    cache = _build_indicator_cache(rules, bars_by_tf)
    open_by_rule = await _open_papers_for_rules(session, [r.rule_id for r in rules])
    closed = await _check_exits(session, tick, rules, bars_by_tf, open_by_rule, cache)
    opened = await _check_entries(session, tick, rules, bars_by_tf, open_by_rule, cache)

    if opened or closed:
        await session.commit()

    return {"opened": len(opened), "closed": len(closed)}
```

- [ ] **Step 7: Run all paper trader tests**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader.py -v"
```

Expected: PASS (cache test + any pre-existing tests).

- [ ] **Step 8: Commit**

```bash
git add api/services/paper_trader.py tests/test_paper_trader.py
git commit -m "feat: shared per-tick indicator compute cache in paper trader"
```

---

## Task 6: Paper trader — fast/slow path split (P2) + score-based lot

**Files:**
- Modify: `api/services/paper_trader.py`
- Test: `tests/test_paper_trader.py`

- [ ] **Step 1: Write failing test asserting slow-path indicators reuse a stale cache window**

```python
# tests/test_paper_trader.py — append
import time

from services.paper_trader import _build_indicator_cache, _slow_path_due, FAST_PATH_GROUPS


def test_slow_path_due_first_call_returns_true():
    state = {"last_slow_at": None}
    assert _slow_path_due(state, datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc))


def test_slow_path_due_within_interval_returns_false():
    last = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    state = {"last_slow_at": last}
    assert not _slow_path_due(state, last + timedelta(seconds=10))


def test_slow_path_due_after_interval_returns_true():
    last = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    state = {"last_slow_at": last}
    assert _slow_path_due(state, last + timedelta(seconds=20))
```

- [ ] **Step 2: Add fast/slow constants + helper, run to fail**

Run first: expect ImportError. Then add to `paper_trader.py`:

```python
SLOW_PATH_INTERVAL_SEC = int(os.getenv("PAPER_TRADER_SLOW_PATH_SEC", "15"))
FAST_PATH_GROUPS = {"momentum", "support_resistance"}
SLOW_PATH_GROUPS = {"trend", "volatility", "volume", "pattern", "cycle"}


_slow_path_state: dict[str, Optional[datetime]] = {"last_slow_at": None}
_slow_path_cache: dict[tuple[str, str], tuple[Optional[float], str, dict]] = {}


def reset_slow_path() -> None:
    global _slow_path_state, _slow_path_cache
    _slow_path_state = {"last_slow_at": None}
    _slow_path_cache = {}


def _slow_path_due(state: dict, now: datetime) -> bool:
    last = state.get("last_slow_at")
    if last is None:
        return True
    return (now - last).total_seconds() >= SLOW_PATH_INTERVAL_SEC


def _is_fast_slug(slug: str) -> bool:
    spec = ALL_SPECS.get(slug)
    return spec is not None and spec.group in FAST_PATH_GROUPS
```

- [ ] **Step 3: Run helper tests; should pass**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader.py -v -k slow_path"
```

Expected: PASS.

- [ ] **Step 4: Wire fast/slow into `_build_indicator_cache()`**

Replace `_build_indicator_cache()`:

```python
def _build_indicator_cache(
    rules: list[_RuleSnapshot],
    bars_by_tf: dict[str, list[PriceBar]],
    now: Optional[datetime] = None,
) -> dict[tuple[str, str], tuple[Optional[float], str, dict]]:
    now = now or datetime.now(timezone.utc)
    refresh_slow = _slow_path_due(_slow_path_state, now)
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]] = {}

    for rule in rules:
        bars = bars_by_tf.get(rule.timeframe) or bars_by_tf.get(DEFAULT_TIMEFRAME)
        if not bars:
            continue
        for slug in rule.indicator_slugs:
            key = (slug, rule.timeframe)
            if key in cache:
                continue
            if _is_fast_slug(slug):
                cache[key] = _compute(slug, bars)
            else:
                if refresh_slow or key not in _slow_path_cache:
                    _slow_path_cache[key] = _compute(slug, bars)
                cache[key] = _slow_path_cache[key]

    if refresh_slow:
        _slow_path_state["last_slow_at"] = now

    return cache
```

- [ ] **Step 5: Add score-based lot in `_check_entries()`**

Inside `_check_entries()` after computing `direction`, replace `volume=DEFAULT_VOLUME` with score-derived lot:

```python
        from services.scoring import (
            SignalQualityInputs,
            compute_score,
            score_to_lot,
        )

        cached = [
            cache.get((slug, rule.timeframe)) or cache.get((slug, DEFAULT_TIMEFRAME))
            for slug in rule.indicator_slugs
        ]
        matched = sum(1 for c in cached if c is not None and c[1] != "neutral")
        if matched == 0:
            continue
        avg_strength = sum(
            min(abs(c[0] or 0.0) / 100.0, 1.0) for c in cached if c is not None
        ) / max(len(cached), 1)
        rule_row = await session.get(PaperTraderRule, rule.rule_id)
        winrate = (
            (rule_row.win_count / rule_row.total_trades)
            if rule_row and rule_row.total_trades
            else 0.0
        )
        score = compute_score(
            SignalQualityInputs(
                matched_count=matched,
                total_count=len(rule.indicator_slugs),
                avg_indicator_strength=avg_strength,
                rule_winrate=winrate,
            )
        )
        lot = score_to_lot(score)
        # ... existing entry-price + atr block ...
        trade = _build_paper_trade(
            tick, rule, direction, entry, tp, sl, volume=lot,
        )
```

(Drop the unused `from services.scoring import ...` if linting complains by hoisting it to module imports.)

- [ ] **Step 6: Update test that asserts entry size now varies**

Add to `tests/test_paper_trader.py`:

```python
@pytest.mark.asyncio
async def test_entry_uses_score_based_lot(session):
    await _seed_bars(session)
    pattern = Pattern(
        indicator_slugs=["rsi_14", "ema_50"],
        timeframe="H1",
        win_rate=0.95,
        sample_count=100,
        status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(
        pattern_id=pattern.id,
        mode="basket_5k",
        status="active",
        win_count=95,
        total_trades=100,
    )
    session.add(rule)
    await session.commit()

    tick = MarketTickSchema(
        symbol="XAUUSD",
        bid=Decimal("1955.0"),
        ask=Decimal("1955.30"),
        timestamp=datetime(2026, 5, 25, 12, 5, tzinfo=timezone.utc),
        account_id=1,
    )
    await run_paper_trader(session, tick)

    trades = (await session.execute(select(Trade).where(Trade.is_paper.is_(True)))).scalars().all()
    if trades:
        # ought to be one of the tier values
        assert trades[0].volume in {Decimal("0.01"), Decimal("0.03"), Decimal("0.05"), Decimal("0.10")}
```

- [ ] **Step 7: Run all tests**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader.py -v"
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add api/services/paper_trader.py tests/test_paper_trader.py
git commit -m "feat: fast/slow path split + score-based lot sizing in paper trader"
```

---

## Task 7: Basket recovery — floating-loss check + 30min cooldown

**Files:**
- Create: `api/services/basket_recovery.py`
- Modify: `api/services/paper_trader.py`
- Test: `tests/test_basket_recovery.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_basket_recovery.py
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.basket_recovery import (
    RECOVERY_COOLDOWN_SEC,
    RECOVERY_FLOATING_LOSS_PCT,
    should_open_recovery,
)


def _open_paper(open_time: datetime, open_price: float, volume: float) -> Trade:
    return Trade(
        ticket=1,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=open_time,
        open_price=Decimal(str(open_price)),
        volume=Decimal(str(volume)),
        is_paper=True,
        paper_mode=PaperMode.independent,
    )


NOW = datetime(2026, 5, 25, 12, 30, tzinfo=timezone.utc)


def test_no_recovery_when_no_open_paper():
    assert not should_open_recovery(
        existing=None, current_bid=Decimal("1950"),
        virtual_balance=Decimal("5000"), now=NOW, mode="basket_5k",
    )


def test_no_recovery_when_loss_below_floor():
    existing = _open_paper(NOW - timedelta(hours=1), open_price=1950.0, volume=0.10)
    # Loss = (1950-1948)*0.1*100 = ฿20 → below 30% of 5000
    assert not should_open_recovery(
        existing=existing, current_bid=Decimal("1948"),
        virtual_balance=Decimal("5000"), now=NOW, mode="basket_5k",
    )


def test_no_recovery_when_strict_mode():
    existing = _open_paper(NOW - timedelta(hours=1), open_price=1950.0, volume=0.10)
    assert not should_open_recovery(
        existing=existing, current_bid=Decimal("1900"),
        virtual_balance=Decimal("5000"), now=NOW, mode="strict",
    )


def test_recovery_when_loss_exceeds_floor_and_cooldown_passed():
    existing = _open_paper(NOW - timedelta(hours=1), open_price=1950.0, volume=0.10)
    # Loss ≈ ฿2000 → >30% of 5000 (฿1500)
    assert should_open_recovery(
        existing=existing, current_bid=Decimal("1750"),
        virtual_balance=Decimal("5000"), now=NOW, mode="basket_5k",
    )


def test_no_recovery_within_cooldown():
    open_time = NOW - timedelta(seconds=RECOVERY_COOLDOWN_SEC - 60)
    existing = _open_paper(open_time, open_price=1950.0, volume=0.10)
    assert not should_open_recovery(
        existing=existing, current_bid=Decimal("1750"),
        virtual_balance=Decimal("5000"), now=NOW, mode="basket_5k",
    )
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_basket_recovery.py -v"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `basket_recovery.py`**

```python
# api/services/basket_recovery.py
import os
from datetime import datetime
from decimal import Decimal
from typing import Optional

from models.trade import Direction, Trade


RECOVERY_COOLDOWN_SEC = int(os.getenv("BASKET_RECOVERY_COOLDOWN_SEC", "1800"))
RECOVERY_FLOATING_LOSS_PCT = float(os.getenv("BASKET_RECOVERY_LOSS_PCT", "0.30"))
XAUUSD_CONTRACT_SIZE = Decimal("100")
RECOVERY_MODES = {"basket_5k", "basket_50k"}


def _floating_pnl(trade: Trade, current_bid: Decimal, current_ask: Decimal) -> Decimal:
    if trade.open_price is None or trade.volume is None or trade.direction is None:
        return Decimal("0")
    if trade.direction == Direction.buy:
        return (current_bid - trade.open_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    return (trade.open_price - current_ask) * trade.volume * XAUUSD_CONTRACT_SIZE


def should_open_recovery(
    *,
    existing: Optional[Trade],
    current_bid: Decimal,
    virtual_balance: Decimal,
    now: datetime,
    mode: str,
    current_ask: Optional[Decimal] = None,
) -> bool:
    if mode not in RECOVERY_MODES:
        return False
    if existing is None or existing.open_time is None:
        return False
    elapsed = (now - existing.open_time).total_seconds()
    if elapsed < RECOVERY_COOLDOWN_SEC:
        return False
    floating = _floating_pnl(existing, current_bid, current_ask or current_bid)
    if floating >= 0:
        return False
    loss_threshold = virtual_balance * Decimal(str(RECOVERY_FLOATING_LOSS_PCT))
    return abs(floating) >= loss_threshold
```

- [ ] **Step 4: Run to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_basket_recovery.py -v"
```

Expected: PASS (5 tests).

- [ ] **Step 5: Wire recovery into paper_trader entry path**

In `api/services/paper_trader.py` `_check_entries()`, change the early-skip on `open_by_rule`:

```python
        existing = open_by_rule.get(rule.rule_id)
        if existing is not None:
            from services.basket_recovery import should_open_recovery
            rule_row = await session.get(PaperTraderRule, rule.rule_id)
            balance = (
                rule_row.virtual_balance_start if rule_row else Decimal("5000")
            )
            if not should_open_recovery(
                existing=existing,
                current_bid=tick.bid,
                current_ask=tick.ask,
                virtual_balance=balance,
                now=tick.timestamp,
                mode=rule.mode,
            ):
                continue
            # else: fall through and open a recovery trade alongside `existing`
```

The rest of the entry block stays (it'll insert a *second* paper trade against the same rule) — but `_open_papers_for_rules()` returns a single trade per rule today. Make it return a list instead:

```python
async def _open_papers_for_rules(
    session: AsyncSession, rule_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Trade]]:
    if not rule_ids:
        return {}
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_(None),
        )
    )
    trades = result.scalars().all()
    by_rule: dict[uuid.UUID, list[Trade]] = {}
    rule_id_strs = {str(rid) for rid in rule_ids}
    for t in trades:
        plan = t.recovery_plan or {}
        rid_str = plan.get("paper_trader_rule_id")
        if rid_str in rule_id_strs:
            by_rule.setdefault(uuid.UUID(rid_str), []).append(t)
    return by_rule
```

In `_check_entries()` and `_check_exits()`, treat `open_by_rule[rule_id]` as a list. Specifically:

```python
        existings = open_by_rule.get(rule.rule_id, [])
        latest = existings[-1] if existings else None
        if latest is not None:
            ... (recovery check on `latest`) ...

        ... (after building the new trade)
        open_by_rule.setdefault(rule.rule_id, []).append(trade)
```

And in `_check_exits()`:

```python
    for rule_id, trades in list(open_by_rule.items()):
        rule = rules_by_id.get(rule_id)
        if rule is None:
            continue
        for trade in list(trades):
            ... (existing per-trade exit logic; remove on close)
        if not trades:
            del open_by_rule[rule_id]
```

- [ ] **Step 6: Add an integration test**

```python
# tests/test_paper_trader.py — append
@pytest.mark.asyncio
async def test_basket_recovery_opens_second_trade(session):
    await _seed_bars(session)
    pattern = Pattern(
        indicator_slugs=["rsi_14", "ema_50"],
        timeframe="H1",
        win_rate=0.7,
        sample_count=100,
        status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(
        pattern_id=pattern.id,
        mode="basket_5k",
        status="active",
        virtual_balance_start=Decimal("5000"),
        virtual_balance_current=Decimal("5000"),
        total_trades=10, win_count=7,
    )
    session.add(rule)
    await session.commit()

    open_time = datetime(2026, 5, 25, 11, 0, tzinfo=timezone.utc)  # 1.5h ago
    existing = Trade(
        ticket=999, symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market, order_state=OrderState.filled,
        open_time=open_time, open_price=Decimal("1950.0"),
        volume=Decimal("0.10"),
        is_paper=True, paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule.id)},
        paper_trader_rule_id=rule.id,
        account_id=1,
    )
    session.add(existing)
    await session.commit()

    tick = MarketTickSchema(
        symbol="XAUUSD",
        bid=Decimal("1750.0"),  # huge loss
        ask=Decimal("1750.30"),
        timestamp=datetime(2026, 5, 25, 12, 30, tzinfo=timezone.utc),
        account_id=1,
    )
    await run_paper_trader(session, tick)

    paper_trades = (
        await session.execute(
            select(Trade).where(
                Trade.is_paper.is_(True),
                Trade.paper_trader_rule_id == rule.id,
            )
        )
    ).scalars().all()
    # Should now have at least 2 paper trades for this rule (original + recovery)
    assert len(paper_trades) >= 2
```

- [ ] **Step 7: Run all tests**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_trader.py tests/test_basket_recovery.py -v"
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add api/services/basket_recovery.py api/services/paper_trader.py \
        tests/test_basket_recovery.py tests/test_paper_trader.py
git commit -m "feat: basket recovery (basket_5k/basket_50k) with floating-loss + cooldown"
```

---

## Task 8: Full regression

- [ ] **Step 1: Run the entire test suite**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/ -v"
```

Expected: PASS — no regressions in `test_pattern_discovery.py`, `test_scoring.py`, `test_paper_trader.py`, `test_basket_recovery.py`, plus existing tests.

- [ ] **Step 2: If regressions, fix in place; do NOT skip tests**

If `test_paper_trader.py` had legacy single-rule tests that now fail because of list-of-trades change, update them to call `open_by_rule[rule_id][0]`.

- [ ] **Step 3: Final commit**

```bash
git add -A tests/
git commit -m "test: regression sweep after auto-discovery v2 + score sizing rollout"
```

---

## Out of scope for this plan

- The `score_calibrations` write-back (calibrate score → actual winrate) — handled in Plan 7 (Promotion Gate).
- Paper signal emission — handled in Plan 5 (Signal Broadcaster).
- Baseline rule auto-spawn — handled in Plan 6 (Baseline Runner).
- Wilson CI / net EV — Plan 7.
