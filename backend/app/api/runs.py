from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.db.session import get_db
from backend.app.db.models import TestRun, TestIteration
from backend.app.schemas.run import TestRunResponse, TestIterationResponse

router = APIRouter(prefix="/runs", tags=["Test Runs"])


@router.get("", response_model=List[TestRunResponse])
def list_runs(db: Session = Depends(get_db)):
    """
    List all test execution sessions. Returns empty list if no runs exist.
    """
    runs = db.query(TestRun).order_by(TestRun.started_at.desc()).all()
    return runs


@router.get("/{run_id}", response_model=TestRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    """
    Get details of a specific test run.
    """
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with ID '{run_id}' not found.",
        )
    return run


@router.get("/{run_id}/iterations", response_model=List[TestIterationResponse])
def list_run_iterations(run_id: str, db: Session = Depends(get_db)):
    """
    List all test iteration records for a run.
    """
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with ID '{run_id}' not found.",
        )
    iterations = db.query(TestIteration).filter(TestIteration.test_run_id == run_id).all()
    return iterations

