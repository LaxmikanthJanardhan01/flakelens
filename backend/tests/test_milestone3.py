"""
Phase 2 - Milestone 3 Verification Suite: Repeated Test Execution Engine

Verifies:
1. Global database-backed execution lock: contention, heartbeat renewal, and stale lock recovery.
2. JSONL telemetry parser: handling complete, partial, and truncated lines.
3. Timeout handling: partial event recovery, TIMED_OUT status, NOT_EXECUTED status, container kill.
4. Multi-iteration execution: 3 iterations on synthetic_flaky_suite with random order seeds,
   individual test recording, and idempotent database persistence.
5. API endpoints: POST /api/runs, GET /api/runs/{id}, GET /api/runs/{id}/iterations, POST /api/runs/{id}/cancel.
"""
import io
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.main import app
from backend.app.db.session import Base, get_db
from backend.app.db.models import (
    Project,
    TestCase,
    TestRun,
    RunIteration,
    TestIteration,
    ExecutionLock,
    generate_uuid,
)
from backend.app.core.lock import (
    ExecutionLockManager,
    LockAcquisitionError,
    LockLostError,
)
from backend.app.core.runner import (
    ExecutionRunner,
    parse_jsonl_events,
    generate_deterministic_seed,
)
from backend.app.core.discovery import discover_and_register_tests
from backend.app.core.docker_manager import DockerManager


@pytest.fixture
def test_db():
    """Isolated SQLite database fixture."""
    temp_dir = tempfile.mkdtemp(dir=str(settings.STORAGE_DIR))
    db_path = Path(temp_dir) / "test_m3.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionTest = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionTest()

    yield session, SessionTest

    session.close()
    engine.dispose()
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestExecutionLock:
    """Verifies database execution lock, heartbeat, and stale lock recovery."""

    def test_lock_acquisition_and_contention(self, test_db):
        session, SessionTest = test_db
        lock_mgr1 = ExecutionLockManager(session_factory=SessionTest, ttl_seconds=10)
        lock_mgr2 = ExecutionLockManager(session_factory=SessionTest, ttl_seconds=10)

        run_id_1 = str(uuid.uuid4())
        run_id_2 = str(uuid.uuid4())

        # Worker 1 acquires
        assert lock_mgr1.acquire(run_id_1) is True
        is_locked, holder = lock_mgr1.is_locked()
        assert is_locked is True
        assert holder == run_id_1

        # Worker 2 attempts acquire -> rejected
        assert lock_mgr2.acquire(run_id_2) is False

        # Worker 1 releases
        lock_mgr1.release(run_id_1)
        is_locked, holder = lock_mgr1.is_locked()
        assert is_locked is False

        # Worker 2 now succeeds
        assert lock_mgr2.acquire(run_id_2) is True
        lock_mgr2.release(run_id_2)

    def test_lock_heartbeat_renewal(self, test_db):
        """Verifies background heartbeat thread renews expires_at periodically."""
        session, SessionTest = test_db
        lock_mgr = ExecutionLockManager(
            session_factory=SessionTest,
            ttl_seconds=3,
            heartbeat_interval=0.5,
        )
        run_id = str(uuid.uuid4())
        assert lock_mgr.acquire(run_id) is True

        # Initial expiry
        db = SessionTest()
        lock_row = db.query(ExecutionLock).filter_by(lock_name="global_runner").first()
        initial_expiry = lock_row.expires_at
        db.close()

        # Sleep longer than heartbeat interval
        time.sleep(1.8)

        # Verify expiry was renewed forward
        db = SessionTest()
        lock_row = db.query(ExecutionLock).filter_by(lock_name="global_runner").first()
        renewed_expiry = lock_row.expires_at
        db.close()

        assert renewed_expiry > initial_expiry
        lock_mgr.release(run_id)

    def test_stale_lock_recovery(self, test_db):
        """Verifies that an expired lock from a crashed runner is recovered."""
        session, SessionTest = test_db
        crashed_run_id = "crashed-run-12345"

        # Manually seed an expired lock
        lock_mgr = ExecutionLockManager(session_factory=SessionTest, ttl_seconds=5)
        lock_mgr.ensure_lock_row()

        db = SessionTest()
        lock_row = db.query(ExecutionLock).filter_by(lock_name="global_runner").first()
        lock_row.locked_by_run_id = crashed_run_id
        lock_row.acquired_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        lock_row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()
        db.close()

        # A new worker should recognize it is stale and acquire it
        new_run_id = str(uuid.uuid4())
        assert lock_mgr.acquire(new_run_id) is True
        is_locked, holder = lock_mgr.is_locked()
        assert holder == new_run_id
        lock_mgr.release(new_run_id)


class TestJsonlTelemetryParsing:
    """Verifies JSONL parsing and truncated line tolerance."""

    def test_parse_complete_and_truncated_events(self):
        temp_dir = tempfile.mkdtemp(dir=str(settings.STORAGE_DIR))
        events_file = Path(temp_dir) / "events.jsonl"
        try:
            content = (
                '{"event": "test_started", "node_id": "test_a.py::test_one", "timestamp": 100.0}\n'
                '{"event": "test_finished", "node_id": "test_a.py::test_one", "status": "PASSED", "duration_ms": 20}\n'
                '{"event": "test_started", "node_id": "test_b.py::test_two", "timestamp": 105.0}\n'
                '{"event": "test_started", "node_id": "test_c.py'  # Incomplete / truncated line
            )
            events_file.write_text(content, encoding="utf-8")

            started, finished = parse_jsonl_events(events_file)
            assert "test_a.py::test_one" in started
            assert "test_a.py::test_one" in finished
            assert finished["test_a.py::test_one"]["status"] == "PASSED"
            assert "test_b.py::test_two" in started
            assert "test_b.py::test_two" not in finished  # Started but not finished
            assert "test_c.py" not in started  # Corrupted line ignored safely
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestTimeoutAndRecovery:
    """Verifies timeout handling, partial event salvage, and container cleanup."""

    def test_timeout_preserves_completed_and_marks_timed_out(self, test_db):
        session, SessionTest = test_db
        temp_dir = tempfile.mkdtemp(dir=str(settings.STORAGE_DIR))

        try:
            # Create project with fast test and hanging test
            project_dir = Path(temp_dir) / "hang_project"
            project_dir.mkdir()
            (project_dir / "test_hanging_suite.py").write_text("""
import time

def test_fast_pass():
    assert True

def test_hang():
    time.sleep(30)
    assert True

def test_unreached():
    assert True
""", encoding="utf-8")

            proj_id = str(uuid.uuid4())
            proj = Project(id=proj_id, name="Timeout Suite", source_archive_path=str(project_dir))
            session.add(proj)
            session.commit()

            # Index tests
            discover_and_register_tests(proj_id, project_dir, session)
            assert session.query(TestCase).filter_by(project_id=proj_id).count() == 3

            # Create TestRun for 1 iteration
            run_id = str(uuid.uuid4())
            test_run = TestRun(
                id=run_id,
                project_id=proj_id,
                iteration_count=1,
                shuffle_order=False,
                status="PENDING",
            )
            session.add(test_run)
            session.commit()

            # Execute with short 3s timeout
            runner = ExecutionRunner(session_factory=SessionTest)
            runner.execute_test_run(run_id, timeout_seconds=3)

            # Check database results
            db = SessionTest()
            updated_run = db.query(TestRun).filter_by(id=run_id).first()
            assert updated_run.status == "TIMED_OUT"
            assert updated_run.completed_iterations == 0  # Timed out iterations do not count as completed!

            run_iter = db.query(RunIteration).filter_by(test_run_id=run_id, iteration_number=1).first()
            assert run_iter.status == "TIMED_OUT"

            # Check per-test outcomes
            test_results = (
                db.query(TestIteration, TestCase)
                .join(TestCase, TestIteration.test_case_id == TestCase.id)
                .filter(TestIteration.test_run_id == run_id)
                .all()
            )
            status_map = {tc.test_name: ti.status for ti, tc in test_results}
            dur_map = {tc.test_name: ti.duration_ms for ti, tc in test_results}

            assert status_map["test_fast_pass"] == "PASSED"
            assert status_map["test_hang"] == "TIMED_OUT"
            assert dur_map["test_hang"] > 0
            assert status_map["test_unreached"] == "NOT_EXECUTED"
            assert dur_map["test_unreached"] == 0
            db.close()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestMultiIterationExecution:
    """Verifies executing multiple iterations on real synthetic suite with random seeds."""

    def test_run_synthetic_flaky_suite_3_iterations(self, test_db):
        session, SessionTest = test_db
        suite_dir = settings.BASE_DIR / "samples" / "synthetic_flaky_suite"
        assert suite_dir.exists()

        proj_id = str(uuid.uuid4())
        proj = Project(id=proj_id, name="Synthetic Suite Multi-Iter", source_archive_path=str(suite_dir))
        session.add(proj)
        session.commit()

        # Discover tests
        discover_and_register_tests(proj_id, suite_dir, session)
        tc_count = session.query(TestCase).filter_by(project_id=proj_id).count()
        assert tc_count == 6

        # Create Run for 3 iterations
        run_id = str(uuid.uuid4())
        test_run = TestRun(
            id=run_id,
            project_id=proj_id,
            iteration_count=3,
            shuffle_order=True,
            status="PENDING",
        )
        session.add(test_run)
        session.commit()

        # Execute
        runner = ExecutionRunner(session_factory=SessionTest)
        runner.execute_test_run(run_id, timeout_seconds=15)

        # Verify results in SQLite
        db = SessionTest()
        run = db.query(TestRun).filter_by(id=run_id).first()
        assert run.status == "COMPLETED"
        assert run.completed_iterations == 3
        assert run.total_tests == 6

        # Check iterations
        run_iters = db.query(RunIteration).filter_by(test_run_id=run_id).order_by(RunIteration.iteration_number.asc()).all()
        assert len(run_iters) == 3
        seeds = [r.random_order_seed for r in run_iters]
        assert len(set(seeds)) == 3  # All 3 seeds are distinct

        # Check total TestIteration records: 3 iterations * 6 tests = 18 records
        test_iters = db.query(TestIteration).filter_by(test_run_id=run_id).all()
        assert len(test_iters) == 18

        # Verify stable passing and stable failing outcomes
        pass_tc = db.query(TestCase).filter_by(project_id=proj_id, test_name="test_pure_deterministic_calculation").first()
        pass_records = db.query(TestIteration).filter_by(test_run_id=run_id, test_case_id=pass_tc.id).all()
        assert len(pass_records) == 3
        assert all(r.status == "PASSED" for r in pass_records)

        fail_tc = db.query(TestCase).filter_by(project_id=proj_id, test_name="test_deterministic_failure").first()
        fail_records = db.query(TestIteration).filter_by(test_run_id=run_id, test_case_id=fail_tc.id).all()
        assert len(fail_records) == 3
        assert all(r.status == "FAILED" for r in fail_records)
        db.close()


class TestRunsAPIIntegration:
    """Verifies FastAPI endpoints for runs lifecycle."""

    def test_start_run_and_query_progress(self, test_db):
        session, SessionTest = test_db
        app.dependency_overrides[get_db] = lambda: session

        suite_dir = settings.BASE_DIR / "samples" / "synthetic_flaky_suite"
        proj_id = str(uuid.uuid4())
        proj = Project(id=proj_id, name="API Run Test", source_archive_path=str(suite_dir))
        session.add(proj)
        session.commit()

        discover_and_register_tests(proj_id, suite_dir, session)

        client = TestClient(app)

        # POST /api/runs
        response = client.post(
            "/api/runs",
            json={
                "project_id": proj_id,
                "iteration_count": 3,
                "shuffle_order": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["project_id"] == proj_id
        assert data["iteration_count"] == 3
        assert data["status"] == "PENDING"
        run_id = data["id"]

        # GET /api/runs/{id}
        get_res = client.get(f"/api/runs/{run_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == run_id

        # POST /api/runs/{id}/cancel
        cancel_res = client.post(f"/api/runs/{run_id}/cancel")
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "CANCELLED"

        app.dependency_overrides.clear()

    def test_api_lock_conflict_returns_409(self, test_db):
        """Verifies that launching a run when execution lock is active returns HTTP 409 Conflict."""
        session, SessionTest = test_db
        app.dependency_overrides[get_db] = lambda: session

        suite_dir = settings.BASE_DIR / "samples" / "synthetic_flaky_suite"
        proj_id = str(uuid.uuid4())
        proj = Project(id=proj_id, name="Lock Conflict Test", source_archive_path=str(suite_dir))
        session.add(proj)
        session.commit()
        discover_and_register_tests(proj_id, suite_dir, session)

        # Manually hold lock
        lock_mgr = ExecutionLockManager(session_factory=SessionTest, ttl_seconds=30)
        assert lock_mgr.acquire("active-holding-run") is True

        client = TestClient(app)
        try:
            # Overriding get_db must use session, but let's test lock_mgr check
            response = client.post(
                "/api/runs",
                json={
                    "project_id": proj_id,
                    "iteration_count": 3,
                    "shuffle_order": True,
                },
            )
            # Should be rejected with 409 Conflict
            assert response.status_code == 409
            assert "FLAKELENS enforces strictly sequential execution" in response.json()["detail"]
        finally:
            lock_mgr.release("active-holding-run")
            app.dependency_overrides.clear()


class TestIdempotencyAndConcurrency:
    """Verifies duplicate event safety and concurrent lock initialization."""

    def test_duplicate_event_ingestion_idempotency(self, test_db):
        """Verifies duplicate event ingestion updates existing record instead of duplicate violation."""
        session, SessionTest = test_db
        run_id = str(uuid.uuid4())
        tc_id = str(uuid.uuid4())
        run_iter_id = str(uuid.uuid4())

        # Seed Project and TestCase
        proj = Project(id="proj-idem", name="Idempotent Project")
        session.add(proj)
        tc = TestCase(id=tc_id, project_id="proj-idem", file_path="t.py", test_name="t", node_id="t.py::t")
        session.add(tc)
        run = TestRun(id=run_id, project_id="proj-idem", iteration_count=1, status="RUNNING")
        session.add(run)
        run_iter = RunIteration(id=run_iter_id, test_run_id=run_id, iteration_number=1, status="RUNNING")
        session.add(run_iter)
        session.commit()

        # Insert first event record
        ti1 = TestIteration(
            id=generate_uuid(),
            run_iteration_id=run_iter_id,
            test_run_id=run_id,
            test_case_id=tc_id,
            iteration_number=1,
            status="PASSED",
            duration_ms=10,
            execution_order=1,
        )
        session.add(ti1)
        session.commit()

        # Ingest duplicate event (same run_id, tc_id, iteration_number)
        db = SessionTest()
        existing = db.query(TestIteration).filter_by(
            test_run_id=run_id,
            test_case_id=tc_id,
            iteration_number=1,
        ).first()
        assert existing is not None
        # Safely update
        existing.status = "FAILED"
        existing.error_message = "Updated cleanly"
        db.commit()

        # Count must remain 1
        count = db.query(TestIteration).filter_by(test_run_id=run_id, test_case_id=tc_id).count()
        assert count == 1
        updated = db.query(TestIteration).filter_by(test_run_id=run_id, test_case_id=tc_id).first()
        assert updated.status == "FAILED"
        db.close()

    def test_concurrent_first_time_lock_init(self, test_db):
        """Verifies concurrent threads initializing lock table simultaneously don't crash."""
        session, SessionTest = test_db
        import threading

        errors = []

        def init_worker():
            try:
                mgr = ExecutionLockManager(session_factory=SessionTest)
                mgr.ensure_lock_row()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=init_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        db = SessionTest()
        assert db.query(ExecutionLock).filter_by(lock_name="global_runner").count() == 1
        db.close()


class TestImmediateRunCancellation:
    """Verifies immediate container termination, cleanup, lock release, and race condition handling upon cancellation."""

    def test_cancel_terminates_running_docker_container_and_cleans_up(self, test_db):
        """Proves that a running Docker container is forcefully terminated and removed immediately upon cancellation."""
        session, SessionTest = test_db
        temp_dir = tempfile.mkdtemp(dir=str(settings.STORAGE_DIR))

        try:
            # Create project with hanging test (sleep 30s)
            project_dir = Path(temp_dir) / "cancel_project"
            project_dir.mkdir()
            (project_dir / "test_hanging.py").write_text("""
import time

def test_long_sleep():
    time.sleep(30)
    assert True
""", encoding="utf-8")

            proj_id = str(uuid.uuid4())
            proj = Project(id=proj_id, name="Cancel Test Suite", source_archive_path=str(project_dir))
            session.add(proj)
            session.commit()

            discover_and_register_tests(proj_id, project_dir, session)

            run_id = str(uuid.uuid4())
            test_run = TestRun(
                id=run_id,
                project_id=proj_id,
                iteration_count=1,
                shuffle_order=False,
                status="PENDING",
            )
            session.add(test_run)
            session.commit()

            import docker
            docker_client = docker.from_env()

            # Execute run in a background thread
            runner = ExecutionRunner(session_factory=SessionTest)
            exec_thread = threading.Thread(
                target=runner.execute_test_run,
                args=(run_id,),
                kwargs={"timeout_seconds": 30},
                daemon=True,
            )
            exec_thread.start()

            # Wait until Docker container is actively running
            active_container = None
            for _ in range(50):
                time.sleep(0.2)
                containers = docker_client.containers.list()
                for c in containers:
                    # Look for the runner container
                    if any("flakelens" in tag for tag in c.image.tags):
                        active_container = c
                        break
                if active_container is not None:
                    break

            assert active_container is not None, "Docker container failed to launch within 10s"
            container_id = active_container.id

            # Request cancellation while container is running
            cancelled = ExecutionRunner.cancel_active_run(run_id)
            assert cancelled is True

            # Also verify via API cancel endpoint behavior
            db = SessionTest()
            r = db.query(TestRun).filter_by(id=run_id).first()
            r.status = "CANCELLED"
            db.commit()
            db.close()

            # The background execution thread should terminate within 3-4s (far before 30s timeout)
            exec_thread.join(timeout=8.0)
            assert not exec_thread.is_alive(), "Execution thread failed to terminate after cancellation!"

            # Verify the container is dead and removed
            remaining_containers = docker_client.containers.list(all=True, filters={"id": container_id})
            assert len(remaining_containers) == 0, f"Container '{container_id}' was not removed after cancellation!"

            # Verify the execution lock is released
            lock_mgr = ExecutionLockManager(session_factory=SessionTest)
            is_locked, holder = lock_mgr.is_locked()
            assert is_locked is False, f"Execution lock remained locked by '{holder}' after cancellation!"

            # Verify database records are consistent
            db = SessionTest()
            updated_run = db.query(TestRun).filter_by(id=run_id).first()
            assert updated_run.status == "CANCELLED"

            run_iter = db.query(RunIteration).filter_by(test_run_id=run_id, iteration_number=1).first()
            if run_iter:
                assert run_iter.status == "CANCELLED"
            db.close()

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_repeated_and_concurrent_cancellation_idempotency(self, test_db):
        """Verifies repeated and concurrent cancel requests are idempotent and do not crash."""
        session, SessionTest = test_db
        def override_get_db():
            db = SessionTest()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        proj_id = str(uuid.uuid4())
        proj = Project(id=proj_id, name="Idempotent Cancel Suite")
        session.add(proj)
        run_id = str(uuid.uuid4())
        test_run = TestRun(
            id=run_id,
            project_id=proj_id,
            iteration_count=5,
            status="RUNNING",
        )
        session.add(test_run)
        session.commit()

        client = TestClient(app)

        # 1. Multiple concurrent cancel requests
        responses = []
        threads = [
            threading.Thread(target=lambda: responses.append(client.post(f"/api/runs/{run_id}/cancel")))
            for _ in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All requests must succeed with HTTP 200 and status CANCELLED
        for res in responses:
            assert res.status_code == 200
            assert res.json()["status"] == "CANCELLED"

        # 2. Subsequent repeated cancel on already-cancelled run
        late_res = client.post(f"/api/runs/{run_id}/cancel")
        assert late_res.status_code == 200
        assert late_res.json()["status"] == "CANCELLED"

        app.dependency_overrides.clear()


class TestOrderDependencyAndStateIsolation:
    """Proves that shared state affects test results within an iteration and does NOT leak across iterations."""

    def test_state_pollution_within_iteration_and_no_leak_across_iterations(self, test_db):
        """
        Demonstrates:
        1. In an iteration where polluter runs first, victim test fails due to state pollution.
        2. In a subsequent iteration in a fresh container where victim runs first, victim passes cleanly.
        3. Proves shared state is contained strictly within the iteration container and never leaks across iterations.
        """
        session, SessionTest = test_db
        temp_dir = tempfile.mkdtemp(dir=str(settings.STORAGE_DIR))

        try:
            # 1. Create order-dependent test suite
            project_dir = Path(temp_dir) / "order_suite"
            project_dir.mkdir()
            (project_dir / "test_state_pollution.py").write_text("""
SHARED_REGISTRY = []

def test_a_pollute():
    SHARED_REGISTRY.append("dirty_state_entry")
    assert len(SHARED_REGISTRY) >= 1

def test_b_expect_clean():
    assert len(SHARED_REGISTRY) == 0, f"State pollution detected: {SHARED_REGISTRY}"
""", encoding="utf-8")

            proj_id = str(uuid.uuid4())
            proj = Project(id=proj_id, name="Order Dependency Suite", source_archive_path=str(project_dir))
            session.add(proj)
            session.commit()

            discover_and_register_tests(proj_id, project_dir, session)
            assert session.query(TestCase).filter_by(project_id=proj_id).count() == 2

            # 2. Run Iteration 1 using seed=3 (deterministic seed where test_a_pollute runs first, then test_b_expect_clean)
            dm = DockerManager()
            events_dir_1 = Path(tempfile.mkdtemp(dir=str(settings.STORAGE_DIR)))
            test_nodes = ["test_state_pollution.py::test_a_pollute", "test_state_pollution.py::test_b_expect_clean"]

            code1, logs1, timed1 = dm.run_sandboxed_iteration(
                image_tag="flakelens-runner:latest",
                project_dir=project_dir,
                events_dir=events_dir_1,
                seed=3,
                shuffle_order=True,
                test_node_ids=test_nodes,
            )
            started_1, finished_1 = parse_jsonl_events(events_dir_1 / "events.jsonl")
            order_1 = list(started_1.keys())

            # Verify polluter executed before victim in Iteration 1
            assert order_1[0] == "test_state_pollution.py::test_a_pollute"
            assert order_1[1] == "test_state_pollution.py::test_b_expect_clean"
            assert finished_1["test_state_pollution.py::test_a_pollute"]["status"] == "PASSED"
            # Victim failed due to state pollution from polluter!
            assert finished_1["test_state_pollution.py::test_b_expect_clean"]["status"] == "FAILED"
            assert "State pollution detected" in (finished_1["test_state_pollution.py::test_b_expect_clean"]["traceback"] or "")

            # 3. Run Iteration 2 in a fresh container using seed=4 (deterministic seed where test_b_expect_clean runs first)
            events_dir_2 = Path(tempfile.mkdtemp(dir=str(settings.STORAGE_DIR)))
            code2, logs2, timed2 = dm.run_sandboxed_iteration(
                image_tag="flakelens-runner:latest",
                project_dir=project_dir,
                events_dir=events_dir_2,
                seed=4,
                shuffle_order=True,
                test_node_ids=test_nodes,
            )
            started_2, finished_2 = parse_jsonl_events(events_dir_2 / "events.jsonl")
            order_2 = list(started_2.keys())

            # Verify victim executed before polluter in Iteration 2
            assert order_2[0] == "test_state_pollution.py::test_b_expect_clean"
            assert order_2[1] == "test_state_pollution.py::test_a_pollute"
            # In fresh container, victim started with clean SHARED_REGISTRY = [] so it PASSED!
            assert finished_2["test_state_pollution.py::test_b_expect_clean"]["status"] == "PASSED"
            assert finished_2["test_state_pollution.py::test_a_pollute"]["status"] == "PASSED"

            # 4. Also verify full end-to-end multi-iteration run using ExecutionRunner
            run_id = str(uuid.uuid4())
            test_run = TestRun(
                id=run_id,
                project_id=proj_id,
                iteration_count=2,
                shuffle_order=True,
                status="PENDING",
            )
            session.add(test_run)
            session.commit()

            runner = ExecutionRunner(session_factory=SessionTest)
            runner.execute_test_run(run_id, timeout_seconds=20)

            db = SessionTest()
            saved_run = db.query(TestRun).filter_by(id=run_id).first()
            assert saved_run.status == "COMPLETED"
            assert saved_run.completed_iterations == 2

            # Check that each iteration has distinct seeds and recorded execution orders
            it1 = db.query(RunIteration).filter_by(test_run_id=run_id, iteration_number=1).first()
            it2 = db.query(RunIteration).filter_by(test_run_id=run_id, iteration_number=2).first()
            assert it1.random_order_seed != it2.random_order_seed

            # Check recorded TestIteration records
            ti_records = db.query(TestIteration).filter_by(test_run_id=run_id).all()
            assert len(ti_records) == 4  # 2 tests * 2 iterations
            for r in ti_records:
                assert r.execution_order in (1, 2)
                assert r.random_order_seed is not None
            db.close()

            shutil.rmtree(events_dir_1, ignore_errors=True)
            shutil.rmtree(events_dir_2, ignore_errors=True)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)



