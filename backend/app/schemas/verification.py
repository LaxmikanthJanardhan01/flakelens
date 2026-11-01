from typing import List, Optional
from pydantic import BaseModel, Field
from backend.app.schemas.run import TestRunResponse


class FixVerificationRequest(BaseModel):
    """Payload to initiate a fix verification execution."""
    project_id: str
    baseline_run_id: str
    target_test_case_id: Optional[str] = None
    iteration_count: int = Field(default=10, ge=5, le=50)
    shuffle_order: bool = Field(default=True)


class FixVerificationVerdict:
    VERIFIED_FIXED = "VERIFIED_FIXED"
    STILL_FLAKY = "STILL_FLAKY"
    STILL_FAILING = "STILL_FAILING"
    INCONCLUSIVE = "INCONCLUSIVE"


class TestVerificationDetail(BaseModel):
    test_case_id: str
    node_id: str
    test_name: str
    file_path: str
    baseline_status: str
    baseline_flakiness_score: float
    baseline_pass_count: int
    baseline_fail_count: int
    baseline_total_runs: int
    baseline_rca_category: Optional[str] = None
    verification_status: str
    verification_flakiness_score: float
    verification_pass_count: int
    verification_fail_count: int
    verification_total_runs: int
    verdict: str
    verdict_message: str
    is_stable: bool


class FixVerificationResponse(BaseModel):
    verification_run: TestRunResponse
    baseline_run: TestRunResponse
    overall_verdict: str
    verdict_summary: str
    tests: List[TestVerificationDetail]

