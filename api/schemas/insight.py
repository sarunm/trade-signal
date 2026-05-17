from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel


class InsightResponse(BaseModel):
    id: UUID
    type: str
    description: str
    confidence: float
    sample_size: int
    discovered_at: datetime
    is_active: bool
    data: Optional[Any] = None

    model_config = {"from_attributes": True}
