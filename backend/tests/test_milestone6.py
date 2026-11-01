import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.db.session import Base, get_db
from backend.app.db.models import Project, TestCase, TestRun, TestIteration, RunIteration, FlakinessReport
from backend.app.core.comparator import ExecutionComparator, ComparisonError
from backend.app.core.verification import FixVerificationEngine, VerificationError
from backend.app.schemas.comparison import TestTransition
from backend.app.schemas.verification import FixVerificationVerdict


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ============================================================================
# Helper Functions
# ============================================================================

def create_project(db: sessionmaker, name: str = "Test Project") -> Project:
    proj = Project(id=str(uuid.uuid4()), name=name, source_archive_path="/fake/path")
    db.add(proj)
    db.commit()
    return proj


def create_test_case(db: sessionmaker, project_id: str, node_id: str) -> TestCase:
    parts = node_id.split("::")
    file_path = parts[0]
    test_name = parts[-1]
    tc = TestCase(
        id=str(uuid.uuid4()),
        project_id=project_id,
        file_path=file_path,
        test_name=test_name,
        node_id=node_id,
    )
    db.add(tc)
    db.commit()
    return tc


def create_run(
    db: sessionmaker,
    project_id: str,
    status: str = "COMPLETED",
    iteration_count: int = 10,
    run_type: str = "STANDARD",
    baseline_run_id: str = None,
    target_test_case_id: str = None,
    started_at: datetime = None,
    completed_at: datetime = None,
) -> TestRun:
    now = datetime.now(timezone.utc)
    run = TestRun(
        id=str(uuid.uuid4()),
        project_id=project_id,
        iteration_count=iteration_count,
        shuffle_order=True,
        run_type=run_type,
        baseline_run_id=baseline_run_id,
        target_test_case_id=target_test_case_id,
        status=status,
        total_tests=0,
        consistently_passing_count=0,
        consistently_failing_count=0,
        flaky_tests_count=0,
        insufficient_data_count=0,
        started_at=started_at or now,
        completed_at=completed_at or (now + timedelta(seconds=15)),
    )
    db.add(run)
    db.commit()
    return run


def add_flakiness_report(
    db: sessionmaker,
    run_id: str,
    test_case_id: str,
    outcome: str,
    flakiness_score: float = 0.0,
    pass_count: int = 0,
    fail_count: int = 0,
    flip_count: int = 0,
    total_runs: int = 10,
    rca_category: str = None,
) -> FlakinessReport:
    rep = FlakinessReport(
        id=str(uuid.uuid4()),
        test_run_id=run_id,
        test_case_id=test_case_id,
        outcome_classification=outcome,
        flakiness_score=flakiness_score,
        total_runs=total_runs,
        pass_count=pass_count,
        fail_count=fail_count,
        flip_count=flip_count,
        root_cause_category=rca_category,
        confidence_score=0.85 if outcome != "CONSISTENTLY_PASSING" else 0.0,
        rca_summary="Sample RCA summary",
        recommendations="Sample recommendations",
    )
    db.add(rep)
    db.commit()
    return rep


# ============================================================================
# 1. DETAILED REPORTS & TELEMETRY TESTS
# ============================================================================

class TestDetailedReports:
    def test_detailed_run_report_success(self, test_db, client):
        """Verifies detailed report endpoint returns full per-test iteration breakdown and duration stats."""
        proj = create_project(test_db, "Detailed Project")
        tc = create_test_case(test_db, proj.id, "tests/test_detail.py::test_alpha")
        run = create_run(test_db, proj.id)

        # Add iterations
        for i in range(1, 6):
            status = "PASSED" if i <= 3 else "FAILED"
            dur = 20.0 + (i * 5.0)
            test_db.add(TestIteration(
                id=str(uuid.uuid4()),
                test_run_id=run.id,
                test_case_id=tc.id,
                iteration_number=i,
                status=status,
                duration_ms=dur,
                execution_order=i,
                stdout=f"stdout log iter {i}",
                stderr=f"stderr log iter {i}" if status == "FAILED" else None,
                error_message="AssertionError: failed" if status == "FAILED" else None,
            ))
        test_db.commit()

        add_flakiness_report(
            test_db, run.id, tc.id, outcome="FLAKY", flakiness_score=0.48,
            pass_count=3, fail_count=2, flip_count=2, total_runs=5, rca_category="TIMING_OR_RACE_CONDITION"
        )

        res = client.get(f"/api/reports/run/{run.id}/detailed")
        assert res.status_code == 200
        data = res.json()

        assert data["run_id"] == run.id
        assert data["project_name"] == "Detailed Project"
        assert len(data["reports"]) == 1

        rep = data["reports"][0]
        assert rep["node_id"] == "tests/test_detail.py::test_alpha"
        assert rep["outcome_classification"] == "FLAKY"
        assert len(rep["iterations"]) == 5
        assert rep["pass_rate"] == 0.60
        assert rep["min_duration_ms"] == 25.0
        assert rep["max_duration_ms"] == 45.0
        assert rep["avg_duration_ms"] == 35.0

    def test_detailed_run_report_404_on_invalid_run(self, client):
        res = client.get("/api/reports/run/nonexistent-run-id/detailed")
        assert res.status_code == 404

    def test_iteration_diff_success(self, test_db, client):
        """Verifies iteration diff endpoint compares passing and failing executions."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_diff.py::test_diff_case")
        run = create_run(test_db, proj.id)

        # Iteration 1: Pass
        test_db.add(TestIteration(
            id=str(uuid.uuid4()),
            test_run_id=run.id,
            test_case_id=tc.id,
            iteration_number=1,
            status="PASSED",
            duration_ms=100.0,
            execution_order=1,
            stdout="Pass log line 1\nPass log line 2\n",
        ))
        # Iteration 2: Fail
        test_db.add(TestIteration(
            id=str(uuid.uuid4()),
            test_run_id=run.id,
            test_case_id=tc.id,
            iteration_number=2,
            status="FAILED",
            duration_ms=250.0,
            execution_order=2,
            stdout="Pass log line 1\nFail error occurred\n",
            stderr="Traceback: line 10 AssertionError\n",
            error_message="AssertionError: expected True got False",
        ))
        test_db.commit()

        res = client.get(f"/api/reports/run/{run.id}/diff/{tc.id}")
        assert res.status_code == 200
        data = res.json()

        assert data["test_case_id"] == tc.id
        assert data["node_id"] == "tests/test_diff.py::test_diff_case"
        assert data["passing_iteration"]["iteration_number"] == 1
        assert data["failing_iteration"]["iteration_number"] == 2
        assert data["duration_delta_ms"] == 150.0
        assert data["stdout_diff"] is not None
        assert "Pass log line 1" in data["stdout_diff"]


# ============================================================================
# 2. EXECUTION COMPARISONS TESTS
# ============================================================================

class TestExecutionComparisons:
    def test_comparison_all_transitions(self, test_db):
        """
        Creates two runs of the same project and rigorously verifies all 8 test transitions:
        RECOVERED, NEWLY_FAILING, NEWLY_FLAKY, STILL_FLAKY, STILL_FAILING, UNCHANGED_PASSING, ADDED, REMOVED.
        """
        proj = create_project(test_db, "Compare Project")

        tc_rec = create_test_case(test_db, proj.id, "tests/t.py::test_recovered")
        tc_reg = create_test_case(test_db, proj.id, "tests/t.py::test_newly_failing")
        tc_flk = create_test_case(test_db, proj.id, "tests/t.py::test_newly_flaky")
        tc_stf = create_test_case(test_db, proj.id, "tests/t.py::test_still_flaky")
        tc_stfail = create_test_case(test_db, proj.id, "tests/t.py::test_still_failing")
        tc_pass = create_test_case(test_db, proj.id, "tests/t.py::test_unchanged_pass")
        tc_add = create_test_case(test_db, proj.id, "tests/t.py::test_added")
        tc_rem = create_test_case(test_db, proj.id, "tests/t.py::test_removed")

        run_a = create_run(test_db, proj.id)
        run_b = create_run(test_db, proj.id)

        # Baseline Run A reports
        add_flakiness_report(test_db, run_a.id, tc_rec.id, outcome="FLAKY", flakiness_score=0.45)
        add_flakiness_report(test_db, run_a.id, tc_reg.id, outcome="CONSISTENTLY_PASSING", flakiness_score=0.0)
        add_flakiness_report(test_db, run_a.id, tc_flk.id, outcome="CONSISTENTLY_PASSING", flakiness_score=0.0)
        add_flakiness_report(test_db, run_a.id, tc_stf.id, outcome="FLAKY", flakiness_score=0.50)
        add_flakiness_report(test_db, run_a.id, tc_stfail.id, outcome="CONSISTENTLY_FAILING", flakiness_score=0.0)
        add_flakiness_report(test_db, run_a.id, tc_pass.id, outcome="CONSISTENTLY_PASSING", flakiness_score=0.0)
        add_flakiness_report(test_db, run_a.id, tc_rem.id, outcome="CONSISTENTLY_PASSING", flakiness_score=0.0)
        # Note: tc_add is NOT in Run A

        # Comparison Run B reports
        add_flakiness_report(test_db, run_b.id, tc_rec.id, outcome="CONSISTENTLY_PASSING", flakiness_score=0.0)
        add_flakiness_report(test_db, run_b.id, tc_reg.id, outcome="CONSISTENTLY_FAILING", flakiness_score=0.0)
        add_flakiness_report(test_db, run_b.id, tc_flk.id, outcome="FLAKY", flakiness_score=0.35)
        add_flakiness_report(test_db, run_b.id, tc_stf.id, outcome="FLAKY", flakiness_score=0.40)
        add_flakiness_report(test_db, run_b.id, tc_stfail.id, outcome="CONSISTENTLY_FAILING", flakiness_score=0.0)
        add_flakiness_report(test_db, run_b.id, tc_pass.id, outcome="CONSISTENTLY_PASSING", flakiness_score=0.0)
        add_flakiness_report(test_db, run_b.id, tc_add.id, outcome="CONSISTENTLY_PASSING", flakiness_score=0.0)
        # Note: tc_rem is NOT in Run B

        comparator = ExecutionComparator()
        res = comparator.compare_runs(run_a.id, run_b.id, test_db)

        # Verify summary delta counts
        assert res.summary_delta.recovered_count == 1
        assert res.summary_delta.newly_failing_count == 1
        assert res.summary_delta.newly_flaky_count == 1
        assert res.summary_delta.still_flaky_count == 1
        assert res.summary_delta.still_failing_count == 1
        assert res.summary_delta.unchanged_passing_count == 1

        trans_map = {item.node_id: item.transition for item in res.test_comparisons}
        assert trans_map["tests/t.py::test_recovered"] == TestTransition.RECOVERED
        assert trans_map["tests/t.py::test_newly_failing"] == TestTransition.NEWLY_FAILING
        assert trans_map["tests/t.py::test_newly_flaky"] == TestTransition.NEWLY_FLAKY
        assert trans_map["tests/t.py::test_still_flaky"] == TestTransition.STILL_FLAKY
        assert trans_map["tests/t.py::test_still_failing"] == TestTransition.STILL_FAILING
        assert trans_map["tests/t.py::test_unchanged_pass"] == TestTransition.UNCHANGED_PASSING
        assert trans_map["tests/t.py::test_added"] == TestTransition.ADDED
        assert trans_map["tests/t.py::test_removed"] == TestTransition.REMOVED

    def test_comparison_rejects_cross_project(self, test_db):
        """Cross-project comparisons are strictly rejected with an error."""
        proj_1 = create_project(test_db, "Project 1")
        proj_2 = create_project(test_db, "Project 2")

        run_1 = create_run(test_db, proj_1.id)
        run_2 = create_run(test_db, proj_2.id)

        comparator = ExecutionComparator()
        with pytest.raises(ComparisonError, match="Cannot compare runs from different projects"):
            comparator.compare_runs(run_1.id, run_2.id, test_db)

    def test_comparison_rejects_active_running_run(self, test_db):
        """Comparing an active running run is strictly rejected."""
        proj = create_project(test_db)
        run_1 = create_run(test_db, proj.id, status="COMPLETED")
        run_2 = create_run(test_db, proj.id, status="RUNNING")

        comparator = ExecutionComparator()
        with pytest.raises(ComparisonError, match="Comparison Run .* is still in progress"):
            comparator.compare_runs(run_1.id, run_2.id, test_db)


# ============================================================================
# 3. FIX VERIFICATION TESTS
# ============================================================================

class TestFixVerification:
    def test_single_pass_execution_does_not_mark_verified_fixed(self, test_db):
        """
        MANDATORY REQUIREMENT:
        Do not automatically mark a fix successful after a single passing execution.
        Must enforce minimum threshold of 5 executions.
        """
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_fix.py::test_race")

        b_run = create_run(test_db, proj.id)
        add_flakiness_report(test_db, b_run.id, tc.id, outcome="FLAKY", flakiness_score=0.45)

        # Verification run with only 2 executions (insufficient data)
        v_run = create_run(
            test_db, proj.id, run_type="VERIFICATION", baseline_run_id=b_run.id, target_test_case_id=tc.id
        )
        add_flakiness_report(
            test_db, v_run.id, tc.id, outcome="INSUFFICIENT_DATA",
            pass_count=2, fail_count=0, total_runs=2
        )

        engine = FixVerificationEngine()
        res = engine.evaluate_verification(v_run.id, test_db)

        # Verdict must NOT be VERIFIED_FIXED; must be INCONCLUSIVE
        assert res.overall_verdict == FixVerificationVerdict.INCONCLUSIVE
        assert res.tests[0].verdict == FixVerificationVerdict.INCONCLUSIVE
        assert res.tests[0].is_stable is False
        assert "minimum of 5 repeated executions are required" in res.tests[0].verdict_message

    def test_verified_fixed_requires_full_threshold_and_zero_failures(self, test_db):
        """When a previously flaky test achieves 10/10 passes across >= 5 runs, it is VERIFIED_FIXED."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_fix.py::test_resolved")

        b_run = create_run(test_db, proj.id)
        add_flakiness_report(test_db, b_run.id, tc.id, outcome="FLAKY", flakiness_score=0.50, pass_count=5, fail_count=5)

        v_run = create_run(
            test_db, proj.id, run_type="VERIFICATION", baseline_run_id=b_run.id, target_test_case_id=tc.id
        )
        add_flakiness_report(
            test_db, v_run.id, tc.id, outcome="CONSISTENTLY_PASSING",
            pass_count=10, fail_count=0, total_runs=10, flakiness_score=0.0
        )

        engine = FixVerificationEngine()
        res = engine.evaluate_verification(v_run.id, test_db)

        assert res.overall_verdict == FixVerificationVerdict.VERIFIED_FIXED
        assert res.tests[0].verdict == FixVerificationVerdict.VERIFIED_FIXED
        assert res.tests[0].is_stable is True
        assert "100% stability" in res.tests[0].verdict_message

    def test_verification_detects_persistent_flakiness(self, test_db):
        """If verification executions encounter intermittent failures, it is marked STILL_FLAKY."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_fix.py::test_stubborn_flake")

        b_run = create_run(test_db, proj.id)
        add_flakiness_report(test_db, b_run.id, tc.id, outcome="FLAKY", flakiness_score=0.40)

        v_run = create_run(
            test_db, proj.id, run_type="VERIFICATION", baseline_run_id=b_run.id, target_test_case_id=tc.id
        )
        add_flakiness_report(
            test_db, v_run.id, tc.id, outcome="FLAKY",
            pass_count=7, fail_count=3, total_runs=10, flakiness_score=0.42
        )

        engine = FixVerificationEngine()
        res = engine.evaluate_verification(v_run.id, test_db)

        assert res.overall_verdict == FixVerificationVerdict.STILL_FLAKY
        assert res.tests[0].verdict == FixVerificationVerdict.STILL_FLAKY
        assert res.tests[0].is_stable is False

    def test_verification_api_rejects_active_baseline(self, test_db, client):
        """POST /api/verification rejects if baseline run is still running."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_fix.py::test_sample")
        b_run = create_run(test_db, proj.id, status="RUNNING")

        res = client.post("/api/verification", json={
            "project_id": proj.id,
            "baseline_run_id": b_run.id,
            "target_test_case_id": tc.id,
            "iteration_count": 10,
        })
        assert res.status_code == 409
        assert "still executing" in res.json()["detail"]

    def test_verification_api_rejects_cross_project_baseline(self, test_db, client):
        """POST /api/verification rejects baseline run belonging to different project."""
        proj_1 = create_project(test_db, "Proj 1")
        proj_2 = create_project(test_db, "Proj 2")
        tc = create_test_case(test_db, proj_1.id, "tests/test_fix.py::test_p1")
        b_run = create_run(test_db, proj_2.id, status="COMPLETED")

        res = client.post("/api/verification", json={
            "project_id": proj_1.id,
            "baseline_run_id": b_run.id,
            "target_test_case_id": tc.id,
            "iteration_count": 10,
        })
        assert res.status_code == 400
        assert "must belong to the same project" in res.json()["detail"]


# ============================================================================
# 4. RUN HISTORY FILTERING & SEARCH TESTS
# ============================================================================

class TestRunHistory:
    def test_run_history_filter_by_project(self, test_db, client):
        proj_1 = create_project(test_db, "Alpha Proj")
        proj_2 = create_project(test_db, "Beta Proj")

        run_1 = create_run(test_db, proj_1.id)
        run_2 = create_run(test_db, proj_2.id)

        res = client.get(f"/api/runs?project_id={proj_1.id}")
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 1
        assert items[0]["id"] == run_1.id
        assert items[0]["project_name"] == "Alpha Proj"

    def test_run_history_filter_by_status_and_type(self, test_db, client):
        proj = create_project(test_db)
        r_comp = create_run(test_db, proj.id, status="COMPLETED", run_type="STANDARD")
        r_ver = create_run(test_db, proj.id, status="COMPLETED", run_type="VERIFICATION")
        r_fail = create_run(test_db, proj.id, status="FAILED", run_type="STANDARD")

        res_v = client.get("/api/runs?run_type=VERIFICATION")
        assert res_v.status_code == 200
        assert len(res_v.json()) == 1
        assert res_v.json()[0]["id"] == r_ver.id

        res_f = client.get("/api/runs?status=FAILED")
        assert res_f.status_code == 200
        assert len(res_f.json()) == 1
        assert res_f.json()[0]["id"] == r_fail.id

    def test_run_history_search(self, test_db, client):
        proj_search = create_project(test_db, "Ecommerce Checkout Suite")
        proj_other = create_project(test_db, "Authentication Core")

        r1 = create_run(test_db, proj_search.id)
        r2 = create_run(test_db, proj_other.id)

        res = client.get("/api/runs?search=checkout")
        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["id"] == r1.id

    def test_run_history_sorting(self, test_db, client):
        proj = create_project(test_db)
        now = datetime.now(timezone.utc)

        r_short = create_run(test_db, proj.id, started_at=now, completed_at=now + timedelta(seconds=5))
        r_long = create_run(test_db, proj.id, started_at=now, completed_at=now + timedelta(seconds=60))

        res_desc = client.get("/api/runs?sort_by=duration&sort_order=desc")
        assert res_desc.status_code == 200
        assert res_desc.json()[0]["id"] == r_long.id
        assert res_desc.json()[1]["id"] == r_short.id

