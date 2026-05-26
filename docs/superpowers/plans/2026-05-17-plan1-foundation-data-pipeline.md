# Trade Signal Partner — Plan 1: Foundation & Data Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Set up Docker infrastructure, PostgreSQL/TimescaleDB schema, FastAPI backend, and MQL5 EA so that MT5 trade events and real-time price bars flow into the database end-to-end.

**Architecture:** MQL5 EA in MT5 POSTs JSON to a FastAPI server running in Docker. FastAPI validates payloads via Pydantic and persists to PostgreSQL with TimescaleDB (for time-series price bars). No business logic in this plan — pure data capture pipeline.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async, asyncpg), Alembic, PostgreSQL 16 + TimescaleDB, pytest + httpx, MQL5, Docker Compose

---

## File Map

```
trade-signal/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                        # FastAPI app + lifespan
│   ├── config.py                      # Settings from env vars
│   ├── database.py                    # Async engine + session factory
│   ├── models/
│   │   ├── __init__.py
│   │   ├── trade.py                   # Trade ORM model
│   │   ├── price_bar.py               # PriceBar ORM model (hypertable)
│   │   └── account_snapshot.py        # AccountSnapshot ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── trade_event.py             # Pydantic: incoming trade event from EA
│   │   └── price_tick.py              # Pydantic: incoming price tick from EA
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── trade_events.py            # POST /api/trade-events
│   │   └── price_tick.py              # POST /api/price-tick
│   ├── services/
│   │   ├── __init__.py
│   │   ├── trade_logger.py            # Upsert trade records
│   │   └── price_handler.py           # Insert bars + account snapshots
│   └── alembic/
│       ├── alembic.ini
│       ├── env.py
│       └── versions/
│           └── 001_initial_schema.py
├── ea/
│   └── TradeSignalBridge.mq5          # MQL5 EA — sends events + price ticks
└── tests/
    ├── conftest.py                    # Test DB setup, async client fixture
    ├── test_health.py
    ├── test_trade_events.py
    └── test_price_tick.py
```

---

## Task 1: Docker Compose + Project Scaffold

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `api/Dockerfile`
- Create: `api/requirements.txt`

- [x] **Step 1: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.venv/
venv/
*.egg-info/
.superpowers/
```

- [x] **Step 2: Create `.env.example`**

```env
DATABASE_URL=postgresql+asyncpg://tradesignal:tradesignal@db:5432/tradesignal
DATABASE_URL_SYNC=postgresql+psycopg2://tradesignal:tradesignal@db:5432/tradesignal
```

- [x] **Step 3: Create `.env` from example**

```bash
cp .env.example .env
```

- [x] **Step 4: Create `api/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
psycopg2-binary==2.9.9
alembic==1.13.3
pydantic==2.9.2
pydantic-settings==2.5.2
python-dotenv==1.0.1
httpx==0.27.2
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-httpx==0.30.0
```

- [x] **Step 5: Create `api/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

- [x] **Step 6: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: tradesignal
      POSTGRES_USER: tradesignal
      POSTGRES_PASSWORD: tradesignal
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tradesignal -d tradesignal"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build: ./api
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./api:/app

volumes:
  pgdata:
```

- [x] **Step 7: Verify DB starts**

```bash
docker compose up db -d
docker compose ps
```

Expected: `db` service is `healthy`

- [x] **Step 8: Commit**

```bash
git init
git add docker-compose.yml .env.example .gitignore api/Dockerfile api/requirements.txt
git commit -m "feat: docker compose scaffold with timescaledb"
```

---

## Task 2: FastAPI Skeleton + Config + Health Check

**Files:**
- Create: `api/config.py`
- Create: `api/database.py`
- Create: `api/main.py`
- Create: `tests/test_health.py`
- Create: `tests/conftest.py`

- [x] **Step 1: Write failing health check test**

Create `tests/conftest.py`:
```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from main import app
from database import get_session, Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_session():
        yield db_session
    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
```

Add `aiosqlite` to `api/requirements.txt`:
```
aiosqlite==0.20.0
```

Create `tests/test_health.py`:
```python
import pytest

@pytest.mark.asyncio
async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [x] **Step 2: Run test — expect FAIL**

```bash
cd api && pip install -r requirements.txt
cd .. && pytest tests/test_health.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` (main.py doesn't exist yet)

- [x] **Step 3: Create `api/config.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://tradesignal:tradesignal@db:5432/tradesignal"
    database_url_sync: str = "postgresql+psycopg2://tradesignal:tradesignal@db:5432/tradesignal"

    class Config:
        env_file = ".env"

settings = Settings()
```

- [x] **Step 4: Create `api/database.py`**

```python
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

- [x] **Step 5: Create `api/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from database import engine, Base

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title="Trade Signal Partner", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [x] **Step 6: Run test — expect PASS**

```bash
pytest tests/test_health.py -v
```

Expected: `PASSED`

- [x] **Step 7: Commit**

```bash
git add api/config.py api/database.py api/main.py tests/conftest.py tests/test_health.py
git commit -m "feat: fastapi skeleton with health check and test harness"
```

---

## Task 3: Database Models + Alembic Migration

**Files:**
- Create: `api/models/__init__.py`
- Create: `api/models/trade.py`
- Create: `api/models/price_bar.py`
- Create: `api/models/account_snapshot.py`
- Create: `api/alembic/alembic.ini`
- Create: `api/alembic/env.py`
- Create: `api/alembic/versions/001_initial_schema.py`

- [x] **Step 1: Create `api/models/__init__.py`**

```python
from .trade import Trade
from .price_bar import PriceBar
from .account_snapshot import AccountSnapshot

__all__ = ["Trade", "PriceBar", "AccountSnapshot"]
```

- [x] **Step 2: Create `api/models/trade.py`**

```python
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Boolean, Numeric, BigInteger, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
import enum

from database import Base

class Direction(str, enum.Enum):
    buy = "buy"
    sell = "sell"

class OrderType(str, enum.Enum):
    market = "market"
    buy_limit = "buy_limit"
    sell_limit = "sell_limit"
    buy_stop = "buy_stop"
    sell_stop = "sell_stop"
    buy_stop_limit = "buy_stop_limit"
    sell_stop_limit = "sell_stop_limit"

class OrderState(str, enum.Enum):
    pending = "pending"
    filled = "filled"
    cancelled = "cancelled"
    expired = "expired"

class PaperMode(str, enum.Enum):
    mirror = "mirror"
    independent = "independent"

class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket: Mapped[int] = mapped_column(BigInteger, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[Direction | None] = mapped_column(SAEnum(Direction), nullable=True)
    order_type: Mapped[OrderType | None] = mapped_column(SAEnum(OrderType), nullable=True)
    order_state: Mapped[OrderState | None] = mapped_column(SAEnum(OrderState), nullable=True)
    pending_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 5), nullable=True)
    open_time: Mapped[datetime | None] = mapped_column(nullable=True)
    fill_time: Mapped[datetime | None] = mapped_column(nullable=True)
    close_time: Mapped[datetime | None] = mapped_column(nullable=True)
    open_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 5), nullable=True)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 5), nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tp: Mapped[Decimal | None] = mapped_column(Numeric(12, 5), nullable=True)
    sl: Mapped[Decimal | None] = mapped_column(Numeric(12, 5), nullable=True)
    profit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    swap: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    commission: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=False)
    paper_mode: Mapped[PaperMode | None] = mapped_column(SAEnum(PaperMode), nullable=True)
```

- [x] **Step 3: Create `api/models/price_bar.py`**

```python
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from database import Base

class Timeframe(str, enum.Enum):
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D = "D"
    W1 = "W1"

class PriceBar(Base):
    __tablename__ = "price_bars"

    time: Mapped[datetime] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 5))
    high: Mapped[Decimal] = mapped_column(Numeric(12, 5))
    low: Mapped[Decimal] = mapped_column(Numeric(12, 5))
    close: Mapped[Decimal] = mapped_column(Numeric(12, 5))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
```

- [x] **Step 4: Create `api/models/account_snapshot.py`**

```python
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    timestamp: Mapped[datetime] = mapped_column(primary_key=True)
    equity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    margin: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    free_margin: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    floating_pl: Mapped[Decimal] = mapped_column(Numeric(14, 2))
```

- [x] **Step 5: Update `api/main.py` to import models so Base.metadata is populated**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from database import engine, Base
import models  # noqa: F401 — registers all ORM models with Base.metadata

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title="Trade Signal Partner", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [x] **Step 6: Set up Alembic**

```bash
cd api && alembic init alembic
```

- [x] **Step 7: Replace `api/alembic/env.py`** with this content:

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from config import settings
import models  # noqa: registers models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from database import Base
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = settings.database_url_sync
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = settings.database_url_sync
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [x] **Step 8: Generate migration**

```bash
cd api && alembic revision --autogenerate -m "initial schema"
```

Expected: creates `api/alembic/versions/xxxx_initial_schema.py`

- [x] **Step 9: Edit the generated migration** to add TimescaleDB hypertable + insert the `create_hypertable` call after `price_bars` table creation. Open the generated file and add to the `upgrade()` function:

```python
def upgrade() -> None:
    # ... (autogenerated table creation code stays here) ...

    # Convert price_bars to TimescaleDB hypertable
    op.execute("SELECT create_hypertable('price_bars', 'time', if_not_exists => TRUE)")
```

And in `downgrade()`, add before dropping `price_bars`:
```python
def downgrade() -> None:
    # TimescaleDB hypertable is dropped automatically with the table
    # ... (autogenerated drop code stays here) ...
```

- [x] **Step 10: Run migration against running DB**

```bash
docker compose up db -d
cd api && alembic upgrade head
```

Expected:
```
INFO  [alembic.runtime.migration] Running upgrade  -> xxxx, initial schema
```

- [x] **Step 11: Verify tables exist**

```bash
docker compose exec db psql -U tradesignal -d tradesignal -c "\dt"
```

Expected: `trades`, `price_bars`, `account_snapshots` all listed

- [x] **Step 12: Run existing tests — expect still PASS**

```bash
pytest tests/test_health.py -v
```

Expected: `PASSED`

- [x] **Step 13: Commit**

```bash
git add api/models/ api/alembic/ api/main.py
git commit -m "feat: db schema for trades, price_bars, account_snapshots with timescaledb hypertable"
```

---

## Task 4: Trade Events Endpoint + Trade Logger

**Files:**
- Create: `api/schemas/__init__.py`
- Create: `api/schemas/trade_event.py`
- Create: `api/routers/__init__.py`
- Create: `api/routers/trade_events.py`
- Create: `api/services/__init__.py`
- Create: `api/services/trade_logger.py`
- Modify: `api/main.py`
- Create: `tests/test_trade_events.py`

- [x] **Step 1: Write failing tests**

Create `tests/test_trade_events.py`:
```python
import pytest
from datetime import datetime, timezone

DEAL_OPEN_PAYLOAD = {
    "transaction_type": "DEAL_ADD",
    "ticket": 123456,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "market",
    "order_state": "filled",
    "open_price": 1950.50,
    "volume": 0.01,
    "tp": 1960.0,
    "sl": None,
    "pending_price": None,
    "open_time": "2026-05-17T09:00:00Z",
    "fill_time": "2026-05-17T09:00:01Z",
    "close_time": None,
    "close_price": None,
    "profit": 0.0,
    "swap": 0.0,
    "commission": -0.5,
}

DEAL_CLOSE_PAYLOAD = {
    "transaction_type": "DEAL_ADD",
    "ticket": 123456,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "market",
    "order_state": "filled",
    "open_price": 1950.50,
    "volume": 0.01,
    "tp": 1960.0,
    "sl": None,
    "pending_price": None,
    "open_time": "2026-05-17T09:00:00Z",
    "fill_time": "2026-05-17T09:00:01Z",
    "close_time": "2026-05-17T09:30:00Z",
    "close_price": 1955.0,
    "profit": 45.0,
    "swap": 0.0,
    "commission": -0.5,
}

PENDING_PAYLOAD = {
    "transaction_type": "ORDER_ADD",
    "ticket": 789012,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "buy_limit",
    "order_state": "pending",
    "pending_price": 1940.0,
    "open_price": None,
    "volume": 0.01,
    "tp": 1960.0,
    "sl": None,
    "open_time": "2026-05-17T10:00:00Z",
    "fill_time": None,
    "close_time": None,
    "close_price": None,
    "profit": 0.0,
    "swap": 0.0,
    "commission": 0.0,
}

@pytest.mark.asyncio
async def test_post_trade_event_returns_201(client):
    response = await client.post("/api/trade-events", json=DEAL_OPEN_PAYLOAD)
    assert response.status_code == 201

@pytest.mark.asyncio
async def test_post_trade_event_saves_to_db(client, db_session):
    await client.post("/api/trade-events", json=DEAL_OPEN_PAYLOAD)
    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(select(Trade).where(Trade.ticket == 123456))
    trade = result.scalar_one_or_none()
    assert trade is not None
    assert str(trade.symbol) == "XAUUSD"
    assert float(trade.open_price) == 1950.50

@pytest.mark.asyncio
async def test_post_trade_close_updates_existing(client, db_session):
    await client.post("/api/trade-events", json=DEAL_OPEN_PAYLOAD)
    await client.post("/api/trade-events", json=DEAL_CLOSE_PAYLOAD)
    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(select(Trade).where(Trade.ticket == 123456))
    trades = result.scalars().all()
    assert len(trades) == 1
    assert float(trades[0].profit) == 45.0
    assert trades[0].close_time is not None

@pytest.mark.asyncio
async def test_post_pending_order(client, db_session):
    response = await client.post("/api/trade-events", json=PENDING_PAYLOAD)
    assert response.status_code == 201
    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(select(Trade).where(Trade.ticket == 789012))
    trade = result.scalar_one_or_none()
    assert trade is not None
    assert trade.order_state.value == "pending"

@pytest.mark.asyncio
async def test_invalid_payload_returns_422(client):
    response = await client.post("/api/trade-events", json={"ticket": "not_a_number"})
    assert response.status_code == 422
```

- [x] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_trade_events.py -v
```

Expected: `ImportError` or `404` (router not registered)

- [x] **Step 3: Create `api/schemas/__init__.py`**

```python
```
(empty)

- [x] **Step 4: Create `api/schemas/trade_event.py`**

```python
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from models.trade import Direction, OrderType, OrderState

class TradeEventSchema(BaseModel):
    transaction_type: str
    ticket: int
    symbol: str
    direction: Direction | None = None
    order_type: OrderType | None = None
    order_state: OrderState | None = None
    pending_price: Decimal | None = None
    open_time: datetime | None = None
    fill_time: datetime | None = None
    close_time: datetime | None = None
    open_price: Decimal | None = None
    close_price: Decimal | None = None
    volume: Decimal | None = None
    tp: Decimal | None = None
    sl: Decimal | None = None
    profit: Decimal | None = None
    swap: Decimal | None = None
    commission: Decimal | None = None

    model_config = {"from_attributes": True}
```

- [x] **Step 5: Create `api/services/__init__.py`**

```python
```
(empty)

- [x] **Step 6: Create `api/services/trade_logger.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.trade import Trade
from schemas.trade_event import TradeEventSchema

async def upsert_trade(session: AsyncSession, event: TradeEventSchema) -> Trade:
    result = await session.execute(
        select(Trade).where(
            Trade.ticket == event.ticket,
            Trade.symbol == event.symbol,
            Trade.is_paper == False,
        )
    )
    trade = result.scalar_one_or_none()

    if trade is None:
        trade = Trade(
            ticket=event.ticket,
            symbol=event.symbol,
            is_paper=False,
        )
        session.add(trade)

    # Update fields from event, skipping None values
    fields = [
        "direction", "order_type", "order_state", "pending_price",
        "open_time", "fill_time", "close_time", "open_price", "close_price",
        "volume", "tp", "sl", "profit", "swap", "commission",
    ]
    for field in fields:
        value = getattr(event, field)
        if value is not None:
            setattr(trade, field, value)

    await session.commit()
    await session.refresh(trade)
    return trade
```

- [x] **Step 7: Create `api/routers/__init__.py`**

```python
```
(empty)

- [x] **Step 8: Create `api/routers/trade_events.py`**

```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.trade_event import TradeEventSchema
from services.trade_logger import upsert_trade

router = APIRouter(prefix="/api", tags=["trade-events"])

@router.post("/trade-events", status_code=status.HTTP_201_CREATED)
async def receive_trade_event(
    event: TradeEventSchema,
    session: AsyncSession = Depends(get_session),
):
    trade = await upsert_trade(session, event)
    return {"id": str(trade.id), "ticket": trade.ticket}
```

- [x] **Step 9: Register router in `api/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from database import engine, Base
import models  # noqa: F401
from routers.trade_events import router as trade_events_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title="Trade Signal Partner", lifespan=lifespan)
app.include_router(trade_events_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [x] **Step 10: Run all tests — expect PASS**

```bash
pytest tests/ -v
```

Expected: all 6 tests `PASSED`

- [x] **Step 11: Commit**

```bash
git add api/schemas/ api/routers/ api/services/ api/main.py tests/test_trade_events.py
git commit -m "feat: trade events endpoint with upsert trade logger"
```

---

## Task 5: Price Tick Endpoint + Price Handler

**Files:**
- Create: `api/schemas/price_tick.py`
- Create: `api/routers/price_tick.py`
- Create: `api/services/price_handler.py`
- Modify: `api/main.py`
- Create: `tests/test_price_tick.py`

- [x] **Step 1: Write failing tests**

Create `tests/test_price_tick.py`:
```python
import pytest

PRICE_TICK_PAYLOAD = {
    "timestamp": "2026-05-17T09:00:00Z",
    "account": {
        "equity": 10500.00,
        "balance": 10000.00,
        "margin": 450.00,
        "free_margin": 10050.00,
        "floating_pl": 500.00,
    },
    "bars": {
        "M5":  {"open": 1950.1, "high": 1951.2, "low": 1949.8, "close": 1950.9, "volume": 1200},
        "M15": {"open": 1948.5, "high": 1951.5, "low": 1948.0, "close": 1950.9, "volume": 3600},
        "M30": {"open": 1947.0, "high": 1952.0, "low": 1946.5, "close": 1950.9, "volume": 7200},
        "H1":  {"open": 1945.0, "high": 1953.0, "low": 1944.5, "close": 1950.9, "volume": 14400},
        "H4":  {"open": 1940.0, "high": 1955.0, "low": 1939.0, "close": 1950.9, "volume": 57600},
        "D":   {"open": 1930.0, "high": 1960.0, "low": 1928.0, "close": 1950.9, "volume": 86400},
        "W1":  {"open": 1920.0, "high": 1965.0, "low": 1918.0, "close": 1950.9, "volume": 604800},
    },
    "symbol": "XAUUSD",
}

@pytest.mark.asyncio
async def test_post_price_tick_returns_200(client):
    response = await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_price_tick_saves_bars(client, db_session):
    await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    from sqlalchemy import select
    from models.price_bar import PriceBar
    result = await db_session.execute(select(PriceBar))
    bars = result.scalars().all()
    assert len(bars) == 7

@pytest.mark.asyncio
async def test_price_tick_saves_account_snapshot(client, db_session):
    await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    from sqlalchemy import select
    from models.account_snapshot import AccountSnapshot
    result = await db_session.execute(select(AccountSnapshot))
    snapshots = result.scalars().all()
    assert len(snapshots) == 1
    assert float(snapshots[0].equity) == 10500.00

@pytest.mark.asyncio
async def test_price_tick_deduplicates_bars(client, db_session):
    await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    await client.post("/api/price-tick", json=PRICE_TICK_PAYLOAD)
    from sqlalchemy import select
    from models.price_bar import PriceBar
    result = await db_session.execute(select(PriceBar))
    bars = result.scalars().all()
    assert len(bars) == 7  # no duplicates on same timestamp+symbol+timeframe
```

- [x] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_price_tick.py -v
```

Expected: `404` (router not registered)

- [x] **Step 3: Create `api/schemas/price_tick.py`**

```python
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel

class OHLCVSchema(BaseModel):
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None

class AccountStateSchema(BaseModel):
    equity: Decimal
    balance: Decimal
    margin: Decimal
    free_margin: Decimal
    floating_pl: Decimal

class PriceTickSchema(BaseModel):
    timestamp: datetime
    symbol: str
    account: AccountStateSchema
    bars: dict[str, OHLCVSchema]
```

- [x] **Step 4: Create `api/services/price_handler.py`**

```python
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import insert

from models.price_bar import PriceBar, Timeframe
from models.account_snapshot import AccountSnapshot
from schemas.price_tick import PriceTickSchema

VALID_TIMEFRAMES = {tf.value for tf in Timeframe}

async def save_price_tick(session: AsyncSession, tick: PriceTickSchema) -> None:
    # Save account snapshot (insert or ignore duplicate timestamp)
    snapshot = AccountSnapshot(
        timestamp=tick.timestamp,
        equity=tick.account.equity,
        balance=tick.account.balance,
        margin=tick.account.margin,
        free_margin=tick.account.free_margin,
        floating_pl=tick.account.floating_pl,
    )
    session.add(snapshot)

    # Save price bars (upsert — ignore duplicates on same PK)
    for tf_str, ohlcv in tick.bars.items():
        if tf_str not in VALID_TIMEFRAMES:
            continue
        bar = PriceBar(
            time=tick.timestamp,
            symbol=tick.symbol,
            timeframe=Timeframe(tf_str),
            open=ohlcv.open,
            high=ohlcv.high,
            low=ohlcv.low,
            close=ohlcv.close,
            volume=ohlcv.volume,
        )
        session.add(bar)

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        # Duplicate PK on same timestamp — silently ignore
```

- [x] **Step 5: Create `api/routers/price_tick.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.price_tick import PriceTickSchema
from services.price_handler import save_price_tick

router = APIRouter(prefix="/api", tags=["price-tick"])

@router.post("/price-tick")
async def receive_price_tick(
    tick: PriceTickSchema,
    session: AsyncSession = Depends(get_session),
):
    await save_price_tick(session, tick)
    return {"status": "saved", "timestamp": tick.timestamp.isoformat()}
```

- [x] **Step 6: Register router in `api/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from database import engine, Base
import models  # noqa: F401
from routers.trade_events import router as trade_events_router
from routers.price_tick import router as price_tick_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title="Trade Signal Partner", lifespan=lifespan)
app.include_router(trade_events_router)
app.include_router(price_tick_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [x] **Step 7: Run all tests — expect PASS**

```bash
pytest tests/ -v
```

Expected: all 11 tests `PASSED`

- [x] **Step 8: Commit**

```bash
git add api/schemas/price_tick.py api/routers/price_tick.py api/services/price_handler.py api/main.py tests/test_price_tick.py
git commit -m "feat: price tick endpoint saves ohlcv bars and account snapshots"
```

---

## Task 6: MQL5 EA — TradeSignalBridge

**Files:**
- Create: `ea/TradeSignalBridge.mq5`

Note: MQL5 code cannot be unit-tested automatically. Manual testing steps provided.

- [x] **Step 1: Create `ea/TradeSignalBridge.mq5`**

```mql5
//+------------------------------------------------------------------+
//| TradeSignalBridge.mq5                                            |
//| Sends trade events and price bars to Trade Signal Partner API    |
//+------------------------------------------------------------------+
#property copyright "Trade Signal Partner"
#property version   "1.00"
#property strict

input string InpServerURL  = "http://localhost:8000";
input string InpSymbol     = "XAUUSD";
input int    InpTimerSec   = 60;

//--- HTTP helper
bool PostJSON(const string endpoint, const string body)
{
   string url     = InpServerURL + endpoint;
   string headers = "Content-Type: application/json\r\n";
   char   post[], result[];
   string result_headers;
   StringToCharArray(body, post, 0, StringLen(body));
   int res = WebRequest("POST", url, headers, 5000, post, result, result_headers);
   if(res == -1) {
      Print("WebRequest error: ", GetLastError(), " URL: ", url);
      return false;
   }
   return true;
}

//--- Format decimal safely
string F(double v) { return DoubleToString(v, 5); }
string F2(double v) { return DoubleToString(v, 2); }

//--- Build OHLCV JSON for one timeframe
string BarJSON(ENUM_TIMEFRAMES tf)
{
   MqlRates rates[];
   if(CopyRates(InpSymbol, tf, 1, 1, rates) < 1) return "null";
   return StringFormat(
      "{\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.0f}",
      rates[0].open, rates[0].high, rates[0].low, rates[0].close, (double)rates[0].tick_volume
   );
}

//--- Get timeframe string label
string TFLabel(ENUM_TIMEFRAMES tf)
{
   switch(tf) {
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D";
      case PERIOD_W1:  return "W1";
      default:         return "UNKNOWN";
   }
}

//--- Direction string
string DirectionStr(ENUM_ORDER_TYPE type)
{
   if(type == ORDER_TYPE_BUY || type == ORDER_TYPE_BUY_LIMIT ||
      type == ORDER_TYPE_BUY_STOP || type == ORDER_TYPE_BUY_STOP_LIMIT)
      return "buy";
   return "sell";
}

//--- OrderType string
string OrderTypeStr(ENUM_ORDER_TYPE type)
{
   switch(type) {
      case ORDER_TYPE_BUY:            return "market";
      case ORDER_TYPE_SELL:           return "market";
      case ORDER_TYPE_BUY_LIMIT:      return "buy_limit";
      case ORDER_TYPE_SELL_LIMIT:     return "sell_limit";
      case ORDER_TYPE_BUY_STOP:       return "buy_stop";
      case ORDER_TYPE_SELL_STOP:      return "sell_stop";
      case ORDER_TYPE_BUY_STOP_LIMIT: return "buy_stop_limit";
      case ORDER_TYPE_SELL_STOP_LIMIT:return "sell_stop_limit";
      default:                        return "market";
   }
}

//--- ISO 8601 datetime
string ISOTime(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
      dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

string NullOrStr(double v)   { return (v == 0.0) ? "null" : F(v); }
string NullOrTime(datetime t){ return (t == 0)   ? "null" : ("\"" + ISOTime(t) + "\""); }

int OnInit()
{
   // Verify WebRequest is allowed in MT5:
   // Tools → Options → Expert Advisors → Allow WebRequest for: http://localhost:8000
   EventSetTimer(InpTimerSec);
   Print("TradeSignalBridge v1.00 started. Sending to: ", InpServerURL);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("TradeSignalBridge stopped.");
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest    &request,
                        const MqlTradeResult     &result)
{
   // Only process events for our target symbol
   if(trans.symbol != InpSymbol) return;

   string trans_type = "";
   string order_state = "filled";

   switch(trans.type) {
      case TRADE_TRANSACTION_ORDER_ADD:
         trans_type  = "ORDER_ADD";
         order_state = "pending";
         break;
      case TRADE_TRANSACTION_ORDER_UPDATE:
         trans_type  = "ORDER_UPDATE";
         order_state = "pending";
         break;
      case TRADE_TRANSACTION_ORDER_DELETE:
         trans_type  = "ORDER_DELETE";
         order_state = (trans.order_state == ORDER_STATE_CANCELED) ? "cancelled" : "expired";
         break;
      case TRADE_TRANSACTION_DEAL_ADD:
         trans_type  = "DEAL_ADD";
         order_state = "filled";
         break;
      case TRADE_TRANSACTION_POSITION_UPDATE:
         trans_type  = "POSITION_UPDATE";
         order_state = "filled";
         break;
      default:
         return; // ignore other transaction types
   }

   // Get deal or order details
   double open_price = 0, close_price = 0, volume = 0, tp = 0, sl = 0;
   double profit = 0, swap = 0, commission = 0, pending_price = 0;
   datetime open_time = 0, fill_time = 0, close_time = 0;
   ENUM_ORDER_TYPE order_type_enum = ORDER_TYPE_BUY;
   long ticket = trans.order;

   if(trans.type == TRADE_TRANSACTION_DEAL_ADD && trans.deal > 0) {
      if(HistoryDealSelect(trans.deal)) {
         ticket      = (long)HistoryDealGetInteger(trans.deal, DEAL_TICKET);
         open_price  = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
         volume      = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
         profit      = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
         swap        = HistoryDealGetDouble(trans.deal, DEAL_SWAP);
         commission  = HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
         fill_time   = (datetime)HistoryDealGetInteger(trans.deal, DEAL_TIME);
         long deal_entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
         if(deal_entry == DEAL_ENTRY_OUT || deal_entry == DEAL_ENTRY_INOUT) {
            close_price = open_price;
            close_time  = fill_time;
            open_price  = 0;
         }
      }
   }

   if(trans.order > 0 && HistoryOrderSelect(trans.order)) {
      if(open_price == 0) open_price = HistoryOrderGetDouble(trans.order, ORDER_PRICE_OPEN);
      tp            = HistoryOrderGetDouble(trans.order, ORDER_TP);
      sl            = HistoryOrderGetDouble(trans.order, ORDER_SL);
      pending_price = HistoryOrderGetDouble(trans.order, ORDER_PRICE_CURRENT);
      open_time     = (datetime)HistoryOrderGetInteger(trans.order, ORDER_TIME_SETUP);
      order_type_enum = (ENUM_ORDER_TYPE)HistoryOrderGetInteger(trans.order, ORDER_TYPE);
      if(volume == 0) volume = HistoryOrderGetDouble(trans.order, ORDER_VOLUME_INITIAL);
   }

   string body = StringFormat(
      "{"
      "\"transaction_type\":\"%s\","
      "\"ticket\":%I64d,"
      "\"symbol\":\"%s\","
      "\"direction\":\"%s\","
      "\"order_type\":\"%s\","
      "\"order_state\":\"%s\","
      "\"pending_price\":%s,"
      "\"open_price\":%s,"
      "\"close_price\":%s,"
      "\"volume\":%.2f,"
      "\"tp\":%s,"
      "\"sl\":%s,"
      "\"open_time\":%s,"
      "\"fill_time\":%s,"
      "\"close_time\":%s,"
      "\"profit\":%.2f,"
      "\"swap\":%.2f,"
      "\"commission\":%.2f"
      "}",
      trans_type, ticket, InpSymbol,
      DirectionStr(order_type_enum),
      OrderTypeStr(order_type_enum),
      order_state,
      NullOrStr(pending_price),
      NullOrStr(open_price),
      NullOrStr(close_price),
      volume,
      NullOrStr(tp),
      NullOrStr(sl),
      NullOrTime(open_time),
      NullOrTime(fill_time),
      NullOrTime(close_time),
      profit, swap, commission
   );

   PostJSON("/api/trade-events", body);
}

void OnTimer()
{
   string now = "\"" + ISOTime(TimeCurrent()) + "\"";

   ENUM_TIMEFRAMES tfs[] = {PERIOD_M5, PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_H4, PERIOD_D1, PERIOD_W1};
   string bars_json = "";
   for(int i = 0; i < ArraySize(tfs); i++) {
      if(bars_json != "") bars_json += ",";
      bars_json += "\"" + TFLabel(tfs[i]) + "\":" + BarJSON(tfs[i]);
   }

   string body = StringFormat(
      "{"
      "\"timestamp\":%s,"
      "\"symbol\":\"%s\","
      "\"account\":{"
         "\"equity\":%.2f,"
         "\"balance\":%.2f,"
         "\"margin\":%.2f,"
         "\"free_margin\":%.2f,"
         "\"floating_pl\":%.2f"
      "},"
      "\"bars\":{%s}"
      "}",
      now,
      InpSymbol,
      AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_MARGIN),
      AccountInfoDouble(ACCOUNT_FREEMARGIN),
      AccountInfoDouble(ACCOUNT_EQUITY) - AccountInfoDouble(ACCOUNT_BALANCE),
      bars_json
   );

   PostJSON("/api/price-tick", body);
}
```

- [x] **Step 2: Manual EA test instructions**

```
1. Copy ea/TradeSignalBridge.mq5 to:
   ~/Library/Application Support/MetaTrader 5/MQL5/Experts/

2. In MT5: Tools → Options → Expert Advisors
   ✅ Allow automated trading
   ✅ Allow WebRequest for listed URL: http://localhost:8000

3. Start Docker: docker compose up

4. Compile and attach EA to XAUUSD M5 chart

5. Check MT5 Journal tab — should see:
   "TradeSignalBridge v1.00 started. Sending to: http://localhost:8000"

6. Wait 1 minute, check API:
   curl http://localhost:8000/health
   → {"status": "ok"}

7. Query DB for price bars:
   docker compose exec db psql -U tradesignal -d tradesignal \
     -c "SELECT timeframe, close, time FROM price_bars ORDER BY time DESC LIMIT 7;"
   → Should show 7 rows (one per timeframe)

8. Place a test pending order in MT5, then check:
   docker compose exec db psql -U tradesignal -d tradesignal \
     -c "SELECT ticket, order_type, order_state FROM trades;"
   → Should show the pending order
```

- [x] **Step 3: Commit**

```bash
git add ea/TradeSignalBridge.mq5
git commit -m "feat: mql5 ea bridge for trade events and price ticks"
```

---

## Task 7: Full Stack Integration Smoke Test

- [x] **Step 1: Start full stack**

```bash
docker compose up --build -d
docker compose ps
```

Expected: `db` and `api` both `healthy`/`running`

- [x] **Step 2: Health check**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [x] **Step 3: Simulate trade event**

```bash
curl -s -X POST http://localhost:8000/api/trade-events \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_type": "DEAL_ADD",
    "ticket": 999001,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "market",
    "order_state": "filled",
    "open_price": 1950.5,
    "volume": 0.01,
    "tp": 1960.0,
    "sl": null,
    "pending_price": null,
    "open_time": "2026-05-17T09:00:00Z",
    "fill_time": "2026-05-17T09:00:01Z",
    "close_time": null,
    "close_price": null,
    "profit": 0.0,
    "swap": 0.0,
    "commission": -0.5
  }'
```

Expected: `{"id":"...","ticket":999001}`

- [x] **Step 4: Verify trade in DB**

```bash
docker compose exec db psql -U tradesignal -d tradesignal \
  -c "SELECT ticket, symbol, direction, open_price FROM trades WHERE ticket=999001;"
```

Expected: 1 row with `ticket=999001`

- [x] **Step 5: Simulate price tick**

```bash
curl -s -X POST http://localhost:8000/api/price-tick \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-05-17T09:01:00Z",
    "symbol": "XAUUSD",
    "account": {"equity":10500,"balance":10000,"margin":450,"free_margin":10050,"floating_pl":500},
    "bars": {
      "M5":  {"open":1950.1,"high":1951.2,"low":1949.8,"close":1950.9},
      "M15": {"open":1948.5,"high":1951.5,"low":1948.0,"close":1950.9},
      "M30": {"open":1947.0,"high":1952.0,"low":1946.5,"close":1950.9},
      "H1":  {"open":1945.0,"high":1953.0,"low":1944.5,"close":1950.9},
      "H4":  {"open":1940.0,"high":1955.0,"low":1939.0,"close":1950.9},
      "D":   {"open":1930.0,"high":1960.0,"low":1928.0,"close":1950.9},
      "W1":  {"open":1920.0,"high":1965.0,"low":1918.0,"close":1950.9}
    }
  }'
```

Expected: `{"status":"saved","timestamp":"2026-05-17T09:01:00+00:00"}`

- [x] **Step 6: Verify price bars in DB**

```bash
docker compose exec db psql -U tradesignal -d tradesignal \
  -c "SELECT timeframe, close FROM price_bars ORDER BY timeframe;"
```

Expected: 7 rows (M5, M15, M30, H1, H4, D, W1)

- [x] **Step 7: Final test suite run**

```bash
pytest tests/ -v
```

Expected: all 11 tests `PASSED`

- [x] **Step 8: Final commit**

```bash
git add .
git commit -m "feat: plan 1 complete — mt5 to postgresql data pipeline working end-to-end"
```

---

## What's Next

**Plan 2** will build on this foundation:
- Insight Engine (pattern discovery from trade history)
- Trend Bias Calculator (per-timeframe bias from price_bars)
- Basic Pattern Detector (engulfing, pin bar on M15/M30)
- Mirror Paper Trader (paper enter on every real trade)
- Alert Manager (equity buffer, double-down, consecutive loss, counter-trend)

All of Plan 2 reads from the tables created in this plan.
