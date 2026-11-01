import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.app.db.models import (
    Base,
    Project,
    TestCase,
    TestRun,
    RunIteration,
    TestIteration,
    ExecutionLock,
)
from backend.app.db.migrate import migrate_db, MigrationDuplicateDataError


def test_foreign_key_enforcement():
    print("================================================================================")
    print("CHECK 1: FOREIGN KEY ENFORCEMENT & ON DELETE CASCADE")
    print("================================================================================")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "test_fk.db"

        # Setup engine with SQLite foreign_keys=ON pragma
        engine = create_engine(f"sqlite:///{db_path}")

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # Migrate DB
        migrate_db(engine)

        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            # 1. Verify PRAGMA foreign_keys returns 1
            with engine.connect() as conn:
                fk_status = conn.execute(text("PRAGMA foreign_keys")).scalar()
                print(f"  [PASS] PRAGMA foreign_keys check: {fk_status} (Expected: 1)")
                assert fk_status == 1, f"Expected foreign_keys=1, got {fk_status}"

            # 2. Setup parent records: Project, TestCase, TestRun
            proj = Project(name="FK Test Project")
            session.add(proj)
            session.commit()

            tc = TestCase(project_id=proj.id, file_path="test_x.py", test_name="test_1", node_id="test_x.py::test_1")
            run = TestRun(project_id=proj.id, iteration_count=3)
            session.add_all([tc, run])
            session.commit()

            # 3. Test invalid foreign key rejection on run_iteration_id
            print("\n  Testing invalid run_iteration_id rejection:")
            invalid_test_iter = TestIteration(
                test_run_id=run.id,
                test_case_id=tc.id,
                iteration_number=1,
                run_iteration_id="nonexistent-run-iteration-uuid",  # Does NOT exist!
                status="PASSED",
                duration_ms=10.0,
                execution_order=1,
            )
            session.add(invalid_test_iter)
            try:
                session.commit()
                assert False, "FAILED! TestIteration with nonexistent run_iteration_id was accepted!"
            except IntegrityError as exc:
                session.rollback()
                print(f"  [PASS] Nonexistent run_iteration_id strictly rejected: {exc.orig}")

            # 4. Test valid foreign key insertion and ON DELETE CASCADE
            print("\n  Testing ON DELETE CASCADE on RunIteration:")
            run_iter = RunIteration(test_run_id=run.id, iteration_number=1, status="COMPLETED")
            session.add(run_iter)
            session.commit()

            valid_test_iter = TestIteration(
                test_run_id=run.id,
                test_case_id=tc.id,
                iteration_number=1,
                run_iteration_id=run_iter.id,
                status="PASSED",
                duration_ms=25.0,
                execution_order=1,
            )
            session.add(valid_test_iter)
            session.commit()
            print(f"  [PASS] Inserted TestIteration linked to valid RunIteration (id='{run_iter.id}').")

            # Verify existence
            ti_count_before = session.query(TestIteration).filter_by(run_iteration_id=run_iter.id).count()
            assert ti_count_before == 1

            # Delete the parent RunIteration
            session.delete(run_iter)
            session.commit()
            print("  [ACTION] Deleted parent RunIteration.")

            # Verify that child TestIteration was deleted by ON DELETE CASCADE
            ti_count_after = session.query(TestIteration).filter_by(id=valid_test_iter.id).count()
            print(f"  [PASS] Child TestIteration count after parent deletion: {ti_count_after} (Expected: 0)")
            assert ti_count_after == 0, "ON DELETE CASCADE failed: Child TestIteration still exists!"

        finally:
            session.close()
            engine.dispose()


def test_existing_duplicate_data_safety():
    print("\n================================================================================")
    print("CHECK 2: EXISTING DUPLICATE DATA SAFETY & TRANSACTION ROLLBACK")
    print("================================================================================")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "test_duplicate_safety.db"

        # ----------------------------------------------------------------------
        # Setup Phase 1 database with intentional duplicate test_iterations rows
        # ----------------------------------------------------------------------
        raw_conn = sqlite3.connect(str(db_path))
        raw_cur = raw_conn.cursor()

        raw_cur.execute("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL, source_archive_path VARCHAR(1024), created_at DATETIME NOT NULL);")
        raw_cur.execute("CREATE TABLE test_cases (id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(36) NOT NULL, file_path VARCHAR(1024), test_name VARCHAR(255), node_id VARCHAR(1024), discovered_at DATETIME);")
        raw_cur.execute("CREATE TABLE test_runs (id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(36) NOT NULL, iteration_count INTEGER, shuffle_order BOOLEAN, status VARCHAR(50), total_tests INTEGER, consistently_passing_count INTEGER, consistently_failing_count INTEGER, flaky_tests_count INTEGER, started_at DATETIME, completed_at DATETIME);")
        raw_cur.execute("CREATE TABLE test_iterations (id VARCHAR(36) PRIMARY KEY, test_run_id VARCHAR(36), test_case_id VARCHAR(36), iteration_number INTEGER, status VARCHAR(50), duration_ms FLOAT, execution_order INTEGER, random_order_seed INTEGER, stdout TEXT, stderr TEXT, error_message TEXT, traceback TEXT);")

        # Insert Project and TestCase
        raw_cur.execute("INSERT INTO projects VALUES ('p-dup', 'Duplicate Test Project', NULL, '2026-11-01 10:00:00')")
        raw_cur.execute("INSERT INTO test_cases VALUES ('tc-dup', 'p-dup', 'test.py', 'test_one', 'test.py::test_one', '2026-11-01 10:00:00')")
        raw_cur.execute("INSERT INTO test_runs VALUES ('run-dup', 'p-dup', 3, 1, 'COMPLETED', 1, 1, 0, 0, '2026-11-01 10:00:00', '2026-11-01 10:00:10')")

        # Insert INTENTIONAL DUPLICATES: Two rows with exact same (test_run_id='run-dup', test_case_id='tc-dup', iteration_number=1)
        raw_cur.execute("INSERT INTO test_iterations VALUES ('row-1', 'run-dup', 'tc-dup', 1, 'PASSED', 10.0, 1, 42, 'run 1', '', NULL, NULL)")
        raw_cur.execute("INSERT INTO test_iterations VALUES ('row-2', 'run-dup', 'tc-dup', 1, 'FAILED', 12.0, 1, 42, 'run 1 duplicate', '', 'err', 'trace')")
        raw_conn.commit()
        raw_conn.close()

        print("  [INITIAL STATE] Seeded database with 2 conflicting rows for (run-dup, tc-dup, iteration=1).")

        # Attempt migration
        engine = create_engine(f"sqlite:///{db_path}")

        print("\n  Executing migrate_db() on database containing duplicates:")
        migration_failed = False
        try:
            migrate_db(engine)
            assert False, "FAILED! migrate_db() should have raised MigrationDuplicateDataError!"
        except MigrationDuplicateDataError as e:
            migration_failed = True
            print(f"  [PASS] Migration cleanly aborted with expected error:\n    --> {e}")
        finally:
            engine.dispose()

        assert migration_failed, "MigrationDuplicateDataError was not raised!"

        # Verify that original database was left completely intact (zero rows deleted or altered)
        print("\n  Verifying database state after aborted migration:")
        verify_conn = sqlite3.connect(str(db_path))
        verify_cur = verify_conn.cursor()

        # Check rows in test_iterations
        verify_cur.execute("SELECT id, status, stdout FROM test_iterations ORDER BY id")
        rows = verify_cur.fetchall()
        print(f"  [PASS] Preserved row count in test_iterations: {len(rows)} (Expected: 2)")
        assert len(rows) == 2, f"Data was modified or lost! Expected 2 rows, found {len(rows)}"
        assert rows[0][0] == "row-1" and rows[0][1] == "PASSED"
        assert rows[1][0] == "row-2" and rows[1][1] == "FAILED"
        print("  [PASS] All duplicate records remain 100% intact with original values.")

        # Check that unique index was NOT created (transaction rolled back)
        verify_cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='uq_test_run_case_iteration'")
        idx = verify_cur.fetchone()
        assert idx is None, "Unique index should NOT exist after aborted transaction!"
        print("  [PASS] Verified unique index was not created due to clean transaction rollback.")

        verify_conn.close()


if __name__ == "__main__":
    test_foreign_key_enforcement()
    test_existing_duplicate_data_safety()
    print("\n================================================================================")
    print("ALL FOREIGN KEY & DUPLICATE SAFETY CHECKS PASSED SUCCESSFULLY!")
    print("================================================================================")

