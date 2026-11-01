"""API package for FLAKELENS."""

from backend.app.api.health import router as health_router
from backend.app.api.projects import router as projects_router
from backend.app.api.runs import router as runs_router
from backend.app.api.reports import router as reports_router

__all__ = [
    "health_router",
    "projects_router",
    "runs_router",
    "reports_router",
]

