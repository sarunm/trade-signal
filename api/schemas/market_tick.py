from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, model_validator


class MarketTickSchema(BaseModel):
    timestamp: datetime
    symbol: str
    bid: Decimal
    ask: Decimal

    @model_validator(mode="after")
    def validate_spread(self):
        if self.bid > self.ask:
            raise ValueError("bid must be less than or equal to ask")
        return self
