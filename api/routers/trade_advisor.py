import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.account_snapshot import AccountSnapshot
from models.price_bar import PriceBar
from models.trade import Direction, OrderState, Trade
from services.trade_advisor import compute_recovery_plan

router = APIRouter(prefix="/api", tags=["trade-advisor"])

CONTRACT_SIZE_XAUUSD = Decimal("100")  # 1 lot = 100 oz

_BKK = timezone(timedelta(hours=7))


def _today_in_bkk() -> date:
    return datetime.now(_BKK).date()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _compute_pnl_summary(
    session: AsyncSession,
    snapshot: Optional[AccountSnapshot],
) -> Optional[dict]:
    today = _today_in_bkk()
    week_start = today - timedelta(days=6)
    month_start = today.replace(day=1)

    stmt = select(Trade).where(
        Trade.is_paper == False,
        Trade.order_state == OrderState.filled,
        Trade.close_time.isnot(None),
        Trade.profit.isnot(None),
    )
    if snapshot and snapshot.account_id is not None:
        stmt = stmt.where(Trade.account_id == snapshot.account_id)
    res = await session.execute(stmt)
    trades = res.scalars().all()

    today_b = Decimal("0.00")
    week_b = Decimal("0.00")
    month_b = Decimal("0.00")
    for t in trades:
        d = _as_utc(t.close_time).astimezone(_BKK).date()
        if d == today:
            today_b += t.profit
        if d >= week_start:
            week_b += t.profit
        if d >= month_start:
            month_b += t.profit

    base = snapshot.balance if snapshot else None

    def _row(b):
        return {
            "baht": float(b.quantize(Decimal("0.01"))),
            "pct": (float(((b / base) * Decimal("100")).quantize(Decimal("0.01")))
                    if base and base != 0 else None),
        }

    return {"today": _row(today_b), "week": _row(week_b), "month": _row(month_b)}


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
    backfilled = False
    for t in trades:
        if t.recovery_plan is None and t.open_price is not None and t.direction is not None:
            await compute_recovery_plan(session, t)
            if t.recovery_plan is not None:
                backfilled = True
    if backfilled:
        await session.flush()
    pending_result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.pending,
            Trade.pending_price.isnot(None),
            Trade.close_time.is_(None),
        )
    )
    pending = pending_result.scalars().all()
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
        .where(PriceBar.symbol == "GOLD#", PriceBar.timeframe == "M5")
        .order_by(PriceBar.time.desc())
        .limit(1)
    )
    latest_close = price_result.scalar_one_or_none()
    basket = _aggregate_basket(trades, snapshot, latest_close)
    basket["pnl_summary"] = await _compute_pnl_summary(session, snapshot)
    basket_with_pending = None
    if pending:
        projected = list(trades) + [_pending_as_filled(p) for p in pending]
        basket_with_pending = _aggregate_basket(projected, snapshot, latest_close)
        basket_with_pending["pnl_summary"] = None
    return {
        "per_trade": per_trade,
        "basket": basket,
        "basket_with_pending": basket_with_pending,
    }


def _pending_as_filled(p: Trade) -> Trade:
    proxy = Trade(
        id=p.id,
        ticket=p.ticket,
        symbol=p.symbol,
        direction=p.direction,
        order_type=p.order_type,
        order_state=OrderState.filled,
        is_paper=p.is_paper,
        open_time=p.open_time,
        open_price=p.pending_price,
        volume=p.volume,
        recovery_plan=p.recovery_plan,
    )
    return proxy


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
    abs_weight = Decimal("0")
    abs_notional = Decimal("0")
    for t in open_trades:
        s = Decimal("1") if t.direction == Direction.buy else Decimal("-1")
        notional += t.open_price * t.volume * s
        weight += t.volume * s
        abs_notional += t.open_price * t.volume
        abs_weight += t.volume
    basket_be = (notional / weight).quantize(Decimal("0.01")) if weight != 0 else None
    mean_entry = (abs_notional / abs_weight).quantize(Decimal("0.01")) if abs_weight != 0 else None

    current = latest_close.quantize(Decimal("0.01")) if latest_close is not None else None
    net_float = None
    if current is not None and basket_be is not None:
        net_float = ((current - basket_be) * sign * abs(net) * CONTRACT_SIZE_XAUUSD).quantize(Decimal("0.01"))

    tp_targets, add_zones, cut = _select_basket_zones(open_trades, direction, abs(net), current)

    return {
        "direction": direction,
        "lot_total": float(abs(net)),
        "order_count": len(open_trades),
        "mean_entry": float(mean_entry) if mean_entry is not None else None,
        "avg_entry": float(mean_entry) if mean_entry is not None else None,
        "current": float(current) if current is not None else None,
        "basket_be": float(basket_be) if basket_be is not None else None,
        "net_float": float(net_float) if net_float is not None else None,
        "ruin": _compute_ruin(direction, abs(net), basket_be, current, snapshot)
                 if snapshot and basket_be and current else None,
        "tp_targets": tp_targets,
        "add_zones": add_zones,
        "cut": cut,
        "pnl_summary": None,
    }


def _select_basket_zones(
    open_trades: list[Trade],
    direction: str,
    abs_lot: Decimal,
    current: Optional[Decimal] = None,
) -> tuple[list, list, Optional[dict]]:
    candidates = [t for t in open_trades if t.recovery_plan and t.direction]
    if not candidates:
        return [], [], None
    if direction == "buy":
        deepest = min(candidates, key=lambda t: t.open_price)
    else:
        deepest = max(candidates, key=lambda t: t.open_price)
    plan = deepest.recovery_plan or {}
    contract = CONTRACT_SIZE_XAUUSD
    reference = current if current is not None else Decimal(str(plan.get("entry_price") or deepest.open_price))
    entry = Decimal(str(reference))
    sign = Decimal("1") if direction == "buy" else Decimal("-1")

    def _baht(price):
        return float(((Decimal(str(price)) - entry) * sign * abs_lot * contract).quantize(Decimal("0.01")))

    tp_raw = list(plan.get("tp") or [])
    tp_targets = [{"label": z["label"], "price": z["price"], "baht": _baht(z["price"])}
                  for z in reversed(tp_raw)]
    add_zones = [{"label": z["label"], "price": z["price"], "baht": _baht(z["price"])}
                 for z in (plan.get("add") or [])]
    cut_raw = plan.get("cut")
    cut = {"label": cut_raw["label"], "price": cut_raw["price"], "baht": _baht(cut_raw["price"])} if cut_raw else None
    return tp_targets, add_zones, cut


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

    if pct_buffer >= Decimal("50"):
        tier = "safe"
    elif pct_buffer >= Decimal("20"):
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
        "mean_entry": None,
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
