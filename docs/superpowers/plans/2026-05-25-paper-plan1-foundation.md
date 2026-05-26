# Plan 1 — Paper Trade Redesign: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-25-paper-trade-system-redesign.md` (FROZEN rev 1)

**Goal:** Land the schema and recovery foundation that every later plan builds on — migrations 011 + 014, plus EA heartbeat + UI status badge — so subsequent components inherit gap-safe behavior from day 1.

**Architecture:**
- Migration 011 adds new columns to `paper_trader_rules` (mode, virtual budget, score_weights, filters, gate_status, etc.) and creates `paper_signals` (TimescaleDB hypertable + 30-day retention) + `score_calibrations`.
- Migration 014 creates `ea_status` and adds the denormalized `trades.paper_trader_rule_id` column with a partial index on open paper trades.
- A new `/api/ea-heartbeat` endpoint upserts EA liveness, the EA posts every 60s, and the React dashboard polls `/api/ea-status` to render an EA status badge.

**Tech Stack:** Alembic, SQLAlchemy 2.0 async, FastAPI, Pydantic v2, pytest-asyncio + httpx (SQLite in-memory), MQL5, React + TailwindCSS.

---

## File Structure

| Path | Action | Purpose |
|------|--------|---------|
| `api/alembic/versions/011_paper_redesign_schema.py` | create | Adds `paper_trader_rules` columns + creates `paper_signals` + `score_calibrations` |
| `api/alembic/versions/014_recovery_foundation.py` | create | Adds `ea_status` table + denormalized `trades.paper_trader_rule_id` |
| `api/models/pattern.py` | modify | New columns on `PaperTraderRule` |
| `api/models/paper_signal.py` | create | ORM for `paper_signals` |
| `api/models/score_calibration.py` | create | ORM for `score_calibrations` |
| `api/models/ea_status.py` | create | ORM for `ea_status` |
| `api/models/trade.py` | modify | Add `paper_trader_rule_id` mapped column |
| `api/models/__init__.py` | modify | Register new models |
| `api/schemas/ea_status.py` | create | `EAHeartbeatSchema`, `EAStatusResponse` |
| `api/routers/ea_status.py` | create | `POST /api/ea-heartbeat`, `GET /api/ea-status` |
| `api/main.py` | modify | Include the new router |
| `ea/TradeSignalBridge.mq5` | modify | Send heartbeat in `OnTimer()` |
| `frontend/src/hooks/useEAStatus.js` | create | Poll `/api/ea-status` every 10s |
| `frontend/src/components/EAStatusBadge.jsx` | create | Render badge in dashboard header |
| `frontend/src/App.jsx` | modify | Mount `<EAStatusBadge />` near `AccountBar` |
| `tests/test_migration_011.py` | create | Verifies new columns/tables exist |
| `tests/test_migration_014.py` | create | Verifies `ea_status` + `trades.paper_trader_rule_id` |
| `tests/test_ea_status_api.py` | create | Heartbeat upsert + status read |

Migration 012 (Adaptive Tuning filters) and 013 (paper_signals hypertable extension if needed) are reserved for later plans, but `011` already creates `paper_signals` so 013 is intentionally skipped to keep numbering monotonic.

---

## Task 1: Migration 011 — paper_trader_rules columns + paper_signals + score_calibrations

**Files:**
- Create: `api/alembic/versions/011_paper_redesign_schema.py`
- Test: `tests/test_migration_011.py`

- [x] **Step 1: Write failing test**

```python
# tests/test_migration_011.py
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
async def test_paper_trader_rules_has_redesign_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {c["name"] for c in inspect(sync_conn).get_columns("paper_trader_rules")}
        )
    expected = {
        "mode", "virtual_balance_start", "virtual_balance_current",
        "score_weights", "filters", "shadow_of_rule_id",
        "gate_status", "promoted_at", "consecutive_stable_days",
        "last_signal_status",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


@pytest.mark.asyncio
async def test_paper_signals_table_exists(engine):
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert "paper_signals" in tables


@pytest.mark.asyncio
async def test_score_calibrations_table_exists(engine):
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert "score_calibrations" in tables
```

- [x] **Step 2: Run test to verify it fails**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_migration_011.py -v"
```

Expected: FAIL with `paper_signals not in tables` / missing columns.

- [x] **Step 3: Write the migration**

```python
# api/alembic/versions/011_paper_redesign_schema.py
"""paper trade redesign — schema additions

Revision ID: 011
Revises: 010
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    rule_cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    additions = [
        ("mode", sa.String(20), "strict"),
        ("virtual_balance_start", sa.Numeric(12, 2), "5000"),
        ("virtual_balance_current", sa.Numeric(12, 2), "5000"),
        ("score_weights", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), None),
        ("filters", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), "[]"),
        ("shadow_of_rule_id", postgresql.UUID(as_uuid=True), None),
        ("gate_status", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), "{}"),
        ("promoted_at", sa.DateTime(timezone=True), None),
        ("consecutive_stable_days", sa.Integer(), "0"),
        ("last_signal_status", sa.String(20), None),
    ]
    for name, col_type, default in additions:
        if name in rule_cols:
            continue
        kwargs = {"nullable": True}
        if default is not None:
            kwargs["server_default"] = default
        op.add_column("paper_trader_rules", sa.Column(name, col_type, **kwargs))

    if "paper_signals" not in inspector.get_table_names():
        op.create_table(
            "paper_signals",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("rule_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("paper_trader_rules.id"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("match_pct", sa.Numeric(5, 4), nullable=False),
            sa.Column("matched_conditions",
                      postgresql.ARRAY(sa.String()).with_variant(sa.JSON(), "sqlite"),
                      nullable=False),
            sa.Column("missing_conditions",
                      postgresql.ARRAY(sa.String()).with_variant(sa.JSON(), "sqlite"),
                      nullable=False),
            sa.Column("score", sa.Numeric(6, 2), nullable=True),
            sa.Column("suggested_lot", sa.Numeric(6, 2), nullable=True),
            sa.Column("emitted_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.text("now()")),
        )
        op.create_index(
            "ix_paper_signals_rule_emitted",
            "paper_signals", ["rule_id", "emitted_at"],
        )
        if bind.dialect.name == "postgresql":
            op.execute(
                "SELECT create_hypertable('paper_signals', 'emitted_at', "
                "if_not_exists => TRUE);"
            )
            op.execute(
                "SELECT add_retention_policy('paper_signals', INTERVAL '30 days', "
                "if_not_exists => TRUE);"
            )

    if "score_calibrations" not in inspector.get_table_names():
        op.create_table(
            "score_calibrations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("score_tier", sa.String(10), nullable=False),
            sa.Column("expected_winrate", sa.Numeric(5, 4), nullable=False),
            sa.Column("actual_winrate", sa.Numeric(5, 4), nullable=False),
            sa.Column("sample_count", sa.Integer(), nullable=False),
            sa.Column("calibrated_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.text("now()")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "score_calibrations" in inspector.get_table_names():
        op.drop_table("score_calibrations")

    if "paper_signals" in inspector.get_table_names():
        op.drop_index("ix_paper_signals_rule_emitted", table_name="paper_signals")
        op.drop_table("paper_signals")

    rule_cols = {c["name"] for c in inspector.get_columns("paper_trader_rules")}
    for name in [
        "last_signal_status", "consecutive_stable_days", "promoted_at",
        "gate_status", "shadow_of_rule_id", "filters", "score_weights",
        "virtual_balance_current", "virtual_balance_start", "mode",
    ]:
        if name in rule_cols:
            op.drop_column("paper_trader_rules", name)
```

- [x] **Step 4: Mirror columns into the ORM so `Base.metadata.create_all` covers them in tests**

Update `api/models/pattern.py`:

```python
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Pattern(Base):
    __tablename__ = "patterns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    indicator_slugs: Mapped[list[str]] = mapped_column(
        ARRAY(String()).with_variant(JSON(), "sqlite"),
    )
    timeframe: Mapped[str] = mapped_column(String(10), default="H1")
    win_rate: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)
    consecutive_stable_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="candidate", index=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperTraderRule(Base):
    __tablename__ = "paper_trader_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patterns.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    spawned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_count: Mapped[int] = mapped_column(Integer, default=0)

    mode: Mapped[str] = mapped_column(String(20), default="strict")
    virtual_balance_start: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("5000"))
    virtual_balance_current: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("5000"))
    score_weights: Mapped[Optional[dict]] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    filters: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), default=list)
    shadow_of_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    gate_status: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), default=dict)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_stable_days_rule: Mapped[int] = mapped_column(
        "consecutive_stable_days", Integer, default=0
    )
    last_signal_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
```

- [x] **Step 5: Add ORM stubs for the new tables**

Create `api/models/paper_signal.py`:

```python
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class PaperSignal(Base):
    __tablename__ = "paper_signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_trader_rules.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20))
    match_pct: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    matched_conditions: Mapped[list[str]] = mapped_column(
        ARRAY(String()).with_variant(JSON(), "sqlite")
    )
    missing_conditions: Mapped[list[str]] = mapped_column(
        ARRAY(String()).with_variant(JSON(), "sqlite")
    )
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    suggested_lot: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    emitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
```

Create `api/models/score_calibration.py`:

```python
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ScoreCalibration(Base):
    __tablename__ = "score_calibrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    score_tier: Mapped[str] = mapped_column(String(10))
    expected_winrate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    actual_winrate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    sample_count: Mapped[int] = mapped_column(Integer)
    calibrated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
```

Update `api/models/__init__.py`:

```python
from models.account_snapshot import AccountSnapshot  # noqa: F401
from models.alert import Alert  # noqa: F401
from models.fib_level import FibLevel  # noqa: F401
from models.indicator_signal import TradeIndicatorSignal  # noqa: F401
from models.insight import Insight  # noqa: F401
from models.paper_signal import PaperSignal  # noqa: F401
from models.pattern import PaperTraderRule, Pattern  # noqa: F401
from models.price_bar import PriceBar  # noqa: F401
from models.score_calibration import ScoreCalibration  # noqa: F401
from models.trade import Trade  # noqa: F401
```

- [x] **Step 6: Run test to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_migration_011.py -v"
```

Expected: PASS (3 tests).

- [x] **Step 7: Run the migration against Postgres to confirm it applies cleanly**

```
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose exec db psql -U tradesignal -d tradesignal -c "\d paper_trader_rules"
docker compose exec db psql -U tradesignal -d tradesignal -c "\dt paper_signals"
```

Expected: column list shows `mode, virtual_balance_start, ...`; `paper_signals` table exists.

- [x] **Step 8: Commit**

```bash
git add api/alembic/versions/011_paper_redesign_schema.py \
        api/models/pattern.py api/models/paper_signal.py \
        api/models/score_calibration.py api/models/__init__.py \
        tests/test_migration_011.py
git commit -m "feat: migration 011 — paper redesign schema (rule columns, paper_signals, score_calibrations)"
```

---

## Task 2: Migration 014 — ea_status + denormalized trades.paper_trader_rule_id

**Files:**
- Create: `api/alembic/versions/014_recovery_foundation.py`
- Modify: `api/models/trade.py`
- Create: `api/models/ea_status.py`
- Modify: `api/models/__init__.py`
- Test: `tests/test_migration_014.py`

- [x] **Step 1: Write failing test**

```python
# tests/test_migration_014.py
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
async def test_ea_status_table_exists(engine):
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert "ea_status" in tables


@pytest.mark.asyncio
async def test_trades_has_paper_trader_rule_id(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("trades")}
        )
    assert "paper_trader_rule_id" in cols
```

- [x] **Step 2: Run test to verify it fails**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_migration_014.py -v"
```

Expected: FAIL with `ea_status not in tables`.

- [x] **Step 3: Write the migration**

```python
# api/alembic/versions/014_recovery_foundation.py
"""recovery foundation — ea_status + trades.paper_trader_rule_id

Revision ID: 014
Revises: 011
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "ea_status" not in inspector.get_table_names():
        op.create_table(
            "ea_status",
            sa.Column("account_id", sa.BigInteger(), primary_key=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.String(20), nullable=True),
            sa.Column("symbol", sa.String(20), nullable=True),
        )

    trade_cols = {c["name"] for c in inspector.get_columns("trades")}
    if "paper_trader_rule_id" not in trade_cols:
        op.add_column(
            "trades",
            sa.Column(
                "paper_trader_rule_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )

    trade_idx = {idx["name"] for idx in inspector.get_indexes("trades")}
    if "ix_trades_open_paper_rule" not in trade_idx:
        if bind.dialect.name == "postgresql":
            op.execute(
                "CREATE INDEX ix_trades_open_paper_rule "
                "ON trades(paper_trader_rule_id) "
                "WHERE close_time IS NULL AND is_paper = true;"
            )
        else:
            op.create_index(
                "ix_trades_open_paper_rule", "trades", ["paper_trader_rule_id"]
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    trade_idx = {idx["name"] for idx in inspector.get_indexes("trades")}
    if "ix_trades_open_paper_rule" in trade_idx:
        op.drop_index("ix_trades_open_paper_rule", table_name="trades")

    trade_cols = {c["name"] for c in inspector.get_columns("trades")}
    if "paper_trader_rule_id" in trade_cols:
        op.drop_column("trades", "paper_trader_rule_id")

    if "ea_status" in inspector.get_table_names():
        op.drop_table("ea_status")
```

- [x] **Step 4: Mirror columns in ORM**

Add to `api/models/trade.py` (after `recovery_plan`):

```python
    paper_trader_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
```

Create `api/models/ea_status.py`:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class EAStatus(Base):
    __tablename__ = "ea_status"

    account_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
```

Add to `api/models/__init__.py`:

```python
from models.ea_status import EAStatus  # noqa: F401
```

- [x] **Step 5: Run test to verify it passes**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_migration_014.py -v"
```

Expected: PASS (2 tests).

- [x] **Step 6: Apply migration**

```
docker compose run --rm api alembic upgrade head
docker compose exec db psql -U tradesignal -d tradesignal -c "\d ea_status"
docker compose exec db psql -U tradesignal -d tradesignal -c "\d trades" | grep paper_trader_rule_id
```

Expected: `ea_status` table exists, `paper_trader_rule_id` column present.

- [x] **Step 7: Commit**

```bash
git add api/alembic/versions/014_recovery_foundation.py \
        api/models/trade.py api/models/ea_status.py api/models/__init__.py \
        tests/test_migration_014.py
git commit -m "feat: migration 014 — ea_status table + denormalized paper_trader_rule_id"
```

---

## Task 3: EA heartbeat schemas

**Files:**
- Create: `api/schemas/ea_status.py`

- [x] **Step 1: Write the schemas**

```python
# api/schemas/ea_status.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EAHeartbeatSchema(BaseModel):
    account_id: int
    version: Optional[str] = None
    symbol: Optional[str] = None
    timestamp: Optional[datetime] = None


class EAStatusResponse(BaseModel):
    account_id: int
    last_seen_at: datetime
    version: Optional[str] = None
    symbol: Optional[str] = None
    seconds_since_last_seen: float = Field(..., ge=0)
    connected: bool

    model_config = {"from_attributes": True}
```

- [x] **Step 2: Commit**

```bash
git add api/schemas/ea_status.py
git commit -m "feat: add EA heartbeat + status schemas"
```

---

## Task 4: Heartbeat router (POST + GET)

**Files:**
- Create: `api/routers/ea_status.py`
- Modify: `api/main.py`
- Test: `tests/test_ea_status_api.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_ea_status_api.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models.ea_status import EAStatus


@pytest.mark.asyncio
async def test_post_heartbeat_inserts_row(client, db_session):
    res = await client.post(
        "/api/ea-heartbeat",
        json={"account_id": 1234567, "version": "1.09", "symbol": "GOLD#"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["account_id"] == 1234567
    assert body["version"] == "1.09"

    rows = (await db_session.execute(select(EAStatus))).scalars().all()
    assert len(rows) == 1
    assert rows[0].version == "1.09"


@pytest.mark.asyncio
async def test_post_heartbeat_upserts(client, db_session):
    await client.post("/api/ea-heartbeat", json={"account_id": 1, "version": "1.0"})
    await client.post("/api/ea-heartbeat", json={"account_id": 1, "version": "1.1"})
    rows = (await db_session.execute(select(EAStatus))).scalars().all()
    assert len(rows) == 1
    assert rows[0].version == "1.1"


@pytest.mark.asyncio
async def test_get_status_returns_connected_when_recent(client, db_session):
    db_session.add(EAStatus(
        account_id=999,
        last_seen_at=datetime.now(timezone.utc),
        version="1.08",
        symbol="GOLD#",
    ))
    await db_session.commit()

    res = await client.get("/api/ea-status?account_id=999")
    assert res.status_code == 200
    body = res.json()
    assert body["connected"] is True
    assert body["seconds_since_last_seen"] >= 0


@pytest.mark.asyncio
async def test_get_status_returns_404_when_no_row(client):
    res = await client.get("/api/ea-status?account_id=42")
    assert res.status_code == 404
```

- [x] **Step 2: Run tests to verify they fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_ea_status_api.py -v"
```

Expected: FAIL with `404 Not Found` on `/api/ea-heartbeat`.

- [x] **Step 3: Write the router**

```python
# api/routers/ea_status.py
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.ea_status import EAStatus
from schemas.ea_status import EAHeartbeatSchema, EAStatusResponse

EA_DISCONNECT_UI_THRESHOLD_SEC = int(os.getenv("EA_DISCONNECT_UI_THRESHOLD_SEC", 120))

router = APIRouter(prefix="/api", tags=["ea-status"])


@router.post("/ea-heartbeat", response_model=EAStatusResponse)
async def post_heartbeat(
    payload: EAHeartbeatSchema,
    session: AsyncSession = Depends(get_session),
):
    now = payload.timestamp or datetime.now(timezone.utc)
    existing = await session.get(EAStatus, payload.account_id)
    if existing is None:
        existing = EAStatus(account_id=payload.account_id, last_seen_at=now)
        session.add(existing)
    existing.last_seen_at = now
    if payload.version is not None:
        existing.version = payload.version
    if payload.symbol is not None:
        existing.symbol = payload.symbol
    await session.commit()
    await session.refresh(existing)
    return _to_response(existing, now)


@router.get("/ea-status", response_model=EAStatusResponse)
async def get_status(
    account_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(EAStatus, account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="ea_status not found")
    return _to_response(row, datetime.now(timezone.utc))


def _to_response(row: EAStatus, now: datetime) -> EAStatusResponse:
    last = row.last_seen_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    seconds = max(0.0, (now - last).total_seconds())
    return EAStatusResponse(
        account_id=row.account_id,
        last_seen_at=last,
        version=row.version,
        symbol=row.symbol,
        seconds_since_last_seen=seconds,
        connected=seconds <= EA_DISCONNECT_UI_THRESHOLD_SEC,
    )
```

- [x] **Step 4: Wire the router into the app**

Edit `api/main.py`:

Add the import next to the other router imports:

```python
from routers.ea_status import router as ea_status_router
```

Register it after `price_bars_router`:

```python
app.include_router(ea_status_router)
```

- [x] **Step 5: Run tests to verify they pass**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_ea_status_api.py -v"
```

Expected: PASS (4 tests).

- [x] **Step 6: Commit**

```bash
git add api/routers/ea_status.py api/main.py tests/test_ea_status_api.py
git commit -m "feat: add /api/ea-heartbeat + /api/ea-status endpoints"
```

---

## Task 5: EA sends heartbeat in OnTimer

**Files:**
- Modify: `ea/TradeSignalBridge.mq5`

- [x] **Step 1: Add `SendHeartbeat()` helper**

After the `SendPriceTick()` function (around line 471–514), add:

```mql5
//--- Send heartbeat — confirms EA is alive, used for recovery + UI badge
void SendHeartbeat()
{
   long account_id = AccountInfoInteger(ACCOUNT_LOGIN);
   string ts = ISOTime(TimeCurrent());
   string body = StringFormat(
      "{"
      "\"account_id\":%I64d,"
      "\"version\":\"1.09\","
      "\"symbol\":\"%s\","
      "\"timestamp\":\"%s\""
      "}",
      account_id, InpSymbol, ts
   );
   PostJSON("/api/ea-heartbeat", body);
}
```

- [x] **Step 2: Call `SendHeartbeat()` in `OnTimer()`**

Replace the `OnTimer()` body (around line 621–625):

```mql5
void OnTimer()
{
   SendPriceTick();
   ComputeFibLevels();
   SendHeartbeat();
}
```

- [x] **Step 3: Bump version banner**

Change line 6 from `#property version   "1.08"` to `#property version   "1.09"` and update the print at line 304:

```mql5
Print("TradeSignalBridge v1.09 started. Sending to: ", InpServerURL, " | Symbol: ", InpSymbol);
```

- [x] **Step 4: Manual verify**

```
# Compile + attach EA to chart, then watch heartbeats land
docker compose logs -f api | grep ea-heartbeat
# Expected: every 60s a 200 response on POST /api/ea-heartbeat
```

- [x] **Step 5: Commit**

```bash
git add ea/TradeSignalBridge.mq5
git commit -m "feat(ea): send heartbeat to /api/ea-heartbeat every InpTimerSec"
```

---

## Task 6: Frontend — useEAStatus hook + EAStatusBadge

**Files:**
- Create: `frontend/src/hooks/useEAStatus.js`
- Create: `frontend/src/components/EAStatusBadge.jsx`
- Modify: `frontend/src/App.jsx`

- [x] **Step 1: Write the polling hook**

```javascript
// frontend/src/hooks/useEAStatus.js
import { useCallback, useEffect, useState } from 'react'

const API = 'http://localhost:8000'
const POLL_MS = 10_000

export function useEAStatus(accountId) {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)

  const fetchStatus = useCallback(async () => {
    if (!accountId) {
      setStatus(null)
      return
    }
    try {
      const res = await fetch(`${API}/api/ea-status?account_id=${accountId}`)
      if (res.status === 404) {
        setStatus({ connected: false, seconds_since_last_seen: null, never_seen: true })
        setError(null)
        return
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const body = await res.json()
      setStatus(body)
      setError(null)
    } catch (err) {
      setError(err)
    }
  }, [accountId])

  useEffect(() => {
    fetchStatus()
    const id = setInterval(fetchStatus, POLL_MS)
    return () => clearInterval(id)
  }, [fetchStatus])

  return { status, error }
}
```

- [x] **Step 2: Write the badge component**

```jsx
// frontend/src/components/EAStatusBadge.jsx
import React from 'react'
import { useEAStatus } from '../hooks/useEAStatus'

function formatGap(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.floor(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  return `${Math.floor(seconds / 3600)}h`
}

export default function EAStatusBadge({ accountId }) {
  const { status } = useEAStatus(accountId)

  if (!status) {
    return (
      <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-500">
        EA: …
      </span>
    )
  }

  if (status.never_seen) {
    return (
      <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-400">
        🔴 EA: never seen
      </span>
    )
  }

  const gap = formatGap(status.seconds_since_last_seen)
  if (status.connected) {
    return (
      <span className="text-xs px-2 py-1 rounded bg-green-900/40 text-green-300">
        🟢 EA connected ({gap} ago)
      </span>
    )
  }
  return (
    <span className="text-xs px-2 py-1 rounded bg-red-900/40 text-red-300 animate-pulse">
      🔴 EA disconnected ({gap})
    </span>
  )
}
```

- [x] **Step 3: Mount the badge in `App.jsx`**

Edit `frontend/src/App.jsx`:

Add the import:

```javascript
import EAStatusBadge from './components/EAStatusBadge'
```

Replace the existing `<AccountBar ... />` line with a wrapper that puts the badge alongside it:

```jsx
      <div className="flex items-start gap-3">
        <AccountBar data={account.data} error={account.error} lastUpdated={account.lastUpdated} />
        <EAStatusBadge accountId={account.data?.account_id} />
      </div>
```

- [x] **Step 4: Build to confirm no syntax errors**

```
cd frontend && npm run build
```

Expected: build succeeds, no errors.

- [x] **Step 5: Manual verify**

Start everything:

```
docker compose up -d
cd frontend && npm run dev
```

Open http://localhost:3000. With the EA running you should see the green badge update every ≤ 10s. Stop the EA — within ~`EA_DISCONNECT_UI_THRESHOLD_SEC` (120s) the badge flips to red.

- [x] **Step 6: Commit**

```bash
git add frontend/src/hooks/useEAStatus.js frontend/src/components/EAStatusBadge.jsx frontend/src/App.jsx
git commit -m "feat(ui): EA connection status badge in dashboard header"
```

---

## Task 7: Full regression

- [x] **Step 1: Run the full backend suite**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/ -v --tb=short"
```

Expected: previous test count + 9 new tests, all green.

- [x] **Step 2: Frontend build**

```
cd frontend && npm run build
```

- [x] **Step 3: Smoke check the new endpoints**

```
curl -X POST http://localhost:8000/api/ea-heartbeat \
     -H "Content-Type: application/json" \
     -d '{"account_id": 1, "version": "1.09", "symbol": "GOLD#"}'
curl "http://localhost:8000/api/ea-status?account_id=1"
```

Expected: both return 200, second response has `"connected": true`.

- [x] **Step 4: Tag end of plan in handoff**

Update `.agents/handoff.md` (or commit message body) with:

```
Plan 1 done.
- migrations 011 + 014 applied
- /api/ea-heartbeat + /api/ea-status live
- EA v1.09 sends heartbeat on every OnTimer tick
- Dashboard shows EA status badge
Next: Plan 2 (Mirror Redesign)
```
