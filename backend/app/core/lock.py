"""
Distributed Execution Lock with Heartbeat and Stale Lock Recovery for FLAKELENS.

Guarantees strictly sequential Docker test execution:
- Database-backed via SQLite execution_locks table.
- Automatic background heartbeat renewal during active test runs.
- Deterministic stale lock recovery after backend crashes.
- Clean heartbeat thread shutdown prior to database lock release.
- Lock ownership verification on every renewal tick.
"""
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.app.config import settings
from backend.app.db.models import ExecutionLock
from backend.app.db.session import SessionLocal


class ExecutionLockError(Exception):
    """Base exception for execution locking errors."""
    pass


class LockAcquisitionError(ExecutionLockError):
    """Raised when unable to acquire the global execution lock."""
    pass


class LockLostError(ExecutionLockError):
    """Raised when active execution lock ownership is lost during heartbeat renewal."""
    pass


class LockShutdownError(ExecutionLockError):
    """Raised when heartbeat thread fails to terminate cleanly before release."""
    pass


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    """Helper to ensure datetimes compared against UTC are timezone-aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ExecutionLockManager:
    """
    Manages the global database execution lock and background heartbeat thread.
    """

    LOCK_NAME = "global_runner"

    def __init__(
        self,
        session_factory=None,
        lock_name: str = "global_runner",
        ttl_seconds: int = 30,
        heartbeat_interval: float = 10.0,
        thread_stop_timeout: float = 5.0,
    ) -> None:
        self.session_factory = session_factory or SessionLocal
        self.lock_name = lock_name
        self.ttl_seconds = ttl_seconds
        self.heartbeat_interval = heartbeat_interval
        self.thread_stop_timeout = thread_stop_timeout

        self._current_run_id: Optional[str] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock_lost_event = threading.Event()

    def ensure_lock_row(self) -> None:
        """
        Ensures the singleton lock row exists in execution_locks table.
        Safe against concurrent first-time initialization.
        """
        db: Session = self.session_factory()
        try:
            lock_row = db.query(ExecutionLock).filter(ExecutionLock.lock_name == self.lock_name).first()
            if not lock_row:
                try:
                    new_lock = ExecutionLock(
                        lock_name=self.lock_name,
                        locked_by_run_id=None,
                        acquired_at=None,
                        last_heartbeat_at=None,
                        expires_at=None,
                    )
                    db.add(new_lock)
                    db.commit()
                except IntegrityError:
                    db.rollback()
        finally:
            db.close()

    def acquire(self, run_id: str) -> bool:
        """
        Attempts to acquire the global execution lock for run_id.
        Recovers stale locks where expires_at < now.

        Returns:
            bool: True if lock was acquired, False if currently held by another active run.
        """
        self.ensure_lock_row()
        db: Session = self.session_factory()
        try:
            now = datetime.now(timezone.utc)
            # Find lock row
            lock_row = (
                db.query(ExecutionLock)
                .filter(ExecutionLock.lock_name == self.lock_name)
                .with_for_update() if db.bind.dialect.name != "sqlite" else db.query(ExecutionLock).filter(ExecutionLock.lock_name == self.lock_name)
            ).first()

            if not lock_row:
                self.ensure_lock_row()
                lock_row = db.query(ExecutionLock).filter(ExecutionLock.lock_name == self.lock_name).first()

            # Check if available or stale
            is_free = lock_row.locked_by_run_id is None
            normalized_expiry = _normalize_dt(lock_row.expires_at)
            is_stale = normalized_expiry is not None and normalized_expiry < now

            if is_free or is_stale:
                new_expiry = now + timedelta(seconds=self.ttl_seconds)
                lock_row.locked_by_run_id = run_id
                lock_row.acquired_at = now
                lock_row.last_heartbeat_at = now
                lock_row.expires_at = new_expiry
                db.commit()

                self._current_run_id = run_id
                self._stop_event.clear()
                self._lock_lost_event.clear()
                self._start_heartbeat()
                return True

            return False
        finally:
            db.close()

    def is_locked(self) -> Tuple[bool, Optional[str]]:
        """
        Check if the lock is currently held by an active run.

        Returns:
            Tuple[bool, Optional[str]]: (is_locked, locked_by_run_id)
        """
        self.ensure_lock_row()
        db: Session = self.session_factory()
        try:
            now = datetime.now(timezone.utc)
            lock_row = db.query(ExecutionLock).filter(ExecutionLock.lock_name == self.lock_name).first()
            if not lock_row or lock_row.locked_by_run_id is None:
                return False, None

            normalized_expiry = _normalize_dt(lock_row.expires_at)
            if normalized_expiry is not None and normalized_expiry < now:
                # Stale lock
                return False, None

            return True, lock_row.locked_by_run_id
        finally:
            db.close()

    def _start_heartbeat(self) -> None:
        """Starts background thread periodically renewing expires_at."""
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"FLAKELENS-Heartbeat-{self._current_run_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        """Background loop executing lock renewal at heartbeat_interval."""
        run_id = self._current_run_id
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.heartbeat_interval):
                break

            # Renew lock
            success = self._renew_lock(run_id)
            if not success:
                self._lock_lost_event.set()
                break

    def _renew_lock(self, run_id: str) -> bool:
        """
        Renews last_heartbeat_at and expires_at in the database strictly matching run_id.

        Returns:
            bool: True if renewed, False if ownership was lost.
        """
        db: Session = self.session_factory()
        try:
            now = datetime.now(timezone.utc)
            new_expiry = now + timedelta(seconds=self.ttl_seconds)

            # Atomic conditional update
            stmt = (
                update(ExecutionLock)
                .where(
                    ExecutionLock.lock_name == self.lock_name,
                    ExecutionLock.locked_by_run_id == run_id,
                )
                .values(
                    last_heartbeat_at=now,
                    expires_at=new_expiry,
                )
            )
            result = db.execute(stmt)
            db.commit()

            if result.rowcount == 0:
                # Lock row was cleared or acquired by someone else
                return False
            return True
        except Exception:
            return False
        finally:
            db.close()

    def is_lock_lost(self) -> bool:
        """Checks if heartbeat detected lock loss."""
        return self._lock_lost_event.is_set()

    def release(self, run_id: Optional[str] = None) -> None:
        """
        Safely releases the execution lock:
        1. Fully stops the heartbeat thread.
        2. Clears lock row in the database matching run_id.
        """
        target_run_id = run_id or self._current_run_id
        if not target_run_id:
            return

        # 1. Stop heartbeat thread cleanly
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._stop_event.set()
            self._heartbeat_thread.join(timeout=self.thread_stop_timeout)
            if self._heartbeat_thread.is_alive():
                raise LockShutdownError(
                    f"Heartbeat thread failed to terminate within {self.thread_stop_timeout}s. "
                    "Unsafe to release database lock while heartbeat may still renew."
                )

        # 2. Release lock in database only after heartbeat has verified stopped
        db: Session = self.session_factory()
        try:
            stmt = (
                update(ExecutionLock)
                .where(
                    ExecutionLock.lock_name == self.lock_name,
                    ExecutionLock.locked_by_run_id == target_run_id,
                )
                .values(
                    locked_by_run_id=None,
                    expires_at=None,
                )
            )
            db.execute(stmt)
            db.commit()
            self._current_run_id = None
        finally:
            db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._current_run_id:
            try:
                self.release(self._current_run_id)
            except Exception:
                pass
