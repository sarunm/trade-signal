# Paper Rule Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ขยาย `PaperRuleCard` เป็น collapsed-with-richer-summary + click-to-expand drawer ที่รวบ trades / signals / shadows / gates / pattern conditions ของรูลเดียวไว้ในที่เดียว.

**Architecture:** Backend reuses existing endpoints + extends `PaperTraderRuleResponse` กับ 4 fields (`virtual_balance_start`, `virtual_balance_current`, `open_trades_count`, `last_activity_at`). Frontend แตก `PaperRuleCard.jsx` เป็น collapsed shell + `PaperRuleDrawer.jsx` ที่ mount เฉพาะตอนเปิด, ใช้ `usePolling` (custom hook ที่มีอยู่แล้ว) สำหรับ list และ on-demand fetch + manual refresh ใน drawer.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async + Alembic; React 18 + Vite + TailwindCSS; pytest + pytest-asyncio + httpx (no frontend test framework — verify with `npm run build` + manual smoke).

**Spec ref:** `docs/superpowers/specs/2026-05-26-paper-rule-drawer-design.md`

---

## File Structure

**Backend (modify only):**
- `api/schemas/pattern.py` — add 4 fields to `PaperTraderRuleResponse`
- `api/routers/patterns.py` — compute `open_trades_count` + `last_activity_at` in `list_paper_trader_rules` (batched, no N+1)

**Backend (test):**
- `tests/test_paper_trader_rules_extended.py` — new test file for the 4 new fields

**Frontend (modify):**
- `frontend/src/components/PaperRuleCard.jsx` — rewrite collapsed view; add expand caret + open-state; render `<PaperRuleDrawer>` when open
- `frontend/src/hooks/usePaperSignals.js` — extend exports with on-demand `fetchPaperRuleDetail(ruleId, patternId)` (no polling — drawer fetches on open + on manual refresh)

**Frontend (create):**
- `frontend/src/components/PaperRuleDrawer.jsx` — shell with header, refresh button, 6 sections
- `frontend/src/components/drawer/SignalTrail.jsx` — colored dots for last 20 signals
- `frontend/src/components/drawer/OrdersTable.jsx` — renders active + closed lists (one component, two modes)
- `frontend/src/components/drawer/PatternConditions.jsx` — indicator slugs + filters + score weights
- `frontend/src/components/drawer/PromotionGates.jsx` — 4-gate breakdown
- `frontend/src/components/drawer/ShadowsList.jsx` — parent vs shadow comparison

---

## Task 1: Extend `PaperTraderRuleResponse` schema with 4 new fields

**Files:**
- Modify: `api/schemas/pattern.py:23-47`
- Test: `tests/test_paper_trader_rules_extended.py` (new)

- [ ] **Step 1: Write the failing test for schema fields**

Create `tests/test_paper_trader_rules_extended.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from models.pattern import Pattern, PaperTraderRule


@pytest.mark.asyncio
async def test_list_rules_returns_balance_and_activity_fields(client, db_session):
    pattern = Pattern(
        id=uuid4(),
        indicator_slugs=["rsi_14"],
        timeframe="M15",
        win_rate=0.6,
        sample_count=20,
        consecutive_stable_days=3,
        status="active",
        discovered_at=datetime.now(timezone.utc),
    )
    rule = PaperTraderRule(
        id=uuid4(),
        pattern_id=pattern.id,
        status="active",
        spawned_at=datetime.now(timezone.utc),
        total_trades=10,
        win_count=6,
        virtual_balance_start=Decimal("5000.00"),
        virtual_balance_current=Decimal("5240.50"),
    )
    db_session.add_all([pattern, rule])
    await db_session.commit()

    res = await client.get("/api/paper-trader-rules")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    row = body[0]
    assert row["virtual_balance_start"] == "5000.00"
    assert row["virtual_balance_current"] == "5240.50"
    assert row["open_trades_count"] == 0
    assert row["last_activity_at"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_paper_trader_rules_extended.py -v"`

Expected: FAIL — response JSON missing `virtual_balance_start`, `virtual_balance_current`, `open_trades_count`, `last_activity_at` keys.

- [ ] **Step 3: Add fields to schema**

Modify `api/schemas/pattern.py`. Replace existing `PaperTraderRuleResponse`:

```python
class PaperTraderRuleResponse(BaseModel):
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
    filters: list[dict] = []
    shadow_of_rule_id: Optional[UUID] = None
    virtual_balance_start: Optional[Decimal] = None
    virtual_balance_current: Optional[Decimal] = None
    open_trades_count: int = 0
    last_activity_at: Optional[datetime] = None

    @computed_field
    @property
    def win_rate(self) -> Optional[float]:
        if self.total_trades == 0:
            return None
        return self.win_count / self.total_trades

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Wire fields into the list builder (without computing the new ones yet)**

Modify `api/routers/patterns.py:46-71`. Update the `out.append(...)` block to include the 4 new fields. Replace the entire `for r in rules:` loop with:

```python
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
                filters=list(getattr(r, "filters", None) or []),
                shadow_of_rule_id=getattr(r, "shadow_of_rule_id", None),
                virtual_balance_start=getattr(r, "virtual_balance_start", None),
                virtual_balance_current=getattr(r, "virtual_balance_current", None),
                open_trades_count=0,
                last_activity_at=None,
            )
        )
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_paper_trader_rules_extended.py -v"`

Expected: PASS — schema now contains the 4 new keys; `open_trades_count=0` and `last_activity_at=None` match the test assertions.

- [ ] **Step 6: Run full backend suite**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -v --tb=short"`

Expected: All tests pass (no regression).

- [ ] **Step 7: Commit**

```bash
git add api/schemas/pattern.py api/routers/patterns.py tests/test_paper_trader_rules_extended.py
git commit -m "feat(api): expose virtual balance + open count + last activity on paper rules"
```

---

## Task 2: Compute `open_trades_count` (batched, no N+1)

**Files:**
- Modify: `api/routers/patterns.py:33-71` (`list_paper_trader_rules`)
- Test: `tests/test_paper_trader_rules_extended.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_paper_trader_rules_extended.py`:

```python
from models.trade import PaperMode, Trade


@pytest.mark.asyncio
async def test_open_trades_count_per_rule(client, db_session):
    pattern = Pattern(
        id=uuid4(),
        indicator_slugs=["rsi_14"],
        timeframe="M15",
        win_rate=0.6,
        sample_count=20,
        consecutive_stable_days=3,
        status="active",
        discovered_at=datetime.now(timezone.utc),
    )
    rule_a = PaperTraderRule(
        id=uuid4(), pattern_id=pattern.id, status="active",
        spawned_at=datetime.now(timezone.utc),
        total_trades=0, win_count=0,
    )
    rule_b = PaperTraderRule(
        id=uuid4(), pattern_id=pattern.id, status="active",
        spawned_at=datetime.now(timezone.utc),
        total_trades=0, win_count=0,
    )
    open1 = Trade(
        id=uuid4(), ticket=1001, symbol="XAUUSD",
        is_paper=True, paper_mode=PaperMode.independent,
        open_time=datetime.now(timezone.utc),
        recovery_plan={"paper_trader_rule_id": str(rule_a.id)},
    )
    open2 = Trade(
        id=uuid4(), ticket=1002, symbol="XAUUSD",
        is_paper=True, paper_mode=PaperMode.independent,
        open_time=datetime.now(timezone.utc),
        recovery_plan={"paper_trader_rule_id": str(rule_a.id)},
    )
    closed = Trade(
        id=uuid4(), ticket=1003, symbol="XAUUSD",
        is_paper=True, paper_mode=PaperMode.independent,
        open_time=datetime.now(timezone.utc),
        close_time=datetime.now(timezone.utc),
        recovery_plan={"paper_trader_rule_id": str(rule_a.id)},
    )
    db_session.add_all([pattern, rule_a, rule_b, open1, open2, closed])
    await db_session.commit()

    res = await client.get("/api/paper-trader-rules")
    body = {row["id"]: row for row in res.json()}
    assert body[str(rule_a.id)]["open_trades_count"] == 2
    assert body[str(rule_b.id)]["open_trades_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_paper_trader_rules_extended.py::test_open_trades_count_per_rule -v"`

Expected: FAIL — assertion `2 == 0` because handler always sets `open_trades_count=0`.

- [ ] **Step 3: Implement the batched count**

Modify `api/routers/patterns.py`. Add this helper above `list_paper_trader_rules`:

```python
async def _open_trades_count_by_rule(session: AsyncSession) -> dict[str, int]:
    """Return {rule_id_str: open_count} for all paper trades currently open."""
    stmt = select(Trade).where(
        Trade.is_paper.is_(True),
        Trade.close_time.is_(None),
    )
    result = await session.execute(stmt)
    counts: dict[str, int] = {}
    for trade in result.scalars().all():
        plan = trade.recovery_plan or {}
        rid = plan.get("paper_trader_rule_id") if isinstance(plan, dict) else None
        if not rid:
            continue
        counts[rid] = counts.get(rid, 0) + 1
    return counts
```

Then in `list_paper_trader_rules`, before the `for r in rules:` loop, fetch the counts once:

```python
    open_counts = await _open_trades_count_by_rule(session)
```

And replace `open_trades_count=0,` with:

```python
                open_trades_count=open_counts.get(str(r.id), 0),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_paper_trader_rules_extended.py -v"`

Expected: PASS for both tests in the file.

- [ ] **Step 5: Run full backend suite**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -v --tb=short"`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add api/routers/patterns.py tests/test_paper_trader_rules_extended.py
git commit -m "feat(api): compute open_trades_count per paper rule (batched)"
```

---

## Task 3: Compute `last_activity_at` from paper_signals

**Files:**
- Modify: `api/routers/patterns.py` (helper + builder)
- Test: `tests/test_paper_trader_rules_extended.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_paper_trader_rules_extended.py`:

```python
from decimal import Decimal as D
from models.paper_signal import PaperSignal


@pytest.mark.asyncio
async def test_last_activity_at_uses_latest_paper_signal(client, db_session):
    pattern = Pattern(
        id=uuid4(),
        indicator_slugs=["rsi_14"],
        timeframe="M15",
        win_rate=0.6,
        sample_count=20,
        consecutive_stable_days=3,
        status="active",
        discovered_at=datetime.now(timezone.utc),
    )
    rule = PaperTraderRule(
        id=uuid4(), pattern_id=pattern.id, status="active",
        spawned_at=datetime.now(timezone.utc),
        total_trades=0, win_count=0,
    )
    older = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    s1 = PaperSignal(
        id=uuid4(), rule_id=rule.id, status="near",
        match_pct=D("0.80"),
        matched_conditions=["a"], missing_conditions=["b"],
        emitted_at=older,
    )
    s2 = PaperSignal(
        id=uuid4(), rule_id=rule.id, status="active",
        match_pct=D("1.00"),
        matched_conditions=["a", "b"], missing_conditions=[],
        emitted_at=newer,
    )
    db_session.add_all([pattern, rule, s1, s2])
    await db_session.commit()

    res = await client.get("/api/paper-trader-rules")
    row = next(r for r in res.json() if r["id"] == str(rule.id))
    assert row["last_activity_at"] is not None
    assert row["last_activity_at"].startswith("2026-05-26T12:00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_paper_trader_rules_extended.py::test_last_activity_at_uses_latest_paper_signal -v"`

Expected: FAIL — `last_activity_at` is None.

- [ ] **Step 3: Implement the batched lookup**

In `api/routers/patterns.py`, add another helper above `list_paper_trader_rules`:

```python
from sqlalchemy import func
from models.paper_signal import PaperSignal


async def _last_activity_by_rule(session: AsyncSession) -> dict[str, datetime]:
    """Return {rule_id_str: latest emitted_at} from paper_signals."""
    stmt = select(
        PaperSignal.rule_id,
        func.max(PaperSignal.emitted_at).label("last_at"),
    ).group_by(PaperSignal.rule_id)
    result = await session.execute(stmt)
    return {str(rid): last_at for rid, last_at in result.all()}
```

Then in `list_paper_trader_rules`, alongside `open_counts`:

```python
    last_activity = await _last_activity_by_rule(session)
```

Replace `last_activity_at=None,` in the response builder with:

```python
                last_activity_at=last_activity.get(str(r.id)),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_paper_trader_rules_extended.py -v"`

Expected: PASS for all tests in the file.

- [ ] **Step 5: Run full backend suite**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -v --tb=short"`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add api/routers/patterns.py tests/test_paper_trader_rules_extended.py
git commit -m "feat(api): compute last_activity_at per paper rule from paper_signals"
```

---

## Task 4: Frontend — collapsed `PaperRuleCard` redesign with expand caret

**Files:**
- Modify: `frontend/src/components/PaperRuleCard.jsx` (full rewrite of return block)

- [ ] **Step 1: Replace `PaperRuleCard.jsx` with the new collapsed layout + expand state**

Replace the entire file `frontend/src/components/PaperRuleCard.jsx` with:

```jsx
import { useState } from 'react'
import TrustTierBadge from './TrustTierBadge'
import PaperRuleDrawer from './PaperRuleDrawer'

const ALIVE_DOT = {
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

function aliveTone(rule) {
  const last = rule.last_activity_at ? new Date(rule.last_activity_at).getTime() : 0
  const ageMs = last ? Date.now() - last : Infinity
  if (rule.last_signal_status === 'active') return 'active'
  if (rule.last_signal_status === 'near') return 'near'
  if (ageMs > 30 * 60 * 1000) return 'idle'
  return rule.last_signal_status || 'idle'
}

function formatBaht(n) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `${sign}฿${Math.round(v).toLocaleString()}`
}

export default function PaperRuleCard({ rule, pattern }) {
  const [open, setOpen] = useState(false)
  const tone = aliveTone(rule)
  const dot = ALIVE_DOT[tone] || ALIVE_DOT.idle

  const start = Number(rule.virtual_balance_start ?? 0)
  const current = Number(rule.virtual_balance_current ?? 0)
  const cumPnl = current - start
  const cumPct = start > 0 ? (cumPnl / start) * 100 : 0
  const balanceTone = current < start ? 'text-red-400' : 'text-gray-100'
  const pnlTone = cumPnl > 0 ? 'text-emerald-400' : cumPnl < 0 ? 'text-red-400' : 'text-gray-300'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded p-3 space-y-2">
      <button
        type="button"
        className="w-full flex items-center justify-between"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${dot}`} />
          <span className="text-sm font-medium">{rule.mode}</span>
          <span className="text-xs text-gray-400">[{ageChip(rule.age_seconds)}]</span>
        </div>
        <div className="flex items-center gap-2">
          <TrustTierBadge tier={rule.trust_tier} />
          <span className="text-gray-500 text-xs">{open ? '▴' : '▾'}</span>
        </div>
      </button>
      <div className="text-xs text-gray-400 text-left">
        {pattern?.indicator_slugs?.join(' + ') || '—'}
      </div>
      <div className="flex justify-between text-xs">
        <div>Open: <span className="text-gray-100">{rule.open_trades_count ?? 0}</span></div>
        <div>
          Balance: <span className={balanceTone}>฿{Math.round(current).toLocaleString()}</span>
          <span className="text-gray-500"> / ฿{Math.round(start).toLocaleString()}</span>
        </div>
      </div>
      <div className="text-xs">
        Cum PnL: <span className={pnlTone}>{formatBaht(cumPnl)}</span>
        <span className={`ml-1 ${pnlTone}`}>({cumPct >= 0 ? '+' : ''}{cumPct.toFixed(1)}%)</span>
      </div>
      {open && <PaperRuleDrawer rule={rule} pattern={pattern} />}
    </div>
  )
}
```

- [ ] **Step 2: Create a placeholder `PaperRuleDrawer.jsx` so the build succeeds**

Create `frontend/src/components/PaperRuleDrawer.jsx`:

```jsx
export default function PaperRuleDrawer({ rule, pattern }) {
  return (
    <div className="border-t border-gray-800 pt-2 text-xs text-gray-500">
      Drawer placeholder for {rule.id}
    </div>
  )
}
```

- [ ] **Step 3: Build the frontend**

Run: `cd frontend && npm run build`

Expected: build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PaperRuleCard.jsx frontend/src/components/PaperRuleDrawer.jsx
git commit -m "feat(ui): collapsed paper rule card with balance/pnl/open + expand toggle"
```

---

## Task 5: Frontend — drawer fetch hook

**Files:**
- Modify: `frontend/src/hooks/usePaperSignals.js` (append new export)

- [ ] **Step 1: Replace the import line at the top of `frontend/src/hooks/usePaperSignals.js`**

The file currently has:

```js
import { useCallback, useEffect, useRef } from 'react'
```

Change it to:

```js
import { useCallback, useEffect, useRef, useState } from 'react'
```

- [ ] **Step 2: Append `usePaperRuleDetail` hook to the same file**

Append to the end of `frontend/src/hooks/usePaperSignals.js`:

```js
export function usePaperRuleDetail(ruleId, patternId) {
  const [data, setData] = useState({
    trades: null,
    signals: null,
    shadows: null,
    gates: null,
  })
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const refetch = useCallback(async () => {
    if (!ruleId) return
    setLoading(true)
    setError(null)
    try {
      const [trades, signals, shadows, gates] = await Promise.all([
        get(`/api/paper-trades?rule_id=${ruleId}`),
        get(`/api/paper-signals?rule_id=${ruleId}&limit=20`),
        get(`/api/paper-trader-rules/${ruleId}/shadows`),
        patternId ? get(`/api/patterns/${patternId}/gates`) : Promise.resolve(null),
      ])
      setData({ trades, signals, shadows, gates })
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }, [ruleId, patternId])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { data, error, loading, refetch }
}
```

- [ ] **Step 3: Build to verify the hook compiles**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/usePaperSignals.js
git commit -m "feat(ui): usePaperRuleDetail hook composes 4 endpoints for drawer"
```

---

## Task 6: Drawer shell with header + manual refresh + section slots

**Files:**
- Rewrite: `frontend/src/components/PaperRuleDrawer.jsx`

- [ ] **Step 1: Replace the placeholder drawer with the full shell**

Replace `frontend/src/components/PaperRuleDrawer.jsx` with:

```jsx
import { usePaperRuleDetail } from '../hooks/usePaperSignals'
import SignalTrail from './drawer/SignalTrail'
import OrdersTable from './drawer/OrdersTable'
import PatternConditions from './drawer/PatternConditions'
import PromotionGates from './drawer/PromotionGates'
import ShadowsList from './drawer/ShadowsList'

export default function PaperRuleDrawer({ rule, pattern }) {
  const { data, error, loading, refetch } = usePaperRuleDetail(rule.id, rule.pattern_id)
  const trades = data.trades || []
  const active = trades.filter((t) => t.status === 'open')
  const closed = trades.filter((t) => t.status === 'closed')

  return (
    <div className="border-t border-gray-800 pt-3 mt-2 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">Drawer</span>
        <button
          type="button"
          onClick={refetch}
          disabled={loading}
          className="text-xs px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-50"
        >
          {loading ? '⟳ refreshing…' : '⟳ refresh'}
        </button>
      </div>
      {error && <div className="text-xs text-red-400">Failed to load: {String(error)}</div>}

      <SignalTrail signals={data.signals} />
      <OrdersTable title={`Active Orders (${active.length})`} trades={active} mode="active" />
      <OrdersTable title="Recent History" trades={closed} mode="history" />
      <PatternConditions rule={rule} pattern={pattern} />
      <PromotionGates gates={data.gates} ruleId={rule.id} />
      <ShadowsList shadows={data.shadows} />
    </div>
  )
}
```

- [ ] **Step 2: Create empty placeholders for the 5 sections so build succeeds**

Create `frontend/src/components/drawer/SignalTrail.jsx`:

```jsx
export default function SignalTrail({ signals }) {
  return <div className="text-xs text-gray-500">Signal trail ({signals?.length ?? 0})</div>
}
```

Create `frontend/src/components/drawer/OrdersTable.jsx`:

```jsx
export default function OrdersTable({ title, trades, mode }) {
  return <div className="text-xs text-gray-500">{title}: {trades?.length ?? 0} ({mode})</div>
}
```

Create `frontend/src/components/drawer/PatternConditions.jsx`:

```jsx
export default function PatternConditions({ rule, pattern }) {
  return <div className="text-xs text-gray-500">Conditions for {rule.id.slice(0, 8)}</div>
}
```

Create `frontend/src/components/drawer/PromotionGates.jsx`:

```jsx
export default function PromotionGates({ gates, ruleId }) {
  return <div className="text-xs text-gray-500">Gates for {ruleId.slice(0, 8)}</div>
}
```

Create `frontend/src/components/drawer/ShadowsList.jsx`:

```jsx
export default function ShadowsList({ shadows }) {
  return <div className="text-xs text-gray-500">Shadows ({shadows?.shadows?.length ?? 0})</div>
}
```

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PaperRuleDrawer.jsx frontend/src/components/drawer/
git commit -m "feat(ui): drawer shell with refresh + 5 section placeholders"
```

---

## Task 7: SignalTrail section

**Files:**
- Rewrite: `frontend/src/components/drawer/SignalTrail.jsx`

- [ ] **Step 1: Implement the colored-dot signal trail**

Replace `frontend/src/components/drawer/SignalTrail.jsx`:

```jsx
const STATUS_COLOR = {
  active: 'bg-emerald-500',
  near: 'bg-amber-400',
  far: 'bg-gray-500',
  idle: 'bg-gray-700',
}

function ago(iso) {
  if (!iso) return '—'
  const ms = Date.now() - new Date(iso).getTime()
  if (ms < 60_000) return 'just now'
  if (ms < 3600_000) return `${Math.floor(ms / 60_000)}m ago`
  if (ms < 86_400_000) return `${Math.floor(ms / 3600_000)}h ago`
  return `${Math.floor(ms / 86_400_000)}d ago`
}

export default function SignalTrail({ signals }) {
  if (!signals) return <div className="text-xs text-gray-500">Signals: loading…</div>
  if (signals.length === 0) return <div className="text-xs text-gray-500">Signals: none yet</div>

  const latest = signals[0]
  const dots = signals.slice(0, 20).slice().reverse()

  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400">Signal Trail (last {dots.length})</div>
      <div className="flex gap-1">
        {dots.map((s) => (
          <span
            key={s.id}
            title={`${s.status} · match ${(Number(s.match_pct) * 100).toFixed(0)}%`}
            className={`w-2 h-2 rounded-full ${STATUS_COLOR[s.status] || STATUS_COLOR.idle}`}
          />
        ))}
      </div>
      <div className="text-xs text-gray-500">
        Last: {ago(latest.emitted_at)} · match {(Number(latest.match_pct) * 100).toFixed(0)}%
        {latest.missing_conditions?.length > 0 && (
          <span> · missing: {latest.missing_conditions.join(', ')}</span>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/drawer/SignalTrail.jsx
git commit -m "feat(ui): signal trail with colored dots + latest match summary"
```

---

## Task 8: OrdersTable section (handles active + history)

**Files:**
- Rewrite: `frontend/src/components/drawer/OrdersTable.jsx`

- [ ] **Step 1: Implement the table**

Replace `frontend/src/components/drawer/OrdersTable.jsx`:

```jsx
function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function fmtPrice(n) {
  if (n == null) return '—'
  return Number(n).toFixed(2)
}

function fmtBaht(n, signed = true) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = signed && v >= 0 ? '+' : ''
  return `${sign}฿${Math.round(v).toLocaleString()}`
}

export default function OrdersTable({ title, trades, mode }) {
  if (!trades) return <div className="text-xs text-gray-500">{title}: loading…</div>
  if (trades.length === 0) return <div className="text-xs text-gray-500">{title}: none</div>

  const rows = mode === 'history' ? trades.slice(0, 20) : trades

  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400">{title}</div>
      <div className={mode === 'history' ? 'max-h-40 overflow-y-auto' : ''}>
        <table className="w-full text-xs">
          <tbody>
            {rows.map((t) => {
              const isWin = (Number(t.profit) || 0) > 0
              const tone = mode === 'active'
                ? 'text-gray-300'
                : isWin ? 'text-emerald-400' : 'text-red-400'
              return (
                <tr key={t.id} className="border-b border-gray-900">
                  <td className="py-1 pr-2">#{t.ticket}</td>
                  <td className="py-1 pr-2 uppercase">{t.direction}</td>
                  <td className="py-1 pr-2 text-gray-500">
                    {mode === 'active' ? `open ${fmtTime(t.open_time)}` : `close ${fmtTime(t.close_time)}`}
                  </td>
                  <td className="py-1 pr-2 text-gray-500">@{fmtPrice(t.open_price)}</td>
                  <td className={`py-1 pr-2 ${tone}`}>{fmtBaht(t.profit)}</td>
                  <td className="py-1 text-gray-500">{t.paper_exit_reason || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/drawer/OrdersTable.jsx
git commit -m "feat(ui): orders table with active + scrollable history modes"
```

---

## Task 9: PatternConditions section

**Files:**
- Rewrite: `frontend/src/components/drawer/PatternConditions.jsx`

- [ ] **Step 1: Implement**

Replace `frontend/src/components/drawer/PatternConditions.jsx`:

```jsx
export default function PatternConditions({ rule, pattern }) {
  const slugs = pattern?.indicator_slugs || []
  const tf = pattern?.timeframe || '—'
  const filters = rule.filters || []
  const weights = rule.score_weights || null

  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400">Pattern Conditions</div>
      <div className="text-xs text-gray-300">
        Indicators: {slugs.length ? slugs.map((s) => `${s} (${tf})`).join(', ') : '—'}
      </div>
      <div className="text-xs text-gray-300">
        Filters:{' '}
        {filters.length === 0
          ? <span className="text-gray-500">none</span>
          : filters.map((f, i) => (
              <span key={i} className="ml-1 inline-block rounded bg-gray-800 px-1">
                {f.feature} ≠ {f.exclude}
              </span>
            ))}
      </div>
      {weights && (
        <div className="text-xs text-gray-300">
          Score weights:{' '}
          {Object.entries(weights).map(([k, v]) => `${k} ${v}`).join(', ')}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/drawer/PatternConditions.jsx
git commit -m "feat(ui): pattern conditions section (indicators + filters + weights)"
```

---

## Task 10: PromotionGates section

**Files:**
- Rewrite: `frontend/src/components/drawer/PromotionGates.jsx`

- [ ] **Step 1: Implement**

Replace `frontend/src/components/drawer/PromotionGates.jsx`:

```jsx
const GATE_LABELS = {
  sample: 'sample',
  performance: 'performance',
  stability: 'stability',
  walk_forward: 'walk_forward',
}

export default function PromotionGates({ gates, ruleId }) {
  if (!gates) return <div className="text-xs text-gray-500">Gates: loading…</div>
  const entry = (gates.rules || []).find((r) => r.rule_id === ruleId)
  if (!entry) return <div className="text-xs text-gray-500">Gates: no data for this rule</div>

  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400">Promotion Gates</div>
      <div className="flex gap-3 text-xs flex-wrap">
        {Object.entries(GATE_LABELS).map(([key, label]) => {
          const passed = entry.gates?.[key] === true
          return (
            <span key={key} className={passed ? 'text-emerald-400' : 'text-red-400'}>
              {passed ? '✓' : '✗'} {label}
            </span>
          )
        })}
      </div>
      <div className="text-xs text-gray-500">
        tier: <span className="text-gray-300">{entry.tier}</span>
        {entry.reason && <span> · {entry.reason}</span>}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/drawer/PromotionGates.jsx
git commit -m "feat(ui): promotion gates breakdown (4 gates + tier + reason)"
```

---

## Task 11: ShadowsList section

**Files:**
- Rewrite: `frontend/src/components/drawer/ShadowsList.jsx`

- [ ] **Step 1: Implement**

Replace `frontend/src/components/drawer/ShadowsList.jsx`:

```jsx
function fmtPct(n) {
  if (n == null) return '—'
  return `${(Number(n) * 100).toFixed(0)}%`
}

function fmtDelta(n) {
  if (n == null) return '—'
  const v = Number(n) * 100
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}%`
}

export default function ShadowsList({ shadows }) {
  if (!shadows) return <div className="text-xs text-gray-500">Shadows: loading…</div>
  const list = shadows.shadows || []
  if (list.length === 0) return <div className="text-xs text-gray-500">Shadows: none</div>

  const parent = shadows.parent
  return (
    <div className="space-y-2">
      <div className="text-xs text-gray-400">Shadows ({list.length})</div>
      {list.map((s) => {
        const filterClause = (s.filters || []).map((f) => `${f.feature} ≠ ${f.exclude}`).join(', ')
        const deltaTone = s.winrate_delta == null
          ? 'text-gray-500'
          : Number(s.winrate_delta) > 0 ? 'text-emerald-400' : 'text-red-400'
        return (
          <div key={s.id} className="border border-gray-800 rounded p-2 space-y-1">
            <div className="text-xs text-amber-300">Testing: {filterClause || '—'}</div>
            <div className="text-xs text-gray-300">
              Parent WR {fmtPct(parent.winrate)} ({parent.trades})
              {' · '}
              Shadow WR {fmtPct(s.winrate)} ({s.trades})
              {' · '}
              Δ <span className={deltaTone}>{fmtDelta(s.winrate_delta)}</span>
            </div>
            <div className="text-xs text-gray-500">status: {s.status}</div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/drawer/ShadowsList.jsx
git commit -m "feat(ui): shadows list with parent vs shadow winrate + delta"
```

---

## Task 12: End-to-end smoke test (manual)

**Files:** none (manual verification)

- [ ] **Step 1: Restart the API**

Run: `docker compose restart api`

- [ ] **Step 2: Build + serve frontend**

Run: `cd frontend && npm run build && npm run preview` (or rely on `npm run dev` if already running)

- [ ] **Step 3: Verify in browser**

Open `http://localhost:3000` (or whichever port the dev server is on) and check:

- Each card shows: alive dot, mode, age, tier, indicator slugs, Open count, Balance current/start, Cum PnL with %
- Clicking caret ▾ expands the drawer; ▴ collapses
- Drawer shows 6 sections; empty sections render their "none" / "loading" message instead of crashing
- Refresh button in drawer triggers a single round-trip per endpoint (verify in DevTools Network tab)
- Closing the drawer (▴) does not refetch the list outside its 5s polling cadence
- Shadow rules do not appear as standalone cards (existing `status !== 'shadow'` filter still applies)

- [ ] **Step 4: Verify backend regression**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -v --tb=short"`

Expected: all tests pass.

- [ ] **Step 5: Commit (only if any wiring tweaks were needed)**

```bash
git status
# if dirty:
git add -A
git commit -m "chore(ui): smoke fixes after end-to-end check"
```

If working tree is clean, skip the commit.
