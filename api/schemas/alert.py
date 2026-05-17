from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: UUID
    type: str
    message: str
    trigger_data: Optional[Any] = None
    sent_at: datetime
    acknowledged: bool

    model_config = {"from_attributes": True}
