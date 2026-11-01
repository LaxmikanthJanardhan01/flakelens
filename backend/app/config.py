import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings for FLAKELENS."""

    PROJECT_NAME: str = "FLAKELENS"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = "development"

    # Base paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    UPLOADS_DIR: Path = STORAGE_DIR / "uploads"
    REPORTS_DIR: Path = STORAGE_DIR / "reports"

    # Database
    DATABASE_URL: str = f"sqlite:///{STORAGE_DIR / 'flakelens.db'}"

    # Container Resource Limits (Conservative defaults suitable for laptops)
    DOCKER_MEMORY_LIMIT: str = "1024m"
    DOCKER_CPU_LIMIT: float = 1.0
    DOCKER_PIDS_LIMIT: int = 100
    DOCKER_ITERATION_TIMEOUT: int = 60
    DOCKER_BUILD_TIMEOUT: int = 120

    # Archive Security Limits
    MAX_ARCHIVE_FILES: int = 1000
    MAX_ARCHIVE_UNCOMPRESSED_SIZE: int = 50 * 1024 * 1024  # 50 MB
    MAX_ARCHIVE_COMPRESSION_RATIO: float = 100.0

    # Execution Lock Settings
    LOCK_TTL_SECONDS: int = 30
    LOCK_HEARTBEAT_INTERVAL: float = 10.0
    LOCK_THREAD_STOP_TIMEOUT: float = 5.0

    # Milestone 4 Detection & Classification Settings
    MIN_VALID_EXECUTIONS_THRESHOLD: int = 5

    # CORS settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# Ensure required storage directories exist
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
os.makedirs(settings.REPORTS_DIR, exist_ok=True)

