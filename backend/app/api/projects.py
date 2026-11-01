from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.db.session import get_db
from backend.app.db.models import Project, TestCase
from backend.app.schemas.project import ProjectResponse, TestCaseResponse

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

