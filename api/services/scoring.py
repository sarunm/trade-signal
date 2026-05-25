from dataclasses import dataclass
from decimal import Decimal


LOT_TIER_FLOOR = Decimal("0.01")
LOT_TIER_LOW = Decimal("0.03")
LOT_TIER_MID = Decimal("0.05")
LOT_TIER_HIGH = Decimal("0.10")

WEIGHT_INDICATOR_COUNT = 0.25
WEIGHT_WINRATE = 0.40
WEIGHT_STRENGTH = 0.20
WEIGHT_CONFLUENCE = 0.15


@dataclass
class SignalQualityInputs:
    matched_count: int
    total_count: int
    avg_indicator_strength: float
    rule_winrate: float


def _safe_div(num: float, denom: float) -> float:
    return num / denom if denom else 0.0


def compute_score(inputs: SignalQualityInputs) -> float:
    confluence = _safe_div(inputs.matched_count, inputs.total_count)
    count_norm = min(inputs.matched_count / 5.0, 1.0)
    strength = max(0.0, min(inputs.avg_indicator_strength, 1.0))
    winrate = max(0.0, min(inputs.rule_winrate, 1.0))
    score = (
        WEIGHT_INDICATOR_COUNT * count_norm
        + WEIGHT_WINRATE * winrate
        + WEIGHT_STRENGTH * strength
        + WEIGHT_CONFLUENCE * confluence
    ) * 100.0
    return round(score, 2)


def score_to_lot(score: float) -> Decimal:
    if score >= 90:
        return LOT_TIER_HIGH
    if score >= 70:
        return LOT_TIER_MID
    if score >= 40:
        return LOT_TIER_LOW
    return LOT_TIER_FLOOR
