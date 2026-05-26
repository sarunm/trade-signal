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
