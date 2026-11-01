import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.config import settings
from backend.app.db.session import get_db
from backend.app.schemas.health import HealthResponse
from backend.app.core.docker_manager import DockerManager

router = APIRouter(prefix="", tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def check_health(db: Session = Depends(get_db)):
    """
    System health check endpoint.
    Verifies SQLite database connectivity, storage directories readiness, and Docker daemon availability.
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

    # 3. Verify Docker Daemon
    docker_mgr = DockerManager()
    is_docker_ok, docker_err = docker_mgr.is_available()
    docker_status = "available" if is_docker_ok else f"unavailable: {docker_err}"

    overall_status = (
        "healthy"
        if db_status == "connected" and storage_status == "ready" and is_docker_ok
        else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        version=settings.VERSION,
        database=db_status,
        storage=storage_status,
        docker=docker_status,
        environment=settings.ENVIRONMENT,
    )
