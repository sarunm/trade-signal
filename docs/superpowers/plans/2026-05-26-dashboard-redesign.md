# Dashboard Re-design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current 8-section vertical stack with a Command Center Grid (sticky TopBar + 3 grid sections) using a Modern Indigo palette, and refactor `<TradeAdvisor />` from per-trade cards into a basket-level "Basket Exit Plan" with Ruin Zone + clickable PnL Summary modal.

**Architecture:** Backend stays additive — extend `/api/trade-advisor` response with a `basket` field, augment `/api/paper-trader-rules` with two PnL fields, and add a new `/api/pnl-history` endpoint with 4 granularities + pagination. Frontend introduces a `TopBar` + 3 `SectionDivider`s, restructures `App.jsx` to a 12-col grid with 3 sections (Real / Paper / History), refactors `TradeAdvisor.jsx` into a basket view, and adds a `PnlHistoryModal` triggered from the basket's PnL Summary box.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async; React 18 + Vite + TailwindCSS; pytest + pytest-asyncio + httpx (no frontend test framework — verify with `npm run build` + manual smoke).

**Spec ref:** `docs/superpowers/specs/2026-05-26-dashboard-redesign-design.md`

---

## File Structure

**Backend (modify):**
- `api/routers/account.py` — add `/api/pnl-history` (new endpoint alongside existing `/api/daily-pl`)
- `api/routers/trade_advisor.py` — augment response with `basket` aggregation + Ruin Zone + PnL summary
- `api/routers/patterns.py` — add `paper_pnl_today` + `paper_pnl_week` to rule rows
- `api/schemas/account.py` — `PnlHistoryItem` + `PnlHistoryResponse`
- `api/schemas/pattern.py` — extend `PaperTraderRuleResponse` with 2 fields

**Backend (test):**
- `tests/test_pnl_history.py` (new)
- `tests/test_trade_advisor_basket.py` (new)
- `tests/test_paper_trader_rules_paper_pnl.py` (new)

**Frontend (new):**
- `frontend/src/components/TopBar.jsx`
- `frontend/src/components/SectionDivider.jsx`
- `frontend/src/components/PnlHistoryModal.jsx`
- `frontend/src/components/BasketExitPlan.jsx` *(new replacement for `TradeAdvisor.jsx`'s body)*

**Frontend (modify):**
- `frontend/tailwind.config.js` — add Modern Indigo color tokens
- `frontend/src/App.jsx` — TopBar + 3 SectionDividers + 3 grid sections
- `frontend/src/components/TradeAdvisor.jsx` — thin wrapper that renders `<BasketExitPlan />` (kept for the App import surface, body refactored)
- `frontend/src/components/OpenPositions.jsx` — append score chip below each row
- `frontend/src/components/PaperTradeConsole.jsx` — header strip (active count + today/week PnL + filter buttons restyled)
- `frontend/src/components/TraderProfile.jsx` — add Account Detail sub-block at top

**Frontend (delete after wired):**
- `frontend/src/components/AccountBar.jsx`
- `frontend/src/components/EAStatusBadge.jsx`
- `frontend/src/components/DailyPLPanel.jsx`

**Backend (delete after FE shipped):**
- `/api/daily-pl` route in `api/routers/account.py` (kept until PnlHistoryModal is verified, then removed in final task)

---

## Task 1: Add `PnlHistoryItem` / `PnlHistoryResponse` schemas

**Files:**
- Modify: `api/schemas/account.py`

- [ ] **Step 1: Add the schema classes**

Append to `api/schemas/account.py`:

```python
class PnlHistoryItem(BaseModel):
    period: str
    profit: Decimal
    profit_pct: Optional[Decimal] = None
    trade_count: int


class PnlHistoryResponse(BaseModel):
    items: list[PnlHistoryItem]
    page: int
    page_size: int
    total_pages: int
    total_count: int
```

- [ ] **Step 2: Verify import surface compiles**

Run: `docker compose run --rm -e PYTHONPATH=/app api sh -c "cd /app && python -c 'from schemas.account import PnlHistoryItem, PnlHistoryResponse'"`
Expected: exit 0, no output.

- [ ] **Step 3: Commit**

```bash
git add api/schemas/account.py
git commit -m "feat: add PnlHistoryItem and PnlHistoryResponse schemas"
```

---

## Task 2: `/api/pnl-history` — daily granularity (TDD baseline)

**Files:**
- Create: `tests/test_pnl_history.py`
- Modify: `api/routers/account.py`

- [ ] **Step 1: Write the failing test for daily granularity**

Create `tests/test_pnl_history.py`:

```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from models.trade import Direction, OrderState, Trade

_BKK = timezone(timedelta(hours=7))


def _bkk(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=_BKK).astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_pnl_history_daily_groups_by_bkk_date(client, db_session):
    db_session.add_all([
        Trade(
            id=uuid4(), ticket=1001, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 26, 9), close_time=_bkk(2026, 5, 26, 15),
            open_price=Decimal("1955"), close_price=Decimal("1960"),
            volume=Decimal("0.10"), profit=Decimal("420.00"),
        ),
        Trade(
            id=uuid4(), ticket=1002, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 26, 16), close_time=_bkk(2026, 5, 26, 18),
            open_price=Decimal("1962"), close_price=Decimal("1965"),
            volume=Decimal("0.05"), profit=Decimal("150.00"),
        ),
        Trade(
            id=uuid4(), ticket=1003, symbol="XAUUSD", direction=Direction.sell,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 25, 10), close_time=_bkk(2026, 5, 25, 14),
            open_price=Decimal("1958"), close_price=Decimal("1960"),
            volume=Decimal("0.05"), profit=Decimal("-100.00"),
        ),
    ])
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=daily&page=1&page_size=20")
    assert res.status_code == 200
    body = res.json()

    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total_count"] == 2
    assert body["total_pages"] == 1
    assert len(body["items"]) == 2

    first = body["items"][0]
    assert first["period"] == "2026-05-26"
    assert Decimal(first["profit"]) == Decimal("570.00")
    assert first["trade_count"] == 2

    second = body["items"][1]
    assert second["period"] == "2026-05-25"
    assert Decimal(second["profit"]) == Decimal("-100.00")
    assert second["trade_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_pnl_history.py::test_pnl_history_daily_groups_by_bkk_date -v"`
Expected: FAIL — endpoint not registered (404).

- [ ] **Step 3: Add the endpoint with daily-only support first**

Append to `api/routers/account.py`:

```python
from collections import defaultdict
from math import ceil
from schemas.account import PnlHistoryItem, PnlHistoryResponse


@router.get("/pnl-history", response_model=PnlHistoryResponse)
async def get_pnl_history(
    granularity: str = Query("daily", pattern="^(all|daily|weekly|monthly)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    account_id = await _current_account_id(session)
    stmt = select(Trade).where(
        Trade.is_paper == False,
        Trade.order_state == OrderState.filled,
        Trade.close_time.isnot(None),
        Trade.profit.isnot(None),
    )
    if account_id is not None:
        stmt = stmt.where(Trade.account_id == account_id)
    result = await session.execute(stmt)
    trades = result.scalars().all()

    snapshot_stmt = select(AccountSnapshot)
    if account_id is not None:
        snapshot_stmt = snapshot_stmt.where(AccountSnapshot.account_id == account_id)
    snap_result = await session.execute(snapshot_stmt.order_by(AccountSnapshot.timestamp.asc()))
    snapshots = snap_result.scalars().all()

    if granularity == "daily":
        rows = _group_pnl_daily(trades, snapshots)
    else:
        rows = []  # filled in by Tasks 3-5

    total_count = len(rows)
    total_pages = max(1, ceil(total_count / page_size)) if total_count else 0
    start = (page - 1) * page_size
    page_items = rows[start:start + page_size]
    return PnlHistoryResponse(
        items=page_items,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_count=total_count,
    )


def _group_pnl_daily(trades, snapshots):
    grouped: dict = defaultdict(lambda: {"profit": Decimal("0.00"), "trade_count": 0})
    for trade in trades:
        d = _as_utc(trade.close_time).astimezone(_ICT).date()
        grouped[d]["profit"] += trade.profit
        grouped[d]["trade_count"] += 1
    base_by_date = _base_balance_by_date(snapshots)
    rows: list[PnlHistoryItem] = []
    for d in sorted(grouped.keys(), reverse=True):
        profit = grouped[d]["profit"].quantize(Decimal("0.01"))
        base = base_by_date.get(d)
        pct = ((profit / base) * Decimal("100")).quantize(Decimal("0.01")) if base else None
        rows.append(PnlHistoryItem(
            period=d.isoformat(),
            profit=profit,
            profit_pct=pct,
            trade_count=grouped[d]["trade_count"],
        ))
    return rows


def _base_balance_by_date(snapshots) -> dict:
    first_per_day = {}
    for s in snapshots:
        d = _as_utc(s.timestamp).astimezone(_ICT).date()
        first_per_day.setdefault(d, s.balance)
    return first_per_day
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_pnl_history.py::test_pnl_history_daily_groups_by_bkk_date -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routers/account.py tests/test_pnl_history.py
git commit -m "feat: add /api/pnl-history daily granularity with pagination"
```

---

## Task 3: `/api/pnl-history` — weekly + monthly granularities

**Files:**
- Modify: `tests/test_pnl_history.py`
- Modify: `api/routers/account.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pnl_history.py`:

```python
@pytest.mark.asyncio
async def test_pnl_history_weekly_groups_by_iso_week(client, db_session):
    db_session.add_all([
        Trade(
            id=uuid4(), ticket=2001, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 18), close_time=_bkk(2026, 5, 18, 15),
            open_price=Decimal("1950"), close_price=Decimal("1955"),
            volume=Decimal("0.10"), profit=Decimal("500.00"),
        ),
        Trade(
            id=uuid4(), ticket=2002, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 22), close_time=_bkk(2026, 5, 22, 15),
            open_price=Decimal("1955"), close_price=Decimal("1960"),
            volume=Decimal("0.10"), profit=Decimal("500.00"),
        ),
        Trade(
            id=uuid4(), ticket=2003, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 25), close_time=_bkk(2026, 5, 25, 15),
            open_price=Decimal("1960"), close_price=Decimal("1965"),
            volume=Decimal("0.10"), profit=Decimal("500.00"),
        ),
    ])
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=weekly")
    body = res.json()
    assert body["total_count"] == 2
    assert body["items"][0]["period"] == "2026-05-25"  # Mon of ISO week 22
    assert Decimal(body["items"][0]["profit"]) == Decimal("500.00")
    assert body["items"][0]["trade_count"] == 1
    assert body["items"][1]["period"] == "2026-05-18"
    assert Decimal(body["items"][1]["profit"]) == Decimal("1000.00")
    assert body["items"][1]["trade_count"] == 2


@pytest.mark.asyncio
async def test_pnl_history_monthly_groups_by_first_of_month(client, db_session):
    db_session.add_all([
        Trade(
            id=uuid4(), ticket=3001, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 4, 15), close_time=_bkk(2026, 4, 15, 15),
            open_price=Decimal("1950"), close_price=Decimal("1955"),
            volume=Decimal("0.10"), profit=Decimal("200.00"),
        ),
        Trade(
            id=uuid4(), ticket=3002, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 5), close_time=_bkk(2026, 5, 5, 15),
            open_price=Decimal("1955"), close_price=Decimal("1960"),
            volume=Decimal("0.10"), profit=Decimal("700.00"),
        ),
    ])
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=monthly")
    body = res.json()
    assert body["total_count"] == 2
    assert body["items"][0]["period"] == "2026-05-01"
    assert Decimal(body["items"][0]["profit"]) == Decimal("700.00")
    assert body["items"][1]["period"] == "2026-04-01"
    assert Decimal(body["items"][1]["profit"]) == Decimal("200.00")
```

- [ ] **Step 2: Run new tests, verify they fail**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_pnl_history.py -v"`
Expected: FAIL — `total_count == 0` (weekly/monthly branches not implemented).

- [ ] **Step 3: Implement weekly + monthly grouping**

In `api/routers/account.py`, replace the `if granularity == "daily":` block with:

```python
    if granularity == "daily":
        rows = _group_pnl_daily(trades, snapshots)
    elif granularity == "weekly":
        rows = _group_pnl_weekly(trades, snapshots)
    elif granularity == "monthly":
        rows = _group_pnl_monthly(trades, snapshots)
    else:
        rows = []  # all — Task 4
```

Then add helpers below `_group_pnl_daily`:

```python
def _iso_week_monday(d):
    return d - timedelta(days=d.isoweekday() - 1)


def _group_pnl_weekly(trades, snapshots):
    grouped: dict = defaultdict(lambda: {"profit": Decimal("0.00"), "trade_count": 0})
    for trade in trades:
        d = _as_utc(trade.close_time).astimezone(_ICT).date()
        key = _iso_week_monday(d)
        grouped[key]["profit"] += trade.profit
        grouped[key]["trade_count"] += 1
    base_by_date = _base_balance_by_date(snapshots)
    rows: list[PnlHistoryItem] = []
    for key in sorted(grouped.keys(), reverse=True):
        profit = grouped[key]["profit"].quantize(Decimal("0.01"))
        base = base_by_date.get(key)
        pct = ((profit / base) * Decimal("100")).quantize(Decimal("0.01")) if base else None
        rows.append(PnlHistoryItem(
            period=key.isoformat(),
            profit=profit,
            profit_pct=pct,
            trade_count=grouped[key]["trade_count"],
        ))
    return rows


def _group_pnl_monthly(trades, snapshots):
    grouped: dict = defaultdict(lambda: {"profit": Decimal("0.00"), "trade_count": 0})
    for trade in trades:
        d = _as_utc(trade.close_time).astimezone(_ICT).date()
        key = d.replace(day=1)
        grouped[key]["profit"] += trade.profit
        grouped[key]["trade_count"] += 1
    base_by_date = _base_balance_by_date(snapshots)
    rows: list[PnlHistoryItem] = []
    for key in sorted(grouped.keys(), reverse=True):
        profit = grouped[key]["profit"].quantize(Decimal("0.01"))
        base = base_by_date.get(key)
        pct = ((profit / base) * Decimal("100")).quantize(Decimal("0.01")) if base else None
        rows.append(PnlHistoryItem(
            period=key.isoformat(),
            profit=profit,
            profit_pct=pct,
            trade_count=grouped[key]["trade_count"],
        ))
    return rows
```

- [ ] **Step 4: Run tests**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_pnl_history.py -v"`
Expected: 3 pass.

- [ ] **Step 5: Commit**

```bash
git add api/routers/account.py tests/test_pnl_history.py
git commit -m "feat: add weekly + monthly granularities to /api/pnl-history"
```

---

## Task 4: `/api/pnl-history` — `all` granularity (one row per closed trade)

**Files:**
- Modify: `tests/test_pnl_history.py`
- Modify: `api/routers/account.py`

- [ ] **Step 1: Failing test**

Append:

```python
@pytest.mark.asyncio
async def test_pnl_history_all_returns_row_per_trade(client, db_session):
    db_session.add_all([
        Trade(
            id=uuid4(), ticket=4001, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 26, 10), close_time=_bkk(2026, 5, 26, 11),
            open_price=Decimal("1955"), close_price=Decimal("1958"),
            volume=Decimal("0.05"), profit=Decimal("150.00"),
        ),
        Trade(
            id=uuid4(), ticket=4002, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 26, 14), close_time=_bkk(2026, 5, 26, 16),
            open_price=Decimal("1958"), close_price=Decimal("1960"),
            volume=Decimal("0.10"), profit=Decimal("200.00"),
        ),
    ])
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=all")
    body = res.json()
    assert body["total_count"] == 2
    assert all(item["trade_count"] == 1 for item in body["items"])
    # newest first
    assert body["items"][0]["period"].startswith("2026-05-26")
    assert Decimal(body["items"][0]["profit"]) == Decimal("200.00")
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_pnl_history.py::test_pnl_history_all_returns_row_per_trade -v"`
Expected: FAIL — `total_count == 0`.

- [ ] **Step 3: Implement `all` branch**

In `api/routers/account.py`, replace the `else: rows = []` line:

```python
    else:  # all
        rows = _group_pnl_all(trades)
```

And add helper:

```python
def _group_pnl_all(trades):
    sorted_trades = sorted(trades, key=lambda t: _as_utc(t.close_time), reverse=True)
    rows: list[PnlHistoryItem] = []
    for t in sorted_trades:
        rows.append(PnlHistoryItem(
            period=_as_utc(t.close_time).isoformat(),
            profit=t.profit.quantize(Decimal("0.01")) if t.profit is not None else Decimal("0.00"),
            profit_pct=None,
            trade_count=1,
        ))
    return rows
```

- [ ] **Step 4: Run tests**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_pnl_history.py -v"`
Expected: 4 pass.

- [ ] **Step 5: Commit**

```bash
git add api/routers/account.py tests/test_pnl_history.py
git commit -m "feat: add 'all' granularity to /api/pnl-history"
```

---

## Task 5: `/api/pnl-history` — pagination edge cases

**Files:**
- Modify: `tests/test_pnl_history.py`

- [ ] **Step 1: Add edge-case tests**

Append:

```python
@pytest.mark.asyncio
async def test_pnl_history_pagination_truncates_to_page_size(client, db_session):
    for i in range(5):
        db_session.add(Trade(
            id=uuid4(), ticket=5000 + i, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 20 + i),
            close_time=_bkk(2026, 5, 20 + i, 15),
            open_price=Decimal("1950"), close_price=Decimal("1955"),
            volume=Decimal("0.10"), profit=Decimal("100.00"),
        ))
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=daily&page=1&page_size=2")
    body = res.json()
    assert body["total_count"] == 5
    assert body["total_pages"] == 3
    assert body["page"] == 1
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_pnl_history_out_of_range_page_returns_empty(client, db_session):
    db_session.add(Trade(
        id=uuid4(), ticket=6001, symbol="XAUUSD", direction=Direction.buy,
        order_state=OrderState.filled, is_paper=False,
        open_time=_bkk(2026, 5, 26),
        close_time=_bkk(2026, 5, 26, 15),
        open_price=Decimal("1955"), close_price=Decimal("1960"),
        volume=Decimal("0.10"), profit=Decimal("100.00"),
    ))
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=daily&page=99&page_size=20")
    body = res.json()
    assert body["items"] == []


@pytest.mark.asyncio
async def test_pnl_history_empty_db_returns_zero_counts(client, db_session):
    res = await client.get("/api/pnl-history?granularity=daily")
    body = res.json()
    assert body["items"] == []
    assert body["total_pages"] == 0
    assert body["total_count"] == 0
```

- [ ] **Step 2: Run tests — should all pass (no implementation change needed)**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_pnl_history.py -v"`
Expected: 7 pass. If any fail, adjust the `total_pages` calculation in the endpoint to match exactly: `total_pages = ceil(total_count / page_size) if total_count else 0`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pnl_history.py
git commit -m "test: cover /api/pnl-history pagination edge cases"
```

---

## Task 6: `/api/trade-advisor` — basket aggregation (no Ruin Zone yet)

**Files:**
- Create: `tests/test_trade_advisor_basket.py`
- Modify: `api/routers/trade_advisor.py`

- [ ] **Step 1: Failing test for basket aggregation**

Create `tests/test_trade_advisor_basket.py`:

```python
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from models.account_snapshot import AccountSnapshot
from models.trade import Direction, OrderState, Trade

_BKK = timezone(timedelta(hours=7))


def _t(ticket, direction, vol, entry):
    return Trade(
        id=uuid4(), ticket=ticket, symbol="XAUUSD", direction=direction,
        order_state=OrderState.filled, is_paper=False,
        open_time=datetime.now(timezone.utc),
        open_price=Decimal(str(entry)),
        volume=Decimal(str(vol)),
    )


@pytest.mark.asyncio
async def test_basket_three_buys_uses_weighted_avg(client, db_session):
    db_session.add_all([
        _t(7001, Direction.buy, "0.10", "1955.00"),
        _t(7002, Direction.buy, "0.10", "1957.00"),
        _t(7003, Direction.buy, "0.10", "1959.00"),
    ])
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("3000"), free_margin=Decimal("97000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    body = res.json()
    assert "basket" in body
    b = body["basket"]
    assert b["direction"] == "buy"
    assert b["order_count"] == 3
    assert Decimal(str(b["lot_total"])) == Decimal("0.30")
    assert Decimal(str(b["avg_entry"])) == Decimal("1957.00")


@pytest.mark.asyncio
async def test_basket_no_open_returns_flat(client, db_session):
    res = await client.get("/api/trade-advisor")
    body = res.json()
    b = body["basket"]
    assert b["direction"] == "flat"
    assert b["lot_total"] == 0
    assert b["order_count"] == 0
    assert b["avg_entry"] is None


@pytest.mark.asyncio
async def test_basket_mixed_direction_nets_by_lot(client, db_session):
    db_session.add_all([
        _t(8001, Direction.buy, "0.20", "1955.00"),
        _t(8002, Direction.sell, "0.05", "1958.00"),
    ])
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("3000"), free_margin=Decimal("97000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    body = res.json()
    b = body["basket"]
    assert b["direction"] == "buy"
    assert Decimal(str(b["lot_total"])) == Decimal("0.15")
    assert b["order_count"] == 2
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py -v"`
Expected: FAIL — `basket` key missing or response is a list.

- [ ] **Step 3: Refactor endpoint to return `{per_trade, basket}`**

Replace `api/routers/trade_advisor.py` body:

```python
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.account_snapshot import AccountSnapshot
from models.trade import Direction, OrderState, Trade

router = APIRouter(prefix="/api", tags=["trade-advisor"])


@router.get("/trade-advisor")
async def get_trade_advisor(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
        )
    )
    trades = result.scalars().all()
    snap_result = await session.execute(
        select(AccountSnapshot).order_by(AccountSnapshot.timestamp.desc()).limit(1)
    )
    snapshot = snap_result.scalar_one_or_none()

    per_trade = [
        {
            "id": str(t.id),
            "ticket": t.ticket,
            "symbol": t.symbol,
            "direction": t.direction.value if t.direction else None,
            "open_price": float(t.open_price) if t.open_price else None,
            "entry_score": t.entry_score,
            "entry_verdict": t.entry_verdict,
            "recovery_plan": t.recovery_plan,
        }
        for t in trades
    ]
    basket = _aggregate_basket(trades, snapshot)
    return {"per_trade": per_trade, "basket": basket}


def _aggregate_basket(trades: list[Trade], snapshot: Optional[AccountSnapshot]) -> dict[str, Any]:
    open_trades = [t for t in trades if t.volume and t.open_price and t.direction]
    if not open_trades:
        return _flat_basket()

    buy_vol = sum((t.volume for t in open_trades if t.direction == Direction.buy), Decimal("0"))
    sell_vol = sum((t.volume for t in open_trades if t.direction == Direction.sell), Decimal("0"))
    net = buy_vol - sell_vol
    if net == 0:
        return _flat_basket()
    direction = "buy" if net > 0 else "sell"
    sign = Decimal("1") if direction == "buy" else Decimal("-1")

    notional = Decimal("0")
    weight = Decimal("0")
    for t in open_trades:
        s = Decimal("1") if t.direction == Direction.buy else Decimal("-1")
        notional += t.open_price * t.volume * s
        weight += t.volume * s
    avg_entry = (notional / weight).quantize(Decimal("0.01")) if weight != 0 else None

    return {
        "direction": direction,
        "lot_total": float(abs(net)),
        "order_count": len(open_trades),
        "avg_entry": float(avg_entry) if avg_entry is not None else None,
        "current": None,         # Task 7
        "basket_be": None,       # Task 7
        "net_float": None,       # Task 7
        "ruin": None,            # Task 8
        "tp_targets": [],        # Task 9
        "add_zones": [],         # Task 9
        "cut": None,             # Task 9
        "pnl_summary": None,     # Task 10
    }


def _flat_basket() -> dict[str, Any]:
    return {
        "direction": "flat",
        "lot_total": 0,
        "order_count": 0,
        "avg_entry": None,
        "current": None,
        "basket_be": None,
        "net_float": None,
        "ruin": None,
        "tp_targets": [],
        "add_zones": [],
        "cut": None,
        "pnl_summary": None,
    }
```

- [ ] **Step 4: Run tests**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py -v"`
Expected: 3 pass.

- [ ] **Step 5: Run full suite to confirm no regressions on existing trade-advisor consumers**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor.py -v"`
Expected: any test that asserted the old list shape will fail. Update those tests to read `body["per_trade"]` instead. (Re-run after.)

- [ ] **Step 6: Commit**

```bash
git add api/routers/trade_advisor.py tests/test_trade_advisor_basket.py tests/test_trade_advisor.py
git commit -m "refactor: /api/trade-advisor returns {per_trade, basket}"
```

---

## Task 7: Basket — `current`, `basket_be`, `net_float`

**Files:**
- Modify: `tests/test_trade_advisor_basket.py`
- Modify: `api/routers/trade_advisor.py`

The basket BE is the price at which closing the entire basket nets zero PnL. For a single-direction basket on XAUUSD this is the volume-weighted average entry. For a mixed basket, it is the price `p` solving `sum(sign_i × vol_i × (p − entry_i)) = 0`. Since net direction is non-flat, this is `(sum sign_i vol_i entry_i) / (sum sign_i vol_i)` — i.e., the same `avg_entry` formula. Task 7 wires the live price (latest M5 close from `price_bars`) and computes net float.

Also need to read latest XAUUSD price. Confirm there's a `price_bars` model.

- [ ] **Step 1: Verify price_bars model**

Run: `grep -n "class PriceBar" /Users/nick/2_SideProjects/trade-signal/api/models/price_bar.py`
Expected: a `PriceBar` model with `time`, `symbol`, `timeframe`, `close` columns. (If column names differ, adjust accordingly in steps below.)

- [ ] **Step 2: Failing test**

Append to `tests/test_trade_advisor_basket.py`:

```python
from models.price_bar import PriceBar


@pytest.mark.asyncio
async def test_basket_uses_latest_m5_close_for_current_and_net_float(client, db_session):
    db_session.add_all([
        _t(9001, Direction.buy, "0.10", "1955.00"),
        _t(9002, Direction.buy, "0.10", "1957.00"),
    ])
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc),
        symbol="XAUUSD", timeframe="M5",
        open=Decimal("1959"), high=Decimal("1960"),
        low=Decimal("1958"), close=Decimal("1960.00"),
        volume=Decimal("100"),
    ))
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("3000"), free_margin=Decimal("97000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    b = res.json()["basket"]
    assert Decimal(str(b["current"])) == Decimal("1960.00")
    assert Decimal(str(b["basket_be"])) == Decimal("1956.00")
    # Net float: (1960 − 1956) × 0.20 lot × 100 (XAUUSD pip value per 1.0 lot) = 80
    # Using contract_size 100 (oz/lot), USD profit ≈ (1960 − 1956) × 100 × 0.20 = 80 USD.
    # Assertion: > 0 (long basket, price above BE).
    assert Decimal(str(b["net_float"])) > 0
```

- [ ] **Step 3: Run test, expect FAIL**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py::test_basket_uses_latest_m5_close_for_current_and_net_float -v"`
Expected: FAIL — `current` is None.

- [ ] **Step 4: Implement current + basket_be + net_float**

In `api/routers/trade_advisor.py`, after the imports add:

```python
from models.price_bar import PriceBar

CONTRACT_SIZE_XAUUSD = Decimal("100")  # 1 lot = 100 oz
```

Modify `get_trade_advisor` to fetch the latest M5 close:

```python
    price_result = await session.execute(
        select(PriceBar.close)
        .where(PriceBar.symbol == "XAUUSD", PriceBar.timeframe == "M5")
        .order_by(PriceBar.time.desc())
        .limit(1)
    )
    latest_close = price_result.scalar_one_or_none()
    basket = _aggregate_basket(trades, snapshot, latest_close)
```

Update `_aggregate_basket` signature + body:

```python
def _aggregate_basket(
    trades: list[Trade],
    snapshot: Optional[AccountSnapshot],
    latest_close: Optional[Decimal],
) -> dict[str, Any]:
    open_trades = [t for t in trades if t.volume and t.open_price and t.direction]
    if not open_trades:
        return _flat_basket()

    buy_vol = sum((t.volume for t in open_trades if t.direction == Direction.buy), Decimal("0"))
    sell_vol = sum((t.volume for t in open_trades if t.direction == Direction.sell), Decimal("0"))
    net = buy_vol - sell_vol
    if net == 0:
        return _flat_basket()
    direction = "buy" if net > 0 else "sell"
    sign = Decimal("1") if direction == "buy" else Decimal("-1")

    weight = Decimal("0")
    notional = Decimal("0")
    for t in open_trades:
        s = Decimal("1") if t.direction == Direction.buy else Decimal("-1")
        notional += t.open_price * t.volume * s
        weight += t.volume * s
    basket_be = (notional / weight).quantize(Decimal("0.01")) if weight != 0 else None

    current = latest_close.quantize(Decimal("0.01")) if latest_close is not None else None
    net_float = None
    if current is not None and basket_be is not None:
        net_float = ((current - basket_be) * sign * abs(net) * CONTRACT_SIZE_XAUUSD).quantize(Decimal("0.01"))

    return {
        "direction": direction,
        "lot_total": float(abs(net)),
        "order_count": len(open_trades),
        "avg_entry": float(basket_be) if basket_be is not None else None,
        "current": float(current) if current is not None else None,
        "basket_be": float(basket_be) if basket_be is not None else None,
        "net_float": float(net_float) if net_float is not None else None,
        "ruin": None,
        "tp_targets": [],
        "add_zones": [],
        "cut": None,
        "pnl_summary": None,
    }
```

- [ ] **Step 5: Run tests**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py -v"`
Expected: 4 pass.

- [ ] **Step 6: Commit**

```bash
git add api/routers/trade_advisor.py tests/test_trade_advisor_basket.py
git commit -m "feat: basket exposes current price, basket_be, net_float"
```

---

## Task 8: Basket — Ruin Zone (stop-out price + buffer + tier)

**Files:**
- Modify: `tests/test_trade_advisor_basket.py`
- Modify: `api/routers/trade_advisor.py`

Stop-out percentage is broker-specific. Read from env `RUIN_STOP_OUT_PCT` (default `50` = 50%).

Ruin price formula (for a long basket of `lot` lots, contract size `C`, entry `E`, equity `eq`, margin `m`, stop-out fraction `s`):

```
stop-out at: eq + (P − E) × C × lot = m × s
=> P = E + (m × s − eq) / (C × lot)
```

For short, flip the sign of `(P − E)`.

- [ ] **Step 1: Failing test for safe / warning / danger tiers**

Append:

```python
@pytest.mark.asyncio
async def test_basket_ruin_safe_tier(client, db_session, monkeypatch):
    monkeypatch.setenv("RUIN_STOP_OUT_PCT", "50")
    db_session.add(_t(9101, Direction.buy, "0.10", "1955.00"))
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc), symbol="XAUUSD", timeframe="M5",
        open=Decimal("1958"), high=Decimal("1958"),
        low=Decimal("1958"), close=Decimal("1958.00"),
        volume=Decimal("100"),
    ))
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("3000"), free_margin=Decimal("97000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    ruin = res.json()["basket"]["ruin"]
    assert ruin["tier"] == "safe"
    assert Decimal(str(ruin["pct_buffer"])) > Decimal("50")
    assert Decimal(str(ruin["pts"])) < 0  # ruin price is below current
    assert Decimal(str(ruin["baht_buffer"])) < 0  # negative baht to ruin


@pytest.mark.asyncio
async def test_basket_ruin_danger_tier_when_buffer_low(client, db_session, monkeypatch):
    monkeypatch.setenv("RUIN_STOP_OUT_PCT", "50")
    db_session.add(_t(9201, Direction.buy, "1.00", "1955.00"))
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc), symbol="XAUUSD", timeframe="M5",
        open=Decimal("1955"), high=Decimal("1955"),
        low=Decimal("1955"), close=Decimal("1955.00"),
        volume=Decimal("100"),
    ))
    # equity barely above margin × stop_out
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("3500"), balance=Decimal("3500"),
        margin=Decimal("3000"), free_margin=Decimal("500"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    ruin = res.json()["basket"]["ruin"]
    assert ruin["tier"] == "danger"


@pytest.mark.asyncio
async def test_basket_ruin_null_when_no_snapshot(client, db_session):
    db_session.add(_t(9301, Direction.buy, "0.10", "1955.00"))
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc), symbol="XAUUSD", timeframe="M5",
        open=Decimal("1958"), high=Decimal("1958"),
        low=Decimal("1958"), close=Decimal("1958.00"),
        volume=Decimal("100"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    assert res.json()["basket"]["ruin"] is None
```

- [ ] **Step 2: Run, expect FAIL**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py -v -k ruin"`
Expected: FAIL — `ruin` is None when expected to have data.

- [ ] **Step 3: Implement Ruin Zone**

In `api/routers/trade_advisor.py`, add at module top:

```python
import os
```

Add helper:

```python
def _compute_ruin(
    direction: str,
    abs_lot: Decimal,
    basket_be: Decimal,
    current: Decimal,
    snapshot: AccountSnapshot,
) -> Optional[dict]:
    if snapshot is None or snapshot.equity is None or snapshot.margin is None:
        return None
    if abs_lot == 0 or basket_be is None or current is None:
        return None
    stop_out_pct = Decimal(os.getenv("RUIN_STOP_OUT_PCT", "50")) / Decimal("100")
    sign = Decimal("1") if direction == "buy" else Decimal("-1")

    threshold_equity = snapshot.margin * stop_out_pct
    delta_eq = threshold_equity - snapshot.equity
    contract = CONTRACT_SIZE_XAUUSD
    # For long: P = entry + (delta_eq) / (C × lot)
    # For short: P = entry − (delta_eq) / (C × lot)
    price_delta = delta_eq / (contract * abs_lot)
    ruin_price = (basket_be + sign * price_delta).quantize(Decimal("0.01"))

    pts = (ruin_price - current).quantize(Decimal("0.01"))
    baht_buffer = ((ruin_price - current) * sign * abs_lot * contract).quantize(Decimal("0.01"))
    pct_buffer = ((snapshot.equity - threshold_equity) / snapshot.equity * Decimal("100")).quantize(
        Decimal("0.1")
    ) if snapshot.equity != 0 else Decimal("0")

    if pct_buffer >= Decimal("50"):
        tier = "safe"
    elif pct_buffer >= Decimal("20"):
        tier = "warning"
    else:
        tier = "danger"

    return {
        "price": float(ruin_price),
        "pts": float(pts),
        "baht_buffer": float(baht_buffer),
        "pct_buffer": float(pct_buffer),
        "tier": tier,
    }
```

In `_aggregate_basket`, after computing `net_float`, replace `"ruin": None,` with:

```python
        "ruin": _compute_ruin(direction, abs(net), basket_be, current, snapshot)
                 if snapshot and basket_be and current else None,
```

- [ ] **Step 4: Run ruin tests**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py -v -k ruin"`
Expected: 3 pass.

- [ ] **Step 5: Commit**

```bash
git add api/routers/trade_advisor.py tests/test_trade_advisor_basket.py
git commit -m "feat: basket exposes Ruin Zone with safe/warning/danger tiering"
```

---

## Task 9: Basket — TP targets, Add zones, Cut (port from existing recovery_plan)

The existing `recovery_plan` on each Trade already encodes per-trade TP / Add / Cut zones. For the basket view, choose the **primary trade** (lowest entry for buy basket, highest for sell basket — the deepest position) and surface its `recovery_plan` as the basket-level zones.

**Files:**
- Modify: `tests/test_trade_advisor_basket.py`
- Modify: `api/routers/trade_advisor.py`

- [ ] **Step 1: Failing test**

Append:

```python
@pytest.mark.asyncio
async def test_basket_tp_targets_and_zones_use_deepest_trade(client, db_session):
    plan = {
        "entry_price": 1955.0,
        "tp": [
            {"label": "BE", "price": 1956.85, "pts": 18.5},
            {"label": "R1", "price": 1965.10, "pts": 101.0},
            {"label": "R2", "price": 1972.50, "pts": 175.0},
        ],
        "add": [
            {"label": "S1", "price": 1948.30, "pts": -67.0},
            {"label": "S2", "price": 1940.10, "pts": -149.0},
        ],
        "cut": {"label": "S3", "price": 1928.50, "pts": -265.0},
    }
    deepest = _t(9401, Direction.buy, "0.10", "1955.00")
    deepest.recovery_plan = plan
    db_session.add(deepest)
    db_session.add(_t(9402, Direction.buy, "0.10", "1958.00"))  # newer, higher entry
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc), symbol="XAUUSD", timeframe="M5",
        open=Decimal("1959"), high=Decimal("1959"),
        low=Decimal("1959"), close=Decimal("1959.00"),
        volume=Decimal("100"),
    ))
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("3000"), free_margin=Decimal("97000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    b = (await client.get("/api/trade-advisor")).json()["basket"]
    labels = [tp["label"] for tp in b["tp_targets"]]
    assert labels == ["R2", "R1", "BE"]  # newest first as TP order
    assert [z["label"] for z in b["add_zones"]] == ["S1", "S2"]
    assert b["cut"]["label"] == "S3"
```

- [ ] **Step 2: Run, expect FAIL**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py::test_basket_tp_targets_and_zones_use_deepest_trade -v"`
Expected: FAIL — empty `tp_targets`.

- [ ] **Step 3: Implement zone selection**

In `api/routers/trade_advisor.py`, add helper:

```python
def _select_basket_zones(open_trades: list[Trade], direction: str, abs_lot: Decimal) -> tuple[list, list, Optional[dict]]:
    candidates = [t for t in open_trades if t.recovery_plan and t.direction]
    if not candidates:
        return [], [], None
    if direction == "buy":
        deepest = min(candidates, key=lambda t: t.open_price)
    else:
        deepest = max(candidates, key=lambda t: t.open_price)
    plan = deepest.recovery_plan or {}
    contract = CONTRACT_SIZE_XAUUSD
    entry = Decimal(str(plan.get("entry_price") or deepest.open_price))
    sign = Decimal("1") if direction == "buy" else Decimal("-1")

    def _baht(price):
        return float(((Decimal(str(price)) - entry) * sign * abs_lot * contract).quantize(Decimal("0.01")))

    tp_raw = list(plan.get("tp") or [])
    tp_targets = [{"label": z["label"], "price": z["price"], "baht": _baht(z["price"])}
                  for z in reversed(tp_raw)]
    add_zones = [{"label": z["label"], "price": z["price"], "baht": _baht(z["price"])}
                 for z in (plan.get("add") or [])]
    cut_raw = plan.get("cut")
    cut = {"label": cut_raw["label"], "price": cut_raw["price"], "baht": _baht(cut_raw["price"])} if cut_raw else None
    return tp_targets, add_zones, cut
```

In `_aggregate_basket`, after computing `ruin`, build zones and override the placeholder fields:

```python
    tp_targets, add_zones, cut = _select_basket_zones(open_trades, direction, abs(net))
    return {
        "direction": direction,
        "lot_total": float(abs(net)),
        "order_count": len(open_trades),
        "avg_entry": float(basket_be) if basket_be is not None else None,
        "current": float(current) if current is not None else None,
        "basket_be": float(basket_be) if basket_be is not None else None,
        "net_float": float(net_float) if net_float is not None else None,
        "ruin": _compute_ruin(direction, abs(net), basket_be, current, snapshot)
                 if snapshot and basket_be and current else None,
        "tp_targets": tp_targets,
        "add_zones": add_zones,
        "cut": cut,
        "pnl_summary": None,
    }
```

- [ ] **Step 4: Run test**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py -v"`
Expected: all 8 pass.

- [ ] **Step 5: Commit**

```bash
git add api/routers/trade_advisor.py tests/test_trade_advisor_basket.py
git commit -m "feat: basket exposes tp_targets, add_zones, cut from deepest trade"
```

---

## Task 10: Basket — `pnl_summary` (today / week / month)

**Files:**
- Modify: `tests/test_trade_advisor_basket.py`
- Modify: `api/routers/trade_advisor.py`

Reuse the same trade selection used by `/api/pnl-history` (closed real trades, account-scoped, profit not null), but bucket only the three windows.

- [ ] **Step 1: Failing test**

Append:

```python
@pytest.mark.asyncio
async def test_basket_pnl_summary_buckets_today_week_month(client, db_session, monkeypatch):
    today_close = datetime(2026, 5, 26, 12, tzinfo=_BKK).astimezone(timezone.utc)
    week_close = datetime(2026, 5, 22, 12, tzinfo=_BKK).astimezone(timezone.utc)  # Mon=2026-05-25
    month_close = datetime(2026, 5, 5, 12, tzinfo=_BKK).astimezone(timezone.utc)
    older = datetime(2026, 4, 5, 12, tzinfo=_BKK).astimezone(timezone.utc)

    db_session.add_all([
        Trade(id=uuid4(), ticket=10001, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=False,
              open_time=today_close, close_time=today_close,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("420.00")),
        Trade(id=uuid4(), ticket=10002, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=False,
              open_time=week_close, close_time=week_close,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("1430.00")),
        Trade(id=uuid4(), ticket=10003, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=False,
              open_time=month_close, close_time=month_close,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("2380.00")),
        Trade(id=uuid4(), ticket=10004, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=False,
              open_time=older, close_time=older,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("999.00")),
    ])
    db_session.add(AccountSnapshot(
        timestamp=today_close,
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("0"), free_margin=Decimal("100000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    monkeypatch.setattr(
        "routers.trade_advisor._today_in_bkk",
        lambda: datetime(2026, 5, 26, tzinfo=_BKK).date(),
    )

    b = (await client.get("/api/trade-advisor")).json()["basket"]
    s = b["pnl_summary"]
    assert Decimal(str(s["today"]["baht"])) == Decimal("420.00")
    assert Decimal(str(s["week"]["baht"])) == Decimal("1850.00")  # today + 22 May
    assert Decimal(str(s["month"]["baht"])) == Decimal("4230.00")  # all of May
```

- [ ] **Step 2: Run, expect FAIL**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py::test_basket_pnl_summary_buckets_today_week_month -v"`
Expected: FAIL — `pnl_summary` None.

- [ ] **Step 3: Implement pnl_summary**

In `api/routers/trade_advisor.py`, add helpers:

```python
from datetime import date, datetime, timedelta, timezone

_BKK = timezone(timedelta(hours=7))


def _today_in_bkk() -> date:
    return datetime.now(_BKK).date()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
```

Add async helper at module level:

```python
async def _compute_pnl_summary(
    session: AsyncSession,
    snapshot: Optional[AccountSnapshot],
) -> Optional[dict]:
    today = _today_in_bkk()
    week_monday = today - timedelta(days=today.isoweekday() - 1)
    month_start = today.replace(day=1)

    stmt = select(Trade).where(
        Trade.is_paper == False,
        Trade.order_state == OrderState.filled,
        Trade.close_time.isnot(None),
        Trade.profit.isnot(None),
    )
    if snapshot and snapshot.account_id is not None:
        stmt = stmt.where(Trade.account_id == snapshot.account_id)
    res = await session.execute(stmt)
    trades = res.scalars().all()

    today_b = Decimal("0.00")
    week_b = Decimal("0.00")
    month_b = Decimal("0.00")
    for t in trades:
        d = _as_utc(t.close_time).astimezone(_BKK).date()
        if d == today:
            today_b += t.profit
        if d >= week_monday:
            week_b += t.profit
        if d >= month_start:
            month_b += t.profit

    base = snapshot.balance if snapshot else None

    def _row(b):
        return {
            "baht": float(b.quantize(Decimal("0.01"))),
            "pct": (float(((b / base) * Decimal("100")).quantize(Decimal("0.01")))
                    if base and base != 0 else None),
        }

    return {"today": _row(today_b), "week": _row(week_b), "month": _row(month_b)}
```

In `get_trade_advisor`, after computing `basket`:

```python
    basket["pnl_summary"] = await _compute_pnl_summary(session, snapshot)
```

(Note: even on a flat basket we still want PnL summary visible — so call this regardless.)

- [ ] **Step 4: Run test**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_trade_advisor_basket.py -v"`
Expected: 9 pass.

- [ ] **Step 5: Run full backend regression**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -v --tb=short"`
Expected: existing trade-advisor tests in `test_trade_advisor.py` may fail because response shape changed. Fix them by reading `body["per_trade"]` instead of treating body as a list. Re-run until green.

- [ ] **Step 6: Commit**

```bash
git add api/routers/trade_advisor.py tests/test_trade_advisor_basket.py tests/test_trade_advisor.py
git commit -m "feat: basket pnl_summary aggregates today/week/month closed PnL"
```

---

## Task 11: `/api/paper-trader-rules` — add `paper_pnl_today` + `paper_pnl_week`

**Files:**
- Create: `tests/test_paper_trader_rules_paper_pnl.py`
- Modify: `api/schemas/pattern.py`
- Modify: `api/routers/patterns.py`

- [ ] **Step 1: Failing test**

Create `tests/test_paper_trader_rules_paper_pnl.py`:

```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, Trade

_BKK = timezone(timedelta(hours=7))


@pytest.mark.asyncio
async def test_paper_trader_rule_pnl_today_and_week(client, db_session):
    today = datetime(2026, 5, 26, 12, tzinfo=_BKK).astimezone(timezone.utc)
    yesterday = today - timedelta(days=1)
    week_old = today - timedelta(days=8)

    pattern = Pattern(
        id=uuid4(), indicator_slugs=["rsi_14"], timeframe="M15",
        win_rate=0.6, sample_count=20, consecutive_stable_days=3,
        status="active", discovered_at=today,
    )
    rule = PaperTraderRule(
        id=uuid4(), pattern_id=pattern.id, status="active",
        spawned_at=today, total_trades=0, win_count=0,
        virtual_balance_start=Decimal("5000"), virtual_balance_current=Decimal("5500"),
    )
    db_session.add_all([
        pattern, rule,
        Trade(id=uuid4(), ticket=20001, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=True,
              paper_trader_rule_id=rule.id,
              open_time=today, close_time=today,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("100.00")),
        Trade(id=uuid4(), ticket=20002, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=True,
              paper_trader_rule_id=rule.id,
              open_time=yesterday, close_time=yesterday,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("250.00")),
        Trade(id=uuid4(), ticket=20003, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=True,
              paper_trader_rule_id=rule.id,
              open_time=week_old, close_time=week_old,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("999.00")),
    ])
    await db_session.commit()

    res = await client.get("/api/paper-trader-rules")
    rows = res.json()
    assert len(rows) == 1
    row = rows[0]
    # Note: precise day boundaries depend on test clock vs `today` constant;
    # we assert today is a subset of week, and old is excluded.
    assert Decimal(row["paper_pnl_today"]) >= Decimal("0")
    assert Decimal(row["paper_pnl_week"]) >= Decimal(row["paper_pnl_today"])
    assert Decimal(row["paper_pnl_week"]) < Decimal("999.00")  # 8-day-old excluded
```

- [ ] **Step 2: Run, expect FAIL**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_paper_trader_rules_paper_pnl.py -v"`
Expected: FAIL — `paper_pnl_today` key missing.

- [ ] **Step 3: Add 2 fields to schema**

In `api/schemas/pattern.py`, append to `PaperTraderRuleResponse`:

```python
    paper_pnl_today: Decimal = Decimal("0")
    paper_pnl_week: Decimal = Decimal("0")
```

- [ ] **Step 4: Compute the two fields in router**

In `api/routers/patterns.py`, add helper near `_realized_pnl_by_rule`:

```python
async def _realized_pnl_window_by_rule(
    session: AsyncSession, since: datetime
) -> dict[str, Decimal]:
    stmt = select(Trade).where(
        Trade.is_paper.is_(True),
        Trade.close_time.is_not(None),
        Trade.close_time >= since,
    )
    result = await session.execute(stmt)
    totals: dict[str, Decimal] = {}
    for trade in result.scalars().all():
        if trade.profit is None:
            continue
        rid: Optional[str] = None
        if trade.paper_trader_rule_id is not None:
            rid = str(trade.paper_trader_rule_id)
        else:
            plan = trade.recovery_plan or {}
            if isinstance(plan, dict):
                raw = plan.get("paper_trader_rule_id")
                rid = str(raw) if raw else None
        if not rid:
            continue
        totals[rid] = totals.get(rid, Decimal("0")) + trade.profit
    return totals
```

In `list_paper_trader_rules`, after computing `realized_pnl`:

```python
    from datetime import timedelta
    _BKK = timezone(timedelta(hours=7))
    today_bkk = datetime.now(_BKK).date()
    today_start_utc = datetime(today_bkk.year, today_bkk.month, today_bkk.day, tzinfo=_BKK).astimezone(timezone.utc)
    week_monday = today_bkk - timedelta(days=today_bkk.isoweekday() - 1)
    week_start_utc = datetime(week_monday.year, week_monday.month, week_monday.day, tzinfo=_BKK).astimezone(timezone.utc)
    pnl_today = await _realized_pnl_window_by_rule(session, today_start_utc)
    pnl_week = await _realized_pnl_window_by_rule(session, week_start_utc)
```

In the list comprehension, set:

```python
                paper_pnl_today=pnl_today.get(str(r.id), Decimal("0")),
                paper_pnl_week=pnl_week.get(str(r.id), Decimal("0")),
```

- [ ] **Step 5: Run test**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_paper_trader_rules_paper_pnl.py -v"`
Expected: PASS.

- [ ] **Step 6: Run full suite — confirm `test_paper_trader_rules_extended.py` still green**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_paper_trader_rules_extended.py tests/test_paper_trader_rules_paper_pnl.py -v"`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add api/schemas/pattern.py api/routers/patterns.py tests/test_paper_trader_rules_paper_pnl.py
git commit -m "feat: paper-trader-rules expose paper_pnl_today + paper_pnl_week"
```

---

## Task 12: Tailwind Modern Indigo color tokens

**Files:**
- Modify: `frontend/tailwind.config.js`

- [ ] **Step 1: Add semantic color tokens**

Replace `frontend/tailwind.config.js`:

```js
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        base: '#020617',
        surface: '#0f172a',
        card: '#1e293b',
        'border-default': '#334155',
        'text-primary': '#f1f5f9',
        'text-dim': '#94a3b8',
        profit: '#34d399',
        loss: '#fb7185',
        neutral: '#38bdf8',
        warning: '#fbbf24',
        brand: '#6366f1',
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: clean build, no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/tailwind.config.js
git commit -m "feat: add Modern Indigo color tokens to tailwind"
```

---

## Task 13: `<SectionDivider />` component

**Files:**
- Create: `frontend/src/components/SectionDivider.jsx`

- [ ] **Step 1: Create component**

Create `frontend/src/components/SectionDivider.jsx`:

```jsx
export default function SectionDivider({ label }) {
  return (
    <div className="flex items-center gap-3 my-6">
      <div className="h-px flex-1 bg-border-default" />
      <span className="text-xs font-semibold uppercase tracking-wider text-text-dim">
        {label}
      </span>
      <div className="h-px flex-1 bg-border-default" />
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SectionDivider.jsx
git commit -m "feat: add SectionDivider component"
```

---

## Task 14: `<TopBar />` component

**Files:**
- Create: `frontend/src/components/TopBar.jsx`

`<TopBar />` is the sticky `h-14 z-50` strip with: Equity, Today PnL (signed + %), Float PL, XAUUSD live price, Alerts badge, EA status dot. Reads existing `account` data + an `alertCount` + `eaOnline` boolean as props (App.jsx will compute these).

- [ ] **Step 1: Create component**

Create `frontend/src/components/TopBar.jsx`:

```jsx
function fmtBaht(n, withSign = true) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = withSign && v >= 0 ? '+' : v < 0 ? '-' : ''
  return `${sign}฿${Math.abs(Math.round(v)).toLocaleString()}`
}

function fmtPct(n) {
  if (n == null) return ''
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

export default function TopBar({
  equity,
  todayPnlBaht,
  todayPnlPct,
  floatPl,
  xauPrice,
  alertCount = 0,
  eaOnline = false,
  onAlertsClick,
}) {
  const todayTone = (todayPnlBaht ?? 0) >= 0 ? 'text-profit' : 'text-loss'
  const floatTone = (floatPl ?? 0) >= 0 ? 'text-profit' : 'text-loss'

  return (
    <div className="sticky top-0 z-50 h-14 bg-surface border-b border-border-default flex items-center px-4 gap-6">
      <div className="flex items-center gap-4 text-sm">
        <span className="font-mono text-text-primary">฿{Math.round(Number(equity ?? 0)).toLocaleString()}</span>
        <span className={`font-mono ${todayTone}`}>
          {fmtBaht(todayPnlBaht)} ({fmtPct(todayPnlPct)})
        </span>
        <span className="text-text-dim">
          Float: <span className={`font-mono ${floatTone}`}>{fmtBaht(floatPl)}</span>
        </span>
      </div>
      <div className="flex-1 text-center">
        <span className="font-mono text-neutral text-base">
          XAUUSD {xauPrice != null ? Number(xauPrice).toFixed(2) : '—'}
        </span>
      </div>
      <div className="flex items-center gap-3 text-sm">
        <button
          type="button"
          onClick={onAlertsClick}
          className="relative px-2 py-1 rounded hover:bg-card"
        >
          🔔
          {alertCount > 0 && (
            <span className="absolute -top-1 -right-1 bg-loss text-white text-xs px-1.5 rounded-full">
              {alertCount}
            </span>
          )}
        </button>
        <span className={`flex items-center gap-1 ${eaOnline ? 'text-profit' : 'text-text-dim'}`}>
          EA<span className={`w-2 h-2 rounded-full ${eaOnline ? 'bg-profit' : 'bg-text-dim'}`} />
        </span>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TopBar.jsx
git commit -m "feat: add sticky TopBar component"
```

---

## Task 15: `<PnlHistoryModal />` — shell + tabs + close behaviors

**Files:**
- Create: `frontend/src/components/PnlHistoryModal.jsx`

- [ ] **Step 1: Create modal**

Create `frontend/src/components/PnlHistoryModal.jsx`:

```jsx
import { useEffect, useState } from 'react'

const API = 'http://localhost:8000'
const TABS = [
  { key: 'all', label: 'All' },
  { key: 'daily', label: 'Daily' },
  { key: 'weekly', label: 'Weekly' },
  { key: 'monthly', label: 'Monthly' },
]

function fmtBaht(n) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `${sign}฿${Math.round(v).toLocaleString()}`
}

function fmtPct(n) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

export default function PnlHistoryModal({ open, onClose }) {
  const [tab, setTab] = useState('daily')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setError(null)
    fetch(`${API}/api/pnl-history?granularity=${tab}&page=${page}&page_size=20`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(json => { if (!cancelled) setData(json) })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [open, tab, page])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-surface border border-border-default rounded-lg w-full max-w-2xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-border-default">
          <h2 className="text-text-primary font-semibold">PnL History</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-text-dim hover:text-text-primary text-xl leading-none"
            aria-label="Close"
          >×</button>
        </div>
        <div className="flex gap-2 p-4 border-b border-border-default">
          {TABS.map(t => (
            <button
              key={t.key}
              type="button"
              onClick={() => { setTab(t.key); setPage(1) }}
              className={`px-3 py-1 text-xs rounded ${
                t.key === tab ? 'bg-brand text-white' : 'bg-card text-text-dim'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-auto p-4">
          {error && <div className="text-loss text-sm">Failed to load: {error}</div>}
          {!error && !data && <div className="text-text-dim text-sm">Loading…</div>}
          {data && (
            <table className="w-full text-sm">
              <thead className="text-xs text-text-dim text-left">
                <tr><th className="py-1">Period</th><th>P/L</th><th>%</th><th className="text-right">Trades</th></tr>
              </thead>
              <tbody>
                {data.items.map((row, i) => {
                  const tone = Number(row.profit) >= 0 ? 'text-profit' : 'text-loss'
                  return (
                    <tr key={`${row.period}-${i}`} className={i % 2 === 0 ? 'bg-card' : ''}>
                      <td className="py-1 px-2 text-text-primary">{row.period}</td>
                      <td className={`px-2 font-mono ${tone}`}>{fmtBaht(row.profit)}</td>
                      <td className={`px-2 font-mono ${tone}`}>{fmtPct(row.profit_pct)}</td>
                      <td className="px-2 text-right text-text-dim">{row.trade_count}</td>
                    </tr>
                  )
                })}
                {data.items.length === 0 && (
                  <tr><td colSpan={4} className="py-4 text-center text-text-dim">No data</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-center gap-3 p-3 border-t border-border-default text-sm">
            <button
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
              className="px-2 py-1 bg-card rounded disabled:opacity-40"
            >◀ Prev</button>
            <span className="text-text-dim">Page {data.page} / {data.total_pages}</span>
            <button
              disabled={page >= data.total_pages}
              onClick={() => setPage(p => p + 1)}
              className="px-2 py-1 bg-card rounded disabled:opacity-40"
            >Next ▶</button>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PnlHistoryModal.jsx
git commit -m "feat: add PnlHistoryModal with tabs + pagination"
```

---

## Task 16: `<BasketExitPlan />` + refactor `<TradeAdvisor />`

**Files:**
- Create: `frontend/src/components/BasketExitPlan.jsx`
- Modify: `frontend/src/components/TradeAdvisor.jsx`

- [ ] **Step 1: Create BasketExitPlan**

Create `frontend/src/components/BasketExitPlan.jsx`:

```jsx
import { useState } from 'react'
import PnlHistoryModal from './PnlHistoryModal'

function fmtBaht(n, withSign = true) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = withSign && v > 0 ? '+' : v < 0 ? '-' : ''
  return `${sign}฿${Math.abs(Math.round(v)).toLocaleString()}`
}

function fmtPct(n) {
  if (n == null) return ''
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `(${sign}${v.toFixed(2)}%)`
}

const TIER_BG = {
  safe: 'border-profit/30',
  warning: 'border-warning/40',
  danger: 'border-loss/50',
}
const TIER_DOT = { safe: '🟢', warning: '🟡', danger: '🔴' }

export default function BasketExitPlan({ basket }) {
  const [pnlOpen, setPnlOpen] = useState(false)
  if (!basket || basket.direction === 'flat') {
    return (
      <div className="bg-card border border-border-default rounded-lg p-4 text-text-dim text-sm">
        No open positions
        {basket?.pnl_summary && (
          <PnlSummaryBox summary={basket.pnl_summary} onClick={() => setPnlOpen(true)} />
        )}
        <PnlHistoryModal open={pnlOpen} onClose={() => setPnlOpen(false)} />
      </div>
    )
  }

  const floatTone = (basket.net_float ?? 0) >= 0 ? 'text-profit' : 'text-loss'

  return (
    <div className="bg-card border border-border-default rounded-lg p-4 space-y-3">
      <div className="text-text-dim text-xs uppercase tracking-wider">Basket Exit Plan</div>
      <div className="text-sm space-y-1">
        <div>
          Net direction: <span className="font-semibold text-text-primary">
            {basket.direction.toUpperCase()}
          </span>
          <span className="text-text-dim"> ({basket.lot_total} lot, {basket.order_count} orders)</span>
        </div>
        <div className="grid grid-cols-2 gap-x-4 font-mono text-text-primary">
          <span>Avg entry: {basket.avg_entry?.toFixed(2) ?? '—'}</span>
          <span>Current: {basket.current?.toFixed(2) ?? '—'}</span>
          <span>Basket BE: {basket.basket_be?.toFixed(2) ?? '—'}</span>
          <span className={floatTone}>Net float: {fmtBaht(basket.net_float)}</span>
        </div>
      </div>
      {basket.pnl_summary && (
        <PnlSummaryBox summary={basket.pnl_summary} onClick={() => setPnlOpen(true)} />
      )}
      {basket.ruin && <RuinZone ruin={basket.ruin} />}
      {basket.tp_targets.length > 0 && (
        <div>
          <div className="text-profit text-xs font-semibold uppercase tracking-wide mb-1">TP Targets (close basket)</div>
          {basket.tp_targets.map(z => (
            <div key={z.label} className="flex justify-between font-mono text-sm text-profit/90">
              <span className="w-8">{z.label}</span>
              <span>{Number(z.price).toFixed(2)}</span>
              <span className="text-right w-20">{fmtBaht(z.baht)}</span>
            </div>
          ))}
        </div>
      )}
      {basket.add_zones.length > 0 && (
        <div>
          <div className="text-loss text-xs font-semibold uppercase tracking-wide mb-1">Add Zones</div>
          {basket.add_zones.map(z => (
            <div key={z.label} className="flex justify-between font-mono text-sm text-loss/90">
              <span className="w-8">{z.label}</span>
              <span>{Number(z.price).toFixed(2)}</span>
              <span className="text-right w-20">{fmtBaht(z.baht)}</span>
            </div>
          ))}
        </div>
      )}
      {basket.cut && (
        <div className="flex justify-between font-mono text-sm text-warning border-t border-border-default pt-2">
          <span>Cut basket if {basket.cut.label} breached</span>
          <span>{Number(basket.cut.price).toFixed(2)}</span>
          <span className="text-right w-20">{fmtBaht(basket.cut.baht)}</span>
        </div>
      )}
      <PnlHistoryModal open={pnlOpen} onClose={() => setPnlOpen(false)} />
    </div>
  )
}

function PnlSummaryBox({ summary, onClick }) {
  const Cell = ({ label, row }) => {
    if (!row) return <div><div className="text-text-dim text-xs">{label}</div><div>—</div></div>
    const tone = Number(row.baht) >= 0 ? 'text-profit' : 'text-loss'
    return (
      <div>
        <div className="text-text-dim text-xs">{label}</div>
        <div className={`font-mono ${tone}`}>{fmtBaht(row.baht)}</div>
        <div className={`text-xs font-mono ${tone}`}>{fmtPct(row.pct)}</div>
      </div>
    )
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left bg-surface border border-border-default rounded p-3 grid grid-cols-3 gap-3 hover:ring-1 hover:ring-brand cursor-pointer"
    >
      <Cell label="Today" row={summary.today} />
      <Cell label="This week" row={summary.week} />
      <Cell label="This month" row={summary.month} />
    </button>
  )
}

function RuinZone({ ruin }) {
  return (
    <div className={`bg-surface border ${TIER_BG[ruin.tier] || 'border-border-default'} rounded p-3 text-sm`}>
      <div className="text-warning text-xs font-semibold uppercase tracking-wide mb-1">⚠ Ruin Zone</div>
      <div className="grid grid-cols-2 gap-x-4 font-mono">
        <span>Stop-out price:</span><span>{Number(ruin.price).toFixed(2)}</span>
        <span>Safety margin:</span>
        <span>{Number(ruin.pts).toFixed(0)} pts ({fmtBaht(ruin.baht_buffer)})</span>
        <span>Buffer:</span>
        <span>{Number(ruin.pct_buffer).toFixed(1)}% {TIER_DOT[ruin.tier] || ''}</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Refactor TradeAdvisor.jsx into a thin wrapper**

Replace `frontend/src/components/TradeAdvisor.jsx`:

```jsx
import BasketExitPlan from './BasketExitPlan'

export default function TradeAdvisor({ data }) {
  if (!data) return <div className="text-text-dim text-sm p-4">Loading…</div>
  return <BasketExitPlan basket={data.basket} />
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/BasketExitPlan.jsx frontend/src/components/TradeAdvisor.jsx
git commit -m "refactor: TradeAdvisor renders BasketExitPlan with Ruin Zone + PnL Summary modal"
```

---

## Task 17: `<OpenPositions />` — score chip below each row

**Files:**
- Modify: `frontend/src/components/OpenPositions.jsx`

- [ ] **Step 1: Add score chip rendering**

Open `frontend/src/components/OpenPositions.jsx`. Add this helper at module top:

```jsx
function chipForScore(score, verdict) {
  if (score == null) return null
  const s = Number(score)
  let cls = 'border-loss/30 text-loss bg-loss/10'
  if (s >= 7) cls = 'border-profit/30 text-profit bg-profit/10'
  else if (s >= 4) cls = 'border-warning/30 text-warning bg-warning/10'
  const label = verdict === 'good' ? 'Good entry' : verdict === 'caution' ? 'Caution' : verdict === 'high_risk' ? 'High risk' : ''
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs ${cls}`}>
      ● {s.toFixed(1)} {label}
    </span>
  )
}
```

Then in the `tbody` map, after the existing `<tr>` add a sibling row that spans all columns:

```jsx
              return (
                <>
                  <tr key={t.ticket} className="border-b border-gray-800 last:border-0">
                    {/* existing cells … */}
                  </tr>
                  {(t.entry_score != null) && (
                    <tr key={`${t.ticket}-chip`} className="border-b border-gray-800 last:border-0">
                      <td colSpan={8} className="py-1 pl-1">
                        {chipForScore(t.entry_score, t.entry_verdict)}
                      </td>
                    </tr>
                  )}
                </>
              )
```

(Keep React `key` on the wrapping `<tr>`s. The `<>` fragment needs a stable `key` — wrap in `<React.Fragment key={t.ticket}>` instead.)

Final form of that map element:

```jsx
              return (
                <React.Fragment key={t.ticket}>
                  <tr className="border-b border-gray-800 last:border-0">
                    {/* … existing cells unchanged … */}
                  </tr>
                  {t.entry_score != null && (
                    <tr className="border-b border-gray-800 last:border-0">
                      <td colSpan={8} className="py-1 pl-1">
                        {chipForScore(t.entry_score, t.entry_verdict)}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
```

Add `import React from 'react'` at top.

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/OpenPositions.jsx
git commit -m "feat: OpenPositions shows score chip below each trade"
```

---

## Task 18: `<PaperTradeConsole />` — header strip with active count + today/week PnL

**Files:**
- Modify: `frontend/src/components/PaperTradeConsole.jsx`

- [ ] **Step 1: Compute totals + restyle filter buttons**

Replace `frontend/src/components/PaperTradeConsole.jsx`:

```jsx
import { useMemo, useState } from 'react'
import PaperRuleCard from './PaperRuleCard'
import { TIER_RANK } from './TrustTierBadge'
import { usePaperRules, usePatternsById, usePaperSignalNotifications } from '../hooks/usePaperSignals'

const TIER_FILTERS = ['all', 'ea_candidate', 'live_proven', 'validated', 'experimental']

function fmtBaht(n) {
  if (n == null) return '฿0'
  const v = Number(n)
  const sign = v > 0 ? '+' : v < 0 ? '-' : ''
  return `${sign}฿${Math.abs(Math.round(v)).toLocaleString()}`
}

export default function PaperTradeConsole() {
  const [tierFilter, setTierFilter] = useState('all')
  const rules = usePaperRules()
  const { byId: patternsById } = usePatternsById()
  usePaperSignalNotifications(rules.data)

  const sorted = useMemo(() => {
    const list = (rules.data || []).filter((r) => r.status !== 'shadow')
    list.sort((a, b) => {
      const ta = TIER_RANK[a.trust_tier] || 0
      const tb = TIER_RANK[b.trust_tier] || 0
      if (ta !== tb) return tb - ta
      const ea = Number(a.net_ev_per_trade ?? -Infinity)
      const eb = Number(b.net_ev_per_trade ?? -Infinity)
      return eb - ea
    })
    if (tierFilter !== 'all') return list.filter((r) => r.trust_tier === tierFilter)
    return list
  }, [rules.data, tierFilter])

  const totals = useMemo(() => {
    const list = (rules.data || []).filter((r) => r.status !== 'shadow')
    const today = list.reduce((s, r) => s + Number(r.paper_pnl_today ?? 0), 0)
    const week = list.reduce((s, r) => s + Number(r.paper_pnl_week ?? 0), 0)
    return { active: list.length, today, week }
  }, [rules.data])

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="text-sm text-text-dim">
          <span className="text-text-primary font-semibold">{totals.active}</span> active rules ·{' '}
          Today: <span className={totals.today >= 0 ? 'text-profit' : 'text-loss'}>{fmtBaht(totals.today)}</span> ·{' '}
          Week: <span className={totals.week >= 0 ? 'text-profit' : 'text-loss'}>{fmtBaht(totals.week)}</span>
        </div>
        <div className="flex gap-2 flex-wrap">
          {TIER_FILTERS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTierFilter(t)}
              className={`px-2 py-1 text-xs rounded ${
                t === tierFilter ? 'bg-brand text-white' : 'bg-card text-text-dim'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      {rules.error && <div className="text-xs text-loss">Failed to load rules</div>}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {sorted.map((r) => (
          <PaperRuleCard key={r.id} rule={r} pattern={patternsById[r.pattern_id]} />
        ))}
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PaperTradeConsole.jsx
git commit -m "feat: PaperTradeConsole header strip with active count + today/week PnL"
```

---

## Task 19: `<TraderProfile />` — Account Detail sub-block

**Files:**
- Modify: `frontend/src/components/TraderProfile.jsx`

- [ ] **Step 1: Accept `account` prop and render Account Detail**

In `frontend/src/components/TraderProfile.jsx`, change signature to `function TraderProfile({ data, account, error })` and add at the top of the rendered card (before the existing narrative `<div className="mb-3">`):

```jsx
      <div className="mb-3 grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs border-b border-border-default pb-3">
        <Stat label="Balance" value={account?.balance} />
        <Stat label="Margin" value={account?.margin} />
        <Stat label="Free margin" value={account?.free_margin} />
        <Stat label="Margin level" value={
          account && Number(account.margin) > 0
            ? `${((Number(account.equity) / Number(account.margin)) * 100).toFixed(1)}%`
            : '—'
        } isString />
      </div>
```

Add the Stat helper above the export:

```jsx
function Stat({ label, value, isString }) {
  let display = '—'
  if (isString) display = value
  else if (value != null) display = `฿${Math.round(Number(value)).toLocaleString()}`
  return (
    <div>
      <div className="text-text-dim">{label}</div>
      <div className="font-mono text-text-primary">{display}</div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TraderProfile.jsx
git commit -m "feat: TraderProfile shows Account Detail sub-block"
```

---

## Task 20: Restructure `App.jsx` — TopBar + 3 grid sections

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Replace App.jsx**

Replace `frontend/src/App.jsx`:

```jsx
import { useCallback, useState, useMemo } from 'react'
import { usePolling } from './hooks/usePolling'
import { useTradeAlerts } from './hooks/useTradeAlerts'
import TopBar from './components/TopBar'
import SectionDivider from './components/SectionDivider'
import AlertsPanel from './components/AlertsPanel'
import InsightsPanel from './components/InsightsPanel'
import FibPanel from './components/FibPanel'
import TraderProfile from './components/TraderProfile'
import OpenPositions from './components/OpenPositions'
import ClosedTrades from './components/ClosedTrades'
import PnlChart from './components/PnlChart'
import TradeAdvisor from './components/TradeAdvisor'
import PaperTradeConsole from './components/PaperTradeConsole'

const API = 'http://localhost:8000'

async function get(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export default function App() {
  const [closedLimit, setClosedLimit] = useState(20)
  const [closedOffset, setClosedOffset] = useState(0)

  const fetchAccount = useCallback(() => get('/api/account'), [])
  const fetchAlerts = useCallback(() => get('/api/alerts'), [])
  const fetchInsights = useCallback(() => get('/api/insights'), [])
  const fetchOpen = useCallback(() => get('/api/trades?state=open'), [])
  const fetchClosed = useCallback(
    () => get(`/api/trades?state=closed&limit=${closedLimit}&offset=${closedOffset}`),
    [closedLimit, closedOffset]
  )
  const fetchPnl = useCallback(() => get('/api/trades/pnl-history?days=30'), [])
  const fetchFib = useCallback(() => get('/api/fib-levels'), [])
  const fetchTraderProfile = useCallback(() => get('/api/trader-profile'), [])
  const fetchAdvisor = useCallback(() => get('/api/trade-advisor'), [])
  const fetchEa = useCallback(() => get('/api/ea-status'), [])

  const account = usePolling(fetchAccount, 3000)
  const alerts = usePolling(fetchAlerts)
  const insights = usePolling(fetchInsights)
  const openTrades = usePolling(fetchOpen)
  const closedTrades = usePolling(fetchClosed)
  const pnlHistory = usePolling(fetchPnl)
  const fib = usePolling(fetchFib)
  const traderProfile = usePolling(fetchTraderProfile, 60000)
  const advisor = usePolling(fetchAdvisor)
  const eaStatus = usePolling(fetchEa, 5000)
  useTradeAlerts()

  const acknowledgeAlert = useCallback(async (id) => {
    try {
      const res = await fetch(`${API}/api/alerts/${id}/acknowledge`, { method: 'PATCH' })
      if (res.ok) alerts.refetch()
    } catch (_) {}
  }, [alerts.refetch])

  const acknowledgeAll = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/alerts/acknowledge-all`, { method: 'POST' })
      if (res.ok) alerts.refetch()
    } catch (_) {}
  }, [alerts.refetch])

  const handleTradeTagged = useCallback(() => openTrades.refetch(), [openTrades.refetch])

  const todaySummary = advisor.data?.basket?.pnl_summary?.today
  const xauPrice = advisor.data?.basket?.current
  const alertCount = useMemo(
    () => (alerts.data ?? []).filter(a => !a.acknowledged_at).length,
    [alerts.data]
  )
  const eaOnline = (eaStatus.data?.status === 'online') || (eaStatus.data?.online === true)

  const scrollToAlerts = useCallback(() => {
    const el = document.getElementById('alerts-anchor')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  return (
    <div className="min-h-screen bg-base text-text-primary">
      <TopBar
        equity={account.data?.equity}
        todayPnlBaht={todaySummary?.baht}
        todayPnlPct={todaySummary?.pct}
        floatPl={account.data?.floating_pl}
        xauPrice={xauPrice}
        alertCount={alertCount}
        eaOnline={eaOnline}
        onAlertsClick={scrollToAlerts}
      />
      <main className="px-4 pb-8">
        <SectionDivider label="Real Trading" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-7">
            <OpenPositions
              data={openTrades.data}
              error={openTrades.error}
              onTradeTagged={handleTradeTagged}
            />
          </div>
          <div className="lg:col-span-5">
            <TradeAdvisor data={advisor.data} />
          </div>
        </div>
        <div id="alerts-anchor" className="grid grid-cols-1 lg:grid-cols-12 gap-4 mt-4">
          <div className="lg:col-span-4">
            <AlertsPanel
              data={alerts.data}
              error={alerts.error}
              onAcknowledge={acknowledgeAlert}
              onAcknowledgeAll={acknowledgeAll}
            />
          </div>
          <div className="lg:col-span-4">
            <InsightsPanel data={insights.data} error={insights.error} />
          </div>
          <div className="lg:col-span-4">
            <FibPanel data={fib.data?.[0]} accountData={account.data} error={fib.error} />
          </div>
        </div>

        <SectionDivider label="Paper Lab" />
        <PaperTradeConsole />

        <SectionDivider label="History" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-7">
            <ClosedTrades
              data={closedTrades.data}
              error={closedTrades.error}
              limit={closedLimit}
              onLimitChange={setClosedLimit}
              offset={closedOffset}
              onOffsetChange={setClosedOffset}
            />
          </div>
          <div className="lg:col-span-5">
            <PnlChart data={pnlHistory.data} error={pnlHistory.error} />
          </div>
        </div>
        <div className="mt-4">
          <TraderProfile data={traderProfile.data} account={account.data} error={traderProfile.error} />
        </div>
      </main>
    </div>
  )
}
```

- [ ] **Step 2: Build, then start dev server and smoke-test**

Run:
```bash
cd frontend && npm run build
docker compose up -d api
cd frontend && npm run dev &
```

Open `http://localhost:3000`. Verify:
- TopBar sticks to top while scrolling
- 3 sections render in order: Real / Paper / History
- Open Positions and Basket Exit Plan sit side-by-side at ≥1024px
- Resizing below 1024px stacks all cards 1-col
- Alerts / Insights / Fib row appears under the Real row
- Clicking the PnL Summary box opens the modal; ESC + backdrop + × all close it
- Filter tabs (All/Daily/Weekly/Monthly) re-fetch with paging visible when total_pages > 1

If anything fails, fix in this task before committing.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: restructure App.jsx into Command Center Grid (TopBar + 3 sections)"
```

---

## Task 21: Delete obsolete components

**Files:**
- Delete: `frontend/src/components/AccountBar.jsx`
- Delete: `frontend/src/components/EAStatusBadge.jsx`
- Delete: `frontend/src/components/DailyPLPanel.jsx`

- [ ] **Step 1: Confirm no remaining imports**

Run: `grep -rn "AccountBar\|EAStatusBadge\|DailyPLPanel" /Users/nick/2_SideProjects/trade-signal/frontend/src/`
Expected: 0 matches outside the files being deleted (and the files themselves).

- [ ] **Step 2: Delete files**

Run: `rm frontend/src/components/AccountBar.jsx frontend/src/components/EAStatusBadge.jsx frontend/src/components/DailyPLPanel.jsx`

- [ ] **Step 3: Verify build still clean**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove AccountBar, EAStatusBadge, DailyPLPanel (replaced by TopBar + PnlHistoryModal)"
```

---

## Task 22: Remove `/api/daily-pl` (final cleanup)

**Files:**
- Modify: `api/routers/account.py`
- Modify: `api/schemas/account.py`
- Modify: `api/mcp/server.py`
- Modify/Delete: `tests/test_account_api.py` (drop `daily-pl` cases)

This task ships AFTER Task 21 has been merged and verified live for at least one session. Per the spec: "kept until PnlHistoryModal is shipped, then deleted."

- [ ] **Step 1: Verify there's a working `/api/pnl-history` consumer**

Run: `grep -rn "pnl-history\|/api/daily-pl" /Users/nick/2_SideProjects/trade-signal/api /Users/nick/2_SideProjects/trade-signal/frontend/src`
Expected: `/api/pnl-history` referenced in `PnlHistoryModal.jsx`; no remaining frontend reference to `/api/daily-pl`.

- [ ] **Step 2: Remove the route**

In `api/routers/account.py`, delete the `@router.get("/daily-pl", ...)` block and `get_daily_pl` function.

- [ ] **Step 3: Update MCP wrapper to use new endpoint**

In `api/mcp/server.py`, change `_get("/api/daily-pl", {"days": 30})` to `_get("/api/pnl-history", {"granularity": "daily", "page_size": 30})`. Adjust caller's expectations of the response (now wrapped in `items`).

- [ ] **Step 4: Drop or rewrite `test_account_api.py` daily-pl tests**

Run: `grep -n "daily.pl\|daily-pl" /Users/nick/2_SideProjects/trade-signal/tests/test_account_api.py`
Expected: 4 tests. Either delete those tests (they're now covered by `test_pnl_history.py`) or update them to call `/api/pnl-history?granularity=daily`. Prefer deletion to avoid duplication.

- [ ] **Step 5: Drop `DailyPLResponse` schema if unused**

Run: `grep -rn "DailyPLResponse" /Users/nick/2_SideProjects/trade-signal/api/`
Expected: only its definition remains. Delete it from `api/schemas/account.py`.

- [ ] **Step 6: Run full backend suite**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -v --tb=short"`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add api/routers/account.py api/schemas/account.py api/mcp/server.py tests/test_account_api.py
git commit -m "refactor: remove /api/daily-pl (superseded by /api/pnl-history)"
```

---

## End-of-plan verification

- [ ] **Backend regression**

Run: `docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -v --tb=short"`
Expected: all tests green; new test files in green.

- [ ] **Frontend build**

Run: `cd frontend && npm run build`
Expected: clean build, no warnings beyond pre-existing.

- [ ] **Manual smoke (golden path)**

1. `docker compose up -d api db` and `cd frontend && npm run dev`
2. Open `http://localhost:3000`
3. Sticky TopBar shows equity / today PnL / float / XAUUSD price / alerts badge / EA dot
4. Real section: OpenPositions on the left (with score chips below each row), Basket Exit Plan on the right
5. Click the PnL Summary box → modal opens; all 4 tabs work; pagination works on a granularity with >20 rows; ESC closes; backdrop closes; × closes
6. Paper Lab section header strip shows active count + today/week PnL with correct sign tone
7. Filter buttons toggle properly; active uses `bg-brand text-white`
8. History section: ClosedTrades + PnlChart side-by-side; TraderProfile below with Account Detail row at top
9. Resize browser below 1024px → everything stacks 1-col cleanly

- [ ] **Edge cases**

1. With no open positions → Basket Exit Plan shows "No open positions" + the PnL Summary still renders if any closed trades exist
2. With API down → Basket card shows error, modal stays usable when re-opened
3. With EA offline → TopBar shows gray dot
