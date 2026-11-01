import logging
from typing import Dict, List, Optional
from sqlalchemy.orm import Session, joinedload

from backend.app.db.models import Project, TestRun, TestCase, FlakinessReport, RunIteration
from backend.app.schemas.run import TestRunResponse
from backend.app.schemas.verification import (
    FixVerificationVerdict,
    TestVerificationDetail,
    FixVerificationResponse,
)

logger = logging.getLogger("flakelens.core.verification")


class VerificationError(Exception):
    """Raised when fix verification evaluation fails."""
    pass


class FixVerificationEngine:
    """
    Evaluates fix verification runs against their historical baseline.
    Enforces strict empirical stability rules:
    - Never marks a fix verified after a single passing run or below threshold executions (< 5).
    - Evaluates whether the test is genuinely stable (100% pass rate, 0 flips, 0 failures across >= 5 runs).
    - Accurately reports ongoing flakiness or regressions.
    """

    MIN_VERIFICATION_THRESHOLD = 5

    def evaluate_verification(
        self,
        verification_run_id: str,
        db: Session,
    ) -> FixVerificationResponse:
        v_run = db.query(TestRun).filter(TestRun.id == verification_run_id).first()
        if not v_run:
            raise VerificationError(f"Verification run '{verification_run_id}' not found.")

        if not v_run.baseline_run_id:
            raise VerificationError(
                f"TestRun '{verification_run_id}' is not linked to a baseline run (baseline_run_id is NULL)."
            )

        b_run = db.query(TestRun).filter(TestRun.id == v_run.baseline_run_id).first()
        if not b_run:
            raise VerificationError(f"Baseline run '{v_run.baseline_run_id}' not found.")

        # Load reports for baseline and verification
        b_reports = (
            db.query(FlakinessReport)
            .options(joinedload(FlakinessReport.test_case))
            .filter(FlakinessReport.test_run_id == b_run.id)
            .all()
        )
        v_reports = (
            db.query(FlakinessReport)
            .options(joinedload(FlakinessReport.test_case))
            .filter(FlakinessReport.test_run_id == v_run.id)
            .all()
        )

        b_map: Dict[str, FlakinessReport] = {r.test_case_id: r for r in b_reports}
        v_map: Dict[str, FlakinessReport] = {r.test_case_id: r for r in v_reports}

        # If verification run targeted a specific test case, filter to it; otherwise all in verification
        target_tc_ids = (
            [v_run.target_test_case_id]
            if v_run.target_test_case_id
            else list(v_map.keys())
        )

        test_details: List[TestVerificationDetail] = []
        fixed_count = 0
        flaky_count = 0
        failing_count = 0
        inconclusive_count = 0

        for tc_id in target_tc_ids:
            v_rep = v_map.get(tc_id)
            b_rep = b_map.get(tc_id)

            tc = (
                v_rep.test_case
                if (v_rep and v_rep.test_case)
                else (b_rep.test_case if (b_rep and b_rep.test_case) else None)
            )
            if not tc:
                tc = db.query(TestCase).filter(TestCase.id == tc_id).first()

            node_id = tc.node_id if tc else tc_id
            test_name = tc.test_name if tc else "Unknown"
            file_path = tc.file_path if tc else ""

            b_status = b_rep.outcome_classification if b_rep else "UNKNOWN"
            b_score = round(b_rep.flakiness_score, 4) if b_rep else 0.0
            b_pass = b_rep.pass_count if b_rep else 0
            b_fail = b_rep.fail_count if b_rep else 0
            b_total = b_rep.total_runs if b_rep else 0
            b_rca = b_rep.root_cause_category if b_rep else None

            v_status = v_rep.outcome_classification if v_rep else "UNKNOWN"
            v_score = round(v_rep.flakiness_score, 4) if v_rep else 0.0
            v_pass = v_rep.pass_count if v_rep else 0
            v_fail = v_rep.fail_count if v_rep else 0
            v_total = v_rep.total_runs if v_rep else 0

            # Rule 1: Cannot mark verified fixed with insufficient executions
            if v_total < self.MIN_VERIFICATION_THRESHOLD:
                verdict = FixVerificationVerdict.INCONCLUSIVE
                verdict_msg = (
                    f"Inconclusive: Test completed {v_total} valid execution(s), but a minimum of "
                    f"{self.MIN_VERIFICATION_THRESHOLD} repeated executions are required to confirm fix stability."
                )
                is_stable = False
                inconclusive_count += 1
            # Rule 2: 100% pass rate, 0 failures, 0 flips across >= threshold executions
            elif v_status == "CONSISTENTLY_PASSING" and v_fail == 0:
                verdict = FixVerificationVerdict.VERIFIED_FIXED
                verdict_msg = (
                    f"Fix Verified: Test passed consistently in all {v_total}/{v_total} repeated executions "
                    f"(100% stability, flakiness score reduced from {b_score:.4f} to 0.0000)."
                )
                is_stable = True
                fixed_count += 1
            # Rule 3: Flakiness persists
            elif v_status == "FLAKY" or (v_pass > 0 and v_fail > 0):
                verdict = FixVerificationVerdict.STILL_FLAKY
                verdict_msg = (
                    f"Fix Ineffective: Test remains flaky with {v_fail} failure(s) across {v_total} runs "
                    f"(flakiness score: {v_score:.4f})."
                )
                is_stable = False
                flaky_count += 1
            # Rule 4: Deterministic failure
            elif v_status == "CONSISTENTLY_FAILING" or v_pass == 0:
                verdict = FixVerificationVerdict.STILL_FAILING
                verdict_msg = (
                    f"Regression / Persistent Bug: Test failed in 100% of verification executions ({v_fail}/{v_total})."
                )
                is_stable = False
                failing_count += 1
            else:
                verdict = FixVerificationVerdict.INCONCLUSIVE
                verdict_msg = f"Inconclusive: Execution telemetry state is '{v_status}'."
                is_stable = False
                inconclusive_count += 1

            test_details.append(
                TestVerificationDetail(
                    test_case_id=tc_id,
                    node_id=node_id,
                    test_name=test_name,
                    file_path=file_path,
                    baseline_status=b_status,
                    baseline_flakiness_score=b_score,
                    baseline_pass_count=b_pass,
                    baseline_fail_count=b_fail,
                    baseline_total_runs=b_total,
                    baseline_rca_category=b_rca,
                    verification_status=v_status,
                    verification_flakiness_score=v_score,
                    verification_pass_count=v_pass,
                    verification_fail_count=v_fail,
                    verification_total_runs=v_total,
                    verdict=verdict,
                    verdict_message=verdict_msg,
                    is_stable=is_stable,
                )
            )

        # Overall verdict
        if not test_details:
            overall_verdict = FixVerificationVerdict.INCONCLUSIVE
            verdict_summary = "No tests were evaluated in this verification run."
        elif all(t.verdict == FixVerificationVerdict.VERIFIED_FIXED for t in test_details):
            overall_verdict = FixVerificationVerdict.VERIFIED_FIXED
            verdict_summary = (
                f"All {len(test_details)} evaluated test(s) achieved 100% stability across repeated executions."
            )
        elif any(t.verdict == FixVerificationVerdict.STILL_FLAKY for t in test_details):
            overall_verdict = FixVerificationVerdict.STILL_FLAKY
            verdict_summary = f"{flaky_count} test(s) continue to exhibit non-deterministic failures."
        elif any(t.verdict == FixVerificationVerdict.STILL_FAILING for t in test_details):
            overall_verdict = FixVerificationVerdict.STILL_FAILING
            verdict_summary = f"{failing_count} test(s) failed consistently during verification."
        else:
            overall_verdict = FixVerificationVerdict.INCONCLUSIVE
            verdict_summary = "Verification run produced insufficient or inconclusive telemetry."

        project = db.query(Project).filter(Project.id == v_run.project_id).first()
        proj_name = project.name if project else "Unknown"

        def _build_dto(r: TestRun) -> TestRunResponse:
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
                project_name=proj_name,
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

        return FixVerificationResponse(
            verification_run=_build_dto(v_run),
            baseline_run=_build_dto(b_run),
            overall_verdict=overall_verdict,
            verdict_summary=verdict_summary,
            tests=test_details,
        )

