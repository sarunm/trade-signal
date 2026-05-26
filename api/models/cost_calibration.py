import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CostCalibration(Base):
    __tablename__ = "cost_calibrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    learned_spread_pip: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    learned_commission_per_lot_thb: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    sample_count_spread: Mapped[int] = mapped_column(Integer)
    sample_count_commission: Mapped[int] = mapped_column(Integer)
    calibrated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
