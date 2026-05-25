from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from models.price_bar import Timeframe


class PriceBarResponse(BaseModel):
    time: datetime
    symbol: str
    timeframe: Timeframe
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[Decimal] = None

    model_config = {"from_attributes": True}
