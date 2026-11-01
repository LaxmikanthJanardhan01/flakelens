import logging
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session, joinedload

from backend.app.db.models import Project, TestRun, TestCase, FlakinessReport, TestIteration, RunIteration
from backend.app.schemas.comparison import (
    TestTransition,
    TestComparisonItem,
    ComparisonSummaryDelta,
    RunComparisonResponse,
)
from backend.app.schemas.run import TestRunResponse

logger = logging.getLogger("flakelens.core.comparator")


class ComparisonError(Exception):
    """Raised when execution comparison validation fails."""
    pass


class ExecutionComparator:
    """
    Compares two completed execution sessions of the same project.
    Identifies test transitions (recovered, newly failing, still flaky),
    calculates empirical metrics deltas (scores, pass rates, durations),
    and strictly avoids fabricating missing historical data.
    """

    def compare_runs(
        self,
        run_a_id: str,
        run_b_id: str,
        db: Session,
    ) -> RunComparisonResponse:
        """
        Executes a rigorous comparison between Run A (baseline) and Run B (comparison).
        """
        run_a = db.query(TestRun).filter(TestRun.id == run_a_id).first()
        if not run_a:
            raise ComparisonError(f"Baseline TestRun with ID '{run_a_id}' does not exist.")

        run_b = db.query(TestRun).filter(TestRun.id == run_b_id).first()
        if not run_b:
            raise ComparisonError(f"Comparison TestRun with ID '{run_b_id}' does not exist.")

        if run_a.project_id != run_b.project_id:
            raise ComparisonError(
                f"Cannot compare runs from different projects: Run '{run_a_id}' belongs to project "
                f"'{run_a.project_id}', but Run '{run_b_id}' belongs to project '{run_b.project_id}'."
            )

        if run_a.status in ("RUNNING", "PENDING"):
            raise ComparisonError(f"Baseline Run '{run_a_id}' is still in progress (status: {run_a.status}).")

        if run_b.status in ("RUNNING", "PENDING"):
            raise ComparisonError(f"Comparison Run '{run_b_id}' is still in progress (status: {run_b.status}).")

        project = db.query(Project).filter(Project.id == run_a.project_id).first()
        project_name = project.name if project else "Unknown Project"

        # Load reports for both runs
        reports_a = (
            db.query(FlakinessReport)
            .options(joinedload(FlakinessReport.test_case))
            .filter(FlakinessReport.test_run_id == run_a_id)
            .all()
        )
        reports_b = (
            db.query(FlakinessReport)
            .options(joinedload(FlakinessReport.test_case))
            .filter(FlakinessReport.test_run_id == run_b_id)
            .all()
        )

        rep_map_a: Dict[str, FlakinessReport] = {r.test_case_id: r for r in reports_a}
        rep_map_b: Dict[str, FlakinessReport] = {r.test_case_id: r for r in reports_b}

        # Load iterations to calculate average durations
        iters_a = db.query(TestIteration).filter(TestIteration.test_run_id == run_a_id).all()
        iters_b = db.query(TestIteration).filter(TestIteration.test_run_id == run_b_id).all()

        durations_a: Dict[str, List[float]] = {}
        for it in iters_a:
            if it.duration_ms > 0:
                durations_a.setdefault(it.test_case_id, []).append(it.duration_ms)

        durations_b: Dict[str, List[float]] = {}
        for it in iters_b:
            if it.duration_ms > 0:
                durations_b.setdefault(it.test_case_id, []).append(it.duration_ms)

        # Build union of test cases
        all_tc_ids = set(rep_map_a.keys()).union(set(rep_map_b.keys()))
        all_test_cases = db.query(TestCase).filter(TestCase.id.in_(all_tc_ids)).all() if all_tc_ids else []
        tc_dict = {tc.id: tc for tc in all_test_cases}

        test_comparisons: List[TestComparisonItem] = []
        recovered_count = 0
        newly_failing_count = 0
        newly_flaky_count = 0
        still_flaky_count = 0
        still_failing_count = 0
        unchanged_passing_count = 0

        for tc_id in sorted(all_tc_ids, key=lambda tid: tc_dict.get(tid).node_id if tc_dict.get(tid) else tid):
            tc = tc_dict.get(tc_id)
            node_id = tc.node_id if tc else tc_id
            test_name = tc.test_name if tc else "Unknown"
            file_path = tc.file_path if tc else ""

            rep_a = rep_map_a.get(tc_id)
            rep_b = rep_map_b.get(tc_id)

            status_a = rep_a.outcome_classification if rep_a else None
            status_b = rep_b.outcome_classification if rep_b else None

            flakiness_a = round(rep_a.flakiness_score, 4) if rep_a else None
            flakiness_b = round(rep_b.flakiness_score, 4) if rep_b else None
            flakiness_delta = (
                round(flakiness_b - flakiness_a, 4)
                if (flakiness_a is not None and flakiness_b is not None)
                else None
            )

            pass_rate_a = (
                round(rep_a.pass_count / rep_a.total_runs, 4)
                if (rep_a and rep_a.total_runs > 0)
                else None
            )
            pass_rate_b = (
                round(rep_b.pass_count / rep_b.total_runs, 4)
                if (rep_b and rep_b.total_runs > 0)
                else None
            )

            durs_a = durations_a.get(tc_id, [])
            avg_dur_a = round(sum(durs_a) / len(durs_a), 2) if durs_a else None

            durs_b = durations_b.get(tc_id, [])
            avg_dur_b = round(sum(durs_b) / len(durs_b), 2) if durs_b else None

            dur_delta = (
                round(avg_dur_b - avg_dur_a, 2)
                if (avg_dur_a is not None and avg_dur_b is not None)
                else None
            )

            rca_a = rep_a.root_cause_category if rep_a else None
            rca_b = rep_b.root_cause_category if rep_b else None

            # Determine Transition
            if rep_a and not rep_b:
                transition = TestTransition.REMOVED
            elif not rep_a and rep_b:
                transition = TestTransition.ADDED
            else:
                # Both present
                if status_a == "CONSISTENTLY_PASSING" and status_b == "CONSISTENTLY_PASSING":
                    transition = TestTransition.UNCHANGED_PASSING
                    unchanged_passing_count += 1
                elif status_a in ("FLAKY", "CONSISTENTLY_FAILING") and status_b == "CONSISTENTLY_PASSING":
                    transition = TestTransition.RECOVERED
                    recovered_count += 1
                elif status_a == "CONSISTENTLY_PASSING" and status_b == "CONSISTENTLY_FAILING":
                    transition = TestTransition.NEWLY_FAILING
                    newly_failing_count += 1
                elif status_a in ("CONSISTENTLY_PASSING", "CONSISTENTLY_FAILING") and status_b == "FLAKY":
                    transition = TestTransition.NEWLY_FLAKY
                    newly_flaky_count += 1
                elif status_a == "FLAKY" and status_b == "FLAKY":
                    transition = TestTransition.STILL_FLAKY
                    still_flaky_count += 1
                elif status_a == "CONSISTENTLY_FAILING" and status_b == "CONSISTENTLY_FAILING":
                    transition = TestTransition.STILL_FAILING
                    still_failing_count += 1
                else:
                    transition = TestTransition.INCONCLUSIVE

            test_comparisons.append(
                TestComparisonItem(
                    test_case_id=tc_id,
                    node_id=node_id,
                    test_name=test_name,
                    file_path=file_path,
                    status_a=status_a,
                    status_b=status_b,
                    flakiness_score_a=flakiness_a,
                    flakiness_score_b=flakiness_b,
                    flakiness_score_delta=flakiness_delta,
                    pass_rate_a=pass_rate_a,
                    pass_rate_b=pass_rate_b,
                    avg_duration_ms_a=avg_dur_a,
                    avg_duration_ms_b=avg_dur_b,
                    duration_delta_ms=dur_delta,
                    transition=transition,
                    rca_category_a=rca_a,
                    rca_category_b=rca_b,
                )
            )

        summary_delta = ComparisonSummaryDelta(
            total_tests_delta=run_b.total_tests - run_a.total_tests,
            flaky_count_delta=run_b.flaky_tests_count - run_a.flaky_tests_count,
            passing_count_delta=run_b.consistently_passing_count - run_a.consistently_passing_count,
            failing_count_delta=run_b.consistently_failing_count - run_a.consistently_failing_count,
            recovered_count=recovered_count,
            newly_failing_count=newly_failing_count,
            newly_flaky_count=newly_flaky_count,
            still_flaky_count=still_flaky_count,
            still_failing_count=still_failing_count,
            unchanged_passing_count=unchanged_passing_count,
        )

        def _build_run_dto(r: TestRun) -> TestRunResponse:
            completed_count = (
                db.query(RunIteration)
                .filter(RunIteration.test_run_id == r.id, RunIteration.status == "COMPLETED")
                .count()
            )
            duration_sec = None
            if r.started_at and r.completed_at:
                duration_sec = round((r.completed_at - r.started_at).total_seconds(), 2)

            return TestRunResponse(
                id=r.id,
                project_id=r.project_id,
                project_name=project_name,
                run_type=r.run_type,
                baseline_run_id=r.baseline_run_id,
                target_test_case_id=r.target_test_case_id,
                iteration_count=r.iteration_count,
                completed_iterations=completed_count,
                shuffle_order=r.shuffle_order,
                status=r.status,
                total_tests=r.total_tests,
                consistently_passing_count=r.consistently_passing_count,
                consistently_failing_count=r.consistently_failing_count,
                flaky_tests_count=r.flaky_tests_count,
                insufficient_data_count=r.insufficient_data_count,
                duration_seconds=duration_sec,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )

        return RunComparisonResponse(
            project_id=run_a.project_id,
            project_name=project_name,
            run_a=_build_run_dto(run_a),
            run_b=_build_run_dto(run_b),
            summary_delta=summary_delta,
            test_comparisons=test_comparisons,
        )

