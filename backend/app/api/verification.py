import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.session import get_db
from backend.app.db.models import Project, TestCase, TestRun
from backend.app.schemas.run import TestRunResponse
from backend.app.schemas.verification import (
    FixVerificationRequest,
    FixVerificationResponse,
)
from backend.app.core.verification import FixVerificationEngine, VerificationError
from backend.app.core.lock import ExecutionLockManager
from backend.app.api.runs import _run_execution_background, _build_run_response

logger = logging.getLogger("flakelens.api.verification")

router = APIRouter(prefix="/verification", tags=["Fix Verification"])


@router.post("", response_model=TestRunResponse, status_code=status.HTTP_201_CREATED)
def start_fix_verification(
    payload: FixVerificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Initiates a Fix Verification execution session for a target project and baseline run.
    Runs targeted test(s) N times (default >= 5) in secure, isolated Docker containers.
    """
    # 1. Verify project exists
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{payload.project_id}' not found.",
        )

    # 2. Verify baseline run exists and belongs to same project
    baseline = db.query(TestRun).filter(TestRun.id == payload.baseline_run_id).first()
    if not baseline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Baseline run with ID '{payload.baseline_run_id}' not found.",
        )

    if baseline.project_id != payload.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Baseline run must belong to the same project as the verification run.",
        )

    if baseline.status in ("RUNNING", "PENDING"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Baseline run '{payload.baseline_run_id}' is still executing.",
        )

    # 3. Verify target test case if provided
    total_tests = 1 if payload.target_test_case_id else baseline.total_tests
    if payload.target_test_case_id:
        tc = db.query(TestCase).filter(
            TestCase.id == payload.target_test_case_id,
            TestCase.project_id == payload.project_id,
        ).first()
        if not tc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target test case with ID '{payload.target_test_case_id}' not found in project.",
            )

    # 4. Enforce global execution lock
    lock_mgr = ExecutionLockManager(session_factory=sessionmaker(bind=db.get_bind()))
    is_locked, locked_by = lock_mgr.is_locked()
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another test run ('{locked_by}') is currently executing.",
        )

    # 5. Create TestRun record
    test_run = TestRun(
        project_id=payload.project_id,
        iteration_count=payload.iteration_count,
        shuffle_order=payload.shuffle_order,
        run_type="VERIFICATION",
        baseline_run_id=payload.baseline_run_id,
        target_test_case_id=payload.target_test_case_id,
        status="PENDING",
        total_tests=total_tests,
    )
    db.add(test_run)
    db.commit()
    db.refresh(test_run)

    # 6. Dispatch execution
    background_tasks.add_task(_run_execution_background, test_run.id)

    return _build_run_response(test_run, db)


@router.get("/{verification_run_id}", response_model=FixVerificationResponse)
def get_fix_verification_result(
    verification_run_id: str,
    db: Session = Depends(get_db),
):
    """
    Evaluates and returns the fix verification outcomes, stability metrics, and verdict.
    """
    engine = FixVerificationEngine()
    try:
        return engine.evaluate_verification(verification_run_id, db)
    except VerificationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Unexpected error evaluating verification run '{verification_run_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification evaluation failed: {e}",
        )

