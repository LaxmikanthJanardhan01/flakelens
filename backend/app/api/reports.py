from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from backend.app.db.session import get_db
from backend.app.db.models import FlakinessReport
from backend.app.schemas.report import FlakinessReportResponse

router = APIRouter(prefix="/reports", tags=["Reports"])


def _serialize_report(r: FlakinessReport) -> FlakinessReportResponse:
    tc = r.test_case
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

