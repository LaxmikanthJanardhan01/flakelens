import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db.session import get_db
from backend.app.db.models import Project, TestCase
from backend.app.schemas.project import ProjectResponse, TestCaseResponse
from backend.app.core.archive import (
    validate_and_extract_zip,
    ArchiveSecurityException,
    ArchiveValidationException,
)
from backend.app.core.docker_manager import (
    DockerManager,
    DockerUnavailableError,
    ProjectBuildError,
    TestDiscoveryError,
    TestDiscoveryTimeoutError,
)
from backend.app.core.discovery import discover_and_register_tests

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    """
    List all ingested projects. Returns empty list if no projects exist (no mock data).
    """
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    results = []
    for proj in projects:
        count = db.query(TestCase).filter(TestCase.project_id == proj.id).count()
        results.append(
            ProjectResponse(
                id=proj.id,
                name=proj.name,
                source_archive_path=proj.source_archive_path,
                created_at=proj.created_at,
                test_cases_count=count,
            )
        )
    return results


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    """
    Get project details by ID.
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    count = db.query(TestCase).filter(TestCase.project_id == proj.id).count()
    return ProjectResponse(
        id=proj.id,
        name=proj.name,
        source_archive_path=proj.source_archive_path,
        created_at=proj.created_at,
        test_cases_count=count,
    )


@router.get("/{project_id}/tests", response_model=List[TestCaseResponse])
def list_project_tests(project_id: str, db: Session = Depends(get_db)):
    """
    List discovered test cases for a project. Returns empty list if none discovered.
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    test_cases = db.query(TestCase).filter(TestCase.project_id == project_id).all()
    return test_cases


@router.post("/upload", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def upload_project(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Upload and ingest a target test repository ZIP archive.

    Enforces:
    1. ZIP filename validation.
    2. Hardened archive extraction (Zip-Slip, Zip Bomb, Symlink checks).
    3. Docker availability verification.
    4. Sandboxed pytest test discovery running strictly inside Docker.
    5. Test case indexing and database persistence.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ZIP archives (.zip) are supported for project ingestion.",
        )

    project_name = name.strip() if name and name.strip() else Path(file.filename).stem
    project_id = str(uuid.uuid4())

    project_dir = settings.UPLOADS_DIR / project_id
    archive_dest = settings.UPLOADS_DIR / f"{project_id}.zip"

    # Save uploaded archive to disk
    try:
        with open(archive_dest, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded archive: {str(e)}",
        )

    # Validate and safely extract the ZIP archive
    try:
        validate_and_extract_zip(archive_dest, project_dir)
    except ArchiveSecurityException as e:
        _cleanup_upload(archive_dest, project_dir)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security rejection: {str(e)}",
        )
    except ArchiveValidationException as e:
        _cleanup_upload(archive_dest, project_dir)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archive validation failed: {str(e)}",
        )
    except Exception as e:
        _cleanup_upload(archive_dest, project_dir)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Archive extraction failed: {str(e)}",
        )

    # Check Docker daemon availability
    docker_mgr = DockerManager()
    is_docker_available, docker_err = docker_mgr.is_available()
    if not is_docker_available:
        _cleanup_upload(archive_dest, project_dir)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Docker service is unavailable: {docker_err}",
        )

    # Create Project in database
    proj = Project(
        id=project_id,
        name=project_name,
        source_archive_path=str(archive_dest),
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)

    # Run sandboxed test discovery strictly inside Docker
    try:
        discovered_tests = discover_and_register_tests(
            project_id=project_id,
            project_dir=project_dir,
            db=db,
            docker_mgr=docker_mgr,
        )
    except ProjectBuildError as e:
        _cleanup_project_db_and_files(proj, archive_dest, project_dir, db)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project dependency build failed: {str(e)}",
        )
    except TestDiscoveryTimeoutError as e:
        _cleanup_project_db_and_files(proj, archive_dest, project_dir, db)
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Test discovery timed out: {str(e)}",
        )
    except TestDiscoveryError as e:
        _cleanup_project_db_and_files(proj, archive_dest, project_dir, db)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pytest collection failed: {str(e)}",
        )
    except Exception as e:
        _cleanup_project_db_and_files(proj, archive_dest, project_dir, db)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test discovery encountered an unexpected error: {str(e)}",
        )

    return ProjectResponse(
        id=proj.id,
        name=proj.name,
        source_archive_path=proj.source_archive_path,
        created_at=proj.created_at,
        test_cases_count=len(discovered_tests),
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    """
    Delete a project, associated test cases, and stored archive/files.
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    project_dir = settings.UPLOADS_DIR / project_id
    archive_dest = settings.UPLOADS_DIR / f"{project_id}.zip"

    _cleanup_project_db_and_files(proj, archive_dest, project_dir, db)
    return None


def _cleanup_upload(archive_dest: Path, project_dir: Path) -> None:
    """Helper to remove uploaded archive and extracted directory on upload failure."""
    if archive_dest.exists():
        try:
            archive_dest.unlink()
        except Exception:
            pass
    if project_dir.exists():
        try:
            shutil.rmtree(project_dir)
        except Exception:
            pass


def _cleanup_project_db_and_files(
    proj: Project,
    archive_dest: Path,
    project_dir: Path,
    db: Session,
) -> None:
    """Helper to cleanly roll back database entry and remove files on error or deletion."""
    try:
        db.delete(proj)
        db.commit()
    except Exception:
        db.rollback()
    _cleanup_upload(archive_dest, project_dir)
