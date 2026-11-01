import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.db.session import Base, get_db
from backend.app.db.models import Project, TestCase, TestRun, RunIteration, TestIteration, FlakinessReport
from backend.app.db.migrate import migrate_db
from backend.app.core.detector import FlakinessDetector, ActiveRunAnalysisError
from backend.app.core.rca_engine import RCAEngine, RCACategory
from backend.app.core.runner import ExecutionRunner
from backend.app.core.discovery import discover_and_register_tests
from backend.app.main import app

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


def create_project(db, name="Test Project"):
    proj = Project(id=str(uuid.uuid4()), name=name)
    db.add(proj)
    db.flush()
    return proj


def create_test_case(db, project_id, node_id):
    tc = TestCase(
        id=str(uuid.uuid4()),
        project_id=project_id,
        node_id=node_id,
        test_name=node_id.split("::")[-1],
        file_path=node_id.split("::")[0],
    )
    db.add(tc)
    db.flush()
    return tc


def create_test_run(db, project_id, iteration_count=5, status="COMPLETED", shuffle_order=True):
    run = TestRun(
        id=str(uuid.uuid4()),
        project_id=project_id,
        iteration_count=iteration_count,
        shuffle_order=shuffle_order,
        status=status,
        total_tests=1,
    )
    db.add(run)
    db.flush()
    return run


# ============================================================================
# 1. UNIT TESTS FOR ALL 8 ROOT CAUSE CATEGORIES
# ============================================================================

class TestRCACategoriesUnit:
    """Verifies that each of the 8 root cause categories is diagnosed accurately."""

    def test_rca_order_dependency(self, test_db):
        """Test B fails whenever Test A precedes it, and passes otherwise (3 fails, 3 passes)."""
        proj = create_project(test_db)
        tc_a = create_test_case(test_db, proj.id, "tests/test_order.py::test_a_pollute")
        tc_b = create_test_case(test_db, proj.id, "tests/test_order.py::test_b_victim")
        run = create_test_run(test_db, proj.id, iteration_count=6)

        # Iterations 1, 2, 3: A executes before B -> B fails
        for iter_num in [1, 2, 3]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=iter_num, status="PASSED", execution_order=1, duration_ms=50
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=iter_num, status="FAILED", execution_order=2, duration_ms=55,
                error_message="AssertionError: Expected initial condition",
                traceback="Traceback: assert False"
            ))

        # Iterations 4, 5, 6: B executes before A -> B passes
        for iter_num in [4, 5, 6]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=iter_num, status="PASSED", execution_order=1, duration_ms=52
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=iter_num, status="PASSED", execution_order=2, duration_ms=48
            ))
        test_db.commit()

        # Step 1: Detect flakiness
        detector = FlakinessDetector(min_samples_threshold=5)
        detector.analyze_test_run(run.id, test_db)

        # Step 2: Run RCA
        rca_engine = RCAEngine()
        reports = rca_engine.analyze_test_run_rca(run.id, test_db)
        report_b = next(r for r in reports if r.test_case_id == tc_b.id)

        assert report_b.outcome_classification == "FLAKY"
        assert report_b.root_cause_category == RCACategory.ORDER_DEPENDENCY
        assert report_b.confidence_score >= 0.70
        assert "tests/test_order.py::test_a_pollute" in report_b.rca_summary
        assert "preceded 3/3 failures" in report_b.rca_summary
        assert "suspected preceding test" in report_b.recommendations
        assert "Execution order permutation correlation" in report_b.rca_summary

        evidence = json.loads(report_b.supporting_evidence)
        assert len(evidence["suspect_preceding_tests"]) == 1
        assert evidence["suspect_preceding_tests"][0]["node_id"] == "tests/test_order.py::test_a_pollute"
        assert evidence["suspect_preceding_tests"][0]["correlation_score"] == 1.0
        assert evidence["suspect_preceding_tests"][0]["suspect_status"] == "heuristic_candidate"

    def test_rca_shared_state_pollution(self, test_db):
        """Explicit state pollution error signature combined with mutator activity."""
        proj = create_project(test_db)
        tc_a = create_test_case(test_db, proj.id, "tests/test_cache.py::test_fill_cache")
        tc_b = create_test_case(test_db, proj.id, "tests/test_cache.py::test_read_cache")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        # 3 failures where A precedes B, with explicit state pollution error
        for i in [1, 2, 3]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=40
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=i, status="FAILED", execution_order=2, duration_ms=45,
                error_message="RuntimeError: Shared state pollution detected: dirty state left in cache",
                traceback="Traceback: cache contains uncleaned residual state"
            ))

        # 2 passes where B precedes A
        for i in [4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=40
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=i, status="PASSED", execution_order=2, duration_ms=40
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        report_b = next(r for r in reports if r.test_case_id == tc_b.id)

        assert report_b.root_cause_category == RCACategory.SHARED_STATE_POLLUTION
        assert report_b.confidence_score >= 0.70
        assert "SHARED_STATE_POLLUTION" in report_b.rca_summary
        assert "Reset shared mutable state" in report_b.recommendations

    def test_rca_timing_or_race_condition(self, test_db):
        """Intermittent failures with async/timeout keywords and high duration variance (spread >= 200ms)."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_async.py::test_event_worker")
        run = create_test_run(test_db, proj.id, iteration_count=6)

        # 3 passes with fast durations (100ms)
        for i in [1, 3, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=100
            ))

        # 3 failures with long durations (900ms) and async timeout traceback
        for i in [2, 4, 6]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=900,
                error_message="asyncio.exceptions.TimeoutError: event loop wait_for timed out",
                traceback="Traceback: async race condition while waiting for thread"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        assert rep.root_cause_category == RCACategory.TIMING_OR_RACE_CONDITION
        assert rep.confidence_score >= 0.70
        assert "TIMING_OR_RACE_CONDITION" in rep.rca_summary
        assert "Avoid fixed `time.sleep()`" in rep.recommendations
        ev = json.loads(rep.supporting_evidence)
        assert ev["duration_stats"]["coefficient_of_variation"] > 0.40
        assert ev["duration_stats"]["spread_ms"] >= 200.0

    def test_rca_resource_exhaustion_corroborated(self, test_db):
        """Failures caused by memory exhaustion / container timeout with OOM signature."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_heavy.py::test_bulk_alloc")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=200
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=5000,
                error_message="MemoryError: out of memory allocating array",
                traceback="Traceback: system memory limit exceeded: out of memory"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        assert rep.root_cause_category == RCACategory.RESOURCE_EXHAUSTION
        assert rep.confidence_score >= 0.70
        assert "RESOURCE_EXHAUSTION" in rep.rca_summary
        assert "Investigate container timeout and resource consumption" in rep.recommendations

    def test_rca_environment_dependency(self, test_db):
        """Intermittent missing file path or environment variable error."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_env.py::test_load_config")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=50
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=50,
                error_message="FileNotFoundError: [Errno 2] No such file or directory: 'config.json'",
                traceback="Traceback: FileNotFoundError: path does not exist"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        assert rep.root_cause_category == RCACategory.ENVIRONMENT_DEPENDENCY
        assert rep.confidence_score >= 0.70
        assert "ENVIRONMENT_DEPENDENCY" in rep.rca_summary
        assert "Eliminate hardcoded filesystem paths" in rep.recommendations

    def test_rca_external_dependency(self, test_db):
        """Intermittent failures due to live network socket connection."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_net.py::test_api_client")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=80
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=80,
                error_message="ConnectionRefusedError: [Errno 111] Connection refused",
                traceback="Traceback: requests.exceptions.ConnectionError: failed to establish a new connection"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        assert rep.root_cause_category == RCACategory.EXTERNAL_DEPENDENCY
        assert rep.confidence_score >= 0.70
        assert "EXTERNAL_DEPENDENCY" in rep.rca_summary
        assert "Mock external HTTP and socket endpoints" in rep.recommendations

    def test_rca_assertion_or_logic_failure(self, test_db):
        """Deterministic bug: 100% failure rate across all iterations."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_bug.py::test_math_regression")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in range(1, 6):
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=30,
                error_message="AssertionError: assert calculate_total() == 100",
                traceback="Traceback: AssertionError: 50 != 100"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        assert rep.outcome_classification == "CONSISTENTLY_FAILING"
        assert rep.root_cause_category == RCACategory.ASSERTION_OR_LOGIC_FAILURE
        assert rep.confidence_score >= 0.80
        assert "ASSERTION_OR_LOGIC_FAILURE" in rep.rca_summary
        assert "deterministic regression or assertion bug" in rep.recommendations

    def test_rca_consistently_passing(self, test_db):
        """Consistently passing tests: root_cause_category is None, confidence is 0.0 (neutral)."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_pass.py::test_stable")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in range(1, 6):
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=25
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        assert rep.outcome_classification == "CONSISTENTLY_PASSING"
        assert rep.root_cause_category is None
        assert rep.confidence_score == 0.0
        assert "passed consistently across all 5 valid executions" in rep.rca_summary
        assert "No remediation or investigation required" in rep.recommendations

    def test_rca_unknown_and_insufficient_data(self, test_db):
        """Fewer than 2 valid runs classifies as UNKNOWN with confidence 0.10."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_sparse.py::test_one_run")
        run = create_test_run(test_db, proj.id, iteration_count=1)

        test_db.add(TestIteration(
            id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
            iteration_number=1, status="FAILED", execution_order=1, duration_ms=20,
            error_message="Unknown generic error"
        ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        assert rep.outcome_classification == "INSUFFICIENT_DATA"
        assert rep.root_cause_category == RCACategory.UNKNOWN
        assert rep.confidence_score == 0.10
        assert "Insufficient execution data" in rep.rca_summary


# ============================================================================
# 2. ORDER DEPENDENCY CORRECTIVE REGRESSION TESTS
# ============================================================================

class TestOrderDependencyCorrective:
    """Verifies sample-size requirements, non-shuffled safety, and heuristic candidate status."""

    def test_order_dependency_rejected_with_only_one_failure(self, test_db):
        """1 failure and 4 passes: must NOT convict preceding test or claim order dependency."""
        proj = create_project(test_db)
        tc_a = create_test_case(test_db, proj.id, "tests/test_order.py::test_innocent")
        tc_b = create_test_case(test_db, proj.id, "tests/test_order.py::test_victim")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        # Iteration 1: A precedes B -> B fails
        test_db.add(TestIteration(
            id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
            iteration_number=1, status="PASSED", execution_order=1, duration_ms=50
        ))
        test_db.add(TestIteration(
            id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
            iteration_number=1, status="FAILED", execution_order=2, duration_ms=50,
            error_message="AssertionError: intermittent error"
        ))

        # Iterations 2, 3, 4, 5: B precedes A -> B passes
        for i in [2, 3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=50
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=i, status="PASSED", execution_order=2, duration_ms=50
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep_b = next(r for r in reports if r.test_case_id == tc_b.id)

        # Because N_fail == 1, order correlation is rejected!
        assert rep_b.root_cause_category != RCACategory.ORDER_DEPENDENCY
        ev = json.loads(rep_b.supporting_evidence)
        assert len(ev["suspect_preceding_tests"]) == 0
        assert any("Insufficient outcome distribution" in note for note in ev["uncertainty_notes"])

    def test_order_dependency_two_fails_and_two_passes(self, test_db):
        """2 failures and 2 passes (>= 2 required): valid permutation correlation identifies candidate."""
        proj = create_project(test_db)
        tc_a = create_test_case(test_db, proj.id, "tests/test_order.py::test_polluter")
        tc_b = create_test_case(test_db, proj.id, "tests/test_order.py::test_victim")
        run = create_test_run(test_db, proj.id, iteration_count=4)

        # 2 failures where A precedes B
        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=40
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=i, status="FAILED", execution_order=2, duration_ms=40,
                error_message="AssertionError: failed"
            ))

        # 2 passes where B precedes A
        for i in [3, 4]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=40
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=i, status="PASSED", execution_order=2, duration_ms=40
            ))
        test_db.commit()

        # Run with threshold 4 to evaluate
        FlakinessDetector(min_samples_threshold=4).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep_b = next(r for r in reports if r.test_case_id == tc_b.id)

        assert rep_b.root_cause_category == RCACategory.ORDER_DEPENDENCY
        ev = json.loads(rep_b.supporting_evidence)
        assert len(ev["suspect_preceding_tests"]) == 1
        assert ev["suspect_preceding_tests"][0]["suspect_status"] == "heuristic_candidate"

    def test_order_dependency_non_shuffled_is_inconclusive(self, test_db):
        """When shuffle_order=False, order correlation is marked inconclusive."""
        proj = create_project(test_db)
        tc_a = create_test_case(test_db, proj.id, "tests/test_fixed.py::test_a")
        tc_b = create_test_case(test_db, proj.id, "tests/test_fixed.py::test_b")
        run = create_test_run(test_db, proj.id, iteration_count=5, shuffle_order=False)

        # Even with 3 failures and 2 passes where A precedes B in all iterations
        for i in [1, 2, 3]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=i, status="FAILED", execution_order=2, duration_ms=30,
                error_message="AssertionError: intermittent"
            ))
        for i in [4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=i, status="PASSED", execution_order=2, duration_ms=30
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep_b = next(r for r in reports if r.test_case_id == tc_b.id)

        assert rep_b.root_cause_category != RCACategory.ORDER_DEPENDENCY
        ev = json.loads(rep_b.supporting_evidence)
        assert len(ev["suspect_preceding_tests"]) == 0
        assert any("shuffle_order=False" in note for note in ev["uncertainty_notes"])

    def test_order_dependency_insufficient_order_variation(self, test_db):
        """When test execution positions did not vary across iterations, correlation is inconclusive."""
        proj = create_project(test_db)
        tc_a = create_test_case(test_db, proj.id, "tests/test_novar.py::test_a")
        tc_b = create_test_case(test_db, proj.id, "tests/test_novar.py::test_b")
        run = create_test_run(test_db, proj.id, iteration_count=5, shuffle_order=True)

        # Relative order never varied (A was always order 1, B was always order 2)
        for i in [1, 2, 3]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=i, status="FAILED", execution_order=2, duration_ms=30,
                error_message="AssertionError: intermittent"
            ))
        for i in [4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_a.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc_b.id,
                iteration_number=i, status="PASSED", execution_order=2, duration_ms=30
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep_b = next(r for r in reports if r.test_case_id == tc_b.id)

        assert rep_b.root_cause_category != RCACategory.ORDER_DEPENDENCY
        ev = json.loads(rep_b.supporting_evidence)
        assert any("Insufficient execution order variation" in note for note in ev["uncertainty_notes"])


# ============================================================================
# 3. CONTRADICTION PENALTY REGRESSION TESTS
# ============================================================================

class TestContradictionPenalty:
    """Verifies contradiction penalty formula, bounds, and supporting_evidence."""

    def test_contradiction_penalty_reduces_confidence(self, test_db):
        """Competing evidence signatures reduce confidence score via contradiction penalty."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_conflict.py::test_mixed_signals")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        # Iterations contain conflicting signals: state pollution AND external dependency
        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=40
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=40,
                error_message="ConnectionRefusedError: failed to establish connection",
                traceback="Traceback: shared state pollution: table already exists"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        evidence = json.loads(rep.supporting_evidence)
        assert "contradiction_penalty" in evidence
        assert evidence["contradiction_penalty"] > 0
        assert any("Conflicting signals observed" in note for note in evidence["uncertainty_notes"])

    def test_zero_competing_evidence_has_zero_penalty(self, test_db):
        """Single strong signal without competing evidence produces penalty == 0.0."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_clean.py::test_single_signal")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=40
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=40,
                error_message="ConnectionRefusedError: connection refused"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        ev = json.loads(reports[0].supporting_evidence)
        assert ev["contradiction_penalty"] == 0.0

    def test_maximum_contradiction_penalty_cap(self, test_db):
        """Penalty cannot exceed 0.35."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_max_pen.py::test_max")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=40
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=40,
                error_message="ConnectionRefusedError: failed to establish connection",
                traceback="Traceback: MemoryError: out of memory allocating array"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        ev = json.loads(reports[0].supporting_evidence)
        assert ev["contradiction_penalty"] <= 0.35


# ============================================================================
# 4. RESOURCE EXHAUSTION CLASSIFICATION CORRECTIVE TESTS
# ============================================================================

class TestResourceExhaustionCorrective:
    """Verifies that TIMED_OUT alone does NOT establish RESOURCE_EXHAUSTION."""

    def test_timeout_only_does_not_establish_resource_exhaustion(self, test_db):
        """TIMED_OUT with no OOM/descriptor signature must NOT classify as RESOURCE_EXHAUSTION."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_hang.py::test_pure_timeout")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=100
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="TIMED_OUT", execution_order=1, duration_ms=30000,
                error_message="Test run exceeded timeout threshold of 30 seconds"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        # Must NOT be classified as RESOURCE_EXHAUSTION
        assert rep.root_cause_category != RCACategory.RESOURCE_EXHAUSTION
        assert rep.root_cause_category == RCACategory.UNKNOWN
        ev = json.loads(rep.supporting_evidence)
        assert any("timed out without explicit memory or descriptor exhaustion" in note for note in ev["uncertainty_notes"])

    def test_timeout_plus_memory_error_classifies_resource_exhaustion(self, test_db):
        """TIMED_OUT corroborated by MemoryError classifies as RESOURCE_EXHAUSTION."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_hang_oom.py::test_oom_timeout")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=100
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="TIMED_OUT", execution_order=1, duration_ms=30000,
                error_message="MemoryError: out of memory allocating array",
                traceback="Traceback: system out of memory limit exceeded"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        assert reports[0].root_cause_category == RCACategory.RESOURCE_EXHAUSTION

    def test_timeout_plus_network_hang_classifies_external_dependency(self, test_db):
        """TIMED_OUT corroborated by network socket signature classifies as EXTERNAL_DEPENDENCY."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_net_hang.py::test_socket_timeout")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=100
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="TIMED_OUT", execution_order=1, duration_ms=30000,
                error_message="requests.exceptions.ConnectionError: failed to establish a new connection"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        assert reports[0].root_cause_category == RCACategory.EXTERNAL_DEPENDENCY

    def test_timeout_plus_deadlock_classifies_timing_race(self, test_db):
        """TIMED_OUT corroborated by deadlock/event loop signature classifies as TIMING_OR_RACE_CONDITION."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_deadlock.py::test_lock_hang")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=100
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="TIMED_OUT", execution_order=1, duration_ms=30000,
                error_message="deadlock detected: event loop wait_for lock acquisition timeout"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        assert reports[0].root_cause_category == RCACategory.TIMING_OR_RACE_CONDITION


# ============================================================================
# 5. DURATION VARIANCE HEURISTIC REGRESSION TESTS
# ============================================================================

class TestDurationVarianceCorrective:
    """Verifies duration spread requirement, zero-duration safety, and sub-millisecond handling."""

    def test_sub_millisecond_jitter_does_not_trigger_race_condition(self, test_db):
        """CV > 0.40 on short durations (e.g. 2ms vs 8ms, spread = 6ms < 200ms) does NOT flag race condition."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_jitter.py::test_short")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=2
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=8,
                error_message="AssertionError: value mismatch"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        # Should NOT be classified as TIMING_OR_RACE_CONDITION
        assert rep.root_cause_category != RCACategory.TIMING_OR_RACE_CONDITION
        ev = json.loads(rep.supporting_evidence)
        assert not any("duration_variance" in sig for sig in ev["matched_signatures"])

    def test_zero_duration_tests_handled_safely(self, test_db):
        """0 ms duration does not cause division-by-zero errors or crash."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_zero.py::test_zero_dur")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in range(1, 6):
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=0
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        assert reports[0].outcome_classification == "CONSISTENTLY_PASSING"
        assert reports[0].confidence_score == 0.0

    def test_large_duration_spread_triggers_timing_heuristic(self, test_db):
        """CV > 0.40 AND spread >= 200ms properly contributes to timing heuristic."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_spread.py::test_large_spread")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        # 50ms vs 850ms (spread = 800ms >= 200ms)
        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=50
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=850,
                error_message="async race condition: wait_for timeout"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        ev = json.loads(reports[0].supporting_evidence)
        assert any("duration_variance" in sig for sig in ev["matched_signatures"])
        assert ev["duration_stats"]["spread_ms"] >= 200.0


# ============================================================================
# 6. BRITTLE KEYWORD MATCHING REGRESSION TESTS
# ============================================================================

class TestKeywordMatchingCorrective:
    """Verifies that normal tracebacks containing /workspace/, platform, KeyError, etc. do NOT false-positive."""

    def test_negative_workspace_path_not_environment_dependency(self, test_db):
        """Standard traceback with '/workspace/' path must NOT trigger ENVIRONMENT_DEPENDENCY."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_normal.py::test_app_logic")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=30,
                error_message="AssertionError: assert calculate() == 100",
                traceback='File "/workspace/tests/test_normal.py", line 12, in test_app_logic\nassert 50 == 100'
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        assert rep.root_cause_category != RCACategory.ENVIRONMENT_DEPENDENCY

    def test_negative_ordinary_keyerror_not_environment_dependency(self, test_db):
        """Ordinary dictionary KeyError: 'user_id' must NOT trigger ENVIRONMENT_DEPENDENCY."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_dict.py::test_user_lookup")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=30,
                error_message="KeyError: 'user_id'",
                traceback="Traceback: data['user_id'] KeyError: 'user_id'"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        rep = reports[0]

        assert rep.root_cause_category != RCACategory.ENVIRONMENT_DEPENDENCY

    def test_negative_generic_platform_not_environment_dependency(self, test_db):
        """Generic 'platform' in variable or docstring must NOT trigger ENVIRONMENT_DEPENDENCY."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_plat.py::test_platform_flag")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=30,
                error_message="AssertionError: platform variable false",
                traceback="Traceback: assert platform == 'linux'"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        assert reports[0].root_cause_category != RCACategory.ENVIRONMENT_DEPENDENCY

    def test_positive_genuine_missing_env_var_detected(self, test_db):
        """Genuine missing environment variable error is accurately detected."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_real_env.py::test_secret")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=30,
                error_message="RuntimeError: missing environment variable 'DATABASE_URL'",
                traceback="Traceback: os.environ['DATABASE_URL'] missing environment variable"
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        reports = RCAEngine().analyze_test_run_rca(run.id, test_db)
        assert reports[0].root_cause_category == RCACategory.ENVIRONMENT_DEPENDENCY


# ============================================================================
# 7. DATABASE TRANSACTION BOUNDARIES REGRESSION TESTS
# ============================================================================

class TestTransactionBoundariesCorrective:
    """Verifies that RCA respects caller outer transactions and uses savepoints safely."""

    def test_rca_success_does_not_commit_outer_uncommitted_changes(self, test_db):
        """Uncommitted changes made by caller before RCA remain uncommitted after RCA returns."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_tx.py::test_isolation")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in range(1, 6):
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
        test_db.commit()

        # Step 1: Detect flakiness
        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)

        # Step 2: Caller stages an uncommitted change in its outer transaction
        staged_proj = Project(id="staged-uncommitted-project", name="Uncommitted Outer Project")
        test_db.add(staged_proj)
        test_db.flush()
        assert test_db.in_transaction(), "Outer transaction must be active before RCA"

        # Step 3: Run RCA
        rca_engine = RCAEngine()
        reports = rca_engine.analyze_test_run_rca(run.id, test_db)
        assert len(reports) == 1

        # Step 4: Verify outer transaction is STILL active and uncommitted
        assert test_db.in_transaction(), "RCA must not commit the outer transaction!"

        # Step 5: Caller rolls back outer transaction
        test_db.rollback()

        # Verify staged_proj was discarded (proving it was NEVER committed)
        assert test_db.query(Project).filter_by(id="staged-uncommitted-project").first() is None, (
            "Staged project was committed by RCA; rollback failed to discard it!"
        )

    def test_rca_failure_does_not_leave_partially_modified_report_data(self, test_db, monkeypatch):
        """If RCA encounters an error mid-computation, savepoint rolls back RCA changes cleanly."""
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_err.py::test_savepoint_rollback")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in range(1, 6):
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=30
            ))
        test_db.commit()

        FlakinessDetector(min_samples_threshold=5).analyze_test_run(run.id, test_db)
        rep = test_db.query(FlakinessReport).filter_by(test_run_id=run.id, test_case_id=tc.id).first()
        initial_rca_summary = rep.rca_summary

        # Force an unhandled error inside _evaluate_test_case_rca
        def faulty_eval(*args, **kwargs):
            raise RuntimeError("Simulated mid-computation hardware crash")

        monkeypatch.setattr(RCAEngine, "_evaluate_test_case_rca", faulty_eval)

        rca_engine = RCAEngine()
        with pytest.raises(RuntimeError, match="Simulated mid-computation hardware crash"):
            rca_engine.analyze_test_run_rca(run.id, test_db)

        # Verify report was cleanly rolled back to initial state by the savepoint
        test_db.refresh(rep)
        assert rep.rca_summary == initial_rca_summary

    def test_runner_status_not_changed_by_isolated_rca_failure(self, test_db, monkeypatch):
        """Runner's COMPLETED status is preserved even if post-execution RCA fails."""
        # Create minimal synthetic suite
        temp_dir = tempfile.mkdtemp(dir=str(settings.STORAGE_DIR))
        SessionTest = test_db.session_factory

        try:
            project_dir = Path(temp_dir) / "safe_suite"
            project_dir.mkdir()
            (project_dir / "test_simple.py").write_text("def test_ok(): assert True\n", encoding="utf-8")

            proj_id = str(uuid.uuid4())
            proj = Project(id=proj_id, name="Runner Safe Suite", source_archive_path=str(project_dir))
            test_db.add(proj)
            test_db.commit()

            discover_and_register_tests(proj_id, project_dir, test_db)

            run_id = str(uuid.uuid4())
            test_run = TestRun(
                id=run_id,
                project_id=proj_id,
                iteration_count=1,
                shuffle_order=False,
                status="PENDING",
            )
            test_db.add(test_run)
            test_db.commit()

            # Mock RCAEngine.analyze_test_run_rca to raise an exception
            def crashing_rca(*args, **kwargs):
                raise RuntimeError("Simulated RCA failure")

            monkeypatch.setattr(RCAEngine, "analyze_test_run_rca", crashing_rca)

            runner = ExecutionRunner(session_factory=SessionTest)
            runner.execute_test_run(run_id, timeout_seconds=15)

            db = SessionTest()
            saved_run = db.query(TestRun).filter_by(id=run_id).first()
            # Status must be COMPLETED despite RCA failure!
            assert saved_run.status == "COMPLETED"
            assert saved_run.completed_iterations == 1
            db.close()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# 8. API ENDPOINTS & DOCKER E2E INTEGRATION
# ============================================================================

class TestRCAEndpointsAndE2E:
    """Verifies REST API behavior for RCA execution and retrieval."""

    def test_api_rca_endpoint_success(self, client, test_db):
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_api.py::test_rca_api")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in [1, 2]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="PASSED", execution_order=1, duration_ms=50
            ))
        for i in [3, 4, 5]:
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=50,
                error_message="ConnectionRefusedError: [Errno 111] Connection refused",
                traceback="Traceback: requests.exceptions.ConnectionError"
            ))
        test_db.commit()

        # Milestone 4 detect
        client.post(f"/api/runs/{run.id}/analyze")

        # Milestone 5 RCA endpoint
        res = client.post(f"/api/runs/{run.id}/rca")
        assert res.status_code == 200
        reports = res.json()
        assert len(reports) == 1
        assert reports[0]["test_run_id"] == run.id
        assert reports[0]["root_cause_category"] == "EXTERNAL_DEPENDENCY"
        assert reports[0]["confidence_score"] >= 0.70
        assert "EXTERNAL_DEPENDENCY" in reports[0]["rca_summary"]
        assert "Mock external HTTP" in reports[0]["recommendations"]
        assert reports[0]["supporting_evidence"]["observed_fail_count"] == 3

        # Check GET /api/runs/{id}/reports includes RCA fields
        rep_res = client.get(f"/api/runs/{run.id}/reports")
        assert rep_res.status_code == 200
        rep_data = rep_res.json()
        assert len(rep_data) == 1
        report = rep_data[0]
        assert report["root_cause_category"] == "EXTERNAL_DEPENDENCY"
        assert report["confidence_score"] >= 0.70
        assert "EXTERNAL_DEPENDENCY" in report["rca_summary"]
        assert "Mock external HTTP" in report["recommendations"]
        assert report["supporting_evidence"]["observed_fail_count"] == 3

    def test_api_rca_endpoint_active_run_conflict(self, client, test_db):
        proj = create_project(test_db)
        run = create_test_run(test_db, proj.id, iteration_count=5, status="RUNNING")
        test_db.commit()

        res = client.post(f"/api/runs/{run.id}/rca")
        assert res.status_code == 409
        assert "in progress" in res.json()["detail"].lower()

    def test_api_analyze_triggers_both_detector_and_rca(self, client, test_db):
        proj = create_project(test_db)
        tc = create_test_case(test_db, proj.id, "tests/test_both.py::test_auto_rca")
        run = create_test_run(test_db, proj.id, iteration_count=5)

        for i in range(1, 6):
            test_db.add(TestIteration(
                id=str(uuid.uuid4()), test_run_id=run.id, test_case_id=tc.id,
                iteration_number=i, status="FAILED", execution_order=1, duration_ms=20,
                error_message="AssertionError: bug", traceback="assert 1 == 2"
            ))
        test_db.commit()

        # Trigger analyze
        res = client.post(f"/api/runs/{run.id}/analyze")
        assert res.status_code == 200

        # Verify report has both M4 and M5 fields populated
        rep_res = client.get(f"/api/runs/{run.id}/reports")
        assert rep_res.status_code == 200
        reports = rep_res.json()
        assert len(reports) == 1
        report = reports[0]
        assert report["outcome_classification"] == "CONSISTENTLY_FAILING"
        assert report["flakiness_score"] == 0.0
        assert report["root_cause_category"] == "ASSERTION_OR_LOGIC_FAILURE"
        assert report["confidence_score"] >= 0.80

    def test_docker_e2e_rca_synthetic_flaky_suite(self, test_db):
        temp_dir = tempfile.mkdtemp(dir=str(settings.STORAGE_DIR))
        SessionTest = test_db.session_factory

        try:
            # Create synthetic project with:
            # 1. State polluter (test_order_step_populate) and victim (test_order_step_expect_clean)
            # 2. Deterministic failure (test_deterministic_failure)
            # 3. Stable passing test (test_stable_passing)
            project_dir = Path(temp_dir) / "synthetic_suite"
            project_dir.mkdir()
            (project_dir / "test_suite.py").write_text("""
SHARED_STORE = []

def test_order_step_populate():
    SHARED_STORE.append("state_pollution_item")
    assert len(SHARED_STORE) >= 1

def test_order_step_expect_clean():
    assert len(SHARED_STORE) == 0, f"state pollution: residual uncleaned state {SHARED_STORE}"

def test_deterministic_failure():
    assert 1 == 2, "AssertionError: deterministic bug"

def test_stable_passing():
    assert True
""", encoding="utf-8")

            proj_id = str(uuid.uuid4())
            proj = Project(id=proj_id, name="Synthetic RCA Suite", source_archive_path=str(project_dir))
            test_db.add(proj)
            test_db.commit()

            discover_and_register_tests(proj_id, project_dir, test_db)
            assert test_db.query(TestCase).filter_by(project_id=proj_id).count() == 4

            run_id = str(uuid.uuid4())
            test_run = TestRun(
                id=run_id,
                project_id=proj_id,
                iteration_count=5,
                shuffle_order=True,
                status="PENDING",
            )
            test_db.add(test_run)
            test_db.commit()

            # Execute run through ExecutionRunner (runs Docker containers and auto-invokes detector + RCA)
            runner = ExecutionRunner(session_factory=SessionTest)
            runner.execute_test_run(run_id, timeout_seconds=30)

            db = SessionTest()
            finished_run = db.query(TestRun).filter_by(id=run_id).first()
            assert finished_run.status == "COMPLETED"
            assert finished_run.completed_iterations == 5

            # Inspect FlakinessReports generated automatically post-execution
            reports = db.query(FlakinessReport, TestCase).join(
                TestCase, FlakinessReport.test_case_id == TestCase.id
            ).filter(FlakinessReport.test_run_id == run_id).all()

            assert len(reports) == 4
            reports_by_name = {tc.test_name: r for r, tc in reports}

            # 1. Deterministic failure
            r_det = reports_by_name["test_deterministic_failure"]
            assert r_det.outcome_classification == "CONSISTENTLY_FAILING"
            assert r_det.root_cause_category == RCACategory.ASSERTION_OR_LOGIC_FAILURE
            assert r_det.confidence_score >= 0.80

            # 2. Stable passing: confidence_score is 0.0 (neutral representation)
            r_pass = reports_by_name["test_stable_passing"]
            assert r_pass.outcome_classification == "CONSISTENTLY_PASSING"
            assert r_pass.root_cause_category is None
            assert r_pass.confidence_score == 0.0

            # 3. Order victim
            r_victim = reports_by_name["test_order_step_expect_clean"]
            if r_victim.fail_count > 0:
                assert r_victim.root_cause_category in (
                    RCACategory.ORDER_DEPENDENCY,
                    RCACategory.SHARED_STATE_POLLUTION,
                )
                assert r_victim.confidence_score >= 0.50

            db.close()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
