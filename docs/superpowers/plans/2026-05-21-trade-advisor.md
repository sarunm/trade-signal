# Trade Advisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เพิ่ม entry scoring, recovery map (fib-based TP/Add/Cut zones), และ live zone alerts พร้อม macOS notification ผ่าน Browser Web Notifications API

**Architecture:** เรียก `compute_entry_score()` + `compute_recovery_plan()` ทุกครั้งที่ trade เปิด (ใน `trade_logger.py` หลัง `fill_entry_context()`). Zone check ทุก market tick ใน `check_advisor_zones()`. Frontend polls `/api/trade-advisor` ทุก 10s และ fires Web Notification เมื่อเจอ alert ใหม่

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async + SQLite (tests) + PostgreSQL (prod) + React + TailwindCSS

---

## File Map

| File | Action | หน้าที่ |
|---|---|---|
| `api/alembic/versions/008_add_trade_advisor_fields.py` | Create | migration: +3 cols บน trades, +1 col บน alerts |
| `api/models/trade.py` | Modify | +`entry_score`, `entry_verdict`, `recovery_plan` |
| `api/models/alert.py` | Modify | +`trade_id` (nullable UUID) |
| `api/schemas/alert.py` | Modify | +`trade_id` ใน `AlertResponse` |
| `api/services/trade_advisor.py` | Create | `compute_entry_score()`, `compute_recovery_plan()`, `check_advisor_zones()` |
| `api/routers/trade_advisor.py` | Create | `GET /api/trade-advisor` |
| `api/routers/alerts.py` | Modify | +`types` query param filter |
| `api/routers/trade_events.py` | Modify | เพิ่ม hook หลัง `fill_entry_context()` |
| `api/routers/market_tick.py` | Modify | เพิ่ม hook ใน tick handler |
| `api/services/trade_logger.py` | Modify | เรียก `compute_entry_score()` + `compute_recovery_plan()` |
| `api/main.py` | Modify | register trade_advisor router |
| `tests/test_trade_advisor.py` | Create | unit tests ทั้งหมด |
| `frontend/src/components/TradeAdvisor.jsx` | Create | panel: score + recovery map |
| `frontend/src/hooks/useTradeAlerts.js` | Create | polls alerts → Web Notification |
| `frontend/src/App.jsx` | Modify | +`<TradeAdvisor>` + `useTradeAlerts()` |

---

## Task 1: Migration + Model Updates

**Files:**
- Create: `api/alembic/versions/008_add_trade_advisor_fields.py`
- Modify: `api/models/trade.py`
- Modify: `api/models/alert.py`
- Modify: `api/schemas/alert.py`

- [ ] **Step 1: Create migration 008**

```python
# api/alembic/versions/008_add_trade_advisor_fields.py
"""add trade advisor fields

Revision ID: 008
Revises: 007
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("entry_score", sa.Integer(), nullable=True))
    op.add_column("trades", sa.Column("entry_verdict", sa.String(20), nullable=True))
    op.add_column("trades", sa.Column("recovery_plan", postgresql.JSONB(), nullable=True))
    op.add_column("alerts", sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "trade_id")
    op.drop_column("trades", "recovery_plan")
    op.drop_column("trades", "entry_verdict")
    op.drop_column("trades", "entry_score")
```

- [ ] **Step 2: Apply migration**

```bash
cd api && alembic upgrade head
```

Expected: `Running upgrade 007 -> 008`

- [ ] **Step 3: Update Trade model** — เพิ่ม 3 columns ใน `api/models/trade.py`

เพิ่มหลัง `account_id`:
```python
from sqlalchemy import JSON
# ... (existing imports)

# ใน class Trade เพิ่ม:
entry_score: Mapped[Optional[int]] = mapped_column(sa.Integer(), nullable=True)
entry_verdict: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
recovery_plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 4: Update Alert model** — เพิ่ม `trade_id` ใน `api/models/alert.py`

```python
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str] = mapped_column(Text)
    trigger_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    trade_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
```

- [ ] **Step 5: Update AlertResponse schema** — เพิ่ม `trade_id` ใน `api/schemas/alert.py`

```python
from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: UUID
    type: str
    message: str
    trigger_data: Optional[Any] = None
    sent_at: datetime
    acknowledged: bool
    trade_id: Optional[UUID] = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 6: Verify models load**

```bash
cd api && python -c "from models.trade import Trade; from models.alert import Alert; print('OK')"
```

Expected: `OK`

---

## Task 2: Entry Scoring Service (TDD)

**Files:**
- Create: `tests/test_trade_advisor.py`
- Create: `api/services/trade_advisor.py`

- [ ] **Step 1: Write failing tests for entry scoring**

```python
# tests/test_trade_advisor.py
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from models.fib_level import FibLevel
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from services.trade_advisor import compute_entry_score


def _make_trade(**kwargs) -> Trade:
    defaults = dict(
        id=uuid.uuid4(),
        ticket=9001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("4700.00"),
        # London peak hour (09:00 UTC Wednesday)
        open_time=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),
        is_paper=False,
        is_rescue=False,
    )
    defaults.update(kwargs)
    return Trade(**defaults)


def _make_fib(db_session, **kwargs):
    defaults = dict(
        symbol="XAUUSD",
        period="W",
        prev_high=4870.0,
        prev_low=4608.0,
        prev_close=4700.0,
        pp=4726.0,
        resistance={"R1": 4787.57, "R2": 4826.35, "R3": 4857.0,
                    "R4": 4888.75, "R5": 4916.66, "R6": 4988.0,
                    "R7": 5050.57, "R8": 5075.66, "R9": 5119.0, "R10": 5150.0},
        support={"S1": 4664.43, "S2": 4625.65, "S3": 4595.0,
                 "S4": 4563.25, "S5": 4535.34, "S6": 4464.0,
                 "S7": 4401.43, "S8": 4376.34, "S9": 4333.0, "S10": 4302.0},
        computed_at=datetime(2026, 5, 20, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    fib = FibLevel(**defaults)
    db_session.add(fib)
    return fib


@pytest.mark.asyncio
async def test_entry_score_good_entry(db_session):
    """PP fib + London peak + bullish pin bar → score ≥ 70"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        near_fib_level="PP",
        fib_distance_pts=Decimal("2.0"),
        entry_candle="pin_bar_bullish",
        entry_candle_tf="H1",
        is_rescue=False,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)

    assert trade.entry_score is not None
    assert trade.entry_score >= 70
    assert trade.entry_verdict == "good"


@pytest.mark.asyncio
async def test_entry_score_high_risk(db_session):
    """No fib + bad session (< 5 samples → neutral) + 2 setup losses → score < 40"""
    # Insert 2 recent losing original trades (setup losses)
    for i in range(2):
        loser = _make_trade(
            id=uuid.uuid4(),
            ticket=8000 + i,
            order_state=OrderState.filled,
            open_time=datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
            profit=Decimal("-150.00"),
            is_rescue=False,
        )
        db_session.add(loser)
    await db_session.commit()

    trade = _make_trade(
        # open outside peak hours (Friday evening)
        open_time=datetime(2026, 5, 22, 18, 0, tzinfo=timezone.utc),
        near_fib_level=None,
        fib_distance_pts=None,
        entry_candle="none",
        is_rescue=False,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)

    assert trade.entry_score is not None
    assert trade.entry_score < 40
    assert trade.entry_verdict == "high_risk"


@pytest.mark.asyncio
async def test_entry_score_rescue_at_fib_gives_bonus(db_session):
    """Rescue trade at fib level → +15 rescue bonus"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        near_fib_level="S1",
        fib_distance_pts=Decimal("1.5"),
        entry_candle="none",
        is_rescue=True,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)

    # fib +20 + rescue at fib +15 + peak hours +10 = 45 min (no losses, no session data)
    assert trade.entry_score >= 40
    assert trade.entry_verdict in ("good", "caution")


@pytest.mark.asyncio
async def test_entry_score_rescue_not_at_fib_gives_penalty(db_session):
    """Rescue trade far from fib → -15 rescue penalty"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        near_fib_level="R3",
        fib_distance_pts=Decimal("25.0"),  # > 5 pts → not aligned
        entry_candle="none",
        is_rescue=True,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)

    # rescue penalty -15 should reduce score
    assert trade.entry_score is not None
    assert trade.entry_verdict is not None


@pytest.mark.asyncio
async def test_entry_score_idempotent(db_session):
    """Calling compute_entry_score twice does not change the score"""
    trade = _make_trade(near_fib_level=None, entry_candle="none", is_rescue=False)
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)
    first_score = trade.entry_score

    await compute_entry_score(db_session, trade)
    assert trade.entry_score == first_score


@pytest.mark.asyncio
async def test_entry_score_peak_hours_penalty(db_session):
    """Friday after 17:00 UTC → -10 peak hours penalty"""
    trade_peak = _make_trade(
        id=uuid.uuid4(), ticket=9010,
        open_time=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),  # Wednesday London peak
        near_fib_level=None, entry_candle="none", is_rescue=False,
    )
    trade_offpeak = _make_trade(
        id=uuid.uuid4(), ticket=9011,
        open_time=datetime(2026, 5, 23, 18, 0, tzinfo=timezone.utc),  # Friday 18:00 UTC
        near_fib_level=None, entry_candle="none", is_rescue=False,
    )
    db_session.add(trade_peak)
    db_session.add(trade_offpeak)
    await db_session.commit()

    await compute_entry_score(db_session, trade_peak)
    await compute_entry_score(db_session, trade_offpeak)

    assert trade_peak.entry_score > trade_offpeak.entry_score
```

- [ ] **Step 2: Run — verify tests fail**

```bash
cd api && pytest ../tests/test_trade_advisor.py -v 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError` for `trade_advisor`

- [ ] **Step 3: Implement `api/services/trade_advisor.py`**

```python
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.alert import Alert
from models.fib_level import FibLevel
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from schemas.market_tick import MarketTickSchema

_FIB_PROXIMITY_PTS = 5.0
_MIN_SESSION_SAMPLE = 5


def _get_session(dt: datetime) -> str | None:
    h = dt.astimezone(timezone.utc).hour if dt.tzinfo else dt.replace(tzinfo=timezone.utc).hour
    if 1 <= h < 9:
        return "Asian"
    if 8 <= h < 16:
        return "London"
    if 13 <= h < 22:
        return "NY"
    return None


def _peak_hours_score(open_time: datetime) -> int:
    dt = open_time.astimezone(timezone.utc) if open_time.tzinfo else open_time.replace(tzinfo=timezone.utc)
    h = dt.hour
    weekday = dt.weekday()  # 0=Monday, 4=Friday
    if (weekday == 4 and h >= 17) or (weekday == 0 and h < 8):
        return -10
    if (8 <= h < 11) or (13 <= h < 16):
        return 10
    return 0


async def _session_win_rate(session: AsyncSession, trade: Trade) -> float | None:
    if trade.open_time is None:
        return None
    current_session = _get_session(trade.open_time)
    if not current_session:
        return None

    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == trade.symbol,
            Trade.order_state == OrderState.filled,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
            Trade.is_rescue == False,
        ).order_by(Trade.close_time.desc()).limit(50)
    )
    trades = result.scalars().all()
    session_trades = [t for t in trades if t.open_time and _get_session(t.open_time) == current_session]
    if len(session_trades) < _MIN_SESSION_SAMPLE:
        return None
    wins = sum(1 for t in session_trades if float(t.profit) > 0)
    return wins / len(session_trades)


async def _consecutive_setup_losses(session: AsyncSession, trade: Trade) -> int:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == trade.symbol,
            Trade.direction == trade.direction,
            Trade.is_rescue == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
            Trade.id != trade.id,
        ).order_by(Trade.close_time.desc()).limit(10)
    )
    recent = result.scalars().all()
    losses = 0
    for t in recent:
        if float(t.profit) < 0:
            losses += 1
        else:
            break
    return min(losses, 2)


async def _atr_score(session: AsyncSession, trade: Trade) -> int:
    result = await session.execute(
        select(PriceBar).where(
            PriceBar.symbol == trade.symbol,
            PriceBar.timeframe == Timeframe.H4,
        ).order_by(PriceBar.time.desc()).limit(21)
    )
    bars = list(reversed(result.scalars().all()))
    if len(bars) < 3:
        return 0
    true_ranges = []
    for i in range(1, len(bars)):
        high = float(bars[i].high)
        low = float(bars[i].low)
        prev_close = float(bars[i - 1].close)
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if not true_ranges:
        return 0
    avg_atr = sum(true_ranges[:-1]) / max(len(true_ranges) - 1, 1)
    current_atr = true_ranges[-1]
    if avg_atr == 0:
        return 0
    return -10 if current_atr > 1.5 * avg_atr else 10


async def compute_entry_score(session: AsyncSession, trade: Trade) -> None:
    if trade.entry_score is not None:
        return
    if trade.open_price is None or trade.direction is None:
        return

    score = 0

    # 1. Fib alignment
    dist = float(trade.fib_distance_pts or 999)
    if trade.near_fib_level == "PP" and dist <= _FIB_PROXIMITY_PTS:
        score += 25
    elif trade.near_fib_level is not None and dist <= _FIB_PROXIMITY_PTS:
        score += 20

    # 2. Session win rate
    win_rate = await _session_win_rate(session, trade)
    if win_rate is not None:
        if win_rate > 0.60:
            score += 20
        elif win_rate < 0.40:
            score -= 15

    # 3. Entry pattern
    candle = trade.entry_candle or ""
    if candle not in ("none", "doji", ""):
        if trade.direction == Direction.buy and "bullish" in candle:
            score += 20
        elif trade.direction == Direction.sell and "bearish" in candle:
            score += 20

    # 4. Rescue placement
    if trade.is_rescue:
        if trade.near_fib_level is not None and dist <= _FIB_PROXIMITY_PTS:
            score += 15
        else:
            score -= 15

    # 5. ATR state
    score += await _atr_score(session, trade)

    # 6. Session peak hours
    if trade.open_time:
        score += _peak_hours_score(trade.open_time)

    # 7. Consecutive setup losses
    losses = await _consecutive_setup_losses(session, trade)
    score -= losses * 15

    trade.entry_score = score
    if score >= 70:
        trade.entry_verdict = "good"
    elif score >= 40:
        trade.entry_verdict = "caution"
    else:
        trade.entry_verdict = "high_risk"
```

- [ ] **Step 4: Run entry scoring tests — verify pass**

```bash
cd api && pytest ../tests/test_trade_advisor.py::test_entry_score_good_entry ../tests/test_trade_advisor.py::test_entry_score_high_risk ../tests/test_trade_advisor.py::test_entry_score_idempotent ../tests/test_trade_advisor.py::test_entry_score_rescue_at_fib_gives_bonus ../tests/test_trade_advisor.py::test_entry_score_rescue_not_at_fib_gives_penalty ../tests/test_trade_advisor.py::test_entry_score_peak_hours_penalty -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add api/alembic/versions/008_add_trade_advisor_fields.py api/models/trade.py api/models/alert.py api/schemas/alert.py api/services/trade_advisor.py tests/test_trade_advisor.py
git commit -m "feat: add trade advisor migration, models, and entry scoring service"
```

---

## Task 3: Recovery Plan Service (TDD)

**Files:**
- Modify: `tests/test_trade_advisor.py`
- Modify: `api/services/trade_advisor.py`

- [ ] **Step 1: Add recovery plan tests**

เพิ่มใน `tests/test_trade_advisor.py`:

```python
from services.trade_advisor import compute_recovery_plan


@pytest.mark.asyncio
async def test_recovery_plan_buy(db_session):
    """BUY @ PP → TP = R levels above, Add = S levels below, Cut = S4"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        open_price=Decimal("4726.00"),  # at PP
        direction=Direction.buy,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_recovery_plan(db_session, trade)

    assert trade.recovery_plan is not None
    plan = trade.recovery_plan
    assert plan["direction"] == "buy"
    assert plan["entry_price"] == pytest.approx(4726.0)

    # TP = R levels above 4726
    assert len(plan["tp"]) == 3
    for zone in plan["tp"]:
        assert zone["price"] > 4726.0
        assert zone["pts"] > 0  # price - entry > 0

    # Add = S levels below 4726
    assert len(plan["add"]) == 3
    for zone in plan["add"]:
        assert zone["price"] < 4726.0
        assert zone["pts"] < 0  # price - entry < 0

    # Cut = 4th S level below entry
    assert plan["cut"]["label"] == "S4"
    assert plan["cut"]["price"] < 4726.0


@pytest.mark.asyncio
async def test_recovery_plan_sell(db_session):
    """SELL @ PP → TP = S levels below, Add = R levels above, Cut = R4"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        open_price=Decimal("4726.00"),
        direction=Direction.sell,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_recovery_plan(db_session, trade)

    plan = trade.recovery_plan
    assert plan["direction"] == "sell"
    assert len(plan["tp"]) == 3
    for zone in plan["tp"]:
        assert zone["price"] < 4726.0  # S levels below entry

    assert len(plan["add"]) == 3
    for zone in plan["add"]:
        assert zone["price"] > 4726.0  # R levels above entry

    assert plan["cut"]["label"] == "R4"


@pytest.mark.asyncio
async def test_recovery_plan_null_when_no_fib(db_session):
    """No fib data → recovery_plan stays None"""
    trade = _make_trade(open_price=Decimal("4700.00"), direction=Direction.buy)
    db_session.add(trade)
    await db_session.commit()

    await compute_recovery_plan(db_session, trade)

    assert trade.recovery_plan is None


@pytest.mark.asyncio
async def test_recovery_plan_idempotent(db_session):
    """Calling compute_recovery_plan twice does not change the plan"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(open_price=Decimal("4726.00"), direction=Direction.buy)
    db_session.add(trade)
    await db_session.commit()

    await compute_recovery_plan(db_session, trade)
    first_plan = dict(trade.recovery_plan)

    await compute_recovery_plan(db_session, trade)
    assert trade.recovery_plan == first_plan
```

- [ ] **Step 2: Run — verify tests fail**

```bash
cd api && pytest ../tests/test_trade_advisor.py::test_recovery_plan_buy -v 2>&1 | head -10
```

Expected: `ImportError` for `compute_recovery_plan`

- [ ] **Step 3: Implement `compute_recovery_plan()` — เพิ่มใน `api/services/trade_advisor.py`**

```python
async def compute_recovery_plan(session: AsyncSession, trade: Trade) -> None:
    if trade.recovery_plan is not None:
        return
    if trade.open_price is None or trade.direction is None:
        return

    result = await session.execute(
        select(FibLevel)
        .where(FibLevel.symbol == trade.symbol)
        .order_by(FibLevel.computed_at.desc())
        .limit(1)
    )
    fib = result.scalar_one_or_none()
    if fib is None:
        return

    entry = float(trade.open_price)
    direction = trade.direction

    all_r = sorted(
        [(k, float(v)) for k, v in fib.resistance.items()],
        key=lambda x: x[1],
    )
    all_s = sorted(
        [(k, float(v)) for k, v in fib.support.items()],
        key=lambda x: x[1],
        reverse=True,
    )

    def make_zone(label: str, price: float) -> dict:
        return {
            "label": label,
            "price": round(price, 2),
            "pts": round(price - entry, 2),
        }

    if direction == Direction.buy:
        tp_candidates = [(k, v) for k, v in all_r if v > entry]
        add_candidates = [(k, v) for k, v in all_s if v < entry]
        cut_candidates = [(k, v) for k, v in all_s if v < entry]
    else:
        tp_candidates = [(k, v) for k, v in all_s if v < entry]
        add_candidates = [(k, v) for k, v in all_r if v > entry]
        cut_candidates = [(k, v) for k, v in all_r if v > entry]

    tp_zones = [make_zone(k, v) for k, v in tp_candidates[:3]]
    add_zones = [make_zone(k, v) for k, v in add_candidates[:3]]
    cut_tuple = cut_candidates[3] if len(cut_candidates) > 3 else (cut_candidates[-1] if cut_candidates else None)

    if not tp_zones or not add_zones or cut_tuple is None:
        return

    trade.recovery_plan = {
        "entry_price": round(entry, 2),
        "direction": direction.value,
        "tp": tp_zones,
        "add": add_zones,
        "cut": make_zone(cut_tuple[0], cut_tuple[1]),
    }
```

- [ ] **Step 4: Run recovery plan tests — verify pass**

```bash
cd api && pytest ../tests/test_trade_advisor.py::test_recovery_plan_buy ../tests/test_trade_advisor.py::test_recovery_plan_sell ../tests/test_trade_advisor.py::test_recovery_plan_null_when_no_fib ../tests/test_trade_advisor.py::test_recovery_plan_idempotent -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/services/trade_advisor.py tests/test_trade_advisor.py
git commit -m "feat: add recovery plan computation to trade advisor service"
```

---

## Task 4: Zone Monitoring Service (TDD)

**Files:**
- Modify: `tests/test_trade_advisor.py`
- Modify: `api/services/trade_advisor.py`

- [ ] **Step 1: Add zone monitoring tests**

เพิ่มใน `tests/test_trade_advisor.py`:

```python
from services.trade_advisor import check_advisor_zones
from schemas.market_tick import MarketTickSchema


def _make_tick(bid: str, symbol: str = "XAUUSD") -> MarketTickSchema:
    return MarketTickSchema(
        timestamp=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        symbol=symbol,
        bid=Decimal(bid),
        ask=Decimal(bid) + Decimal("0.30"),
    )


def _make_trade_with_plan(direction: Direction, entry: str, plan: dict, **kwargs) -> Trade:
    return _make_trade(
        direction=direction,
        open_price=Decimal(entry),
        recovery_plan=plan,
        close_time=None,
        order_state=OrderState.filled,
        **kwargs,
    )


_BUY_PLAN = {
    "entry_price": 4726.0,
    "direction": "buy",
    "tp": [{"label": "R1", "price": 4787.57, "pts": 61.57}],
    "add": [
        {"label": "S1", "price": 4664.43, "pts": -61.57},
        {"label": "S2", "price": 4625.65, "pts": -100.35},
        {"label": "S3", "price": 4595.0, "pts": -131.0},
    ],
    "cut": {"label": "S4", "price": 4563.25, "pts": -162.75},
}


@pytest.mark.asyncio
async def test_zone_check_tp_alert(db_session):
    """BUY price crosses above R1 → tp_zone_reached alert"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4788.00")  # above R1 (4787.57)
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "tp_zone_reached")
    )
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].trade_id == trade.id
    assert alerts[0].trigger_data["label"] == "R1"


@pytest.mark.asyncio
async def test_zone_check_add_alert(db_session):
    """BUY price crosses below S1 → add_zone_reached alert"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4664.00")  # below S1 (4664.43)
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "add_zone_reached")
    )
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].trigger_data["label"] == "S1"


@pytest.mark.asyncio
async def test_zone_check_cut_alert(db_session):
    """BUY price crosses below S4 → cut_zone_reached alert"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4563.00")  # below S4 (4563.25)
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "cut_zone_reached")
    )
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_zone_check_cooldown(db_session):
    """Same zone triggered twice → only 1 alert created"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4664.00")  # below S1
    await check_advisor_zones(db_session, tick)
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "add_zone_reached", Alert.trade_id == trade.id)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_zone_check_no_alert_when_price_not_crossed(db_session):
    """Price still above S1 → no alert"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4700.00")  # between entry and S1
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(select(Alert))
    assert result.scalars().first() is None
```

- [ ] **Step 2: Run — verify tests fail**

```bash
cd api && pytest ../tests/test_trade_advisor.py::test_zone_check_add_alert -v 2>&1 | head -10
```

Expected: `ImportError` for `check_advisor_zones`

- [ ] **Step 3: Implement `check_advisor_zones()` — เพิ่มใน `api/services/trade_advisor.py`**

```python
def _zone_crossed(bid: float, level: float, direction: Direction, side: str) -> bool:
    if direction == Direction.buy:
        return bid >= level if side == "tp" else bid <= level
    else:
        return bid <= level if side == "tp" else bid >= level


async def _already_alerted(session: AsyncSession, trade_id, alert_type: str, label: str) -> bool:
    result = await session.execute(
        select(Alert).where(
            Alert.type == alert_type,
            Alert.trade_id == trade_id,
        )
    )
    existing = result.scalars().all()
    return any(
        a.trigger_data and a.trigger_data.get("label") == label
        for a in existing
    )


async def _fire_alert(
    session: AsyncSession,
    trade: Trade,
    zone: dict,
    alert_type: str,
) -> None:
    if await _already_alerted(session, trade.id, alert_type, zone["label"]):
        return

    messages = {
        "tp_zone_reached": f"Price at {zone['label']} ({zone['price']:.2f}) — TP reached",
        "add_zone_reached": f"Price at {zone['label']} ({zone['price']:.2f}) — Add zone reached",
        "cut_zone_reached": f"⚠️ {zone['label']} breached ({zone['price']:.2f}) — consider cutting",
    }
    session.add(Alert(
        type=alert_type,
        message=messages[alert_type],
        trigger_data={**zone, "trade_id": str(trade.id)},
        sent_at=datetime.now(timezone.utc),
        trade_id=trade.id,
    ))


async def check_advisor_zones(session: AsyncSession, tick: MarketTickSchema) -> None:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.symbol == tick.symbol,
            Trade.recovery_plan.isnot(None),
        )
    )
    open_trades = result.scalars().all()

    bid = float(tick.bid)
    for trade in open_trades:
        plan = trade.recovery_plan

        for zone in plan.get("tp", []):
            if _zone_crossed(bid, zone["price"], trade.direction, "tp"):
                await _fire_alert(session, trade, zone, "tp_zone_reached")

        for zone in plan.get("add", []):
            if _zone_crossed(bid, zone["price"], trade.direction, "add"):
                await _fire_alert(session, trade, zone, "add_zone_reached")

        cut = plan.get("cut")
        if cut and _zone_crossed(bid, cut["price"], trade.direction, "cut"):
            await _fire_alert(session, trade, cut, "cut_zone_reached")

    await session.commit()
```

- [ ] **Step 4: Run zone monitoring tests — verify pass**

```bash
cd api && pytest ../tests/test_trade_advisor.py::test_zone_check_tp_alert ../tests/test_trade_advisor.py::test_zone_check_add_alert ../tests/test_trade_advisor.py::test_zone_check_cut_alert ../tests/test_trade_advisor.py::test_zone_check_cooldown ../tests/test_trade_advisor.py::test_zone_check_no_alert_when_price_not_crossed -v
```

Expected: 5 passed

- [ ] **Step 5: Run all trade advisor tests**

```bash
cd api && pytest ../tests/test_trade_advisor.py -v
```

Expected: 14 passed

- [ ] **Step 6: Commit**

```bash
git add api/services/trade_advisor.py tests/test_trade_advisor.py
git commit -m "feat: add zone monitoring and alert firing to trade advisor service"
```

---

## Task 5: Router + Wire-up + Alerts Filter

**Files:**
- Create: `api/routers/trade_advisor.py`
- Modify: `api/routers/alerts.py`
- Modify: `api/services/trade_logger.py`
- Modify: `api/routers/market_tick.py`
- Modify: `api/main.py`

- [ ] **Step 1: Create trade advisor router**

```python
# api/routers/trade_advisor.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.trade import Trade, OrderState

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
    return [
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
```

- [ ] **Step 2: Add `types` filter to alerts router**

แก้ `api/routers/alerts.py` — เพิ่ม `types` param:

```python
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.alert import Alert
from schemas.alert import AlertResponse

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    unacknowledged_only: bool = False,
    types: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Alert).order_by(Alert.sent_at.desc())
    if unacknowledged_only:
        query = query.where(Alert.acknowledged == False)
    if types:
        type_list = [t.strip() for t in types.split(",")]
        query = query.where(Alert.type.in_(type_list))
    result = await session.execute(query)
    return result.scalars().all()


@router.patch("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    await session.commit()
    await session.refresh(alert)
    return alert


@router.post("/alerts/acknowledge-all")
async def acknowledge_all_alerts(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Alert).where(Alert.acknowledged == False))
    alerts = result.scalars().all()
    count = len(alerts)
    for alert in alerts:
        alert.acknowledged = True
    await session.commit()
    return {"acknowledged": count}
```

- [ ] **Step 3: Wire entry scoring into `trade_logger.py`**

แก้ `api/services/trade_logger.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.trade import Trade
from schemas.trade_event import TradeEventSchema
from services.entry_context import fill_entry_context
from services.trade_advisor import compute_entry_score, compute_recovery_plan


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

    fields = [
        "direction", "order_type", "order_state", "pending_price",
        "open_time", "fill_time", "close_time", "open_price", "close_price",
        "volume", "tp", "sl", "profit", "swap", "commission",
    ]
    for field in fields:
        value = getattr(event, field)
        if value is not None:
            setattr(trade, field, value)

    if event.account_id is not None:
        trade.account_id = event.account_id

    if event.open_price is not None and event.close_price is None:
        await fill_entry_context(session, trade)
        await compute_entry_score(session, trade)
        await compute_recovery_plan(session, trade)

    await session.commit()
    await session.refresh(trade)
    return trade
```

- [ ] **Step 4: Wire zone check into `market_tick.py`**

แก้ `api/routers/market_tick.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.market_tick import MarketTickSchema
from services.paper_exit_manager import close_paper_trades_on_tick
from services.alert_manager import check_large_adverse_move
from services.trade_advisor import check_advisor_zones

router = APIRouter(prefix="/api", tags=["market-tick"])


@router.post("/market-tick")
async def receive_market_tick(
    tick: MarketTickSchema,
    session: AsyncSession = Depends(get_session),
):
    closed = await close_paper_trades_on_tick(session, tick)
    await check_large_adverse_move(session, tick)
    await check_advisor_zones(session, tick)
    return {
        "status": "processed",
        "timestamp": tick.timestamp.isoformat(),
        "closed_paper_trades": closed,
    }
```

- [ ] **Step 5: Register router in `api/main.py`**

เพิ่ม import และ `app.include_router(trade_advisor.router)` ต่อท้าย routers ที่มีอยู่:

```python
from routers import trade_advisor  # เพิ่มบรรทัดนี้

# เพิ่มในส่วน include_router:
app.include_router(trade_advisor.router)
```

- [ ] **Step 6: Run full test suite**

```bash
cd api && pytest ../tests/ -v
```

Expected: all existing tests pass + test_trade_advisor (14 tests) pass

- [ ] **Step 7: Commit**

```bash
git add api/routers/trade_advisor.py api/routers/alerts.py api/services/trade_logger.py api/routers/market_tick.py api/main.py
git commit -m "feat: wire trade advisor router, zone check hook, and alerts type filter"
```

---

## Task 6: Frontend

**Files:**
- Create: `frontend/src/components/TradeAdvisor.jsx`
- Create: `frontend/src/hooks/useTradeAlerts.js`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Create `TradeAdvisor.jsx`**

```jsx
// frontend/src/components/TradeAdvisor.jsx

const VERDICT_CONFIG = {
  good:      { label: '✅ Good entry',  cls: 'text-green-400' },
  caution:   { label: '⚠️ Caution',     cls: 'text-yellow-400' },
  high_risk: { label: '❌ High risk',   cls: 'text-red-400' },
}

function RecoveryMap({ plan }) {
  const { tp, add, cut, entry_price } = plan
  return (
    <div className="text-sm mt-3 space-y-1">
      <div className="text-green-400 font-semibold text-xs uppercase tracking-wide">▲ TP Targets</div>
      {[...tp].reverse().map(z => (
        <div key={z.label} className="flex justify-between px-2 text-green-300">
          <span className="w-8">{z.label}</span>
          <span>{z.price.toFixed(2)}</span>
          <span className="text-right w-20">+{Math.abs(z.pts).toFixed(0)} pts</span>
        </div>
      ))}
      <div className="border-t border-gray-600 my-1 text-center text-xs text-gray-500">
        entry {entry_price.toFixed(2)}
      </div>
      <div className="text-red-400 font-semibold text-xs uppercase tracking-wide">▼ Add Zones</div>
      {add.map(z => (
        <div key={z.label} className="flex justify-between px-2 text-red-300">
          <span className="w-8">{z.label}</span>
          <span>{z.price.toFixed(2)}</span>
          <span className="text-right w-20">{z.pts.toFixed(0)} pts</span>
        </div>
      ))}
      <div className="flex justify-between px-2 mt-2 text-orange-400 font-semibold">
        <span>✂️ Cut if {cut.label} breached</span>
        <span>{cut.price.toFixed(2)}</span>
        <span className="text-right w-20">{cut.pts.toFixed(0)} pts</span>
      </div>
    </div>
  )
}

function TradeCard({ trade }) {
  const { direction, open_price, entry_score, entry_verdict, recovery_plan } = trade
  const verdict = VERDICT_CONFIG[entry_verdict] || { label: 'Pending', cls: 'text-gray-400' }

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="flex justify-between items-center">
        <span className="font-bold">
          {direction?.toUpperCase()} @ {open_price?.toFixed(2)}
        </span>
        <span className={`font-bold ${verdict.cls}`}>
          {entry_score != null ? `Score: ${entry_score}  ` : ''}{verdict.label}
        </span>
      </div>
      {recovery_plan
        ? <RecoveryMap plan={recovery_plan} />
        : <div className="text-gray-500 text-sm mt-2">Waiting for fib data</div>
      }
    </div>
  )
}

export default function TradeAdvisor({ data }) {
  if (!data || data.length === 0) {
    return <div className="text-gray-400 text-sm p-4">No open trades</div>
  }
  return (
    <div className="space-y-3">
      {data.map(trade => <TradeCard key={trade.id} trade={trade} />)}
    </div>
  )
}
```

- [ ] **Step 2: Create `useTradeAlerts.js`**

```javascript
// frontend/src/hooks/useTradeAlerts.js
import { useEffect, useRef } from 'react'

const ALERT_TYPES = 'tp_zone_reached,add_zone_reached,cut_zone_reached'

export function useTradeAlerts() {
  const notifiedIds = useRef(new Set())

  useEffect(() => {
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      Notification.requestPermission()
    }

    const poll = async () => {
      try {
        const res = await fetch(`/api/alerts?unacknowledged_only=true&types=${ALERT_TYPES}`)
        if (!res.ok) return
        const alerts = await res.json()
        for (const alert of alerts) {
          if (notifiedIds.current.has(alert.id)) continue
          notifiedIds.current.add(alert.id)
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification('Trade Alert', { body: alert.message })
          }
        }
      } catch (_) {}
    }

    poll()
    const interval = setInterval(poll, 10000)
    return () => clearInterval(interval)
  }, [])
}
```

- [ ] **Step 3: Wire into `App.jsx`**

เพิ่ม import และ state/polling ใน `frontend/src/App.jsx`:

```jsx
// เพิ่ม imports:
import TradeAdvisor from './components/TradeAdvisor'
import { useTradeAlerts } from './hooks/useTradeAlerts'

// ภายใน App component เพิ่ม:
const [advisorData, setAdvisorData] = useState([])
useTradeAlerts()

// เพิ่มใน useEffect polling หรือ usePolling:
usePolling(() => fetch('/api/trade-advisor').then(r => r.json()).then(setAdvisorData))

// เพิ่ม <TradeAdvisor /> ใน JSX (หลัง FibPanel หรือ OpenTrades):
<section>
  <h2 className="text-lg font-semibold mb-2">Trade Advisor</h2>
  <TradeAdvisor data={advisorData} />
</section>
```

- [ ] **Step 4: Build frontend**

```bash
cd frontend && npm run build
```

Expected: build succeeds, no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TradeAdvisor.jsx frontend/src/hooks/useTradeAlerts.js frontend/src/App.jsx
git commit -m "feat: add TradeAdvisor component and useTradeAlerts hook"
```

---

## Task 7: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
cd api && pytest ../tests/ -v
```

Expected: all tests pass (no regressions)

- [ ] **Step 2: Build check**

```bash
cd frontend && npm run build
```

Expected: success

- [ ] **Step 3: Smoke test API**

```bash
curl -s http://localhost:8000/api/trade-advisor | python3 -m json.tool
curl -s "http://localhost:8000/api/alerts?types=tp_zone_reached,add_zone_reached,cut_zone_reached" | python3 -m json.tool
```

Expected: valid JSON arrays

- [ ] **Step 4: Update backlog**

แก้ `.agents/backlog.md` — เปลี่ยน status ของ `Trade Advisor` task เป็น `done` + เพิ่ม commit hash ใน remark

- [ ] **Step 5: Final commit**

```bash
git add .agents/backlog.md
git commit -m "chore: mark trade advisor task done"
```
