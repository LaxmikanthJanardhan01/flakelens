import os
import uuid
from pathlib import Path
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.db.session import Base
from backend.app.db.models import Project, TestCase, TestRun, RunIteration, TestIteration, FlakinessReport
from backend.app.db.migrate import migrate_db
from backend.app.core.discovery import discover_and_register_tests
from backend.app.core.runner import ExecutionRunner
from backend.app.core.detector import FlakinessDetector, ActiveRunAnalysisError
from backend.app.main import app
from backend.app.db.session import get_db

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture
def test_db():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    migrate_db(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    db.session_factory = TestingSessionLocal
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


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


def create_sample_project_and_test(db, name="Test Project", node_id="tests/test_demo.py::test_sample"):
    proj = Project(
        id=str(uuid.uuid4()),
        name=name,
    )
    db.add(proj)
    db.flush()

    tc = TestCase(
        id=str(uuid.uuid4()),
        project_id=proj.id,
        node_id=node_id,
        test_name=node_id.split("::")[-1],
        file_path=node_id.split("::")[0],
    )
    db.add(tc)
    db.flush()
    return proj, tc


def create_test_run(db, project_id, iteration_count=10, status="COMPLETED"):
    run = TestRun(
        id=str(uuid.uuid4()),
        project_id=project_id,
        iteration_count=iteration_count,
        shuffle_order=True,
        status=status,
        total_tests=1,
    )
    db.add(run)
    db.flush()
    return run


def add_iterations(db, run_id, tc_id, status_sequence):
    """Helper to add sequential iterations with given statuses."""
    for idx, st in enumerate(status_sequence, start=1):
        ti = TestIteration(
            id=str(uuid.uuid4()),
            test_run_id=run_id,
            test_case_id=tc_id,
            iteration_number=idx,
            status=st,
            duration_ms=10.0,
            execution_order=idx,
        )
        db.add(ti)
    db.commit()


# =========================================================================
# 1. MINIMUM VALID EXECUTION THRESHOLD TESTS (<5 runs -> INSUFFICIENT_DATA)
# =========================================================================
class TestMinimumValidExecutionThreshold:
    def test_under_threshold_flaky_sequence_classified_as_insufficient_data(self, test_db):
        """2 runs with [PASS, FAIL] must be INSUFFICIENT_DATA, not FLAKY."""
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["PASSED", "FAILED"])

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)

        assert len(reports) == 1
        rep = reports[0]
        assert rep.outcome_classification == "INSUFFICIENT_DATA"
        assert rep.flakiness_score == 0.0
        assert rep.total_runs == 2
        assert rep.pass_count == 1
        assert rep.fail_count == 1
        assert rep.flip_count == 1

        # Summary counters on TestRun
        assert run.consistently_passing_count == 0
        assert run.consistently_failing_count == 0
        assert run.flaky_tests_count == 0
        assert run.insufficient_data_count == 1

    def test_under_threshold_passing_sequence_classified_as_insufficient_data(self, test_db):
        """4 runs with [PASS, PASS, PASS, PASS] must be INSUFFICIENT_DATA, not CONSISTENTLY_PASSING."""
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["PASSED", "PASSED", "PASSED", "PASSED"])

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)

        assert len(reports) == 1
        rep = reports[0]
        assert rep.outcome_classification == "INSUFFICIENT_DATA"
        assert rep.flakiness_score == 0.0
        assert rep.total_runs == 4
        assert rep.pass_count == 4
        assert rep.fail_count == 0
        assert rep.flip_count == 0
        assert run.insufficient_data_count == 1


# =========================================================================
# 2. CLUSTERED FAILURES VS ALTERNATING OUTCOMES (SAME F, DIFFERENT KAPPA)
# =========================================================================
class TestClusteredVsAlternatingOutcomes:
    def test_same_flakiness_score_different_flip_counts(self, test_db):
        """
        Test A: [P, P, P, P, P, F, F, F, F, F] -> F = 1.0, kappa = 1
        Test B: [P, F, P, F, P, F, P, F, P, F] -> F = 1.0, kappa = 9
        Both tests have 50% pass rate (F = 1.0), but Test B has 9x higher temporal volatility.
        """
        proj = Project(id=str(uuid.uuid4()), name="Multi-Test Project")
        test_db.add(proj)
        test_db.flush()

        tc_a = TestCase(
            id=str(uuid.uuid4()),
            project_id=proj.id,
            node_id="tests/test_x.py::test_clustered",
            test_name="test_clustered",
            file_path="tests/test_x.py",
        )
        tc_b = TestCase(
            id=str(uuid.uuid4()),
            project_id=proj.id,
            node_id="tests/test_x.py::test_alternating",
            test_name="test_alternating",
            file_path="tests/test_x.py",
        )
        test_db.add_all([tc_a, tc_b])
        test_db.flush()

        run = TestRun(
            id=str(uuid.uuid4()),
            project_id=proj.id,
            iteration_count=10,
            status="COMPLETED",
            total_tests=2,
        )
        test_db.add(run)
        test_db.flush()

        # Test A: Clustered (5 P followed by 5 F)
        add_iterations(test_db, run.id, tc_a.id, ["PASSED"] * 5 + ["FAILED"] * 5)
        # Test B: Alternating (P, F, P, F, ...)
        add_iterations(test_db, run.id, tc_b.id, ["PASSED", "FAILED"] * 5)

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)
        assert len(reports) == 2

        rep_map = {r.test_case_id: r for r in reports}
        rep_a = rep_map[tc_a.id]
        rep_b = rep_map[tc_b.id]

        # Both are FLAKY with F = 1.0
        assert rep_a.outcome_classification == "FLAKY"
        assert rep_b.outcome_classification == "FLAKY"
        assert rep_a.flakiness_score == 1.0
        assert rep_b.flakiness_score == 1.0

        # Flip counts strictly distinguish volatility
        assert rep_a.flip_count == 1
        assert rep_b.flip_count == 9

        # Run counters
        assert run.flaky_tests_count == 2
        assert run.consistently_passing_count == 0
        assert run.consistently_failing_count == 0
        assert run.insufficient_data_count == 0


# =========================================================================
# 3. THRESHOLD BOUNDARY TESTS (EXACTLY 5 RUNS)
# =========================================================================
class TestThresholdBoundary:
    def test_five_passes_classified_consistently_passing(self, test_db):
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["PASSED"] * 5)

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)
        rep = reports[0]

        assert rep.outcome_classification == "CONSISTENTLY_PASSING"
        assert rep.flakiness_score == 0.0
        assert rep.total_runs == 5
        assert rep.pass_count == 5
        assert rep.fail_count == 0
        assert rep.flip_count == 0
        assert run.consistently_passing_count == 1

    def test_five_fails_classified_consistently_failing(self, test_db):
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["FAILED"] * 5)

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)
        rep = reports[0]

        assert rep.outcome_classification == "CONSISTENTLY_FAILING"
        assert rep.flakiness_score == 0.0
        assert rep.total_runs == 5
        assert rep.pass_count == 0
        assert rep.fail_count == 5
        assert rep.flip_count == 0
        assert run.consistently_failing_count == 1

    def test_four_passes_one_fail_flaky_score(self, test_db):
        """4 passes, 1 fail -> P = 0.8 -> F = 1 - |2(0.8) - 1| = 0.4."""
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["PASSED", "PASSED", "PASSED", "PASSED", "FAILED"])

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)
        rep = reports[0]

        assert rep.outcome_classification == "FLAKY"
        assert rep.flakiness_score == 0.4
        assert rep.total_runs == 5
        assert rep.pass_count == 4
        assert rep.fail_count == 1
        assert rep.flip_count == 1
        assert run.flaky_tests_count == 1


# =========================================================================
# 4. TIMEOUT HANDLING (TIMED_OUT AS EXECUTION FAILURE)
# =========================================================================
class TestTimeoutHandling:
    def test_timeout_counted_as_failure_in_denominator_and_flips(self, test_db):
        """[P, TIMED_OUT, P, TIMED_OUT, P] -> 3 P, 2 F -> N=5 -> P=0.6 -> F = 0.8, kappa = 4."""
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["PASSED", "TIMED_OUT", "PASSED", "TIMED_OUT", "PASSED"])

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)
        rep = reports[0]

        assert rep.outcome_classification == "FLAKY"
        assert rep.total_runs == 5
        assert rep.pass_count == 3
        assert rep.fail_count == 2
        assert rep.flakiness_score == 0.8  # 1 - |2(0.6) - 1| = 1 - 0.2 = 0.8
        assert rep.flip_count == 4


# =========================================================================
# 5. EXCLUSION OF SKIPPED, CANCELLED, NOT_EXECUTED
# =========================================================================
class TestStatusExclusion:
    def test_unexecuted_statuses_excluded_from_valid_denominator(self, test_db):
        """
        Sequence: [P, CANCELLED, P, NOT_EXECUTED, P, SKIPPED, P, P]
        Valid runs: 5 P (the 3 non-evaluated iterations are strictly excluded).
        Expected: CONSISTENTLY_PASSING (P = 1.0, F = 0.0, kappa = 0).
        """
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(
            test_db,
            run.id,
            tc.id,
            ["PASSED", "CANCELLED", "PASSED", "NOT_EXECUTED", "PASSED", "SKIPPED", "PASSED", "PASSED"],
        )

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)
        rep = reports[0]

        assert rep.outcome_classification == "CONSISTENTLY_PASSING"
        assert rep.flakiness_score == 0.0
        assert rep.total_runs == 5
        assert rep.pass_count == 5
        assert rep.fail_count == 0
        assert rep.flip_count == 0


# =========================================================================
# 6. PARTIALLY COMPLETED RUNS & NEVER-EXECUTED TESTS
# =========================================================================
class TestPartiallyCompletedRunsAndUnexecuted:
    def test_reports_generated_for_every_discovered_test_including_unexecuted(self, test_db):
        """
        Project has 3 discovered tests.
        Run cancelled in iteration 2:
        - Test 1 has 2 passes (INSUFFICIENT_DATA)
        - Test 2 has 1 fail (INSUFFICIENT_DATA)
        - Test 3 was NEVER executed (0 iterations) (INSUFFICIENT_DATA)
        Every discovered test must receive a FlakinessReport.
        """
        proj = Project(id=str(uuid.uuid4()), name="Three Test Proj")
        test_db.add(proj)
        test_db.flush()

        tc1 = TestCase(id=str(uuid.uuid4()), project_id=proj.id, node_id="t.py::t1", test_name="t1", file_path="t.py")
        tc2 = TestCase(id=str(uuid.uuid4()), project_id=proj.id, node_id="t.py::t2", test_name="t2", file_path="t.py")
        tc3 = TestCase(id=str(uuid.uuid4()), project_id=proj.id, node_id="t.py::t3", test_name="t3", file_path="t.py")
        test_db.add_all([tc1, tc2, tc3])
        test_db.flush()

        run = TestRun(id=str(uuid.uuid4()), project_id=proj.id, iteration_count=10, status="CANCELLED", total_tests=3)
        test_db.add(run)
        test_db.flush()

        add_iterations(test_db, run.id, tc1.id, ["PASSED", "PASSED"])
        add_iterations(test_db, run.id, tc2.id, ["FAILED"])
        # tc3 has zero iterations

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)

        assert len(reports) == 3
        rep_map = {r.test_case_id: r for r in reports}

        assert rep_map[tc1.id].outcome_classification == "INSUFFICIENT_DATA"
        assert rep_map[tc1.id].total_runs == 2

        assert rep_map[tc2.id].outcome_classification == "INSUFFICIENT_DATA"
        assert rep_map[tc2.id].total_runs == 1

        assert rep_map[tc3.id].outcome_classification == "INSUFFICIENT_DATA"
        assert rep_map[tc3.id].total_runs == 0
        assert rep_map[tc3.id].pass_count == 0
        assert rep_map[tc3.id].fail_count == 0
        assert rep_map[tc3.id].flakiness_score == 0.0

        assert run.insufficient_data_count == 3
        assert run.consistently_passing_count == 0
        assert run.consistently_failing_count == 0
        assert run.flaky_tests_count == 0


# =========================================================================
# 7. SAFEGUARDS VERIFICATION
# =========================================================================
class TestMilestone4Safeguards:
    def test_safeguard_1_reject_analysis_on_active_run(self, test_db, client):
        """Active run (RUNNING) must reject analysis with ActiveRunAnalysisError and HTTP 409 Conflict."""
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id, status="RUNNING")
        add_iterations(test_db, run.id, tc.id, ["PASSED"] * 5)

        detector = FlakinessDetector(min_samples_threshold=5)
        # Direct detector call raises ActiveRunAnalysisError
        with pytest.raises(ActiveRunAnalysisError):
            detector.analyze_test_run(run.id, test_db, allow_active=False)

        # API call returns HTTP 409 Conflict
        resp = client.post(f"/api/runs/{run.id}/analyze")
        assert resp.status_code == 409
        assert "while execution is in progress" in resp.json()["detail"]

    def test_safeguard_2_reports_scoped_strictly_to_current_run_project(self, test_db):
        """Test cases from Project B must NOT be reported in Project A's run analysis."""
        proj_a, tc_a = create_sample_project_and_test(test_db, name="Project A", node_id="a.py::test_a")
        proj_b, tc_b = create_sample_project_and_test(test_db, name="Project B", node_id="b.py::test_b")

        run_a = create_test_run(test_db, proj_a.id)
        add_iterations(test_db, run_a.id, tc_a.id, ["PASSED"] * 5)

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run_a.id, test_db)

        assert len(reports) == 1
        assert reports[0].test_case_id == tc_a.id

    def test_safeguard_3_recalculate_all_counters_without_blind_increment(self, test_db):
        """TestRun counters must be strictly recalculated, clearing any stale or corrupted values."""
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["PASSED"] * 5)

        # Manually corrupt the counters
        run.consistently_passing_count = 999
        run.consistently_failing_count = 888
        run.flaky_tests_count = 777
        run.insufficient_data_count = 666
        test_db.commit()

        detector = FlakinessDetector(min_samples_threshold=5)
        detector.analyze_test_run(run.id, test_db)

        test_db.refresh(run)
        # Correctly recalculated
        assert run.consistently_passing_count == 1
        assert run.consistently_failing_count == 0
        assert run.flaky_tests_count == 0
        assert run.insufficient_data_count == 0

    def test_safeguard_5_rca_fields_remain_strictly_null(self, test_db):
        """RCA fields must be NULL and confidence_score must be 0.0 in Milestone 4."""
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["PASSED", "FAILED"] * 5)

        detector = FlakinessDetector(min_samples_threshold=5)
        reports = detector.analyze_test_run(run.id, test_db)
        rep = reports[0]

        assert rep.root_cause_category is None
        assert rep.confidence_score == 0.0
        assert rep.rca_summary is None
        assert rep.recommendations is None

    def test_idempotent_repeated_analysis(self, test_db):
        """Repeated analysis calls update existing report records without creating duplicates."""
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["PASSED"] * 5)

        detector = FlakinessDetector(min_samples_threshold=5)
        reports_1 = detector.analyze_test_run(run.id, test_db)
        assert len(reports_1) == 1
        rep1_id = reports_1[0].id

        # Re-run analysis
        reports_2 = detector.analyze_test_run(run.id, test_db)
        assert len(reports_2) == 1
        assert reports_2[0].id == rep1_id

        # Verify database total count
        total_reps = test_db.query(FlakinessReport).filter(FlakinessReport.test_run_id == run.id).count()
        assert total_reps == 1


# =========================================================================
# 8. API CONTRACT VERIFICATION
# =========================================================================
class TestMilestone4APIContracts:
    def test_get_run_reports_enriched_metadata(self, test_db, client):
        proj, tc = create_sample_project_and_test(test_db, node_id="tests/test_api.py::test_contract")
        run = create_test_run(test_db, proj.id)
        add_iterations(test_db, run.id, tc.id, ["PASSED"] * 5)

        detector = FlakinessDetector(min_samples_threshold=5)
        detector.analyze_test_run(run.id, test_db)

        # Query /api/reports/run/{run_id}
        resp = client.get(f"/api/reports/run/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        rep = data[0]
        assert rep["test_run_id"] == run.id
        assert rep["test_case_id"] == tc.id
        assert rep["node_id"] == "tests/test_api.py::test_contract"
        assert rep["test_name"] == "test_contract"
        assert rep["file_path"] == "tests/test_api.py"
        assert rep["outcome_classification"] == "CONSISTENTLY_PASSING"
        assert rep["flakiness_score"] == 0.0
        assert rep["total_runs"] == 5

        # Query alias /api/runs/{run_id}/reports
        resp_alias = client.get(f"/api/runs/{run.id}/reports")
        assert resp_alias.status_code == 200
        assert resp_alias.json() == data

    def test_post_run_analyze_endpoint(self, test_db, client):
        proj, tc = create_sample_project_and_test(test_db)
        run = create_test_run(test_db, proj.id, status="COMPLETED")
        add_iterations(test_db, run.id, tc.id, ["PASSED", "FAILED"] * 5)

        resp = client.post(f"/api/runs/{run.id}/analyze")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["outcome_classification"] == "FLAKY"
        assert data[0]["flakiness_score"] == 1.0
        assert data[0]["flip_count"] == 9


# =========================================================================
# 9. REAL DOCKER END-TO-END EXECUTION & POST-RUN REPORT SYNTHESIS
# =========================================================================
class TestSyntheticSuiteEndToEndClassification:
    def test_synthetic_suite_5_iterations_end_to_end_classification(self, test_db):
        """
        Executes synthetic_flaky_suite for 5 iterations inside Docker containers.
        Verifies:
        1. All 6 tests receive FlakinessReport records generated automatically.
        2. test_pure_deterministic_calculation is CONSISTENTLY_PASSING (F = 0.0).
        3. test_deterministic_failure is CONSISTENTLY_FAILING (F = 0.0).
        4. Summary counters on TestRun match the reports exactly.
        5. RCA fields are strictly NULL.
        """
        suite_dir = settings.BASE_DIR / "samples" / "synthetic_flaky_suite"
        if not suite_dir.exists():
            pytest.skip("synthetic_flaky_suite sample not found")

        proj_id = str(uuid.uuid4())
        proj = Project(id=proj_id, name="Synthetic Suite E2E", source_archive_path=str(suite_dir))
        test_db.add(proj)
        test_db.commit()

        # Discover tests
        discover_and_register_tests(proj_id, suite_dir, test_db)
        test_cases = test_db.query(TestCase).filter_by(project_id=proj_id).all()
        assert len(test_cases) == 6

        # Create Run for 5 iterations
        run_id = str(uuid.uuid4())
        test_run = TestRun(
            id=run_id,
            project_id=proj_id,
            iteration_count=5,
            shuffle_order=True,
            status="PENDING",
            total_tests=6,
        )
        test_db.add(test_run)
        test_db.commit()

        # Execute 5 iterations via ExecutionRunner
        runner = ExecutionRunner(session_factory=test_db.session_factory)
        runner.execute_test_run(run_id, timeout_seconds=20)

        # Query synthesized reports
        reports = (
            test_db.query(FlakinessReport)
            .filter_by(test_run_id=run_id)
            .all()
        )
        assert len(reports) == 6

        rep_by_name = {}
        for r in reports:
            tc = test_db.query(TestCase).filter_by(id=r.test_case_id).first()
            rep_by_name[tc.test_name] = r

        # Verify deterministic pass test
        pass_rep = rep_by_name["test_pure_deterministic_calculation"]
        assert pass_rep.outcome_classification == "CONSISTENTLY_PASSING"
        assert pass_rep.flakiness_score == 0.0
        assert pass_rep.pass_count == 5
        assert pass_rep.fail_count == 0
        assert pass_rep.total_runs == 5
        assert pass_rep.flip_count == 0

        # Verify deterministic failure test
        fail_rep = rep_by_name["test_deterministic_failure"]
        assert fail_rep.outcome_classification == "CONSISTENTLY_FAILING"
        assert fail_rep.flakiness_score == 0.0
        assert fail_rep.pass_count == 0
        assert fail_rep.fail_count == 5
        assert fail_rep.total_runs == 5
        assert fail_rep.flip_count == 0

        # Verify TestRun summary counters match
        test_db.refresh(test_run)
        assert test_run.status == "COMPLETED"
        assert test_run.completed_iterations == 5
        assert test_run.total_tests == 6
        assert test_run.consistently_passing_count == sum(
            1 for r in reports if r.outcome_classification == "CONSISTENTLY_PASSING"
        )
        assert test_run.consistently_failing_count == sum(
            1 for r in reports if r.outcome_classification == "CONSISTENTLY_FAILING"
        )
        assert test_run.flaky_tests_count == sum(
            1 for r in reports if r.outcome_classification == "FLAKY"
        )
        assert test_run.insufficient_data_count == sum(
            1 for r in reports if r.outcome_classification == "INSUFFICIENT_DATA"
        )

        # Verify RCA fields strictly NULL
        for r in reports:
            assert r.root_cause_category is None
            assert r.confidence_score == 0.0
            assert r.rca_summary is None
            assert r.recommendations is None

