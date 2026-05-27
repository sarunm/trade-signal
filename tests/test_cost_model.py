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
            id=uuid.uuid4(), ticket=i, symbol="GOLD#",
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
