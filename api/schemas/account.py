from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class AccountResponse(BaseModel):
    equity: Decimal
    balance: Decimal
    margin: Decimal
    free_margin: Decimal
    floating_pl: Decimal
    timestamp: datetime

    model_config = {"from_attributes": True}
