from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class LiveAccountSnapshot:
    equity: Decimal
    floating_pl: Decimal


_cache: dict[int, LiveAccountSnapshot] = {}


def push_live_account(account_id: int, equity: Decimal, floating_pl: Decimal) -> None:
    if account_id is None:
        return
    _cache[account_id] = LiveAccountSnapshot(equity=equity, floating_pl=floating_pl)


def get_live_account(account_id: Optional[int]) -> Optional[LiveAccountSnapshot]:
    if account_id is None:
        return None
    return _cache.get(account_id)


def clear_live_account() -> None:
    _cache.clear()
