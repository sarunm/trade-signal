import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ScoreCalibration(Base):
    __tablename__ = "score_calibrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    score_tier: Mapped[str] = mapped_column(String(10))
    expected_winrate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    actual_winrate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    sample_count: Mapped[int] = mapped_column(Integer)
    calibrated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
