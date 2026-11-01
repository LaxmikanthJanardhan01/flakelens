from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class TestCaseResponse(BaseModel):
    """Schema for discovered pytest test case."""

    id: str
    project_id: str
    file_path: str
    test_name: str
    node_id: str
    discovered_at: datetime

    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    """Schema for creating a project."""

    name: str = Field(..., min_length=1, max_length=255)


class ProjectResponse(BaseModel):
    """Schema for project details."""

    id: str
    name: str
    source_archive_path: Optional[str] = None
    created_at: datetime
    test_cases_count: int = 0

    class Config:
        from_attributes = True

