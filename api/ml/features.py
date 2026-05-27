from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade import Trade
from models.indicator_signal import TradeIndicatorSignal

FIB_LEVELS = ("R1", "R2", "R3", "S1", "S2", "S3", "PP")


async def extract_trade_features(session: AsyncSession, trade: Trade) -> dict:
    sigs = (await session.execute(
        select(TradeIndicatorSignal).where(TradeIndicatorSignal.trade_id == trade.id)
    )).scalars().all()

    matched = [s for s in sigs if s.matched]
    rsi = next(
        (s.value for s in sigs if s.indicator_slug == "rsi" and s.value is not None),
        0.0,
    )
    ema_align = next(
        (1.0 if s.direction == "bull" else -1.0 if s.direction == "bear" else 0.0
         for s in sigs if s.indicator_slug == "ema_cross"),
        0.0,
    )
    direction_value = trade.direction.value if trade.direction else "buy"
    if direction_value == "sell":
        ema_align = -ema_align

    feats = {
        "entry_score": int(trade.entry_score or 0),
        "direction_buy": 1 if direction_value == "buy" else 0,
        "hour_of_day_utc": trade.open_time.hour if trade.open_time else 0,
        "day_of_week": trade.open_time.weekday() if trade.open_time else 0,
        "signal_match_count": len(matched),
        "signal_density": len(matched) / len(sigs) if sigs else 0.0,
        "rsi_value": float(rsi),
        "ema_alignment": ema_align,
    }
    fib = trade.near_fib_level or "none"
    for level in FIB_LEVELS:
        feats[f"near_fib_{level}"] = 1 if fib == level else 0
    feats["near_fib_none"] = 1 if fib == "none" else 0
    return feats


def feature_order() -> list[str]:
    base = [
        "entry_score", "direction_buy", "hour_of_day_utc", "day_of_week",
        "signal_match_count", "signal_density", "rsi_value", "ema_alignment",
    ]
    base += [f"near_fib_{lvl}" for lvl in FIB_LEVELS]
    base.append("near_fib_none")
    return base


def to_vector(feats: dict) -> list[float]:
    return [float(feats.get(k, 0)) for k in feature_order()]
