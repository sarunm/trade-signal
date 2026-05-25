import os
from datetime import datetime
from decimal import Decimal
from typing import Optional

from models.trade import Direction, Trade


RECOVERY_COOLDOWN_SEC = int(os.getenv("BASKET_RECOVERY_COOLDOWN_SEC", "1800"))
RECOVERY_FLOATING_LOSS_PCT = float(os.getenv("BASKET_RECOVERY_LOSS_PCT", "0.30"))
XAUUSD_CONTRACT_SIZE = Decimal("100")
RECOVERY_MODES = {"basket_5k", "basket_50k"}


def _floating_pnl(trade: Trade, current_bid: Decimal, current_ask: Decimal) -> Decimal:
    if trade.open_price is None or trade.volume is None or trade.direction is None:
        return Decimal("0")
    if trade.direction == Direction.buy:
        return (current_bid - trade.open_price) * trade.volume * XAUUSD_CONTRACT_SIZE
    return (trade.open_price - current_ask) * trade.volume * XAUUSD_CONTRACT_SIZE


def should_open_recovery(
    *,
    existing: Optional[Trade],
    current_bid: Decimal,
    virtual_balance: Decimal,
    now: datetime,
    mode: str,
    current_ask: Optional[Decimal] = None,
) -> bool:
    if mode not in RECOVERY_MODES:
        return False
    if existing is None or existing.open_time is None:
        return False
    elapsed = (now - existing.open_time).total_seconds()
    if elapsed < RECOVERY_COOLDOWN_SEC:
        return False
    floating = _floating_pnl(existing, current_bid, current_ask or current_bid)
    if floating >= 0:
        return False
    loss_threshold = virtual_balance * Decimal(str(RECOVERY_FLOATING_LOSS_PCT))
    return abs(floating) >= loss_threshold
