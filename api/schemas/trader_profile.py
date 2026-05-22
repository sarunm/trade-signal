from typing import Optional

from pydantic import BaseModel


class CandidateRule(BaseModel):
    setup_pattern: str
    trade_bias: Optional[str] = None
    count: int
    win_rate: Optional[float] = None
    threshold: int = 15


class TraderProfileSummary(BaseModel):
    dominant_setup: Optional[str] = None
    dominant_bias: Optional[str] = None
    dominant_entry: Optional[str] = None
    dominant_fib: Optional[str] = None
    rescue_rate: float
    total_tagged: int


class TraderProfileResponse(BaseModel):
    summary: TraderProfileSummary
    candidates: list[CandidateRule]
