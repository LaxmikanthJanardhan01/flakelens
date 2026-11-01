from typing import List, Optional
from pydantic import BaseModel
from backend.app.schemas.run import TestRunResponse


class TestTransition:
    RECOVERED = "RECOVERED"
    NEWLY_FAILING = "NEWLY_FAILING"
    NEWLY_FLAKY = "NEWLY_FLAKY"
    STILL_FLAKY = "STILL_FLAKY"
    STILL_FAILING = "STILL_FAILING"
    UNCHANGED_PASSING = "UNCHANGED_PASSING"
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    INCONCLUSIVE = "INCONCLUSIVE"


class TestComparisonItem(BaseModel):
    test_case_id: str
    node_id: str
    test_name: str
    file_path: str
    status_a: Optional[str] = None
    status_b: Optional[str] = None
    flakiness_score_a: Optional[float] = None
    flakiness_score_b: Optional[float] = None
    flakiness_score_delta: Optional[float] = None
    pass_rate_a: Optional[float] = None
    pass_rate_b: Optional[float] = None
    avg_duration_ms_a: Optional[float] = None
    avg_duration_ms_b: Optional[float] = None
    duration_delta_ms: Optional[float] = None
    transition: str
    rca_category_a: Optional[str] = None
    rca_category_b: Optional[str] = None


class ComparisonSummaryDelta(BaseModel):
    total_tests_delta: int
    flaky_count_delta: int
    passing_count_delta: int
    failing_count_delta: int
    recovered_count: int
    newly_failing_count: int
    newly_flaky_count: int
    still_flaky_count: int
    still_failing_count: int
    unchanged_passing_count: int


class RunComparisonResponse(BaseModel):
    project_id: str
    project_name: str
    run_a: TestRunResponse
    run_b: TestRunResponse
    summary_delta: ComparisonSummaryDelta
    test_comparisons: List[TestComparisonItem]

