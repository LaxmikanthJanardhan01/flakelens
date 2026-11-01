import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.core.comparator import ExecutionComparator, ComparisonError
from backend.app.schemas.comparison import RunComparisonResponse

logger = logging.getLogger("flakelens.api.comparison")

router = APIRouter(prefix="/comparison", tags=["Execution Comparison"])


@router.get("", response_model=RunComparisonResponse)
def compare_runs(
    run_a_id: str = Query(..., description="ID of the baseline / earlier run"),
    run_b_id: str = Query(..., description="ID of the comparison / later run"),
    db: Session = Depends(get_db),
):
    """
    Compares two completed execution sessions of the same project.
    Identifies test transitions (recovered, newly failing, still flaky, unchanged),
    duration deltas, and flakiness score deltas without fabricating historical data.
    """
    comparator = ExecutionComparator()
    try:
        return comparator.compare_runs(run_a_id=run_a_id, run_b_id=run_b_id, db=db)
    except ComparisonError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Unexpected error comparing runs '{run_a_id}' and '{run_b_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Run comparison failed: {e}",
        )

