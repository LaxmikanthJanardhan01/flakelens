import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.config import settings
from backend.app.db.session import get_db
from backend.app.schemas.health import HealthResponse

router = APIRouter(prefix="", tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def check_health(db: Session = Depends(get_db)):
    """
    System health check endpoint.
    Verifies SQLite database connectivity, storage directories readiness, and returns system info.
    """
    # 1. Verify Database
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {str(exc)}"

    # 2. Verify Storage
    storage_status = "ready"
    try:
        if not (os.path.exists(settings.STORAGE_DIR) and os.path.exists(settings.UPLOADS_DIR)):
            storage_status = "directory_missing"
    except Exception as exc:
        storage_status = f"unhealthy: {str(exc)}"

    overall_status = "healthy" if db_status == "connected" and storage_status == "ready" else "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.VERSION,
        database=db_status,
        storage=storage_status,
        environment=settings.ENVIRONMENT,
    )

