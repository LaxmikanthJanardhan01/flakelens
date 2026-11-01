import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.session import get_db, SessionLocal
from backend.app.db.models import Project, TestCase, TestRun, RunIteration, TestIteration
from backend.app.schemas.run import (
    TestRunCreate,
    TestRunResponse,
    TestIterationResponse,
    RunIterationResponse,
    TestIterationDetailResponse,
)
from backend.app.schemas.report import FlakinessReportResponse
from backend.app.core.lock import ExecutionLockManager
from backend.app.core.runner import ExecutionRunner
from backend.app.core.detector import FlakinessDetector, ActiveRunAnalysisError
from backend.app.api.reports import _serialize_report

logger = logging.getLogger("flakelens.api.runs")

router = APIRouter(prefix="/runs", tags=["Test Runs"])


def _run_execution_background(run_id: str):
    """Background task worker function to run the execution engine."""
    runner = ExecutionRunner()
    runner.execute_test_run(run_id)


def _build_run_response(run: TestRun, db: Session) -> TestRunResponse:
    """Helper to construct TestRunResponse with actual completed iterations from SQLite."""
    completed_count = (
        db.query(RunIteration)
        .filter(
            RunIteration.test_run_id == run.id,
            RunIteration.status == "COMPLETED",
        )
        .count()
    )
    return TestRunResponse(
        id=run.id,
        project_id=run.project_id,
        iteration_count=run.iteration_count,
        completed_iterations=completed_count,
        shuffle_order=run.shuffle_order,
        status=run.status,
        total_tests=run.total_tests,
        consistently_passing_count=run.consistently_passing_count,
        consistently_failing_count=run.consistently_failing_count,
        flaky_tests_count=run.flaky_tests_count,
        insufficient_data_count=run.insufficient_data_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("", response_model=List[TestRunResponse])
def list_runs(db: Session = Depends(get_db)):
    """
    List all test execution sessions with actual database progress.
    """
    runs = db.query(TestRun).order_by(TestRun.started_at.desc().nullslast(), TestRun.id.desc()).all()
    return [_build_run_response(r, db) for r in runs]


@router.post("", response_model=TestRunResponse, status_code=status.HTTP_201_CREATED)
def start_run(
    payload: TestRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Initiates a repeated test execution run for a target project.

    Enforces:
    1. Project existence and discovered tests check.
    2. Global execution lock verification to guarantee single-container sequential execution.
    3. Asynchronous background execution dispatch.
    """
    # 1. Verify project exists
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{payload.project_id}' not found.",
        )

    # 2. Verify test cases exist
    test_count = db.query(TestCase).filter(TestCase.project_id == payload.project_id).count()
    if test_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project '{project.name}' has no discovered test cases. Run test discovery before initiating an analysis run.",
        )

    # 3. Check execution lock
    lock_mgr = ExecutionLockManager(session_factory=sessionmaker(bind=db.get_bind()))
    is_locked, locked_by = lock_mgr.is_locked()
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another test run ('{locked_by}') is currently executing. "
                   "FLAKELENS enforces strictly sequential execution to protect system resources and eliminate test cross-talk.",
        )

    # 4. Create TestRun record
    test_run = TestRun(
        project_id=payload.project_id,
        iteration_count=payload.iteration_count,
        shuffle_order=payload.shuffle_order,
        status="PENDING",
        total_tests=test_count,
    )
    db.add(test_run)
    db.commit()
    db.refresh(test_run)

    # 5. Dispatch background execution
    background_tasks.add_task(_run_execution_background, test_run.id)

    return _build_run_response(test_run, db)


@router.get("/{run_id}", response_model=TestRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    """
    Get details and live progress of a specific test run.
    """
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with ID '{run_id}' not found.",
        )
    return _build_run_response(run, db)


@router.get("/{run_id}/run_iterations", response_model=List[RunIterationResponse])
def list_run_iterations_summary(run_id: str, db: Session = Depends(get_db)):
    """
    List iteration-level execution records for a run.
    """
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with ID '{run_id}' not found.",
        )
    iterations = (
        db.query(RunIteration)
        .filter(RunIteration.test_run_id == run_id)
        .order_by(RunIteration.iteration_number.asc())
        .all()
    )
    return iterations


@router.get("/{run_id}/iterations", response_model=List[TestIterationDetailResponse])
def list_run_test_iterations(run_id: str, db: Session = Depends(get_db)):
    """
    List individual test iteration records with joined test case metadata (node ID, file path).
    """
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with ID '{run_id}' not found.",
        )

    results = (
        db.query(TestIteration, TestCase)
        .join(TestCase, TestIteration.test_case_id == TestCase.id)
        .filter(TestIteration.test_run_id == run_id)
        .order_by(TestIteration.iteration_number.asc(), TestIteration.execution_order.asc())
        .all()
    )

    details: List[TestIterationDetailResponse] = []
    for ti, tc in results:
        details.append(
            TestIterationDetailResponse(
                id=ti.id,
                test_run_id=ti.test_run_id,
                test_case_id=ti.test_case_id,
                node_id=tc.node_id,
                test_name=tc.test_name,
                file_path=tc.file_path,
                iteration_number=ti.iteration_number,
                status=ti.status,
                duration_ms=ti.duration_ms,
                execution_order=ti.execution_order,
                random_order_seed=ti.random_order_seed,
                stdout=ti.stdout,
                stderr=ti.stderr,
                error_message=ti.error_message,
                traceback=ti.traceback,
            )
        )
    return details


@router.post("/{run_id}/cancel", response_model=TestRunResponse)
def cancel_run(run_id: str, db: Session = Depends(get_db)):
    """
    Safely request immediate cancellation of an active test run:
    1. Sets database status to CANCELLED.
    2. Signals ExecutionRunner to immediately kill the active Docker container.
    3. Handles cancellation races and duplicate calls idempotently.
    """
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with ID '{run_id}' not found.",
        )

    if run.status in ("RUNNING", "PENDING"):
        run.status = "CANCELLED"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)

        # Trigger immediate termination of active container and runner abort
        ExecutionRunner.cancel_active_run(run_id)

    return _build_run_response(run, db)


@router.get("/{run_id}/reports", response_model=List[FlakinessReportResponse])
def get_run_reports_alias(run_id: str, db: Session = Depends(get_db)):
    """
    Get all test flakiness reports for a given run ID (alias for /api/reports/run/{run_id}).
    """
    from backend.app.db.models import FlakinessReport
    from sqlalchemy.orm import joinedload
    reports = (
        db.query(FlakinessReport)
        .options(joinedload(FlakinessReport.test_case))
        .filter(FlakinessReport.test_run_id == run_id)
        .all()
    )
    return [_serialize_report(r) for r in reports]


@router.post("/{run_id}/analyze", response_model=List[FlakinessReportResponse])
def trigger_run_analysis(run_id: str, db: Session = Depends(get_db)):
    """
    Explicitly trigger flakiness detection and scoring for a test run.
    Safeguards:
    - Rejects analysis if the run is actively running (HTTP 409 Conflict).
    - Idempotently updates FlakinessReport records and recalculates TestRun summary counters.
    """
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with ID '{run_id}' not found.",
        )

    lock_mgr = ExecutionLockManager()
    is_locked, holder_run_id = lock_mgr.is_locked()
    if run.status == "RUNNING" or (is_locked and holder_run_id == run_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot analyze test run '{run_id}' while execution is in progress.",
        )

    try:
        detector = FlakinessDetector()
        reports = detector.analyze_test_run(run_id, db)
        return [_serialize_report(r) for r in reports]
    except ActiveRunAnalysisError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Error during analysis for run '{run_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {e}",
        )
