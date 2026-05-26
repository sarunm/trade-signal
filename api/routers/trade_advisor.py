import os
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.account_snapshot import AccountSnapshot
from models.price_bar import PriceBar
from models.trade import Direction, OrderState, Trade

router = APIRouter(prefix="/api", tags=["trade-advisor"])

CONTRACT_SIZE_XAUUSD = Decimal("100")  # 1 lot = 100 oz


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
    price_result = await session.execute(
        select(PriceBar.close)
        .where(PriceBar.symbol == "XAUUSD", PriceBar.timeframe == "M5")
        .order_by(PriceBar.time.desc())
        .limit(1)
    )
    latest_close = price_result.scalar_one_or_none()
    basket = _aggregate_basket(trades, snapshot, latest_close)
    return {"per_trade": per_trade, "basket": basket}


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
        "ruin": _compute_ruin(direction, abs(net), basket_be, current, snapshot)
                 if snapshot and basket_be and current else None,
        "tp_targets": [],
        "add_zones": [],
        "cut": None,
        "pnl_summary": None,
    }


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
    price_delta = delta_eq / (contract * abs_lot)
    ruin_price = (basket_be + sign * price_delta).quantize(Decimal("0.01"))

    pts = (ruin_price - current).quantize(Decimal("0.01"))
    baht_buffer = ((ruin_price - current) * sign * abs_lot * contract).quantize(Decimal("0.01"))
    pct_buffer = ((snapshot.equity - threshold_equity) / snapshot.equity * Decimal("100")).quantize(
        Decimal("0.1")
    ) if snapshot.equity != 0 else Decimal("0")

    if pct_buffer >= Decimal("90"):
        tier = "safe"
    elif pct_buffer >= Decimal("66"):
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
