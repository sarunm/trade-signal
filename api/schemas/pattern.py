from datetime import datetime
from decimal import Decimal
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
    mode: str = "strict"
    trust_tier: str = "experimental"
    age_seconds: int = 0
    net_ev_per_trade: Optional[Decimal] = None
    wilson_lower_95: Optional[Decimal] = None
    baseline_delta: Optional[Decimal] = None
    last_signal_status: Optional[str] = None
    filters: list[dict] = []
    shadow_of_rule_id: Optional[UUID] = None

    @computed_field
    @property
    def win_rate(self) -> Optional[float]:
        if self.total_trades == 0:
            return None
        return self.win_count / self.total_trades

    model_config = {"from_attributes": True}


class PaperTradeResponse(BaseModel):
    id: UUID
    ticket: int
    symbol: str
    direction: Optional[str] = None
    open_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    tp: Optional[Decimal] = None
    sl: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    paper_exit_reason: Optional[str] = None
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    rule_id: Optional[UUID] = None
    status: str

    model_config = {"from_attributes": True}
