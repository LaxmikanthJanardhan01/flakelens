from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.db.session import get_db
from backend.app.db.models import FlakinessReport
from backend.app.schemas.report import FlakinessReportResponse

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/run/{run_id}", response_model=List[FlakinessReportResponse])
def get_run_reports(run_id: str, db: Session = Depends(get_db)):
    """
    Get all test flakiness and RCA reports for a given run ID.
    Returns an empty list if none exist.
    """
    reports = db.query(FlakinessReport).filter(FlakinessReport.test_run_id == run_id).all()
    return reports


@router.get("/{report_id}", response_model=FlakinessReportResponse)
def get_report(report_id: str, db: Session = Depends(get_db)):
    """
    Get a specific flakiness diagnosis report by ID.
    """
    report = db.query(FlakinessReport).filter(FlakinessReport.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID '{report_id}' not found.",
        )
    return report

