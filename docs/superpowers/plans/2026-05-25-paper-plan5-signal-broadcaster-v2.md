# Plan 5 — Signal Broadcaster + Console UI + Trust Badges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-25-paper-trade-system-redesign-v2.md` § "Component 5 — Signal broadcaster + Console UI" (carry-over) + § "Trust tier (4-badge UI)"

**Goal:** On every market tick, compute each active rule's signal status (`active` / `near` / `far` / `idle`) and write a row to `paper_signals` **only when status changes** (P3). Expose `/api/paper-signals` + `/api/paper-trader-rules` enriched with trust tier, age, and net EV. Build a `PaperTradeConsole` page that lists rules as cards, each with a 4-tier trust badge, age chip, sortable by trust + net EV. Browser notifications fire only for `live_proven` and `ea_candidate` rules.

**Architecture:**
- New `signal_broadcaster.py` — called from `/api/market-tick` immediately after `paper_trader.run_paper_trader()`. Reads in-memory `_last_signal_status` (per rule) and only emits a `paper_signals` row when status differs.
- `paper_trader_rules.last_signal_status` is updated in-place so the broadcaster can recover state after a process restart by reading from DB.
- `/api/paper-signals?rule_id=X&since=...` returns recent broadcasts; `/api/paper-trader-rules` is enriched with `age_seconds`, `trust_tier`, `net_ev_per_trade`, `wilson_lower_95`, `baseline_delta` (last three live in `paper_trader_rules` as cached columns from migration 016, written by the promotion gate cron).
- Console UI: `PaperTradeConsole.jsx` mounted in `App.jsx`; cards render age chip + trust badge; filter chips for trust tier; sort by `(trust_tier_rank desc, net_ev desc)`. Browser noti is a thin gate over the existing pattern in `useTradeAlerts.js`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2, React + TailwindCSS, browser Notification API, pytest-asyncio + httpx.

---

## File Structure

| Path | Action | Purpose |
|------|--------|---------|
| `api/services/signal_broadcaster.py` | create | Status compute + status-change-only persistence |
| `api/routers/paper_signals.py` | create | `GET /api/paper-signals` |
| `api/routers/patterns.py` | modify | Enrich `/api/paper-trader-rules` with tier/age/EV |
| `api/schemas/paper_signal.py` | create | `PaperSignalResponse` |
| `api/schemas/pattern.py` | modify | Add tier/age/EV fields to `PaperTraderRuleResponse` |
| `api/routers/market_tick.py` | modify | Call `broadcast_signals()` after paper trader |
| `api/main.py` | modify | Include `paper_signals` router |
| `frontend/src/components/PaperTradeConsole.jsx` | create | Page-level wrapper; filter + sort + grid |
| `frontend/src/components/PaperRuleCard.jsx` | create | Individual rule card |
| `frontend/src/components/TrustTierBadge.jsx` | create | 4-tier coloured badge |
| `frontend/src/hooks/usePaperSignals.js` | create | Polls `/api/paper-trader-rules` + `/api/paper-signals` |
| `frontend/src/hooks/useTradeAlerts.js` | modify | Noti gate by trust tier |
| `frontend/src/App.jsx` | modify | Mount the console |
| `tests/test_signal_broadcaster.py` | create | Unit + integration |
| `tests/test_paper_signals_api.py` | create | API contract |

---

## Task 1: Signal broadcaster — status compute

**Files:**
- Create: `api/services/signal_broadcaster.py`
- Test: `tests/test_signal_broadcaster.py`

- [x] **Step 1: Write failing test for `compute_status()`**

```python
# tests/test_signal_broadcaster.py
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.signal_broadcaster import (
    SignalEvalInputs,
    STATUS_ACTIVE,
    STATUS_NEAR,
    STATUS_FAR,
    STATUS_IDLE,
    compute_status,
)


def test_status_active_when_all_match():
    inputs = SignalEvalInputs(matched_count=4, total_count=4, has_open_paper=False)
    assert compute_status(inputs) == STATUS_ACTIVE


def test_status_near_when_one_missing_of_three_or_more():
    inputs = SignalEvalInputs(matched_count=3, total_count=4, has_open_paper=False)
    assert compute_status(inputs) == STATUS_NEAR


def test_status_far_when_some_match_but_not_near():
    inputs = SignalEvalInputs(matched_count=2, total_count=5, has_open_paper=False)
    assert compute_status(inputs) == STATUS_FAR


def test_status_idle_when_no_match():
    inputs = SignalEvalInputs(matched_count=0, total_count=4, has_open_paper=False)
    assert compute_status(inputs) == STATUS_IDLE


def test_status_active_when_open_paper_overrides():
    inputs = SignalEvalInputs(matched_count=1, total_count=5, has_open_paper=True)
    assert compute_status(inputs) == STATUS_ACTIVE
```

- [x] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_signal_broadcaster.py -v -k status"
```

Expected: FAIL — module not found.

- [x] **Step 3: Implement `compute_status()`**

```python
# api/services/signal_broadcaster.py
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
```

- [x] **Step 4: Run to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_signal_broadcaster.py -v -k status"
```

Expected: PASS (5 tests).

- [x] **Step 5: Commit**

```bash
git add api/services/signal_broadcaster.py tests/test_signal_broadcaster.py
git commit -m "feat: paper signal status compute (active/near/far/idle)"
```

---

## Task 2: Signal broadcaster — status-change-only persistence

**Files:**
- Modify: `api/services/signal_broadcaster.py`
- Test: `tests/test_signal_broadcaster.py`

- [x] **Step 1: Write failing test**

Append to `tests/test_signal_broadcaster.py`:

```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from services.signal_broadcaster import (
    RuleEval,
    broadcast_status_changes,
    reset_broadcaster_state,
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


async def _seed_rule(session, status="active") -> PaperTraderRule:
    pattern = Pattern(
        indicator_slugs=["rsi_14", "ema_50"],
        timeframe="H1",
        win_rate=0.7,
        sample_count=20,
        status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(pattern_id=pattern.id, status=status, mode="strict")
    session.add(rule)
    await session.commit()
    return rule


@pytest.mark.asyncio
async def test_broadcasts_when_status_changes(session):
    reset_broadcaster_state()
    rule = await _seed_rule(session)

    evals = [
        RuleEval(
            rule_id=rule.id,
            inputs=SignalEvalInputs(matched_count=2, total_count=2, has_open_paper=False),
            matched_conditions=["rsi_14", "ema_50"],
            missing_conditions=[],
            score=80.0,
            suggested_lot=Decimal("0.05"),
        )
    ]
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    written = await broadcast_status_changes(session, evals, now=now)
    assert len(written) == 1
    assert written[0].status == STATUS_ACTIVE


@pytest.mark.asyncio
async def test_no_broadcast_when_status_unchanged(session):
    reset_broadcaster_state()
    rule = await _seed_rule(session)
    evals = [
        RuleEval(
            rule_id=rule.id,
            inputs=SignalEvalInputs(matched_count=2, total_count=2, has_open_paper=False),
            matched_conditions=["rsi_14", "ema_50"],
            missing_conditions=[],
        )
    ]
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    await broadcast_status_changes(session, evals, now=now)
    second = await broadcast_status_changes(session, evals, now=now)
    assert second == []


@pytest.mark.asyncio
async def test_broadcasts_again_when_status_flips(session):
    reset_broadcaster_state()
    rule = await _seed_rule(session)
    e_active = [RuleEval(
        rule_id=rule.id,
        inputs=SignalEvalInputs(matched_count=2, total_count=2, has_open_paper=False),
        matched_conditions=["rsi_14", "ema_50"], missing_conditions=[],
    )]
    e_far = [RuleEval(
        rule_id=rule.id,
        inputs=SignalEvalInputs(matched_count=1, total_count=4, has_open_paper=False),
        matched_conditions=["rsi_14"], missing_conditions=["ema_50", "macd", "atr"],
    )]
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    await broadcast_status_changes(session, e_active, now=now)
    flipped = await broadcast_status_changes(session, e_far, now=now)
    assert len(flipped) == 1
    assert flipped[0].status == STATUS_FAR
```

- [x] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_signal_broadcaster.py -v"
```

Expected: FAIL — `RuleEval`/`broadcast_status_changes` not defined.

- [x] **Step 3: Implement `broadcast_status_changes()`**

Append to `api/services/signal_broadcaster.py`:

```python
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
```

- [x] **Step 4: Run to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_signal_broadcaster.py -v"
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add api/services/signal_broadcaster.py tests/test_signal_broadcaster.py
git commit -m "feat: status-change-only paper signal persistence"
```

---

## Task 3: Wire broadcaster into the market-tick path

**Files:**
- Modify: `api/services/paper_trader.py` — return per-rule eval data
- Modify: `api/routers/market_tick.py`
- Test: `tests/test_signal_broadcaster.py`

- [x] **Step 1: Add a function that turns the paper-trader cache into a `list[RuleEval]`**

In `api/services/paper_trader.py`, add a public helper at module level:

```python
def evals_for_broadcaster(
    rules: list[_RuleSnapshot],
    cache: dict[tuple[str, str], tuple[Optional[float], str, dict]],
    open_by_rule: dict[uuid.UUID, list["Trade"]],
) -> list:
    from services.signal_broadcaster import RuleEval, SignalEvalInputs

    out = []
    for rule in rules:
        matched: list[str] = []
        missing: list[str] = []
        for slug in rule.indicator_slugs:
            item = cache.get((slug, rule.timeframe)) or cache.get((slug, DEFAULT_TIMEFRAME))
            direction = item[1] if item else "neutral"
            if direction == "neutral":
                missing.append(slug)
            else:
                matched.append(slug)
        out.append(
            RuleEval(
                rule_id=rule.rule_id,
                inputs=SignalEvalInputs(
                    matched_count=len(matched),
                    total_count=len(rule.indicator_slugs),
                    has_open_paper=bool(open_by_rule.get(rule.rule_id)),
                ),
                matched_conditions=matched,
                missing_conditions=missing,
            )
        )
    return out
```

Modify `run_paper_trader()` to also return these evals:

```python
async def run_paper_trader(
    session: AsyncSession, tick: MarketTickSchema
) -> dict:
    if not PAPER_TRADER_ENABLED:
        return {"opened": 0, "closed": 0, "skipped": "disabled", "evals": []}

    rules = await load_active_rules(session, tick.timestamp)
    if not rules:
        return {"opened": 0, "closed": 0, "evals": []}

    timeframes = {rule.timeframe for rule in rules}
    bars_by_tf: dict[str, list[PriceBar]] = {}
    for tf in timeframes:
        bars_by_tf[tf] = await _fetch_bars(session, tick.symbol, tf, tick.timestamp)

    cache = _build_indicator_cache(rules, bars_by_tf, tick.timestamp)
    open_by_rule = await _open_papers_for_rules(session, [r.rule_id for r in rules])
    closed = await _check_exits(session, tick, rules, bars_by_tf, open_by_rule, cache)
    opened = await _check_entries(session, tick, rules, bars_by_tf, open_by_rule, cache)

    if opened or closed:
        await session.commit()

    return {
        "opened": len(opened),
        "closed": len(closed),
        "evals": evals_for_broadcaster(rules, cache, open_by_rule),
    }
```

- [x] **Step 2: Wire `broadcast_status_changes()` into `routers/market_tick.py`**

Read the existing router first:

```
grep -n "" api/routers/market_tick.py
```

Then replace the handler so it calls the broadcaster after the paper trader:

```python
# api/routers/market_tick.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.market_tick import MarketTickSchema
from services.paper_trader import run_paper_trader
from services.signal_broadcaster import broadcast_status_changes
from services.spread_buffer import push_spread  # added in Plan 4

router = APIRouter(prefix="/api", tags=["market-tick"])


@router.post("/market-tick")
async def post_market_tick(
    payload: MarketTickSchema,
    session: AsyncSession = Depends(get_session),
):
    push_spread(payload.ask - payload.bid)
    result = await run_paper_trader(session, payload)
    evals = result.pop("evals", [])
    if evals:
        written = await broadcast_status_changes(session, evals, now=payload.timestamp)
        result["signals_emitted"] = len(written)
    return result
```

(If `push_spread` does not yet exist because Plan 4 hasn't landed, gate the import with a try/except — see comment in `market_tick.py` at integration time.)

- [x] **Step 3: Run market-tick test if exists; otherwise skip**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/ -v -k market_tick"
```

Expected: PASS or no tests collected.

- [x] **Step 4: Commit**

```bash
git add api/services/paper_trader.py api/routers/market_tick.py
git commit -m "feat: wire signal broadcaster into market tick handler"
```

---

## Task 4: `/api/paper-signals` router

**Files:**
- Create: `api/schemas/paper_signal.py`
- Create: `api/routers/paper_signals.py`
- Modify: `api/main.py`
- Test: `tests/test_paper_signals_api.py`

- [x] **Step 1: Write failing test**

```python
# tests/test_paper_signals_api.py
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base, get_session
from main import app
from models.paper_signal import PaperSignal
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
            indicator_slugs=["rsi", "ema"], timeframe="H1",
            win_rate=0.6, sample_count=20, status="active",
        )
        setup.add(pattern)
        await setup.flush()
        rule = PaperTraderRule(pattern_id=pattern.id, status="active", mode="strict")
        setup.add(rule)
        await setup.flush()
        for i, status in enumerate(["far", "near", "active"]):
            setup.add(PaperSignal(
                rule_id=rule.id, status=status, match_pct=Decimal("0.5"),
                matched_conditions=["rsi"], missing_conditions=["ema"],
                emitted_at=datetime(2026, 5, 25, 12, i, tzinfo=timezone.utc),
            ))
        await setup.commit()
        rule_id = rule.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, rule_id
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_list_paper_signals_for_rule(client):
    c, rule_id = client
    res = await c.get(f"/api/paper-signals?rule_id={rule_id}")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    statuses = [d["status"] for d in data]
    assert statuses == ["active", "near", "far"]  # newest first


@pytest.mark.asyncio
async def test_list_paper_signals_since_filter(client):
    c, rule_id = client
    cutoff = datetime(2026, 5, 25, 12, 1, tzinfo=timezone.utc).isoformat()
    res = await c.get(f"/api/paper-signals?rule_id={rule_id}&since={cutoff}")
    data = res.json()
    statuses = [d["status"] for d in data]
    assert "far" not in statuses
```

- [x] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_signals_api.py -v"
```

Expected: FAIL with 404.

- [x] **Step 3: Schema**

```python
# api/schemas/paper_signal.py
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PaperSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_id: UUID
    status: str
    match_pct: Decimal
    matched_conditions: list[str]
    missing_conditions: list[str]
    score: Optional[Decimal] = None
    suggested_lot: Optional[Decimal] = None
    emitted_at: datetime
```

- [x] **Step 4: Router**

```python
# api/routers/paper_signals.py
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.paper_signal import PaperSignal
from schemas.paper_signal import PaperSignalResponse

router = APIRouter(prefix="/api", tags=["paper-signals"])

DEFAULT_LIMIT = 200


@router.get("/paper-signals", response_model=list[PaperSignalResponse])
async def list_paper_signals(
    rule_id: Optional[UUID] = Query(None),
    since: Optional[datetime] = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(PaperSignal).order_by(PaperSignal.emitted_at.desc()).limit(limit)
    if rule_id is not None:
        stmt = stmt.where(PaperSignal.rule_id == rule_id)
    if since is not None:
        stmt = stmt.where(PaperSignal.emitted_at > since)
    result = await session.execute(stmt)
    return result.scalars().all()
```

- [x] **Step 5: Register the router**

In `api/main.py`:

```python
from routers.paper_signals import router as paper_signals_router
...
app.include_router(paper_signals_router)
```

- [x] **Step 6: Run to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_signals_api.py -v"
```

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add api/schemas/paper_signal.py api/routers/paper_signals.py api/main.py \
        tests/test_paper_signals_api.py
git commit -m "feat: GET /api/paper-signals endpoint"
```

---

## Task 5: Enrich `/api/paper-trader-rules` with trust tier + age + EV

**Files:**
- Modify: `api/schemas/pattern.py`
- Modify: `api/routers/patterns.py`

- [x] **Step 1: Write failing test**

Add to `tests/test_paper_signals_api.py`:

```python
@pytest.mark.asyncio
async def test_paper_trader_rule_response_includes_trust_tier(client):
    c, rule_id = client
    res = await c.get("/api/paper-trader-rules")
    assert res.status_code == 200
    rules = res.json()
    assert any(r["id"] == str(rule_id) for r in rules)
    sample = [r for r in rules if r["id"] == str(rule_id)][0]
    for key in ("trust_tier", "age_seconds", "net_ev_per_trade",
                 "wilson_lower_95", "baseline_delta", "mode"):
        assert key in sample
```

- [x] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_signals_api.py::test_paper_trader_rule_response_includes_trust_tier -v"
```

Expected: FAIL — fields missing.

- [x] **Step 3: Read current schema** then modify `api/schemas/pattern.py` to add fields:

```python
# Append/modify in api/schemas/pattern.py — preserve existing fields
class PaperTraderRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pattern_id: UUID
    status: str
    spawned_at: datetime
    total_trades: int
    win_count: int
    mode: str = "strict"
    trust_tier: str = "experimental"
    age_seconds: int = 0
    net_ev_per_trade: Optional[Decimal] = None
    wilson_lower_95: Optional[Decimal] = None
    baseline_delta: Optional[Decimal] = None
    last_signal_status: Optional[str] = None
```

(Imports: `from decimal import Decimal`, `from typing import Optional`, `from datetime import datetime`, `from uuid import UUID`.)

- [x] **Step 4: Modify `api/routers/patterns.py` to compute `age_seconds` per rule**

```python
# api/routers/patterns.py — replace the list_paper_trader_rules() body
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
            )
        )
    return out
```

- [x] **Step 5: Run to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_signals_api.py -v"
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add api/schemas/pattern.py api/routers/patterns.py tests/test_paper_signals_api.py
git commit -m "feat: enrich paper-trader-rules response with trust tier, age, EV"
```

---

## Task 6: Frontend — TrustTierBadge component

**Files:**
- Create: `frontend/src/components/TrustTierBadge.jsx`

- [x] **Step 1: Implement the component**

```jsx
// frontend/src/components/TrustTierBadge.jsx
const TIER_META = {
  ea_candidate: { label: '🎯 EA Candidate', cls: 'bg-yellow-600 text-yellow-50' },
  live_proven: { label: '★ Live Proven', cls: 'bg-emerald-700 text-emerald-50' },
  validated: { label: '✓ Validated', cls: 'bg-blue-700 text-blue-50' },
  experimental: { label: '🧪 Experimental', cls: 'bg-gray-700 text-gray-200' },
}

export default function TrustTierBadge({ tier }) {
  const meta = TIER_META[tier] || TIER_META.experimental
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${meta.cls}`}>
      {meta.label}
    </span>
  )
}

export const TIER_RANK = {
  ea_candidate: 4,
  live_proven: 3,
  validated: 2,
  experimental: 1,
}
```

- [x] **Step 2: Commit**

```bash
git add frontend/src/components/TrustTierBadge.jsx
git commit -m "feat: TrustTierBadge component"
```

---

## Task 7: Frontend — PaperRuleCard component

**Files:**
- Create: `frontend/src/components/PaperRuleCard.jsx`

- [x] **Step 1: Implement card**

```jsx
// frontend/src/components/PaperRuleCard.jsx
import TrustTierBadge from './TrustTierBadge'

const STATUS_DOT = {
  active: 'bg-emerald-500',
  near: 'bg-amber-400',
  far: 'bg-gray-500',
  idle: 'bg-gray-700',
}

function ageChip(seconds) {
  if (!seconds || seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}

export default function PaperRuleCard({ rule, pattern }) {
  const dot = STATUS_DOT[rule.last_signal_status] || STATUS_DOT.idle
  const ev = rule.net_ev_per_trade != null
    ? `฿${Number(rule.net_ev_per_trade).toFixed(0)}`
    : '—'
  const wilson = rule.wilson_lower_95 != null
    ? `${(Number(rule.wilson_lower_95) * 100).toFixed(0)}%`
    : '—'
  const baseline = rule.baseline_delta != null
    ? `${Number(rule.baseline_delta) >= 0 ? '+' : ''}${(Number(rule.baseline_delta) * 100).toFixed(1)}%`
    : '—'
  return (
    <div className="bg-gray-900 border border-gray-800 rounded p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${dot}`} />
          <span className="text-sm font-medium">{rule.mode}</span>
          <span className="text-xs text-gray-400">[{ageChip(rule.age_seconds)}]</span>
        </div>
        <TrustTierBadge tier={rule.trust_tier} />
      </div>
      <div className="text-xs text-gray-400">
        {pattern?.indicator_slugs?.join(' + ') || '—'}
      </div>
      <div className="flex justify-between text-xs">
        <div>Net EV: <span className="text-gray-100">{ev}</span>/trade</div>
        <div>Wilson: <span className="text-gray-100">{wilson}</span></div>
        <div>vs Baseline: <span className="text-gray-100">{baseline}</span></div>
      </div>
      <div className="text-xs text-gray-500">
        Trades {rule.total_trades} · Wins {rule.win_count}
      </div>
    </div>
  )
}
```

- [x] **Step 2: Commit**

```bash
git add frontend/src/components/PaperRuleCard.jsx
git commit -m "feat: PaperRuleCard component"
```

---

## Task 8: Frontend — usePaperSignals hook + console page

**Files:**
- Create: `frontend/src/hooks/usePaperSignals.js`
- Create: `frontend/src/components/PaperTradeConsole.jsx`
- Modify: `frontend/src/App.jsx`

- [x] **Step 1: Implement hook**

```jsx
// frontend/src/hooks/usePaperSignals.js
import { usePolling } from './usePolling'
import { useCallback } from 'react'

const API = 'http://localhost:8000'

async function get(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function usePaperRules() {
  const fetcher = useCallback(() => get('/api/paper-trader-rules?status=active'), [])
  return usePolling(fetcher, 5000)
}

export function usePatternsById() {
  const fetcher = useCallback(() => get('/api/patterns'), [])
  const { data, ...rest } = usePolling(fetcher, 30000)
  const byId = {}
  for (const p of data || []) byId[p.id] = p
  return { byId, ...rest }
}
```

- [x] **Step 2: Implement console page**

```jsx
// frontend/src/components/PaperTradeConsole.jsx
import { useMemo, useState } from 'react'
import PaperRuleCard from './PaperRuleCard'
import { TIER_RANK } from './TrustTierBadge'
import { usePaperRules, usePatternsById } from '../hooks/usePaperSignals'

const TIER_FILTERS = ['all', 'ea_candidate', 'live_proven', 'validated', 'experimental']

export default function PaperTradeConsole() {
  const [tierFilter, setTierFilter] = useState('all')
  const rules = usePaperRules()
  const { byId: patternsById } = usePatternsById()

  const sorted = useMemo(() => {
    const list = (rules.data || []).slice()
    list.sort((a, b) => {
      const ta = TIER_RANK[a.trust_tier] || 0
      const tb = TIER_RANK[b.trust_tier] || 0
      if (ta !== tb) return tb - ta
      const ea = Number(a.net_ev_per_trade ?? -Infinity)
      const eb = Number(b.net_ev_per_trade ?? -Infinity)
      return eb - ea
    })
    if (tierFilter !== 'all') {
      return list.filter((r) => r.trust_tier === tierFilter)
    }
    return list
  }, [rules.data, tierFilter])

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Paper Trade Console</h2>
        <div className="flex gap-2 flex-wrap">
          {TIER_FILTERS.map((t) => (
            <button
              key={t}
              onClick={() => setTierFilter(t)}
              className={`px-2 py-1 text-xs rounded ${
                t === tierFilter ? 'bg-blue-600' : 'bg-gray-800'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      {rules.error && (
        <div className="text-xs text-red-400">Failed to load rules</div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {sorted.map((r) => (
          <PaperRuleCard key={r.id} rule={r} pattern={patternsById[r.pattern_id]} />
        ))}
      </div>
    </section>
  )
}
```

- [x] **Step 3: Mount in `App.jsx`**

In `frontend/src/App.jsx`, add the import and mount it after `PnlChart`:

```jsx
import PaperTradeConsole from './components/PaperTradeConsole'
...
      <PnlChart data={pnlHistory.data} error={pnlHistory.error} />
      <PaperTradeConsole />
      <section>
```

- [x] **Step 4: Smoke test in the browser**

```
docker compose up -d
```

Open `http://localhost:3000`. The console section should render below the PnL chart. With no rules in the DB the grid is empty (this is expected).

- [x] **Step 5: Commit**

```bash
git add frontend/src/hooks/usePaperSignals.js \
        frontend/src/components/PaperTradeConsole.jsx \
        frontend/src/App.jsx
git commit -m "feat: PaperTradeConsole with tier filter + sort"
```

---

## Task 9: Browser noti gate — only fire for live_proven / ea_candidate

**Files:**
- Modify: `frontend/src/hooks/useTradeAlerts.js`

- [x] **Step 1: Read existing file** to understand current notification behavior

```
grep -n "" frontend/src/hooks/useTradeAlerts.js
```

- [x] **Step 2: Add a separate hook `usePaperSignalNotifications`**

Append to `frontend/src/hooks/usePaperSignals.js`:

```jsx
import { useEffect, useRef } from 'react'

const NOTIFY_TIERS = new Set(['live_proven', 'ea_candidate'])
const NOTIFY_STATUSES = new Set(['near', 'active'])

export function usePaperSignalNotifications(rules) {
  const lastSeen = useRef({})
  useEffect(() => {
    if (typeof Notification === 'undefined') return
    if (Notification.permission === 'default') Notification.requestPermission()
  }, [])

  useEffect(() => {
    if (!rules) return
    if (typeof Notification === 'undefined') return
    if (Notification.permission !== 'granted') return
    for (const r of rules) {
      if (!NOTIFY_TIERS.has(r.trust_tier)) continue
      if (!NOTIFY_STATUSES.has(r.last_signal_status)) continue
      if (lastSeen.current[r.id] === r.last_signal_status) continue
      lastSeen.current[r.id] = r.last_signal_status
      new Notification(`${r.mode} signal ${r.last_signal_status}`, {
        body: `Trust: ${r.trust_tier} · Net EV: ฿${Number(r.net_ev_per_trade ?? 0).toFixed(0)}`,
        tag: `paper-rule-${r.id}-${r.last_signal_status}`,
      })
    }
  }, [rules])
}
```

- [x] **Step 3: Wire it into `PaperTradeConsole`**

In `frontend/src/components/PaperTradeConsole.jsx`, import and call:

```jsx
import { usePaperRules, usePatternsById, usePaperSignalNotifications } from '../hooks/usePaperSignals'

export default function PaperTradeConsole() {
  ...
  const rules = usePaperRules()
  usePaperSignalNotifications(rules.data)
  ...
}
```

- [x] **Step 4: Smoke test** — temporarily set a rule's `trust_tier='live_proven'` + `last_signal_status='near'` in the DB; reload UI; expect a browser notification once permission is granted.

- [x] **Step 5: Commit**

```bash
git add frontend/src/hooks/usePaperSignals.js \
        frontend/src/components/PaperTradeConsole.jsx
git commit -m "feat: gate browser noti by trust tier (live_proven/ea_candidate)"
```

---

## Task 10: Full regression

- [x] **Step 1: Backend tests**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/ -v"
```

Expected: PASS.

- [x] **Step 2: Frontend smoke**

Start dev server, open browser, verify:
- `PaperTradeConsole` renders below `PnlChart`
- Filter chips toggle the visible cards
- An EA-Candidate-tier rule with `last_signal_status='near'` triggers a browser notification

- [x] **Step 3: Commit if any test fixups**

```bash
git add -A tests/ frontend/
git commit -m "test: regression sweep after broadcaster + console rollout"
```

---

## Out of scope for this plan

- Computing `trust_tier`, `net_ev_per_trade`, `wilson_lower_95`, `baseline_delta` — Plan 7 (promotion gate) writes these.
- Baseline rule auto-spawn — Plan 6.
- Adaptive shadow rules — Plan 8.
