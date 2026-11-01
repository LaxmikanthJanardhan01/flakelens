import difflib
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from backend.app.db.session import get_db
from backend.app.db.models import FlakinessReport, TestRun, TestIteration, TestCase, Project
from backend.app.schemas.report import (
    FlakinessReportResponse,
    IterationLogItem,
    DetailedTestCaseReport,
    DetailedRunReportResponse,
    IterationDiffResponse,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


def _serialize_report(r: FlakinessReport) -> FlakinessReportResponse:
    tc = r.test_case
    evidence_dict = None
    if getattr(r, "supporting_evidence", None):
        try:
            evidence_dict = json.loads(r.supporting_evidence)
        except Exception:
            evidence_dict = {"raw": r.supporting_evidence}

    return FlakinessReportResponse(
        id=r.id,
        test_run_id=r.test_run_id,
        test_case_id=r.test_case_id,
        node_id=tc.node_id if tc else None,
        test_name=tc.test_name if tc else None,
        file_path=tc.file_path if tc else None,
        outcome_classification=r.outcome_classification,
        flakiness_score=r.flakiness_score,
        total_runs=r.total_runs,
        pass_count=r.pass_count,
        fail_count=r.fail_count,
        flip_count=r.flip_count,
        root_cause_category=r.root_cause_category,
        confidence_score=r.confidence_score,
        rca_summary=r.rca_summary,
        recommendations=r.recommendations,
        supporting_evidence=evidence_dict,
    )


@router.get("/run/{run_id}", response_model=List[FlakinessReportResponse])
def get_run_reports(run_id: str, db: Session = Depends(get_db)):
    """
    Get all test flakiness and RCA reports for a given run ID.
    Returns an empty list if none exist.
    """
    reports = (
        db.query(FlakinessReport)
        .options(joinedload(FlakinessReport.test_case))
        .filter(FlakinessReport.test_run_id == run_id)
        .all()
    )
    return [_serialize_report(r) for r in reports]


@router.get("/run/{run_id}/detailed", response_model=DetailedRunReportResponse)
def get_detailed_run_report(run_id: str, db: Session = Depends(get_db)):
    """
    Comprehensive per-run report with per-test execution history, iteration logs, and RCA.
    """
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with ID '{run_id}' not found.",
        )

    project = db.query(Project).filter(Project.id == run.project_id).first()
    project_name = project.name if project else "Unknown"

    reports = (
        db.query(FlakinessReport)
        .options(joinedload(FlakinessReport.test_case))
        .filter(FlakinessReport.test_run_id == run_id)
        .all()
    )

    iterations = (
        db.query(TestIteration)
        .filter(TestIteration.test_run_id == run_id)
        .order_by(TestIteration.iteration_number.asc(), TestIteration.execution_order.asc())
        .all()
    )

    iters_by_tc = {}
    for it in iterations:
        iters_by_tc.setdefault(it.test_case_id, []).append(it)

    detailed_reports: List[DetailedTestCaseReport] = []
    for r in reports:
        tc = r.test_case
        tc_iters = iters_by_tc.get(r.test_case_id, [])

        iter_logs = [
            IterationLogItem(
                iteration_number=it.iteration_number,
                status=it.status,
                duration_ms=it.duration_ms,
                execution_order=it.execution_order,
                random_order_seed=it.random_order_seed,
                error_message=it.error_message,
                traceback=it.traceback,
                stdout=it.stdout,
                stderr=it.stderr,
            )
            for it in tc_iters
        ]

        durs = [it.duration_ms for it in tc_iters if it.duration_ms > 0]
        avg_dur = round(sum(durs) / len(durs), 2) if durs else 0.0
        min_dur = round(min(durs), 2) if durs else 0.0
        max_dur = round(max(durs), 2) if durs else 0.0
        pass_rate = round(r.pass_count / r.total_runs, 4) if r.total_runs > 0 else 0.0

        evidence_dict = None
        if getattr(r, "supporting_evidence", None):
            try:
                evidence_dict = json.loads(r.supporting_evidence)
            except Exception:
                evidence_dict = {"raw": r.supporting_evidence}

        detailed_reports.append(
            DetailedTestCaseReport(
                id=r.id,
                test_run_id=r.test_run_id,
                test_case_id=r.test_case_id,
                node_id=tc.node_id if tc else None,
                test_name=tc.test_name if tc else None,
                file_path=tc.file_path if tc else None,
                outcome_classification=r.outcome_classification,
                flakiness_score=r.flakiness_score,
                total_runs=r.total_runs,
                pass_count=r.pass_count,
                fail_count=r.fail_count,
                flip_count=r.flip_count,
                root_cause_category=r.root_cause_category,
                confidence_score=r.confidence_score,
                rca_summary=r.rca_summary,
                recommendations=r.recommendations,
                supporting_evidence=evidence_dict,
                iterations=iter_logs,
                pass_rate=pass_rate,
                avg_duration_ms=avg_dur,
                min_duration_ms=min_dur,
                max_duration_ms=max_dur,
            )
        )

    return DetailedRunReportResponse(
        run_id=run.id,
        project_id=run.project_id,
        project_name=project_name,
        iteration_count=run.iteration_count,
        status=run.status,
        total_tests=run.total_tests,
        consistently_passing_count=run.consistently_passing_count,
        consistently_failing_count=run.consistently_failing_count,
        flaky_tests_count=run.flaky_tests_count,
        insufficient_data_count=run.insufficient_data_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
        reports=detailed_reports,
    )


@router.get("/run/{run_id}/diff/{test_case_id}", response_model=IterationDiffResponse)
def get_iteration_diff(run_id: str, test_case_id: str, db: Session = Depends(get_db)):
    """
    Extracts side-by-side execution evidence comparing a passing iteration vs a failing iteration.
    """
    tc = db.query(TestCase).filter(TestCase.id == test_case_id).first()
    if not tc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestCase '{test_case_id}' not found.",
        )

    iters = (
        db.query(TestIteration)
        .filter(TestIteration.test_run_id == run_id, TestIteration.test_case_id == test_case_id)
        .order_by(TestIteration.iteration_number.asc())
        .all()
    )

    pass_it = next((it for it in iters if it.status == "PASSED"), None)
    fail_it = next((it for it in iters if it.status in ("FAILED", "TIMED_OUT")), None)

    pass_dto = (
        IterationLogItem(
            iteration_number=pass_it.iteration_number,
            status=pass_it.status,
            duration_ms=pass_it.duration_ms,
            execution_order=pass_it.execution_order,
            random_order_seed=pass_it.random_order_seed,
            stdout=pass_it.stdout,
            stderr=pass_it.stderr,
        )
        if pass_it
        else None
    )

    fail_dto = (
        IterationLogItem(
            iteration_number=fail_it.iteration_number,
            status=fail_it.status,
            duration_ms=fail_it.duration_ms,
            execution_order=fail_it.execution_order,
            random_order_seed=fail_it.random_order_seed,
            error_message=fail_it.error_message,
            traceback=fail_it.traceback,
            stdout=fail_it.stdout,
            stderr=fail_it.stderr,
        )
        if fail_it
        else None
    )

    dur_delta = None
    if pass_it and fail_it:
        dur_delta = round(fail_it.duration_ms - pass_it.duration_ms, 2)

    stdout_diff_str = None
    if pass_it and fail_it:
        pass_lines = (pass_it.stdout or "").splitlines(keepends=True)
        fail_lines = (fail_it.stdout or "").splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(
                pass_lines,
                fail_lines,
                fromfile=f"Iteration #{pass_it.iteration_number} (PASSED)",
                tofile=f"Iteration #{fail_it.iteration_number} ({fail_it.status})",
            )
        )
        stdout_diff_str = "".join(diff) if diff else None

    stderr_diff_str = None
    if pass_it and fail_it:
        pass_err = (pass_it.stderr or "").splitlines(keepends=True)
        fail_err = (fail_it.stderr or (fail_it.traceback or "")).splitlines(keepends=True)
        diff_err = list(
            difflib.unified_diff(
                pass_err,
                fail_err,
                fromfile=f"Iteration #{pass_it.iteration_number} (PASSED)",
                tofile=f"Iteration #{fail_it.iteration_number} ({fail_it.status})",
            )
        )
        stderr_diff_str = "".join(diff_err) if diff_err else None

    return IterationDiffResponse(
        test_case_id=tc.id,
        node_id=tc.node_id,
        test_name=tc.test_name,
        passing_iteration=pass_dto,
        failing_iteration=fail_dto,
        duration_delta_ms=dur_delta,
        stdout_diff=stdout_diff_str,
        stderr_diff=stderr_diff_str,
    )


@router.get("/{report_id}", response_model=FlakinessReportResponse)
def get_report(report_id: str, db: Session = Depends(get_db)):
    """
    Get a specific flakiness diagnosis report by ID.
    """
    report = (
        db.query(FlakinessReport)
        .options(joinedload(FlakinessReport.test_case))
        .filter(FlakinessReport.id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID '{report_id}' not found.",
        )
    return _serialize_report(report)

