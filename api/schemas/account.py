from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class AccountResponse(BaseModel):
    equity: Decimal
    balance: Decimal
    margin: Decimal
    free_margin: Decimal
    floating_pl: Decimal
    timestamp: datetime
    account_id: Optional[int] = None

    model_config = {"from_attributes": True}
