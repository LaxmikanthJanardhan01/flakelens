from typing import Optional
from pydantic import BaseModel, Field


class FlakinessReportResponse(BaseModel):
    """Schema for synthesized flakiness and RCA report."""

    id: str
    test_run_id: str
    test_case_id: str
    node_id: Optional[str] = None
    test_name: Optional[str] = None
    file_path: Optional[str] = None
    outcome_classification: str  # CONSISTENTLY_PASSING, CONSISTENTLY_FAILING, FLAKY, INSUFFICIENT_DATA
    flakiness_score: float
    total_runs: int
    pass_count: int
    fail_count: int
    flip_count: int
    root_cause_category: Optional[str] = None
    confidence_score: float
    rca_summary: Optional[str] = None
    recommendations: Optional[str] = None

    class Config:
        from_attributes = True

