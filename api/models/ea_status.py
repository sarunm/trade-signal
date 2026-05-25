from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class EAStatus(Base):
    __tablename__ = "ea_status"

    account_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
