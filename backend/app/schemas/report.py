from typing import Optional, Dict, Any
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
    supporting_evidence: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class IterationLogItem(BaseModel):
    iteration_number: int
    status: str
    duration_ms: float
    execution_order: int
    random_order_seed: Optional[int] = None
    error_message: Optional[str] = None
    traceback: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None

    class Config:
        from_attributes = True


class DetailedTestCaseReport(FlakinessReportResponse):
    iterations: list[IterationLogItem] = []
    pass_rate: float = 0.0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = 0.0
    max_duration_ms: float = 0.0


class DetailedRunReportResponse(BaseModel):
    run_id: str
    project_id: str
    project_name: str
    iteration_count: int
    status: str
    total_tests: int
    consistently_passing_count: int
    consistently_failing_count: int
    flaky_tests_count: int
    insufficient_data_count: int
    started_at: Optional[Any] = None
    completed_at: Optional[Any] = None
    reports: list[DetailedTestCaseReport]


class IterationDiffResponse(BaseModel):
    test_case_id: str
    node_id: str
    test_name: str
    passing_iteration: Optional[IterationLogItem] = None
    failing_iteration: Optional[IterationLogItem] = None
    duration_delta_ms: Optional[float] = None
    stdout_diff: Optional[str] = None
    stderr_diff: Optional[str] = None


