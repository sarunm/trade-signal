from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class IndicatorSignalResponse(BaseModel):
    id: UUID
    trade_id: UUID
    indicator_slug: str
    timeframe: str
    value: Optional[float] = None
    direction: Optional[str] = None
    matched: bool
    metadata: dict = Field(default_factory=dict, validation_alias="signal_metadata")
    calculated_at: datetime

    model_config = {"from_attributes": True}
