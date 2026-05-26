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
