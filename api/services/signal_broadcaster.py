import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.paper_signal import PaperSignal
from models.pattern import PaperTraderRule

logger = logging.getLogger(__name__)

STATUS_ACTIVE = "active"
STATUS_NEAR = "near"
STATUS_FAR = "far"
STATUS_IDLE = "idle"

NEAR_MISSING_MAX = int(os.getenv("BROADCASTER_NEAR_MISSING_MAX", "1"))
NEAR_MIN_TOTAL = int(os.getenv("BROADCASTER_NEAR_MIN_TOTAL", "3"))


@dataclass
class SignalEvalInputs:
    matched_count: int
    total_count: int
    has_open_paper: bool


def compute_status(inputs: SignalEvalInputs) -> str:
    if inputs.has_open_paper:
        return STATUS_ACTIVE
    if inputs.total_count == 0:
        return STATUS_IDLE
    if inputs.matched_count == 0:
        return STATUS_IDLE
    if inputs.matched_count == inputs.total_count:
        return STATUS_ACTIVE
    missing = inputs.total_count - inputs.matched_count
    if inputs.total_count >= NEAR_MIN_TOTAL and missing <= NEAR_MISSING_MAX:
        return STATUS_NEAR
    return STATUS_FAR
