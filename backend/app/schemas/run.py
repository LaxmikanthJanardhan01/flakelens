from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class TestRunCreate(BaseModel):
    """Schema for initiating an analysis run."""

    project_id: str
    iteration_count: int = Field(default=10, ge=3, le=50)
    shuffle_order: bool = Field(default=True)
    run_type: str = Field(default="STANDARD")
    baseline_run_id: Optional[str] = None
    target_test_case_id: Optional[str] = None


class TestIterationResponse(BaseModel):
    """Schema for individual test iteration outcome."""

    id: str
    test_run_id: str
    test_case_id: str
    iteration_number: int
    status: str
    duration_ms: float
    execution_order: int
    random_order_seed: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_message: Optional[str] = None
    traceback: Optional[str] = None

    class Config:
        from_attributes = True


class RunIterationResponse(BaseModel):
    """Schema for iteration-level execution record."""

    id: str
    test_run_id: str
    iteration_number: int
    status: str
    random_order_seed: Optional[int] = None
    duration_ms: float
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TestIterationDetailResponse(BaseModel):
    """Schema for test iteration with joined test case metadata."""

    id: str
    test_run_id: str
    test_case_id: str
    node_id: str
    test_name: str
    file_path: str
    iteration_number: int
    status: str
    duration_ms: float
    execution_order: int
    random_order_seed: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_message: Optional[str] = None
    traceback: Optional[str] = None

    class Config:
        from_attributes = True


class TestRunResponse(BaseModel):
    """Schema for test run metadata and live execution status."""

    id: str
    project_id: str
    project_name: Optional[str] = None
    run_type: str = "STANDARD"
    baseline_run_id: Optional[str] = None
    target_test_case_id: Optional[str] = None
    iteration_count: int
    completed_iterations: int = 0
    shuffle_order: bool
    status: str
    total_tests: int
    consistently_passing_count: int = 0
    consistently_failing_count: int = 0
    flaky_tests_count: int = 0
    insufficient_data_count: int = 0
    duration_seconds: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
