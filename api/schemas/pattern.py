from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, computed_field


class PatternResponse(BaseModel):
    id: UUID
    indicator_slugs: list[str]
    timeframe: str
    win_rate: float
    sample_count: int
    consecutive_stable_days: int
    status: str
    discovered_at: datetime
    promoted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaperTraderRuleResponse(BaseModel):
    id: UUID
    pattern_id: UUID
    status: str
    spawned_at: datetime
    total_trades: int
    win_count: int

    @computed_field
    @property
    def win_rate(self) -> Optional[float]:
        if self.total_trades == 0:
            return None
        return self.win_count / self.total_trades

    model_config = {"from_attributes": True}
