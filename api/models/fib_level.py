from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class FibLevel(Base):
    __tablename__ = "fib_levels"
    __table_args__ = (UniqueConstraint("symbol", "timeframe", name="uq_fib_symbol_tf"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    swing_high: Mapped[float] = mapped_column(Numeric(12, 5), nullable=False)
    swing_low: Mapped[float] = mapped_column(Numeric(12, 5), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    levels: Mapped[dict] = mapped_column(JSON, nullable=False)
    extensions: Mapped[dict] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
