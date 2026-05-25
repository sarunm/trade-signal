from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EAHeartbeatSchema(BaseModel):
    account_id: int
    version: Optional[str] = None
    symbol: Optional[str] = None
    timestamp: Optional[datetime] = None


class EAStatusResponse(BaseModel):
    account_id: int
    last_seen_at: datetime
    version: Optional[str] = None
    symbol: Optional[str] = None
    seconds_since_last_seen: float = Field(..., ge=0)
    connected: bool

    model_config = {"from_attributes": True}
