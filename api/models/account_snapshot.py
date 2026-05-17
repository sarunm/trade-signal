from datetime import datetime
from decimal import Decimal
from sqlalchemy import Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    equity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    margin: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    free_margin: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    floating_pl: Mapped[Decimal] = mapped_column(Numeric(14, 2))
