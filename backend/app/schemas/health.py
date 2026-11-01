from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema for system health check status."""

    status: str = Field(..., example="healthy")
    version: str = Field(..., example="0.1.0")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    database: str = Field(..., example="connected")
    storage: str = Field(..., example="ready")
    docker: Optional[str] = Field(default="available", example="available")
    environment: str = Field(..., example="development")
