from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class TestRunCreate(BaseModel):
    """Schema for initiating an analysis run."""

    project_id: str
    iteration_count: int = Field(default=10, ge=3, le=50)
    shuffle_order: bool = Field(default=True)


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


class TestRunResponse(BaseModel):
    """Schema for test run metadata and summary counts."""

    id: str
    project_id: str
    iteration_count: int
    shuffle_order: bool
    status: str
    total_tests: int
    consistently_passing_count: int
    consistently_failing_count: int
    flaky_tests_count: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

