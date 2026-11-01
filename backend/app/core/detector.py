import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db.models import TestCase, TestRun, TestIteration, FlakinessReport

logger = logging.getLogger("flakelens.core.detector")


class ActiveRunAnalysisError(Exception):
    """Raised when re-analysis is attempted on an actively running test run."""
    pass


class FlakinessDetector:
    """
    Pure deterministic flakiness analysis and statistical classification engine.
    Calculates outcome distribution flakiness scores (F), consecutive flip counts (kappa),
    and enforces sample size thresholds.
    """

    VALID_PASS_STATUSES = {"PASSED"}
    VALID_FAIL_STATUSES = {"FAILED", "TIMED_OUT"}
    VALID_STATUSES = VALID_PASS_STATUSES | VALID_FAIL_STATUSES
    EXCLUDED_STATUSES = {"SKIPPED", "CANCELLED", "NOT_EXECUTED"}

    def __init__(self, min_samples_threshold: Optional[int] = None):
        self.min_samples_threshold = (
            min_samples_threshold
            if min_samples_threshold is not None
            else settings.MIN_VALID_EXECUTIONS_THRESHOLD
        )

    def analyze_test_run(
        self,
        test_run_id: str,
        db: Session,
        allow_active: bool = False,
    ) -> List[FlakinessReport]:
        """
        Analyzes all test iterations for a given run and generates synthesized FlakinessReport records.

        Safeguards enforced:
        1. Active runs reject analysis unless allow_active=True (used internally by runner completion hooks).
        2. Generates reports ONLY for TestCase records belonging to the current run's project.
        3. Recalculates all TestRun summary counters from the persisted reports on every analysis.
        4. Keeps RCA fields strictly NULL.
        """
        test_run = db.query(TestRun).filter(TestRun.id == test_run_id).first()
        if not test_run:
            raise ValueError(f"TestRun with ID '{test_run_id}' does not exist.")

        # Safeguard 1: Reject re-analysis during active runs
        if not allow_active and test_run.status == "RUNNING":
            raise ActiveRunAnalysisError(
                f"Cannot analyze test run '{test_run_id}' while execution is actively running."
            )

        # Safeguard 2: Query only TestCases belonging strictly to current run's project
        project_test_cases = (
            db.query(TestCase)
            .filter(TestCase.project_id == test_run.project_id)
            .order_by(TestCase.file_path.asc(), TestCase.test_name.asc())
            .all()
        )

        # Query all iterations for this run
        all_iterations = (
            db.query(TestIteration)
            .filter(TestIteration.test_run_id == test_run_id)
            .order_by(TestIteration.iteration_number.asc())
            .all()
        )

        # Group iterations by test_case_id
        iterations_by_case = {}
        for it in all_iterations:
            iterations_by_case.setdefault(it.test_case_id, []).append(it)

        # Map existing FlakinessReport records for idempotent upsert
        existing_reports = {
            rep.test_case_id: rep
            for rep in db.query(FlakinessReport).filter(FlakinessReport.test_run_id == test_run_id).all()
        }

        generated_reports: List[FlakinessReport] = []

        # Analyze every discovered test case belonging to the project
        for tc in project_test_cases:
            case_iters = iterations_by_case.get(tc.id, [])
            report = self._compute_test_case_report(
                test_run_id=test_run_id,
                test_case_id=tc.id,
                iterations=case_iters,
                existing_report=existing_reports.get(tc.id),
            )
            db.add(report)
            generated_reports.append(report)

        # Flush reports to database before recalculating aggregate counters
        db.flush()

        # Safeguard 3: Recalculate ALL TestRun counters strictly from current reports
        test_run.consistently_passing_count = sum(
            1 for r in generated_reports if r.outcome_classification == "CONSISTENTLY_PASSING"
        )
        test_run.consistently_failing_count = sum(
            1 for r in generated_reports if r.outcome_classification == "CONSISTENTLY_FAILING"
        )
        test_run.flaky_tests_count = sum(
            1 for r in generated_reports if r.outcome_classification == "FLAKY"
        )
        test_run.insufficient_data_count = sum(
            1 for r in generated_reports if r.outcome_classification == "INSUFFICIENT_DATA"
        )

        db.commit()

        # Refresh objects to return clean state
        for r in generated_reports:
            db.refresh(r)
        db.refresh(test_run)

        return generated_reports

    def _compute_test_case_report(
        self,
        test_run_id: str,
        test_case_id: str,
        iterations: List[TestIteration],
        existing_report: Optional[FlakinessReport] = None,
    ) -> FlakinessReport:
        """
        Computes flakiness score, flip count, and outcome classification for a single test case.
        """
        # Sort iterations chronologically by iteration_number
        sorted_iters = sorted(iterations, key=lambda x: x.iteration_number)

        # Filter strictly valid executions (PASSED, FAILED, TIMED_OUT)
        # Exclude SKIPPED, CANCELLED, NOT_EXECUTED
        valid_iters = [it for it in sorted_iters if it.status in self.VALID_STATUSES]

        pass_count = sum(1 for it in valid_iters if it.status in self.VALID_PASS_STATUSES)
        fail_count = sum(1 for it in valid_iters if it.status in self.VALID_FAIL_STATUSES)
        total_valid = pass_count + fail_count

        # Compute consecutive flip count (kappa)
        flip_count = 0
        if total_valid > 1:
            for i in range(len(valid_iters) - 1):
                curr_is_pass = valid_iters[i].status in self.VALID_PASS_STATUSES
                next_is_pass = valid_iters[i + 1].status in self.VALID_PASS_STATUSES
                if curr_is_pass != next_is_pass:
                    flip_count += 1

        # Classification and flakiness score calculation
        if total_valid < self.min_samples_threshold:
            classification = "INSUFFICIENT_DATA"
            flakiness_score = 0.0
        else:
            if fail_count == 0:
                classification = "CONSISTENTLY_PASSING"
                flakiness_score = 0.0
            elif pass_count == 0:
                classification = "CONSISTENTLY_FAILING"
                flakiness_score = 0.0
            else:
                classification = "FLAKY"
                pass_rate = pass_count / float(total_valid)
                # Formula: F = 1 - |2P - 1|
                flakiness_score = round(1.0 - abs(2.0 * pass_rate - 1.0), 4)

        if existing_report is not None:
            report = existing_report
            report.outcome_classification = classification
            report.flakiness_score = flakiness_score
            report.total_runs = total_valid
            report.pass_count = pass_count
            report.fail_count = fail_count
            report.flip_count = flip_count
            # Safeguard 5: RCA fields remain strictly NULL
            report.root_cause_category = None
            report.confidence_score = 0.0
            report.rca_summary = None
            report.recommendations = None
        else:
            report = FlakinessReport(
                test_run_id=test_run_id,
                test_case_id=test_case_id,
                outcome_classification=classification,
                flakiness_score=flakiness_score,
                total_runs=total_valid,
                pass_count=pass_count,
                fail_count=fail_count,
                flip_count=flip_count,
                # Safeguard 5: RCA fields remain strictly NULL
                root_cause_category=None,
                confidence_score=0.0,
                rca_summary=None,
                recommendations=None,
            )

        return report

