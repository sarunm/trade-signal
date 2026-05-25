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
    assert trade.close_time.replace(tzinfo=timezone.utc) == now


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
