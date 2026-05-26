import math
from decimal import Decimal
from typing import Sequence


WILSON_Z_95 = 1.96


def wilson_lower(p: float, n: int, z: float = WILSON_Z_95) -> float:
    if n <= 0:
        return 0.0
    p = max(0.0, min(1.0, p))
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    lower = (centre - margin) / denom
    return max(0.0, min(1.0, lower))


def net_ev(profits: Sequence[Decimal], total_cost: Decimal) -> Decimal:
    if not profits:
        return Decimal("0.00")
    gross = sum(profits, Decimal("0"))
    net = gross - total_cost
    return (net / Decimal(len(profits))).quantize(Decimal("0.01"))


def profit_factor(profits: Sequence[Decimal]) -> Decimal:
    wins = sum((p for p in profits if p > 0), Decimal("0"))
    losses = sum((p for p in profits if p < 0), Decimal("0"))
    if losses == 0:
        return Decimal("9999.0000") if wins > 0 else Decimal("0.0000")
    return (wins / abs(losses)).quantize(Decimal("0.0001"))
