# Plan 2 — Mirror Paper Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-25-paper-trade-system-redesign.md` (FROZEN rev 1) — Component 1.

**Goal:** Replace the legacy `_average_offset`-based mirror trader with a rule-driven mirror that exits at daily pivot R/S + momentum weakening, momentum reversal, or hard stop ฿2,500. Outcome powers `early_exit_cost` (mirror.profit − real.profit).

**Architecture:**
- `mirror_trader.create_mirror_trade()` still spawns one mirror per real entry but no longer pre-computes `tp` / `sl` from history — exits are evaluated tick-by-tick.
- A new `mirror_exit_manager.evaluate_mirror_exits()` runs in the existing `/api/market-tick` flow (replacing the relevant portion of `paper_exit_manager.close_paper_trades_on_tick`). It computes TP at the nearest daily pivot R1/R2 (buy) or S1/S2 (sell) gated by a momentum weakening check, falls back to a momentum-flip exit, and finally a hard-stop at ฿2,500 floating loss.
- The existing closing-by-tp/sl logic for **mirror** trades is removed because mirror trades no longer carry pre-set TP/SL — but is preserved for `independent` paper trades by Plan 3.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, pandas-ta, pytest-asyncio + httpx, existing indicator REGISTRY (`pivot_std`, `rsi_14`).

---

## File Structure

| Path | Action | Purpose |
|------|--------|---------|
| `api/services/mirror_trader.py` | rewrite | Spawn mirror only — no pre-set TP/SL |
| `api/services/mirror_exit_manager.py` | create | Tick-driven TP/momentum/hard-stop logic |
| `api/services/paper_exit_manager.py` | modify | Delegate mirror trades to new manager |
| `api/routers/market_tick.py` | modify | Call `evaluate_mirror_exits()` |
| `tests/test_mirror_trader.py` | rewrite | Cover new spawn behavior |
| `tests/test_mirror_exit_manager.py` | create | Cover tp_pivot / momentum_flip / hard_stop |

---

## Task 1: Strip TP/SL pre-computation from mirror_trader

**Files:**
- Modify: `api/services/mirror_trader.py`
- Rewrite: `tests/test_mirror_trader.py`

- [ ] **Step 1: Replace tests with the new behavior contract**

```python
# tests/test_mirror_trader.py
import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select

from models.trade import Trade, Direction, OrderState, PaperMode
from services.mirror_trader import create_mirror_trade
from schemas.trade_event import TradeEventSchema


def _entry_event(ticket: int = 1001, direction: str = "buy") -> TradeEventSchema:
    return TradeEventSchema(
        transaction_type="DEAL_ADD",
        ticket=ticket,
        symbol="XAUUSD",
        direction=direction,
        order_type="market",
        order_state="filled",
        open_price=Decimal("1950.00"),
        volume=Decimal("0.10"),
        open_time=datetime.now(timezone.utc),
    )


def _exit_event(ticket: int = 1001) -> TradeEventSchema:
    return TradeEventSchema(
        transaction_type="DEAL_ADD",
        ticket=ticket,
        symbol="XAUUSD",
        direction="buy",
        order_type="market",
        order_state="filled",
        close_price=Decimal("1960.00"),
        close_time=datetime.now(timezone.utc),
        profit=Decimal("100.00"),
    )


@pytest.mark.asyncio
async def test_creates_mirror_trade_on_entry(db_session):
    await create_mirror_trade(db_session, _entry_event())
    await db_session.commit()

    rows = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalars().all()
    assert len(rows) == 1
    paper = rows[0]
    assert paper.paper_mode == PaperMode.mirror
    assert paper.ticket == 1001
    assert float(paper.open_price) == pytest.approx(1950.00)


@pytest.mark.asyncio
async def test_mirror_does_not_set_tp_sl(db_session):
    """Spec: TP/SL are evaluated per tick; nothing pre-computed at spawn."""
    await create_mirror_trade(db_session, _entry_event())
    await db_session.commit()
    paper = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalar_one()
    assert paper.tp is None
    assert paper.sl is None
    assert paper.paper_exit_strategy == "rule_driven"


@pytest.mark.asyncio
async def test_no_mirror_on_exit_event(db_session):
    await create_mirror_trade(db_session, _exit_event())
    await db_session.commit()
    rows = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_no_duplicate_mirror(db_session):
    await create_mirror_trade(db_session, _entry_event())
    await db_session.commit()
    await create_mirror_trade(db_session, _entry_event())
    await db_session.commit()
    rows = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_mirror_copies_account_id_and_direction(db_session):
    event = _entry_event(direction="sell")
    event.account_id = 335297575
    await create_mirror_trade(db_session, event)
    await db_session.commit()
    paper = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalar_one()
    assert paper.account_id == 335297575
    assert paper.direction == Direction.sell
```

- [ ] **Step 2: Run tests to verify the old behavior fails**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_mirror_trader.py -v"
```

Expected: `test_mirror_does_not_set_tp_sl` FAILS (legacy code sets tp/sl).

- [ ] **Step 3: Rewrite `mirror_trader.py`**

```python
# api/services/mirror_trader.py
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade import OrderState, PaperMode, Trade
from schemas.trade_event import TradeEventSchema


MIRROR_EXIT_STRATEGY = "rule_driven"


async def create_mirror_trade(session: AsyncSession, event: TradeEventSchema) -> None:
    if event.order_state != OrderState.filled:
        return
    if event.close_price is not None:
        return
    if event.open_price is None:
        return

    existing = await session.execute(
        select(Trade).where(
            Trade.ticket == event.ticket,
            Trade.symbol == event.symbol,
            Trade.is_paper == True,
            Trade.paper_mode == PaperMode.mirror,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    session.add(Trade(
        ticket=event.ticket,
        symbol=event.symbol,
        direction=event.direction,
        order_type=event.order_type,
        order_state=OrderState.filled,
        open_price=event.open_price,
        volume=event.volume,
        open_time=event.open_time or datetime.now(timezone.utc),
        tp=None,
        sl=None,
        account_id=event.account_id,
        is_paper=True,
        paper_mode=PaperMode.mirror,
        paper_exit_strategy=MIRROR_EXIT_STRATEGY,
    ))
```

- [ ] **Step 4: Run tests to verify they pass**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_mirror_trader.py -v"
```

Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/mirror_trader.py tests/test_mirror_trader.py
git commit -m "refactor(mirror): drop pre-set TP/SL — rule-driven exits handled per tick"
```

---

## Task 2: Mirror exit manager — pivot TP / momentum flip / hard stop

**Files:**
- Create: `api/services/mirror_exit_manager.py`
- Test: `tests/test_mirror_exit_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_mirror_exit_manager.py
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, PaperMode, Trade
from schemas.market_tick import MarketTickSchema
from services.mirror_exit_manager import (
    HARD_STOP_LOSS_THB,
    evaluate_mirror_exits,
)


def _bar(time, open_, high, low, close, volume=100):
    return PriceBar(
        symbol="XAUUSD",
        timeframe=Timeframe.D,
        time=time,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
    )


async def _seed_daily(db_session, anchor):
    """Seed two daily bars + 250 H1 bars so pivot + RSI can be computed."""
    db_session.add(_bar(anchor - timedelta(days=2), 1900, 1920, 1880, 1910))
    db_session.add(_bar(anchor - timedelta(days=1), 1910, 1955, 1905, 1950))
    h1_anchor = anchor - timedelta(hours=250)
    for i in range(250):
        db_session.add(PriceBar(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            time=h1_anchor + timedelta(hours=i),
            open=Decimal("1950"),
            high=Decimal("1955"),
            low=Decimal("1948"),
            close=Decimal("1950") + Decimal("0.5") * (i % 5),
            volume=Decimal("100"),
        ))
    await db_session.commit()


def _mirror(direction, open_price, volume="0.10"):
    return Trade(
        id=uuid.uuid4(),
        ticket=int(datetime.now().timestamp()) % 1_000_000,
        symbol="XAUUSD",
        direction=Direction[direction],
        order_type=None,
        order_state=OrderState.filled,
        open_time=datetime.now(timezone.utc),
        open_price=Decimal(str(open_price)),
        volume=Decimal(volume),
        is_paper=True,
        paper_mode=PaperMode.mirror,
        paper_exit_strategy="rule_driven",
    )


@pytest.mark.asyncio
async def test_tp_pivot_buy_exits_at_r1(db_session, monkeypatch):
    """Buy mirror: tick.bid hits R1, momentum check passes → exit tp_pivot."""
    monkeypatch.setattr(
        "services.mirror_exit_manager._momentum_weakening", lambda *a, **k: True
    )
    now = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    await _seed_daily(db_session, now)
    trade = _mirror("buy", 1920.00)
    db_session.add(trade)
    await db_session.commit()

    # Pivot from prev day (H+L+C)/3 = (1955+1905+1950)/3 = 1936.667
    # R1 = 2*PP - L = 2*1936.667 - 1905 = 1968.333
    tick = MarketTickSchema(
        symbol="XAUUSD",
        bid=Decimal("1968.50"),
        ask=Decimal("1968.55"),
        timestamp=now,
        account_id=1,
    )
    closed = await evaluate_mirror_exits(db_session, tick)
    assert closed == 1
    await db_session.refresh(trade)
    assert trade.paper_exit_reason == "tp_pivot"
    assert trade.close_time == now


@pytest.mark.asyncio
async def test_tp_pivot_skipped_when_momentum_strong(db_session, monkeypatch):
    monkeypatch.setattr(
        "services.mirror_exit_manager._momentum_weakening", lambda *a, **k: False
    )
    now = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    await _seed_daily(db_session, now)
    trade = _mirror("buy", 1920.00)
    db_session.add(trade)
    await db_session.commit()

    tick = MarketTickSchema(
        symbol="XAUUSD",
        bid=Decimal("1968.50"),
        ask=Decimal("1968.55"),
        timestamp=now,
        account_id=1,
    )
    closed = await evaluate_mirror_exits(db_session, tick)
    assert closed == 0


@pytest.mark.asyncio
async def test_momentum_flip_triggers_exit(db_session, monkeypatch):
    monkeypatch.setattr(
        "services.mirror_exit_manager._momentum_weakening", lambda *a, **k: False
    )
    monkeypatch.setattr(
        "services.mirror_exit_manager._momentum_flipped", lambda *a, **k: True
    )
    now = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    await _seed_daily(db_session, now)
    trade = _mirror("buy", 1920.00)
    db_session.add(trade)
    await db_session.commit()

    tick = MarketTickSchema(
        symbol="XAUUSD",
        bid=Decimal("1932.00"),
        ask=Decimal("1932.10"),
        timestamp=now,
        account_id=1,
    )
    closed = await evaluate_mirror_exits(db_session, tick)
    assert closed == 1
    await db_session.refresh(trade)
    assert trade.paper_exit_reason == "momentum_flip"


@pytest.mark.asyncio
async def test_hard_stop_at_floating_loss_2500(db_session, monkeypatch):
    monkeypatch.setattr(
        "services.mirror_exit_manager._momentum_weakening", lambda *a, **k: False
    )
    monkeypatch.setattr(
        "services.mirror_exit_manager._momentum_flipped", lambda *a, **k: False
    )
    now = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    await _seed_daily(db_session, now)
    # 0.10 lot * 100 contract * (1920-1670) = 2500 THB floating
    trade = _mirror("buy", 1920.00)
    db_session.add(trade)
    await db_session.commit()

    tick = MarketTickSchema(
        symbol="XAUUSD",
        bid=Decimal("1670.00"),
        ask=Decimal("1670.10"),
        timestamp=now,
        account_id=1,
    )
    closed = await evaluate_mirror_exits(db_session, tick)
    assert closed == 1
    await db_session.refresh(trade)
    assert trade.paper_exit_reason == "hard_stop"
    assert trade.profit is not None
    assert trade.profit <= Decimal(f"-{HARD_STOP_LOSS_THB}")


@pytest.mark.asyncio
async def test_no_exit_when_below_thresholds(db_session, monkeypatch):
    monkeypatch.setattr(
        "services.mirror_exit_manager._momentum_weakening", lambda *a, **k: False
    )
    monkeypatch.setattr(
        "services.mirror_exit_manager._momentum_flipped", lambda *a, **k: False
    )
    now = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    await _seed_daily(db_session, now)
    trade = _mirror("buy", 1920.00)
    db_session.add(trade)
    await db_session.commit()

    tick = MarketTickSchema(
        symbol="XAUUSD",
        bid=Decimal("1922.00"),
        ask=Decimal("1922.10"),
        timestamp=now,
        account_id=1,
    )
    closed = await evaluate_mirror_exits(db_session, tick)
    assert closed == 0
```

- [ ] **Step 2: Run to confirm they fail**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_mirror_exit_manager.py -v"
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `mirror_exit_manager.py`**

```python
# api/services/mirror_exit_manager.py
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, PaperMode, Trade
from schemas.market_tick import MarketTickSchema
from services.indicators.common import _to_frame
from services.indicators.sr.pivot_std import compute as pivot_compute  # noqa: F401  (registers spec)
from services.indicators.common import SR_SPECS
from services.indicators.common import MOMENTUM_SPECS

HARD_STOP_LOSS_THB = Decimal(os.getenv("MIRROR_HARD_STOP_THB", "2500"))
XAUUSD_CONTRACT_SIZE = Decimal("100")
RSI_WEAKEN_BUY_THRESHOLD = Decimal("60")    # buy: RSI < 60 = weakening
RSI_WEAKEN_SELL_THRESHOLD = Decimal("40")   # sell: RSI > 40 = weakening
DAILY_LOOKBACK = 30
H1_LOOKBACK = 250


async def evaluate_mirror_exits(session: AsyncSession, tick: MarketTickSchema) -> int:
    rows = await session.execute(
        select(Trade).where(
            Trade.symbol == tick.symbol,
            Trade.is_paper.is_(True),
            Trade.paper_mode == PaperMode.mirror,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
        )
    )
    open_mirrors = list(rows.scalars().all())
    if not open_mirrors:
        return 0

    daily_bars = await _fetch_bars(session, tick.symbol, Timeframe.D, DAILY_LOOKBACK)
    h1_bars = await _fetch_bars(session, tick.symbol, Timeframe.H1, H1_LOOKBACK)

    closed = 0
    for trade in open_mirrors:
        exit_price, reason = _exit_decision(trade, tick, daily_bars, h1_bars)
        if exit_price is None:
            continue
        trade.close_price = exit_price
        trade.close_time = tick.timestamp
        trade.profit = _floating_pnl(trade, exit_price)
        trade.paper_exit_reason = reason
        closed += 1

    if closed:
        await session.commit()
    return closed


def _exit_decision(
    trade: Trade,
    tick: MarketTickSchema,
    daily_bars: list[PriceBar],
    h1_bars: list[PriceBar],
) -> tuple[Optional[Decimal], Optional[str]]:
    if trade.direction is None or trade.open_price is None:
        return None, None

    pivot_levels = _pivot_levels(daily_bars)
    tp_level = _tp_level(trade.direction, tick, pivot_levels)
    if tp_level is not None and _momentum_weakening(trade.direction, h1_bars):
        return tp_level, "tp_pivot"

    if _momentum_flipped(trade.direction, h1_bars):
        cur = tick.bid if trade.direction == Direction.buy else tick.ask
        return cur, "momentum_flip"

    floating = _floating_pnl(trade, tick.bid if trade.direction == Direction.buy else tick.ask)
    if floating is not None and floating <= -HARD_STOP_LOSS_THB:
        cur = tick.bid if trade.direction == Direction.buy else tick.ask
        return cur, "hard_stop"

    return None, None


def _pivot_levels(daily_bars: list[PriceBar]) -> dict[str, Decimal]:
    spec = SR_SPECS.get("pivot_std")
    if spec is None or not daily_bars:
        return {}
    _, _, metadata = spec.compute(_to_frame(daily_bars))
    return {
        k: Decimal(str(v))
        for k, v in metadata.items()
        if k in ("r1", "r2", "s1", "s2") and v is not None
    }


def _tp_level(direction: Direction, tick: MarketTickSchema, levels: dict[str, Decimal]) -> Optional[Decimal]:
    if direction == Direction.buy:
        for key in ("r1", "r2"):
            level = levels.get(key)
            if level is not None and tick.bid >= level:
                return level
        return None
    for key in ("s1", "s2"):
        level = levels.get(key)
        if level is not None and tick.ask <= level:
            return level
    return None


def _momentum_weakening(direction: Direction, h1_bars: list[PriceBar]) -> bool:
    rsi = _rsi(h1_bars)
    if rsi is None:
        return False
    if direction == Direction.buy:
        return rsi < RSI_WEAKEN_BUY_THRESHOLD
    return rsi > RSI_WEAKEN_SELL_THRESHOLD


def _momentum_flipped(direction: Direction, h1_bars: list[PriceBar]) -> bool:
    spec = MOMENTUM_SPECS.get("rsi_14")
    if spec is None or not h1_bars:
        return False
    _, dir_label, _ = spec.compute(_to_frame(h1_bars))
    if direction == Direction.buy:
        return dir_label == "bearish"
    return dir_label == "bullish"


def _rsi(h1_bars: list[PriceBar]) -> Optional[Decimal]:
    spec = MOMENTUM_SPECS.get("rsi_14")
    if spec is None or not h1_bars:
        return None
    value, _, _ = spec.compute(_to_frame(h1_bars))
    return Decimal(str(value)) if value is not None else None


async def _fetch_bars(
    session: AsyncSession, symbol: str, tf: Timeframe, limit: int,
) -> list[PriceBar]:
    res = await session.execute(
        select(PriceBar)
        .where(PriceBar.symbol == symbol, PriceBar.timeframe == tf)
        .order_by(PriceBar.time.desc())
        .limit(limit)
    )
    return list(reversed(res.scalars().all()))


def _floating_pnl(trade: Trade, mark_price: Decimal) -> Optional[Decimal]:
    if trade.open_price is None or trade.volume is None or trade.direction is None:
        return None
    if trade.direction == Direction.buy:
        raw = (mark_price - trade.open_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    else:
        raw = (trade.open_price - mark_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

- [ ] **Step 4: Run mirror-exit tests to verify pass**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_mirror_exit_manager.py -v"
```

Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/mirror_exit_manager.py tests/test_mirror_exit_manager.py
git commit -m "feat(mirror): tick-driven exits — tp_pivot, momentum_flip, hard_stop"
```

---

## Task 3: Wire mirror exits into market-tick + drop legacy mirror branch in paper_exit_manager

**Files:**
- Modify: `api/routers/market_tick.py`
- Modify: `api/services/paper_exit_manager.py`
- Test: `tests/test_paper_exit_manager.py`

- [ ] **Step 1: Read current paper_exit_manager test to see what coverage to keep**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_exit_manager.py -v"
```

Note which tests cover `mirror` mode vs `independent` mode — we keep independent unchanged but mirror moves out.

- [ ] **Step 2: Update `paper_exit_manager.py` to skip mirror trades**

Replace the `paper_mode == PaperMode.mirror` filter with `paper_mode == PaperMode.independent`:

```python
# api/services/paper_exit_manager.py — query change
result = await session.execute(
    select(Trade).where(
        Trade.symbol == tick.symbol,
        Trade.is_paper == True,
        Trade.paper_mode == PaperMode.independent,
        Trade.order_state == OrderState.filled,
        Trade.close_time.is_(None),
        Trade.close_price.is_(None),
    )
)
```

This keeps the existing TP/SL touch logic available for `independent` (Plan 3) trades and removes responsibility for `mirror` trades from this manager.

- [ ] **Step 3: Modify `market_tick.py` to call both managers**

```python
# api/routers/market_tick.py
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.market_tick import MarketTickSchema
from services.alert_manager import check_large_adverse_move
from services.mirror_exit_manager import evaluate_mirror_exits
from services.paper_exit_manager import close_paper_trades_on_tick
from services.paper_trader import run_paper_trader
from services.trade_advisor import check_advisor_zones

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["market-tick"])


@router.post("/market-tick")
async def receive_market_tick(
    tick: MarketTickSchema,
    session: AsyncSession = Depends(get_session),
):
    closed_independent = await close_paper_trades_on_tick(session, tick)
    closed_mirror = await evaluate_mirror_exits(session, tick)
    await check_large_adverse_move(session, tick)
    await check_advisor_zones(session, tick)

    try:
        await run_paper_trader(session, tick)
    except Exception:
        logger.exception("paper trader run failed for tick %s", tick.timestamp)

    return {
        "status": "processed",
        "timestamp": tick.timestamp.isoformat(),
        "closed_paper_trades": closed_independent + closed_mirror,
        "closed_mirror": closed_mirror,
        "closed_independent": closed_independent,
    }
```

- [ ] **Step 4: Update existing paper_exit_manager test fixtures**

If a test in `tests/test_paper_exit_manager.py` creates `paper_mode=PaperMode.mirror`, update those rows to `paper_mode=PaperMode.independent` so they continue to assert the same TP/SL logic now scoped to independent trades. Use `Edit` per occurrence to keep the diff minimal.

- [ ] **Step 5: Run regression**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/test_paper_exit_manager.py tests/test_mirror_exit_manager.py tests/test_market_tick.py -v"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/routers/market_tick.py api/services/paper_exit_manager.py tests/test_paper_exit_manager.py
git commit -m "refactor: route mirror trades to mirror_exit_manager; paper_exit_manager handles independent only"
```

---

## Task 4: Full regression + smoke

- [ ] **Step 1: Run the full backend suite**

```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api \
  sh -c "cd /app && pytest tests/ -v --tb=short"
```

Expected: previous count + new mirror tests, all green.

- [ ] **Step 2: Smoke**

```
docker compose up -d
# Open a real trade in MT5 → confirm mirror appears in DB:
docker compose exec db psql -U tradesignal -d tradesignal -c \
  "SELECT ticket, paper_mode, tp, sl, paper_exit_strategy FROM trades WHERE is_paper=true ORDER BY open_time DESC LIMIT 3;"
# Expected: paper_mode='mirror', tp/sl NULL, paper_exit_strategy='rule_driven'
```

- [ ] **Step 3: Update handoff**

```
Plan 2 done.
- mirror_trader spawns rule-driven mirrors (no pre-set TP/SL)
- mirror_exit_manager handles tp_pivot / momentum_flip / hard_stop
- /api/market-tick now closes mirror + independent paper trades separately
Next: Plan 3 (Auto Discovery + Score Sizing)
```
