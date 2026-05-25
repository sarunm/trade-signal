# Plan 6 — Baseline Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-25-paper-trade-system-redesign-v2.md` § "Baseline rules"

**Goal:** Auto-spawn one signal-less baseline rule that opens trades at every session boundary (London 7:00 / NY 13:00 / Asia 22:00 UTC) with alternating direction. Use it as a "random benchmark" — promotion gate fails any non-baseline rule that doesn't beat the baseline winrate by ≥ 5%.

**Architecture:**
- New `baseline_runner.py` — runs as an APScheduler cron at each session boundary. On fire: looks up the active baseline rule (creating one if missing), determines next direction by `(last_baseline_trade.direction → opposite)`, and inserts a `Trade` with `is_paper=True`, `paper_mode=independent`, `paper_trader_rule_id=baseline_rule.id`.
- New `baseline_stats.py` — `get_baseline_winrate(session, days=30) -> float` is the single read API used by the promotion gate.
- The baseline trade exits the same way a `basket_5k` paper trade exits (TP touch / momentum flip / hard stop on virtual budget) — no schema change needed; we reuse `paper_exit_manager` / paper_trader exit logic by tagging the rule with `mode='basket_5k'` plus the new `is_baseline=True` flag.
- A new `Pattern` row with `indicator_slugs=[]`, `status='baseline'`, `timeframe='H1'` represents the baseline (one row per period; today the period is "global"). The `PaperTraderRule` row gets `is_baseline=True`, `spawn_strategy='random_session_start'`. Both columns come from migration 016 (Plan 7); guard the writes with `getattr` so this plan can land before that migration.

**Tech Stack:** APScheduler, SQLAlchemy 2.0 async, FastAPI lifespan hook, pytest-asyncio (SQLite in-memory).

---

## File Structure

| Path | Action | Purpose |
|------|--------|---------|
| `api/services/baseline_runner.py` | create | Cron handler that opens session-boundary trades |
| `api/services/baseline_stats.py` | create | Rolling winrate query for promotion gate |
| `api/main.py` | modify | Register 3 cron jobs (London/NY/Asia) |
| `tests/test_baseline_runner.py` | create | Unit + integration |
| `tests/test_baseline_stats.py` | create | Winrate query |

---

## Task 1: Baseline runner — auto-spawn baseline pattern + rule

**Files:**
- Create: `api/services/baseline_runner.py`
- Test: `tests/test_baseline_runner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_baseline_runner.py
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from services.baseline_runner import (
    BASELINE_PATTERN_STATUS,
    BASELINE_RULE_MODE,
    ensure_baseline_rule,
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


@pytest.mark.asyncio
async def test_ensure_baseline_creates_pattern_and_rule(session):
    rule = await ensure_baseline_rule(session)
    assert rule is not None
    assert rule.mode == BASELINE_RULE_MODE
    assert getattr(rule, "is_baseline", True) is True

    patterns = (await session.execute(
        select(Pattern).where(Pattern.status == BASELINE_PATTERN_STATUS)
    )).scalars().all()
    assert len(patterns) == 1
    assert patterns[0].indicator_slugs == []


@pytest.mark.asyncio
async def test_ensure_baseline_idempotent(session):
    rule_a = await ensure_baseline_rule(session)
    rule_b = await ensure_baseline_rule(session)
    assert rule_a.id == rule_b.id
    rules = (await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.status == "active")
    )).scalars().all()
    # Only one baseline rule
    baselines = [r for r in rules if getattr(r, "is_baseline", False)]
    assert len(baselines) == 1
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_baseline_runner.py -v -k ensure_baseline"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `ensure_baseline_rule()`**

```python
# api/services/baseline_runner.py
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade

logger = logging.getLogger(__name__)

BASELINE_ENABLED = os.getenv("BASELINE_ENABLED", "1") == "1"
BASELINE_RULE_MODE = os.getenv("BASELINE_RULE_MODE", "basket_5k")
BASELINE_PATTERN_STATUS = "baseline"
BASELINE_SPAWN_STRATEGY = "random_session_start"
BASELINE_DIRECTION_STRATEGY = os.getenv("BASELINE_DIRECTION_STRATEGY", "alternating")
BASELINE_VOLUME = Decimal(os.getenv("BASELINE_VOLUME", "0.10"))
BASELINE_VIRTUAL_BUDGET = Decimal(os.getenv("BASELINE_VIRTUAL_BUDGET", "5000"))


def _set_if_attr(obj, **kwargs) -> None:
    """Best-effort assignment for columns that may or may not exist yet
    (depends on which migrations have run)."""
    for k, v in kwargs.items():
        if hasattr(obj, k):
            setattr(obj, k, v)


async def _find_baseline_pattern(session: AsyncSession) -> Optional[Pattern]:
    result = await session.execute(
        select(Pattern).where(Pattern.status == BASELINE_PATTERN_STATUS)
    )
    return result.scalars().first()


async def _find_baseline_rule(session: AsyncSession) -> Optional[PaperTraderRule]:
    result = await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.status == "active")
    )
    for rule in result.scalars().all():
        if getattr(rule, "is_baseline", False):
            return rule
    return None


async def ensure_baseline_rule(session: AsyncSession) -> PaperTraderRule:
    """Create the baseline pattern + rule if they don't exist; idempotent."""
    pattern = await _find_baseline_pattern(session)
    if pattern is None:
        pattern = Pattern(
            indicator_slugs=[],
            timeframe="H1",
            win_rate=0.0,
            sample_count=0,
            status=BASELINE_PATTERN_STATUS,
        )
        session.add(pattern)
        await session.flush()

    rule = await _find_baseline_rule(session)
    if rule is None:
        rule = PaperTraderRule(
            pattern_id=pattern.id,
            status="active",
            mode=BASELINE_RULE_MODE,
            virtual_balance_start=BASELINE_VIRTUAL_BUDGET,
            virtual_balance_current=BASELINE_VIRTUAL_BUDGET,
        )
        _set_if_attr(rule, is_baseline=True, spawn_strategy=BASELINE_SPAWN_STRATEGY)
        session.add(rule)
        await session.flush()

    await session.commit()
    return rule
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_baseline_runner.py -v -k ensure_baseline"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/baseline_runner.py tests/test_baseline_runner.py
git commit -m "feat: ensure baseline pattern + rule (idempotent)"
```

---

## Task 2: Direction strategy — alternating buy/sell

**Files:**
- Modify: `api/services/baseline_runner.py`
- Test: `tests/test_baseline_runner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_baseline_runner.py`:

```python
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.baseline_runner import next_direction


@pytest.mark.asyncio
async def test_first_baseline_trade_is_buy(session):
    rule = await ensure_baseline_rule(session)
    direction = await next_direction(session, rule)
    assert direction == Direction.buy


@pytest.mark.asyncio
async def test_alternates_after_buy(session):
    rule = await ensure_baseline_rule(session)
    session.add(Trade(
        ticket=1, symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market, order_state=OrderState.filled,
        open_time=datetime(2026, 5, 25, 7, 0, tzinfo=timezone.utc),
        open_price=Decimal("1950"), volume=Decimal("0.10"),
        is_paper=True, paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule.id), "is_baseline": True},
    ))
    await session.commit()
    direction = await next_direction(session, rule)
    assert direction == Direction.sell


@pytest.mark.asyncio
async def test_alternates_after_sell(session):
    rule = await ensure_baseline_rule(session)
    session.add(Trade(
        ticket=2, symbol="XAUUSD",
        direction=Direction.sell,
        order_type=OrderType.market, order_state=OrderState.filled,
        open_time=datetime(2026, 5, 25, 7, 0, tzinfo=timezone.utc),
        open_price=Decimal("1950"), volume=Decimal("0.10"),
        is_paper=True, paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule.id), "is_baseline": True},
    ))
    await session.commit()
    direction = await next_direction(session, rule)
    assert direction == Direction.buy
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_baseline_runner.py -v -k 'first_baseline or alternates'"
```

Expected: FAIL — `next_direction` not defined.

- [ ] **Step 3: Implement `next_direction()`**

Append to `api/services/baseline_runner.py`:

```python
async def _last_baseline_trade(
    session: AsyncSession, rule: PaperTraderRule
) -> Optional[Trade]:
    rule_id_str = str(rule.id)
    result = await session.execute(
        select(Trade)
        .where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
        )
        .order_by(Trade.open_time.desc().nullslast())
        .limit(50)
    )
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        if plan.get("paper_trader_rule_id") == rule_id_str:
            return trade
    return None


async def next_direction(
    session: AsyncSession, rule: PaperTraderRule
) -> Direction:
    if BASELINE_DIRECTION_STRATEGY == "longonly":
        return Direction.buy
    if BASELINE_DIRECTION_STRATEGY == "shortonly":
        return Direction.sell
    if BASELINE_DIRECTION_STRATEGY == "random":
        import random

        return random.choice([Direction.buy, Direction.sell])
    last = await _last_baseline_trade(session, rule)
    if last is None or last.direction == Direction.sell:
        return Direction.buy
    return Direction.sell
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_baseline_runner.py -v"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/baseline_runner.py tests/test_baseline_runner.py
git commit -m "feat: alternating direction selection for baseline runner"
```

---

## Task 3: Open a baseline trade at session boundary

**Files:**
- Modify: `api/services/baseline_runner.py`
- Modify: `tests/test_baseline_runner.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_baseline_runner.py`:

```python
from models.price_bar import PriceBar, Timeframe
from services.baseline_runner import open_baseline_trade


def _bar(t: datetime, close: float = 1950.0) -> PriceBar:
    return PriceBar(
        symbol="XAUUSD", timeframe=Timeframe.H1, time=t,
        open=Decimal(str(close)), high=Decimal(str(close + 1)),
        low=Decimal(str(close - 1)), close=Decimal(str(close)),
        volume=Decimal("100"),
    )


async def _seed_bars(session, start: datetime, count: int = 200):
    from datetime import timedelta as td
    for i in range(count):
        session.add(_bar(start - td(hours=count - i), close=1950 + (i % 5)))
    await session.commit()


@pytest.mark.asyncio
async def test_open_baseline_trade_inserts_paper(session):
    now = datetime(2026, 5, 25, 7, 0, tzinfo=timezone.utc)
    await _seed_bars(session, now)
    rule = await ensure_baseline_rule(session)
    trade = await open_baseline_trade(session, account_id=1, now=now)
    assert trade is not None
    assert trade.is_paper is True
    assert trade.direction == Direction.buy
    assert trade.recovery_plan["is_baseline"] is True
    assert trade.recovery_plan["paper_trader_rule_id"] == str(rule.id)


@pytest.mark.asyncio
async def test_open_baseline_skipped_if_already_open(session):
    now = datetime(2026, 5, 25, 7, 0, tzinfo=timezone.utc)
    await _seed_bars(session, now)
    rule = await ensure_baseline_rule(session)
    first = await open_baseline_trade(session, account_id=1, now=now)
    assert first is not None
    second = await open_baseline_trade(session, account_id=1, now=now)
    assert second is None
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_baseline_runner.py -v -k open_baseline"
```

Expected: FAIL — `open_baseline_trade` not defined.

- [ ] **Step 3: Implement `open_baseline_trade()`**

Append to `api/services/baseline_runner.py`:

```python
from models.price_bar import PriceBar, Timeframe


async def _has_open_baseline(session: AsyncSession, rule: PaperTraderRule) -> bool:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_(None),
        )
    )
    rule_id_str = str(rule.id)
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        if plan.get("paper_trader_rule_id") == rule_id_str:
            return True
    return False


async def _latest_h1_close(session: AsyncSession, symbol: str = "XAUUSD") -> Optional[Decimal]:
    result = await session.execute(
        select(PriceBar)
        .where(PriceBar.symbol == symbol, PriceBar.timeframe == Timeframe.H1)
        .order_by(PriceBar.time.desc())
        .limit(1)
    )
    bar = result.scalars().first()
    return bar.close if bar else None


async def open_baseline_trade(
    session: AsyncSession,
    account_id: Optional[int],
    now: Optional[datetime] = None,
) -> Optional[Trade]:
    """Insert a paper trade tagged as baseline at the current session boundary."""
    if not BASELINE_ENABLED:
        return None
    now = now or datetime.now(timezone.utc)
    rule = await ensure_baseline_rule(session)
    if await _has_open_baseline(session, rule):
        logger.info("baseline_runner: existing open baseline trade — skipping")
        return None

    last_close = await _latest_h1_close(session)
    if last_close is None:
        logger.warning("baseline_runner: no price bars; skipping")
        return None

    direction = await next_direction(session, rule)
    trade = Trade(
        ticket=int(now.timestamp() * 1000) % 1_000_000_000_000,
        symbol="XAUUSD",
        direction=direction,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=now,
        fill_time=now,
        open_price=last_close,
        volume=BASELINE_VOLUME,
        is_paper=True,
        paper_mode=PaperMode.independent,
        recovery_plan={
            "paper_trader_rule_id": str(rule.id),
            "is_baseline": True,
        },
        account_id=account_id,
    )
    _set_if_attr(trade, paper_trader_rule_id=rule.id)
    session.add(trade)
    rule.total_trades = (rule.total_trades or 0) + 1
    await session.commit()
    logger.info(
        "baseline_runner: opened %s baseline trade #%s @ %s",
        direction.value, trade.ticket, last_close,
    )
    return trade
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_baseline_runner.py -v"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/baseline_runner.py tests/test_baseline_runner.py
git commit -m "feat: open baseline trade at session boundary"
```

---

## Task 4: Schedule baseline cron jobs in main.py

**Files:**
- Modify: `api/main.py`

- [ ] **Step 1: Add session-boundary cron handler + 3 jobs**

Update `api/main.py`. Add the import:

```python
from services.baseline_runner import BASELINE_ENABLED, open_baseline_trade
from database import SessionLocal
```

Add a wrapper near the existing `_safe_run_pattern_discovery`:

```python
BASELINE_DEFAULT_ACCOUNT_ID = int(os.getenv("BASELINE_ACCOUNT_ID", "0"))


async def _safe_open_baseline() -> None:
    try:
        async with SessionLocal() as session:
            await open_baseline_trade(
                session,
                account_id=BASELINE_DEFAULT_ACCOUNT_ID or None,
            )
    except Exception:
        logger.exception("baseline runner cron failed")
```

Inside `lifespan()`, after pattern discovery scheduler init:

```python
        if BASELINE_ENABLED:
            scheduler.add_job(
                _safe_open_baseline, "cron", hour=7, minute=0, timezone="UTC",
                id="baseline_london", replace_existing=True,
            )
            scheduler.add_job(
                _safe_open_baseline, "cron", hour=13, minute=0, timezone="UTC",
                id="baseline_ny", replace_existing=True,
            )
            scheduler.add_job(
                _safe_open_baseline, "cron", hour=22, minute=0, timezone="UTC",
                id="baseline_asia", replace_existing=True,
            )
```

Note: the existing scheduler init only fires when `PATTERN_DISCOVERY_ENABLED` is true. Refactor so the scheduler starts whenever **any** cron is enabled:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler: AsyncIOScheduler | None = None
    needs_scheduler = PATTERN_DISCOVERY_ENABLED or BASELINE_ENABLED
    if needs_scheduler:
        scheduler = AsyncIOScheduler(timezone="UTC")
        if PATTERN_DISCOVERY_ENABLED:
            scheduler.add_job(
                _safe_run_pattern_discovery, "cron", hour=0, minute=0,
                id="pattern_discovery_daily", replace_existing=True,
            )
        if BASELINE_ENABLED:
            for jid, hour in [("baseline_london", 7), ("baseline_ny", 13), ("baseline_asia", 22)]:
                scheduler.add_job(
                    _safe_open_baseline, "cron", hour=hour, minute=0, timezone="UTC",
                    id=jid, replace_existing=True,
                )
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    await engine.dispose()
```

- [ ] **Step 2: Run app smoke test**

```
docker compose up -d
docker compose logs api --tail 50
```

Expected: log line `Scheduler started` once. No exceptions.

```
docker compose down
```

- [ ] **Step 3: Commit**

```bash
git add api/main.py
git commit -m "feat: register baseline runner cron jobs (London/NY/Asia)"
```

---

## Task 5: Baseline stats — rolling winrate query

**Files:**
- Create: `api/services/baseline_stats.py`
- Test: `tests/test_baseline_stats.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_baseline_stats.py
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.baseline_runner import ensure_baseline_rule
from services.baseline_stats import get_baseline_winrate


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


def _baseline_trade(rule_id, close_time, profit, ticket):
    return Trade(
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=close_time - timedelta(hours=1),
        close_time=close_time,
        open_price=Decimal("1950"),
        close_price=Decimal("1955" if profit > 0 else "1945"),
        volume=Decimal("0.10"),
        profit=Decimal(str(profit)),
        is_paper=True,
        paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule_id), "is_baseline": True},
    )


@pytest.mark.asyncio
async def test_baseline_winrate_returns_zero_with_no_trades(session):
    await ensure_baseline_rule(session)
    assert await get_baseline_winrate(session, days=30) == 0.0


@pytest.mark.asyncio
async def test_baseline_winrate_three_of_five_wins(session):
    rule = await ensure_baseline_rule(session)
    base = datetime.now(timezone.utc) - timedelta(days=5)
    for i, profit in enumerate([10, -5, 15, -8, 20]):
        session.add(_baseline_trade(rule.id, base + timedelta(hours=i), profit, ticket=i + 100))
    await session.commit()
    assert await get_baseline_winrate(session, days=30) == 0.6


@pytest.mark.asyncio
async def test_baseline_winrate_excludes_outside_window(session):
    rule = await ensure_baseline_rule(session)
    old = datetime.now(timezone.utc) - timedelta(days=60)
    new = datetime.now(timezone.utc) - timedelta(days=2)
    session.add(_baseline_trade(rule.id, old, profit=10, ticket=1))
    session.add(_baseline_trade(rule.id, new, profit=-5, ticket=2))
    await session.commit()
    assert await get_baseline_winrate(session, days=30) == 0.0
```

- [ ] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_baseline_stats.py -v"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `baseline_stats.py`**

```python
# api/services/baseline_stats.py
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.pattern import PaperTraderRule
from models.trade import PaperMode, Trade

logger = logging.getLogger(__name__)

BASELINE_WINRATE_WINDOW_DAYS = int(os.getenv("BASELINE_WINRATE_WINDOW_DAYS", "30"))


async def _baseline_rule_id(session: AsyncSession) -> Optional[str]:
    result = await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.status == "active")
    )
    for rule in result.scalars().all():
        if getattr(rule, "is_baseline", False):
            return str(rule.id)
    # fallback — no flag column yet, infer via pattern
    return None


async def get_baseline_winrate(
    session: AsyncSession, days: Optional[int] = None
) -> float:
    """Rolling baseline winrate over the last `days` days. 0.0 when no data."""
    days = days or BASELINE_WINRATE_WINDOW_DAYS
    rule_id = await _baseline_rule_id(session)
    if rule_id is None:
        return 0.0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.independent,
            Trade.close_time.is_not(None),
            Trade.close_time >= cutoff,
        )
    )
    total = 0
    wins = 0
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        if plan.get("paper_trader_rule_id") != rule_id:
            continue
        total += 1
        if trade.profit is not None and trade.profit > 0:
            wins += 1
    return wins / total if total else 0.0
```

- [ ] **Step 4: Run to verify**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_baseline_stats.py -v"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/baseline_stats.py tests/test_baseline_stats.py
git commit -m "feat: rolling baseline winrate query"
```

---

## Task 6: Full regression

- [ ] **Step 1: Run all tests**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/ -v"
```

Expected: PASS.

- [ ] **Step 2: Smoke test app start**

```
docker compose up -d
docker compose logs api --tail 30 | grep -i scheduler
```

Expected: scheduler started, 3 baseline jobs registered (verify by checking job count via APScheduler logs or by hitting `/health` and tailing).

```
docker compose down
```

- [ ] **Step 3: Commit any test fixups**

```bash
git add -A tests/
git commit -m "test: regression sweep after baseline runner rollout"
```

---

## Out of scope for this plan

- Promotion gate's "beats baseline by ≥ 5%" check — Plan 7 imports `get_baseline_winrate()`.
- Migration 016 (`is_baseline`, `spawn_strategy` columns) — Plan 7 introduces it. Until then, rules are tagged via in-memory `_set_if_attr` with no-op fallback; the test fixtures use `Pattern.status == 'baseline'` to identify them.
- Per-session baseline (one rule per London/NY/Asia separately) — keep one global baseline; revisit if confounding becomes an issue.
