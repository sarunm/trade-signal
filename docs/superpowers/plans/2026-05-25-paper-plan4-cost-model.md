# Plan 4 — Cost Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-25-paper-trade-system-redesign-v2.md` § "Cost Model"

**Goal:** Auto-learn XAUUSD spread (from market ticks) and commission (from closed real trades), persist rolling calibrations, and expose `apply_cost(gross, cost) → net` so promotion gates and signal broadcaster compute net P/L instead of raw.

**Architecture:**
- New `cost_calibrations` table stores periodic snapshots (`learned_spread_pip`, `learned_commission_per_lot_thb`, sample counts).
- `cost_model.py` keeps a 5-min in-memory cache and exposes `estimate_cost(volume_lot)` and `apply_cost(gross_thb, cost)`.
- `refresh_cost_cache()` runs hourly via the existing APScheduler (in `main.py`) — reads market_tick spreads from a small in-memory ring buffer plus `trades.commission` from the DB, computes p50 spread and avg commission/lot, writes a new `cost_calibrations` row.
- A tiny ring buffer in `market_tick.py` records `ask − bid` per tick (cap 2000) so the refresh job has data without scanning a hypertable.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, APScheduler, pytest-asyncio + httpx, Pydantic v2.

---

## File Structure

| Path | Action | Purpose |
|------|--------|---------|
| `api/alembic/versions/015_cost_model.py` | create | Adds `cost_calibrations` table |
| `api/models/cost_calibration.py` | create | ORM for `cost_calibrations` |
| `api/models/__init__.py` | modify | Register the model |
| `api/services/cost_model.py` | create | TradeCost dataclass + estimate/apply + refresh job |
| `api/services/spread_buffer.py` | create | Process-local ring buffer for ask-bid samples |
| `api/routers/market_tick.py` | modify | Push spread sample on each tick |
| `api/main.py` | modify | Wire hourly `refresh_cost_cache()` cron |
| `tests/test_migration_015.py` | create | Verifies table |
| `tests/test_cost_model.py` | create | Unit + integration tests |
| `tests/test_spread_buffer.py` | create | Ring buffer behavior |

---

## Task 1: Migration 015 — cost_calibrations

**Files:**
- Create: `api/alembic/versions/015_cost_model.py`
- Test: `tests/test_migration_015.py`

- [x] **Step 1: Write failing test**

```python
# tests/test_migration_015.py
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
async def test_cost_calibrations_exists(engine):
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert "cost_calibrations" in tables


@pytest.mark.asyncio
async def test_cost_calibrations_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("cost_calibrations")}
        )
    expected = {
        "id", "learned_spread_pip", "learned_commission_per_lot_thb",
        "sample_count_spread", "sample_count_commission", "calibrated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"
```

- [x] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_migration_015.py -v"
```

Expected: FAIL.

- [x] **Step 3: Write the migration**

```python
# api/alembic/versions/015_cost_model.py
"""cost model — cost_calibrations table

Revision ID: 015
Revises: 014
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cost_calibrations" not in inspector.get_table_names():
        op.create_table(
            "cost_calibrations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("learned_spread_pip", sa.Numeric(8, 2), nullable=False),
            sa.Column("learned_commission_per_lot_thb", sa.Numeric(10, 4), nullable=False),
            sa.Column("sample_count_spread", sa.Integer(), nullable=False),
            sa.Column("sample_count_commission", sa.Integer(), nullable=False),
            sa.Column(
                "calibrated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_cost_calibrations_calibrated",
            "cost_calibrations",
            ["calibrated_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cost_calibrations" in inspector.get_table_names():
        idx = {i["name"] for i in inspector.get_indexes("cost_calibrations")}
        if "ix_cost_calibrations_calibrated" in idx:
            op.drop_index("ix_cost_calibrations_calibrated", table_name="cost_calibrations")
        op.drop_table("cost_calibrations")
```

- [x] **Step 4: Add ORM model**

```python
# api/models/cost_calibration.py
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CostCalibration(Base):
    __tablename__ = "cost_calibrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    learned_spread_pip: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    learned_commission_per_lot_thb: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    sample_count_spread: Mapped[int] = mapped_column(Integer)
    sample_count_commission: Mapped[int] = mapped_column(Integer)
    calibrated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
```

Register in `api/models/__init__.py`:

```python
from models.cost_calibration import CostCalibration  # noqa: F401
```

- [x] **Step 5: Run to verify pass**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_migration_015.py -v"
```

Expected: PASS (2 tests).

- [x] **Step 6: Apply Postgres migration**

```
docker compose run --rm api alembic upgrade head
docker compose exec db psql -U tradesignal -d tradesignal -c "\d cost_calibrations"
```

- [x] **Step 7: Commit**

```bash
git add api/alembic/versions/015_cost_model.py \
        api/models/cost_calibration.py api/models/__init__.py \
        tests/test_migration_015.py
git commit -m "feat: migration 015 — cost_calibrations table"
```

---

## Task 2: Spread ring buffer

**Files:**
- Create: `api/services/spread_buffer.py`
- Test: `tests/test_spread_buffer.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_spread_buffer.py
from decimal import Decimal

from services.spread_buffer import SpreadBuffer


def test_buffer_capped_at_max_size():
    buf = SpreadBuffer(max_size=3)
    for v in [Decimal("0.10"), Decimal("0.20"), Decimal("0.30"), Decimal("0.40")]:
        buf.push(v)
    assert buf.size() == 3
    assert buf.values() == [Decimal("0.20"), Decimal("0.30"), Decimal("0.40")]


def test_p50_returns_median():
    buf = SpreadBuffer(max_size=10)
    for v in [Decimal("1"), Decimal("3"), Decimal("5"), Decimal("7"), Decimal("9")]:
        buf.push(v)
    assert buf.p50() == Decimal("5")


def test_p50_returns_none_when_empty():
    buf = SpreadBuffer(max_size=10)
    assert buf.p50() is None


def test_clear():
    buf = SpreadBuffer(max_size=10)
    buf.push(Decimal("1"))
    buf.clear()
    assert buf.size() == 0
```

- [x] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_spread_buffer.py -v"
```

Expected: FAIL — module missing.

- [x] **Step 3: Implement**

```python
# api/services/spread_buffer.py
from collections import deque
from decimal import Decimal
from typing import Optional


class SpreadBuffer:
    def __init__(self, max_size: int = 2000):
        self._dq: deque[Decimal] = deque(maxlen=max_size)

    def push(self, value: Decimal) -> None:
        if value is None or value < 0:
            return
        self._dq.append(value)

    def p50(self) -> Optional[Decimal]:
        if not self._dq:
            return None
        ordered = sorted(self._dq)
        n = len(ordered)
        mid = n // 2
        if n % 2 == 1:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2

    def size(self) -> int:
        return len(self._dq)

    def values(self) -> list[Decimal]:
        return list(self._dq)

    def clear(self) -> None:
        self._dq.clear()


_buffer = SpreadBuffer()


def push_spread(value: Decimal) -> None:
    _buffer.push(value)


def get_buffer() -> SpreadBuffer:
    return _buffer
```

- [x] **Step 4: Run tests to pass**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_spread_buffer.py -v"
```

Expected: PASS (4 tests).

- [x] **Step 5: Commit**

```bash
git add api/services/spread_buffer.py tests/test_spread_buffer.py
git commit -m "feat(cost): in-memory spread ring buffer (max 2000)"
```

---

## Task 3: cost_model.py — TradeCost + estimate + apply + refresh

**Files:**
- Create: `api/services/cost_model.py`
- Test: `tests/test_cost_model.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_cost_model.py
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.cost_calibration import CostCalibration
from models.trade import Direction, OrderState, Trade
from services import cost_model
from services.spread_buffer import get_buffer


@pytest.fixture(autouse=True)
def reset_state():
    cost_model.invalidate_cache()
    get_buffer().clear()
    yield
    cost_model.invalidate_cache()
    get_buffer().clear()


@pytest.mark.asyncio
async def test_estimate_uses_defaults_when_no_calibration(db_session):
    cost = await cost_model.estimate_cost(db_session, volume_lot=Decimal("0.10"))
    # Defaults: spread 30 pip, commission 10/lot, slippage 2 pip × 2 (round-trip)
    # XAUUSD: 1 pip = 0.01 price; per 0.10 lot, spread cost ≈ 30 * 0.01 * 0.10 * 100 = 3 THB
    # Slippage 4 pip → 4 * 0.01 * 0.10 * 100 = 4 THB; commission 10 * 0.10 = 1 THB; total ≈ 8 THB
    assert cost.total_thb > Decimal("0")
    assert cost.spread_pip == Decimal("30")
    assert cost.slippage_pip == Decimal("2")


@pytest.mark.asyncio
async def test_estimate_uses_latest_calibration(db_session):
    db_session.add(CostCalibration(
        id=uuid.uuid4(),
        learned_spread_pip=Decimal("12"),
        learned_commission_per_lot_thb=Decimal("4.5"),
        sample_count_spread=500,
        sample_count_commission=50,
        calibrated_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()
    cost = await cost_model.estimate_cost(db_session, volume_lot=Decimal("0.10"))
    assert cost.spread_pip == Decimal("12")
    assert cost.commission_thb == Decimal("0.45")  # 4.5/lot * 0.10


def test_apply_cost_subtracts_from_gross():
    from services.cost_model import TradeCost, apply_cost
    cost = TradeCost(
        spread_pip=Decimal("30"),
        commission_thb=Decimal("1"),
        slippage_pip=Decimal("2"),
        total_thb=Decimal("8"),
    )
    assert apply_cost(Decimal("100"), cost) == Decimal("92")
    assert apply_cost(Decimal("-50"), cost) == Decimal("-58")


@pytest.mark.asyncio
async def test_refresh_writes_calibration_when_samples_present(db_session, monkeypatch):
    buf = get_buffer()
    for v in [Decimal("0.10"), Decimal("0.20"), Decimal("0.15")] * 50:
        buf.push(v)

    now = datetime.now(timezone.utc)
    db_session.add_all([
        Trade(
            id=uuid.uuid4(), ticket=i, symbol="XAUUSD",
            direction=Direction.buy, order_state=OrderState.filled,
            open_time=now - timedelta(days=1), close_time=now - timedelta(days=1),
            open_price=Decimal("1900"), close_price=Decimal("1910"),
            volume=Decimal("0.10"), commission=Decimal("-1.5"),
            is_paper=False, profit=Decimal("100"),
        ) for i in range(15)
    ])
    await db_session.commit()

    await cost_model.refresh_cost_cache(db_session)

    rows = (await db_session.execute(
        select(CostCalibration).order_by(CostCalibration.calibrated_at.desc())
    )).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    # spread p50 of [.10,.20,.15] in pip terms — pip = 0.01 → 0.15/0.01 = 15
    assert row.learned_spread_pip == Decimal("15")
    # commission per lot: |sum(-1.5*15)| / sum(0.10*15) = 22.5 / 1.5 = 15
    assert row.learned_commission_per_lot_thb == Decimal("15")


@pytest.mark.asyncio
async def test_refresh_skips_when_below_min_samples(db_session):
    buf = get_buffer()
    for v in [Decimal("0.10")] * 5:
        buf.push(v)

    await cost_model.refresh_cost_cache(db_session)

    rows = (await db_session.execute(select(CostCalibration))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_cache_invalidates_after_ttl(db_session, monkeypatch):
    db_session.add(CostCalibration(
        id=uuid.uuid4(),
        learned_spread_pip=Decimal("5"),
        learned_commission_per_lot_thb=Decimal("1"),
        sample_count_spread=500,
        sample_count_commission=50,
        calibrated_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    cost1 = await cost_model.estimate_cost(db_session, volume_lot=Decimal("0.10"))
    assert cost1.spread_pip == Decimal("5")

    # Insert a newer row
    db_session.add(CostCalibration(
        id=uuid.uuid4(),
        learned_spread_pip=Decimal("99"),
        learned_commission_per_lot_thb=Decimal("1"),
        sample_count_spread=500,
        sample_count_commission=50,
        calibrated_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    ))
    await db_session.commit()

    # Cache still warm — should still see 5
    cost2 = await cost_model.estimate_cost(db_session, volume_lot=Decimal("0.10"))
    assert cost2.spread_pip == Decimal("5")

    cost_model.invalidate_cache()
    cost3 = await cost_model.estimate_cost(db_session, volume_lot=Decimal("0.10"))
    assert cost3.spread_pip == Decimal("99")
```

- [x] **Step 2: Run to confirm fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_cost_model.py -v"
```

Expected: FAIL — module missing.

- [x] **Step 3: Implement `cost_model.py`**

```python
# api/services/cost_model.py
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models.cost_calibration import CostCalibration
from models.trade import OrderState, Trade
from services.spread_buffer import get_buffer

logger = logging.getLogger(__name__)

PAPER_COST_SPREAD_PIP_DEFAULT = Decimal(os.getenv("PAPER_COST_SPREAD_PIP_DEFAULT", "30"))
PAPER_COST_COMMISSION_PER_LOT_DEFAULT = Decimal(os.getenv("PAPER_COST_COMMISSION_PER_LOT_DEFAULT", "10"))
PAPER_COST_SLIPPAGE_PIP = Decimal(os.getenv("PAPER_COST_SLIPPAGE_PIP", "2"))
COST_LEARN_WINDOW_DAYS = int(os.getenv("COST_LEARN_WINDOW_DAYS", 7))
COST_LEARN_MIN_SAMPLE_SPREAD = int(os.getenv("COST_LEARN_MIN_SAMPLE_SPREAD", 100))
COST_LEARN_MIN_SAMPLE_COMMISSION = int(os.getenv("COST_LEARN_MIN_SAMPLE_COMMISSION", 10))
CACHE_TTL_SECONDS = int(os.getenv("COST_CACHE_TTL_SEC", 300))   # 5 min

XAUUSD_PIP_PRICE = Decimal("0.01")     # 1 pip = 0.01 price units
XAUUSD_CONTRACT_SIZE = Decimal("100")


@dataclass
class TradeCost:
    spread_pip: Decimal
    commission_thb: Decimal
    slippage_pip: Decimal
    total_thb: Decimal


_cache: Optional[CostCalibration] = None
_cached_at: Optional[datetime] = None


def invalidate_cache() -> None:
    global _cache, _cached_at
    _cache = None
    _cached_at = None


async def _load_latest(session: AsyncSession) -> Optional[CostCalibration]:
    res = await session.execute(
        select(CostCalibration)
        .order_by(CostCalibration.calibrated_at.desc())
        .limit(1)
    )
    return res.scalars().first()


async def _calibration(session: AsyncSession) -> Optional[CostCalibration]:
    global _cache, _cached_at
    now = datetime.now(timezone.utc)
    if _cache is not None and _cached_at is not None:
        if (now - _cached_at).total_seconds() < CACHE_TTL_SECONDS:
            return _cache
    _cache = await _load_latest(session)
    _cached_at = now
    return _cache


async def estimate_cost(session: AsyncSession, volume_lot: Decimal) -> TradeCost:
    cal = await _calibration(session)
    spread_pip = cal.learned_spread_pip if cal else PAPER_COST_SPREAD_PIP_DEFAULT
    commission_per_lot = (
        cal.learned_commission_per_lot_thb if cal else PAPER_COST_COMMISSION_PER_LOT_DEFAULT
    )

    spread_thb = (
        spread_pip * XAUUSD_PIP_PRICE * volume_lot * XAUUSD_CONTRACT_SIZE
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    slippage_thb = (
        PAPER_COST_SLIPPAGE_PIP * Decimal("2") * XAUUSD_PIP_PRICE * volume_lot * XAUUSD_CONTRACT_SIZE
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    commission_thb = (
        commission_per_lot * volume_lot
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    total = spread_thb + slippage_thb + commission_thb
    return TradeCost(
        spread_pip=Decimal(spread_pip),
        commission_thb=commission_thb,
        slippage_pip=PAPER_COST_SLIPPAGE_PIP,
        total_thb=total,
    )


def apply_cost(gross_thb: Decimal, cost: TradeCost) -> Decimal:
    return (gross_thb - cost.total_thb).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def refresh_cost_cache(session: Optional[AsyncSession] = None) -> Optional[CostCalibration]:
    if session is None:
        async with SessionLocal() as owned:
            return await _refresh_with_session(owned)
    return await _refresh_with_session(session)


async def _refresh_with_session(session: AsyncSession) -> Optional[CostCalibration]:
    spread_p50 = _learn_spread()
    commission = await _learn_commission(session)

    if spread_p50 is None and commission is None:
        logger.info("cost_model.refresh: no samples")
        return None

    fallback_spread = PAPER_COST_SPREAD_PIP_DEFAULT
    fallback_commission = PAPER_COST_COMMISSION_PER_LOT_DEFAULT

    row = CostCalibration(
        id=uuid.uuid4(),
        learned_spread_pip=spread_p50 if spread_p50 is not None else fallback_spread,
        learned_commission_per_lot_thb=(
            commission["value"] if commission else fallback_commission
        ),
        sample_count_spread=get_buffer().size(),
        sample_count_commission=commission["sample_count"] if commission else 0,
        calibrated_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.commit()
    invalidate_cache()
    return row


def _learn_spread() -> Optional[Decimal]:
    buf = get_buffer()
    if buf.size() < COST_LEARN_MIN_SAMPLE_SPREAD:
        return None
    p50_price = buf.p50()
    if p50_price is None:
        return None
    return (p50_price / XAUUSD_PIP_PRICE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def _learn_commission(session: AsyncSession) -> Optional[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=COST_LEARN_WINDOW_DAYS)
    res = await session.execute(
        select(Trade).where(
            Trade.is_paper.is_(False),
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_not(None),
            Trade.close_time >= cutoff,
            Trade.commission.is_not(None),
            Trade.volume.is_not(None),
        )
    )
    rows = res.scalars().all()
    if len(rows) < COST_LEARN_MIN_SAMPLE_COMMISSION:
        return None
    total_commission = sum(abs(r.commission) for r in rows if r.commission is not None)
    total_volume = sum(r.volume for r in rows if r.volume is not None)
    if total_volume <= 0:
        return None
    value = (total_commission / total_volume).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return {"value": value, "sample_count": len(rows)}
```

- [x] **Step 4: Run cost_model tests to pass**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_cost_model.py -v"
```

Expected: PASS (6 tests).

- [x] **Step 5: Commit**

```bash
git add api/services/cost_model.py tests/test_cost_model.py
git commit -m "feat(cost): TradeCost dataclass + estimate/apply + refresh job"
```

---

## Task 4: Wire spread sample push on every market tick

**Files:**
- Modify: `api/routers/market_tick.py`

- [x] **Step 1: Modify the route to push (ask − bid)**

Add the import at the top:

```python
from services.spread_buffer import push_spread
```

After the `tick: MarketTickSchema` line in `receive_market_tick`, push the sample before any work:

```python
push_spread(tick.ask - tick.bid)
```

So the function reads:

```python
@router.post("/market-tick")
async def receive_market_tick(
    tick: MarketTickSchema,
    session: AsyncSession = Depends(get_session),
):
    push_spread(tick.ask - tick.bid)
    closed_independent = await close_paper_trades_on_tick(session, tick)
    closed_mirror = await evaluate_mirror_exits(session, tick)
    ...
```

- [x] **Step 2: Smoke**

```
docker compose up -d
curl -X POST http://localhost:8000/api/market-tick \
     -H "Content-Type: application/json" \
     -d '{"symbol":"XAUUSD","bid":1950.10,"ask":1950.40,"timestamp":"2026-05-25T10:00:00Z","account_id":1}'
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  python -c "from services.spread_buffer import get_buffer; print(get_buffer().size())"
```

Expected: buffer size ≥ 1 inside the running container — note that buffer is process-local so test by reading from inside the same `api` container with `docker compose exec api python -c "..."` if needed.

- [x] **Step 3: Commit**

```bash
git add api/routers/market_tick.py
git commit -m "feat(cost): record (ask-bid) per market tick into spread buffer"
```

---

## Task 5: Schedule hourly cost refresh in main.py

**Files:**
- Modify: `api/main.py`

- [x] **Step 1: Add the cron**

Edit `api/main.py`:

Add the import:

```python
from services.cost_model import refresh_cost_cache
```

Add an env flag at the top:

```python
COST_REFRESH_ENABLED = os.getenv("COST_REFRESH_ENABLED", "1") == "1"
COST_REFRESH_INTERVAL_MIN = int(os.getenv("COST_REFRESH_INTERVAL_MIN", 60))
```

In `lifespan()`, after the existing `pattern_discovery_daily` job:

```python
    if COST_REFRESH_ENABLED:
        if scheduler is None:
            scheduler = AsyncIOScheduler(timezone="UTC")
            scheduler.start()
        scheduler.add_job(
            _safe_refresh_cost,
            "interval",
            minutes=COST_REFRESH_INTERVAL_MIN,
            id="cost_refresh_hourly",
            replace_existing=True,
        )
```

Add the helper:

```python
async def _safe_refresh_cost() -> None:
    try:
        await refresh_cost_cache()
    except Exception:
        logger.exception("cost refresh cron failed")
```

- [x] **Step 2: Smoke**

```
docker compose up -d --build api
docker compose logs api | grep -i scheduler
# Trigger manually:
docker compose exec api python -c "import asyncio; from services.cost_model import refresh_cost_cache; asyncio.run(refresh_cost_cache())"
docker compose exec db psql -U tradesignal -d tradesignal -c \
  "SELECT learned_spread_pip, sample_count_spread, calibrated_at FROM cost_calibrations ORDER BY calibrated_at DESC LIMIT 1;"
```

- [x] **Step 3: Commit**

```bash
git add api/main.py
git commit -m "feat(cost): hourly APScheduler cron for cost refresh"
```

---

## Task 6: Full regression

- [x] **Step 1: Run the suite**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/ -v --tb=short"
```

Expected: previous count + new tests, all green.

- [x] **Step 2: Update handoff**

```
Plan 4 done.
- migration 015 applied (cost_calibrations)
- spread ring buffer (max 2000) populated by /api/market-tick
- TradeCost.estimate_cost / apply_cost API live
- hourly cost refresh cron writes calibration snapshots
Next: Plan 3 (Auto Discovery v2 — 3 variants)
```
