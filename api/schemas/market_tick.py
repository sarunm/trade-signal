from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, model_validator


class MarketTickSchema(BaseModel):
    timestamp: datetime
    symbol: str
    bid: Decimal
    ask: Decimal
    account_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_spread(self):
        if self.bid > self.ask:
            raise ValueError("bid must be less than or equal to ask")
        return self
