from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator
from services.symbol_normalizer import normalize_symbol


class MarketTickSchema(BaseModel):
    timestamp: datetime
    symbol: str
    bid: Decimal
    ask: Decimal
    account_id: Optional[int] = None
    equity: Optional[Decimal] = None
    floating_pl: Optional[Decimal] = None

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        return normalize_symbol(v)

    @model_validator(mode="after")
    def validate_spread(self):
        if self.bid > self.ask:
            raise ValueError("bid must be less than or equal to ask")
        return self
