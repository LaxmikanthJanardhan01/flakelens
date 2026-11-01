"""
Repeated Test Execution Engine for FLAKELENS.

Orchestrates multi-iteration test execution strictly inside isolated Docker containers:
- Sequential single-container execution enforced via database execution lock.
- Background heartbeat renewal and stale lock detection.
- Structured real-time event ingestion from pytest JSONL telemetry.
- Post-mortem recovery for timeouts and forced container terminations.
- Per-iteration and per-test database recording with unique constraints.
"""
import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db.models import (
    Project,
    TestCase,
    TestRun,
    RunIteration,
    TestIteration,
    generate_uuid,
)
from backend.app.db.session import SessionLocal
from backend.app.core.docker_manager import (
    DockerManager,
    DockerUnavailableError,
    ProjectBuildError,
)
from backend.app.core.lock import (
    ExecutionLockManager,
    LockAcquisitionError,
    LockLostError,
)

logger = logging.getLogger(__name__)


def generate_deterministic_seed(run_id: str, iteration_number: int) -> int:
    """
    Generates a deterministic, reproducible integer random-order seed for an iteration.
    """
    raw_key = f"{run_id}-iter-{iteration_number}".encode("utf-8")
    hex_digest = hashlib.sha256(raw_key).hexdigest()
    # 32-bit positive integer suitable for pytest-random-order
    return int(hex_digest[:8], 16) % 1_000_000


def parse_jsonl_events(events_file_path: Path) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """
    Safely parses JSONL events from the telemetry file.
    Tolerates truncated or corrupt trailing lines resulting from forced container termination.

    Returns:
        Tuple[Dict[node_id, started_event], Dict[node_id, finished_event]]
    """
    started: Dict[str, dict] = {}
    finished: Dict[str, dict] = {}

    if not events_file_path.exists():
        return started, finished

    try:
        with open(events_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    ev_type = event.get("event")
                    node_id = event.get("node_id")
                    if not node_id:
                        continue

                    if ev_type == "test_started":
                        started[node_id] = event
                    elif ev_type == "test_finished":
                        finished[node_id] = event
                except json.JSONDecodeError:
                    # Incomplete or corrupt line due to SIGKILL; safely ignore
                    continue
    except Exception as e:
        logger.warning(f"Error reading JSONL telemetry file {events_file_path}: {e}")

    return started, finished


class ExecutionRunner:
    """
    Engine executing discovered test cases across N iterations inside isolated containers.
    """
    _active_runners: Dict[str, "ExecutionRunner"] = {}
    _registry_lock = threading.Lock()

    @classmethod
    def get_active_runner(cls, run_id: str) -> Optional["ExecutionRunner"]:
        with cls._registry_lock:
            return cls._active_runners.get(run_id)

    @classmethod
    def register_active_runner(cls, run_id: str, runner: "ExecutionRunner") -> None:
        with cls._registry_lock:
            cls._active_runners[run_id] = runner

    @classmethod
    def unregister_active_runner(cls, run_id: str) -> None:
        with cls._registry_lock:
            cls._active_runners.pop(run_id, None)

    @classmethod
    def cancel_active_run(cls, run_id: str) -> bool:
        """
        Signals immediate cancellation to the active runner and forcefully kills the active container.
        """
        with cls._registry_lock:
            runner = cls._active_runners.get(run_id)
        if runner:
            return runner.request_cancel()
        return False

    def __init__(
        self,
        session_factory=None,
        docker_mgr: Optional[DockerManager] = None,
        lock_mgr: Optional[ExecutionLockManager] = None,
    ) -> None:
        self.session_factory = session_factory or SessionLocal
        self.docker_mgr = docker_mgr or DockerManager()
        self.lock_mgr = lock_mgr or ExecutionLockManager(session_factory=self.session_factory)
        self._cancel_event = threading.Event()
        self._container_lock = threading.Lock()
        self._active_container: Optional[Any] = None

    def _set_active_container(self, container: Optional[Any]) -> None:
        """Tracks the actively executing Docker container for immediate cancellation."""
        with self._container_lock:
            self._active_container = container
            if self._cancel_event.is_set() and container is not None:
                try:
                    logger.info(f"Cancellation active; immediately terminating container '{container.id}'")
                    container.kill()
                except Exception as e:
                    logger.warning(f"Error terminating container on cancellation: {e}")

    def request_cancel(self) -> bool:
        """Initiates immediate cancellation and forcefully kills any active container."""
        self._cancel_event.set()
        with self._container_lock:
            if self._active_container is not None:
                try:
                    logger.info(f"Killing active Docker container '{self._active_container.id}' due to user cancellation")
                    self._active_container.kill()
                except Exception as e:
                    logger.warning(f"Error killing active container during cancel request: {e}")
        return True

    def execute_test_run(
        self,
        test_run_id: str,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        """
        Executes all iterations for test_run_id sequentially under global execution lock.

        Args:
            test_run_id: UUID of the TestRun database entity.
            timeout_seconds: Maximum wall-clock time allowed per iteration (default settings.DOCKER_ITERATION_TIMEOUT).
        """
        ExecutionRunner.register_active_runner(test_run_id, self)
        iteration_timeout = timeout_seconds or settings.DOCKER_ITERATION_TIMEOUT
        db: Session = self.session_factory()

        try:
            # 1. Fetch test run
            test_run = db.query(TestRun).filter(TestRun.id == test_run_id).first()
            if not test_run:
                logger.error(f"TestRun '{test_run_id}' not found.")
                return

            if test_run.status == "CANCELLED" or self._cancel_event.is_set():
                logger.info(f"TestRun '{test_run_id}' was cancelled before execution started.")
                return

            # 2. Acquire global execution lock
            acquired = self.lock_mgr.acquire(test_run_id)
            if not acquired:
                test_run.status = "FAILED"
                db.commit()
                raise LockAcquisitionError(
                    f"Execution lock is currently held by another active run. "
                    f"Run '{test_run_id}' rejected to guarantee sequential execution."
                )

            if test_run.status == "CANCELLED" or self._cancel_event.is_set():
                test_run.status = "CANCELLED"
                test_run.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            # 3. Verify Docker availability
            is_avail, docker_err = self.docker_mgr.is_available()
            if not is_avail:
                test_run.status = "FAILED"
                db.commit()
                raise DockerUnavailableError(docker_err or "Docker daemon unavailable.")

            # 4. Fetch project and test cases
            project = db.query(Project).filter(Project.id == test_run.project_id).first()
            if not project:
                test_run.status = "FAILED"
                db.commit()
                return

            project_dir = settings.UPLOADS_DIR / project.id
            if not project_dir.exists() and project.source_archive_path:
                project_dir = Path(project.source_archive_path)

            test_cases = db.query(TestCase).filter(TestCase.project_id == project.id).all()
            if not test_cases:
                # No tests to run
                test_run.status = "COMPLETED"
                test_run.total_tests = 0
                test_run.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            test_run.total_tests = len(test_cases)

            # 5. Stage A: Prepare execution image
            image_tag = self.docker_mgr.prepare_project_image(project_dir, project.id)

            if test_run.status == "CANCELLED" or self._cancel_event.is_set():
                test_run.status = "CANCELLED"
                test_run.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            # 6. Mark run active
            test_run.status = "RUNNING"
            test_run.started_at = datetime.now(timezone.utc)
            db.commit()

            total_iterations = test_run.iteration_count
            has_timed_out_iteration = False

            # 7. Iteration Loop
            for iter_idx in range(1, total_iterations + 1):
                # Check for external cancellation
                db.refresh(test_run)
                if test_run.status == "CANCELLED" or self._cancel_event.is_set():
                    logger.info(f"TestRun '{test_run_id}' was cancelled by user.")
                    break

                # Verify lock ownership was not lost
                if self.lock_mgr.is_lock_lost():
                    test_run.status = "FAILED"
                    db.commit()
                    raise LockLostError("Execution lock lost during active run execution.")

                # Generate seed and initialize RunIteration record
                seed = generate_deterministic_seed(test_run_id, iter_idx)
                run_iter = (
                    db.query(RunIteration)
                    .filter(
                        RunIteration.test_run_id == test_run_id,
                        RunIteration.iteration_number == iter_idx,
                    )
                    .first()
                )
                if not run_iter:
                    run_iter = RunIteration(
                        id=generate_uuid(),
                        test_run_id=test_run_id,
                        iteration_number=iter_idx,
                        status="RUNNING",
                        random_order_seed=seed,
                        started_at=datetime.now(timezone.utc),
                    )
                    db.add(run_iter)
                    db.commit()
                    db.refresh(run_iter)

                # Prepare ephemeral host telemetry directory
                events_dir = Path(tempfile.mkdtemp(dir=str(settings.STORAGE_DIR)))
                events_file = events_dir / "events.jsonl"
                iter_start_time = time.time()

                try:
                    # Execute iteration in isolated Docker container using discovered test node IDs
                    test_node_ids = [tc.node_id for tc in test_cases]
                    exit_code, logs, timed_out = self.docker_mgr.run_sandboxed_iteration(
                        image_tag=image_tag,
                        project_dir=project_dir,
                        events_dir=events_dir,
                        seed=seed,
                        shuffle_order=test_run.shuffle_order,
                        test_node_ids=test_node_ids,
                        timeout_seconds=iteration_timeout,
                        cancel_event=self._cancel_event,
                        on_container_started=self._set_active_container,
                    )
                    iter_duration_ms = max(1, int((time.time() - iter_start_time) * 1000))

                    # Immediate handling if cancelled during iteration
                    if self._cancel_event.is_set() or test_run.status == "CANCELLED":
                        logger.info(f"Iteration {iter_idx} cancelled by user for run '{test_run_id}'.")
                        run_iter.status = "CANCELLED"
                        run_iter.duration_ms = iter_duration_ms
                        run_iter.completed_at = datetime.now(timezone.utc)

                        started_events, finished_events = parse_jsonl_events(events_file)
                        for tc in test_cases:
                            node_id = tc.node_id
                            if node_id in finished_events:
                                ev = finished_events[node_id]
                                status = ev.get("status", "FAILED")
                                dur_ms = ev.get("duration_ms", 1)
                                stdout_text = ev.get("stdout", "")
                                stderr_text = ev.get("stderr", "")
                                err_msg = ev.get("error_message")
                                tb_text = ev.get("traceback")
                            else:
                                status = "CANCELLED"
                                dur_ms = 0
                                stdout_text = ""
                                stderr_text = ""
                                err_msg = "Execution cancelled by user"
                                tb_text = None

                            existing_ti = (
                                db.query(TestIteration)
                                .filter(
                                    TestIteration.test_run_id == test_run_id,
                                    TestIteration.test_case_id == tc.id,
                                    TestIteration.iteration_number == iter_idx,
                                )
                                .first()
                            )
                            if existing_ti:
                                existing_ti.run_iteration_id = run_iter.id
                                existing_ti.status = status
                                existing_ti.duration_ms = dur_ms
                                existing_ti.error_message = err_msg
                            else:
                                new_ti = TestIteration(
                                    id=generate_uuid(),
                                    run_iteration_id=run_iter.id,
                                    test_run_id=test_run_id,
                                    test_case_id=tc.id,
                                    iteration_number=iter_idx,
                                    status=status,
                                    duration_ms=dur_ms,
                                    execution_order=0,
                                    random_order_seed=seed,
                                    stdout=stdout_text,
                                    stderr=stderr_text,
                                    error_message=err_msg,
                                    traceback=tb_text,
                                )
                                db.add(new_ti)
                        db.commit()
                        break

                    if timed_out:
                        has_timed_out_iteration = True

                    # Ingest real-time JSONL events
                    started_events, finished_events = parse_jsonl_events(events_file)

                    # Determine execution order based on started events
                    started_order = list(started_events.keys())

                    for tc in test_cases:
                        node_id = tc.node_id
                        exec_order = (
                            started_order.index(node_id) + 1
                            if node_id in started_order
                            else len(started_order) + 1
                        )

                        if node_id in finished_events:
                            ev = finished_events[node_id]
                            status = ev.get("status", "FAILED")
                            dur_ms = ev.get("duration_ms", 1)
                            stdout_text = ev.get("stdout", "")
                            stderr_text = ev.get("stderr", "")
                            err_msg = ev.get("error_message")
                            tb_text = ev.get("traceback")
                        elif node_id in started_events:
                            # Test was active when container was terminated
                            start_t = started_events[node_id].get("timestamp", iter_start_time)
                            dur_ms = max(1, int((time.time() - start_t) * 1000))
                            status = "TIMED_OUT"
                            stdout_text = ""
                            stderr_text = ""
                            err_msg = f"Execution timed out after {iteration_timeout}s"
                            tb_text = None
                        else:
                            # Test never began execution
                            status = "NOT_EXECUTED"
                            dur_ms = 0
                            stdout_text = ""
                            stderr_text = ""
                            err_msg = "Not executed due to iteration timeout"
                            tb_text = None

                        # Idempotent database record persistence
                        existing_ti = (
                            db.query(TestIteration)
                            .filter(
                                TestIteration.test_run_id == test_run_id,
                                TestIteration.test_case_id == tc.id,
                                TestIteration.iteration_number == iter_idx,
                            )
                            .first()
                        )
                        if existing_ti:
                            existing_ti.run_iteration_id = run_iter.id
                            existing_ti.status = status
                            existing_ti.duration_ms = dur_ms
                            existing_ti.execution_order = exec_order
                            existing_ti.random_order_seed = seed
                            existing_ti.stdout = stdout_text
                            existing_ti.stderr = stderr_text
                            existing_ti.error_message = err_msg
                            existing_ti.traceback = tb_text
                        else:
                            new_ti = TestIteration(
                                id=generate_uuid(),
                                run_iteration_id=run_iter.id,
                                test_run_id=test_run_id,
                                test_case_id=tc.id,
                                iteration_number=iter_idx,
                                status=status,
                                duration_ms=dur_ms,
                                execution_order=exec_order,
                                random_order_seed=seed,
                                stdout=stdout_text,
                                stderr=stderr_text,
                                error_message=err_msg,
                                traceback=tb_text,
                            )
                            db.add(new_ti)

                    # Update iteration status: TIMED_OUT or COMPLETED
                    run_iter.status = "TIMED_OUT" if timed_out else "COMPLETED"
                    run_iter.duration_ms = iter_duration_ms
                    run_iter.completed_at = datetime.now(timezone.utc)
                    db.commit()

                finally:
                    shutil.rmtree(events_dir, ignore_errors=True)

            # 8. Finalize TestRun status
            db.refresh(test_run)
            if self._cancel_event.is_set() or test_run.status == "CANCELLED":
                test_run.status = "CANCELLED"
                test_run.completed_at = datetime.now(timezone.utc)
                db.commit()
            else:
                test_run.status = "TIMED_OUT" if has_timed_out_iteration else "COMPLETED"
                test_run.completed_at = datetime.now(timezone.utc)
                db.commit()

            # 9. Milestone 4: Trigger flakiness detection and report synthesis
            try:
                from backend.app.core.detector import FlakinessDetector
                detector = FlakinessDetector()
                detector.analyze_test_run(test_run_id, db, allow_active=True)
            except Exception as e:
                logger.exception(f"Error during post-execution flakiness analysis for run '{test_run_id}': {e}")

            # 10. Milestone 5: Trigger evidence-based Root Cause Analysis (RCA)
            try:
                from backend.app.core.rca_engine import RCAEngine
                rca_engine = RCAEngine()
                rca_engine.analyze_test_run_rca(test_run_id, db, allow_active=True)
                db.commit()
            except Exception as e:
                logger.exception(f"Error during post-execution root cause analysis for run '{test_run_id}': {e}")

        except Exception as e:
            logger.exception(f"Unhandled error during test run execution '{test_run_id}': {e}")
            try:
                db.refresh(test_run)
                if test_run.status not in ("COMPLETED", "CANCELLED"):
                    test_run.status = "FAILED"
                    db.commit()
            except Exception:
                pass
            raise

        finally:
            # Always safely release execution lock after container and heartbeat termination
            try:
                self.lock_mgr.release(test_run_id)
            except Exception as e:
                logger.warning(f"Error releasing execution lock for run '{test_run_id}': {e}")
            ExecutionRunner.unregister_active_runner(test_run_id)
            db.close()
