from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PaperSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_id: UUID
    status: str
    match_pct: Decimal
    matched_conditions: list[str]
    missing_conditions: list[str]
    score: Optional[Decimal] = None
    suggested_lot: Optional[Decimal] = None
    emitted_at: datetime
