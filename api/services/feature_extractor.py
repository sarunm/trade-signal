from datetime import datetime
from typing import Sequence

SESSION_LONDON = "london"
SESSION_NY = "ny"
SESSION_ASIA = "asia"

HOUR_BUCKETS = ("00-04", "04-08", "08-12", "12-16", "16-20", "20-24")
DOW_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

VOL_LOW = "low"
VOL_MID = "mid"
VOL_HIGH = "high"
VOL_UNKNOWN = "unknown"

_VOL_HISTORY_MIN = 5
_VOL_LOW_PCTILE = 0.30
_VOL_HIGH_PCTILE = 0.70


def classify_session(dt: datetime) -> str:
    """Map UTC hour to session label.

    London 07:00–13:00, NY 13:00–22:00, Asia 22:00–07:00.
    """
    h = dt.hour
    if 7 <= h < 13:
        return SESSION_LONDON
    if 13 <= h < 22:
        return SESSION_NY
    return SESSION_ASIA


def hour_bucket(dt: datetime) -> str:
    h = dt.hour
    start = (h // 4) * 4
    return f"{start:02d}-{start + 4:02d}"


def day_of_week(dt: datetime) -> str:
    return DOW_NAMES[dt.weekday()]


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    n = len(sorted_values)
    if n == 0:
        return 0.0
    k = max(0, min(n - 1, int(pct * (n - 1))))
    return sorted_values[k]


def volatility_regime(atr_value: float, history: Sequence[float]) -> str:
    """Classify ATR vs its own recent distribution."""
    if len(history) < _VOL_HISTORY_MIN:
        return VOL_UNKNOWN
    s = sorted(history)
    if atr_value < _percentile(s, _VOL_LOW_PCTILE):
        return VOL_LOW
    if atr_value > _percentile(s, _VOL_HIGH_PCTILE):
        return VOL_HIGH
    return VOL_MID
