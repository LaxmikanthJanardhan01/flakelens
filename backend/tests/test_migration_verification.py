import io
import os
import shutil
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
from backend.app.db.migrate import migrate_db


def test_sqlite_phase1_migration_and_constraints():
    print("================================================================================")
    print("PHASE 1 DATABASE MIGRATION & CONSTRAINT VERIFICATION")
    print("================================================================================")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "flakelens_phase1_copy.db"

        # --------------------------------------------------------------------------
        # STEP 1: Construct an exact Phase 1 SQLite Database (with pre-existing data)
        # --------------------------------------------------------------------------
        print("\n--- STEP 1: Setting up exact Phase 1 database schema with pre-existing records ---")
        raw_conn = sqlite3.connect(str(db_path))
        raw_cur = raw_conn.cursor()

        # Create exact Phase 1 tables (without run_iterations, execution_locks, or run_iteration_id)
        raw_cur.execute("""
            CREATE TABLE projects (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                source_archive_path VARCHAR(1024),
                created_at DATETIME NOT NULL
            );
        """)
        raw_cur.execute("""
            CREATE TABLE test_cases (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                file_path VARCHAR(1024) NOT NULL,
                test_name VARCHAR(255) NOT NULL,
                node_id VARCHAR(1024) NOT NULL,
                discovered_at DATETIME NOT NULL
            );
        """)
        raw_cur.execute("""
            CREATE TABLE test_runs (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                iteration_count INTEGER NOT NULL,
                shuffle_order BOOLEAN NOT NULL,
                status VARCHAR(50) NOT NULL,
                total_tests INTEGER NOT NULL,
                consistently_passing_count INTEGER NOT NULL,
                consistently_failing_count INTEGER NOT NULL,
                flaky_tests_count INTEGER NOT NULL,
                started_at DATETIME,
                completed_at DATETIME
            );
        """)
        raw_cur.execute("""
            CREATE TABLE test_iterations (
                id VARCHAR(36) PRIMARY KEY,
                test_run_id VARCHAR(36) NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
                test_case_id VARCHAR(36) NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
                iteration_number INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL,
                duration_ms FLOAT NOT NULL,
                execution_order INTEGER NOT NULL,
                random_order_seed INTEGER,
                stdout TEXT,
                stderr TEXT,
                error_message TEXT,
                traceback TEXT
            );
        """)

        # Insert realistic pre-existing Phase 1 records
        raw_cur.execute("INSERT INTO projects VALUES ('proj-1', 'Legacy Phase 1 Project', '/path/proj.zip', '2026-11-01 10:00:00')")
        raw_cur.execute("INSERT INTO test_cases VALUES ('tc-1', 'proj-1', 'tests/test_a.py', 'test_alpha', 'tests/test_a.py::test_alpha', '2026-11-01 10:00:01')")
        raw_cur.execute("INSERT INTO test_cases VALUES ('tc-2', 'proj-1', 'tests/test_b.py', 'test_beta', 'tests/test_b.py::test_beta', '2026-11-01 10:00:01')")
        raw_cur.execute("INSERT INTO test_runs VALUES ('run-1', 'proj-1', 5, 1, 'COMPLETED', 2, 2, 0, 0, '2026-11-01 10:05:00', '2026-11-01 10:05:10')")
        raw_cur.execute("INSERT INTO test_iterations VALUES ('ti-1', 'run-1', 'tc-1', 1, 'PASSED', 15.2, 1, 42, 'output ok', '', NULL, NULL)")
        raw_cur.execute("INSERT INTO test_iterations VALUES ('ti-2', 'run-1', 'tc-2', 1, 'PASSED', 22.8, 2, 42, 'output ok', '', NULL, NULL)")
        raw_conn.commit()
        raw_conn.close()

        print("  [INITIAL STATE] Phase 1 database created with:")
        print("    - 1 project ('proj-1')")
        print("    - 2 test cases ('tc-1', 'tc-2')")
        print("    - 1 test run ('run-1')")
        print("    - 2 test iterations ('ti-1', 'ti-2') (without run_iteration_id column)")

        # --------------------------------------------------------------------------
        # STEP 2: Execute Migration Engine on the Database Copy
        # --------------------------------------------------------------------------
        print("\n--- STEP 2: Executing migrate_db() on the database ---")
        engine = create_engine(f"sqlite:///{db_path}")

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # Run migration
        migrate_db(engine)
        print("  [PASS] migrate_db(engine) finished without errors.")

        # --------------------------------------------------------------------------
        # STEP 3: Verify Existing Data Remains Completely Intact
        # --------------------------------------------------------------------------
        print("\n--- STEP 3: Verifying that pre-existing Phase 1 records are intact ---")
        inspector = inspect(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            # Verify Project
            p = session.query(Project).filter_by(id="proj-1").first()
            assert p is not None, "Pre-existing project lost during migration!"
            assert p.name == "Legacy Phase 1 Project", f"Project name altered: {p.name}"
            print(f"  [PASS] Verified Project preserved: ID='{p.id}', Name='{p.name}'")

            # Verify TestCases
            cases = session.query(TestCase).filter_by(project_id="proj-1").all()
            assert len(cases) == 2, f"Expected 2 test cases, found {len(cases)}"
            print(f"  [PASS] Verified {len(cases)} TestCases preserved: {[c.node_id for c in cases]}")

            # Verify TestRun
            r = session.query(TestRun).filter_by(id="run-1").first()
            assert r is not None, "Pre-existing test run lost during migration!"
            assert r.iteration_count == 5
            print(f"  [PASS] Verified TestRun preserved: ID='{r.id}', Iterations={r.iteration_count}")

            # Verify TestIterations (existing records have run_iteration_id = None)
            iters = session.query(TestIteration).filter_by(test_run_id="run-1").all()
            assert len(iters) == 2, f"Expected 2 test iterations, found {len(iters)}"
            for it in iters:
                assert it.status == "PASSED"
                assert it.run_iteration_id is None, f"Expected NULL run_iteration_id for legacy records, got {it.run_iteration_id}"
            print(f"  [PASS] Verified {len(iters)} legacy TestIterations preserved with new nullable run_iteration_id=None.")

            # --------------------------------------------------------------------------
            # STEP 4: Verify New Tables, Columns & Foreign Keys
            # --------------------------------------------------------------------------
            print("\n--- STEP 4: Verifying new tables, columns, and foreign keys ---")
            tables = inspector.get_table_names()
            assert "run_iterations" in tables, "Table 'run_iterations' missing!"
            assert "execution_locks" in tables, "Table 'execution_locks' missing!"
            print(f"  [PASS] Tables in migrated DB: {tables}")

            ti_cols = [c["name"] for c in inspector.get_columns("test_iterations")]
            assert "run_iteration_id" in ti_cols, "Column 'run_iteration_id' was not added to test_iterations!"
            print(f"  [PASS] Column 'run_iteration_id' successfully verified in test_iterations: {ti_cols}")

            # Check foreign key from test_iterations to run_iterations
            ti_fks = inspector.get_foreign_keys("test_iterations")
            has_fk_to_run_iter = any(
                fk.get("referred_table") == "run_iterations" and "run_iteration_id" in fk.get("constrained_columns", [])
                for fk in ti_fks
            )
            print(f"  [PASS] Verified foreign keys on test_iterations: {ti_fks}")
            assert has_fk_to_run_iter, "Foreign key from test_iterations to run_iterations missing!"

            # --------------------------------------------------------------------------
            # STEP 5: Explicit Test of UniqueConstraint(test_run_id, test_case_id, iteration_number)
            # --------------------------------------------------------------------------
            print("\n--- STEP 5: Explicit test of TestIteration UniqueConstraint ---")
            # Legacy DB already has (run-1, tc-1, 1). Attempting to insert duplicate must fail!
            dup_test_iter = TestIteration(
                id="ti-duplicate",
                test_run_id="run-1",
                test_case_id="tc-1",
                iteration_number=1,  # Duplicate combination!
                status="FAILED",
                duration_ms=99.0,
                execution_order=99,
            )
            session.add(dup_test_iter)
            try:
                session.commit()
                assert False, "FAILED! Duplicate (test_run_id, test_case_id, iteration_number) was accepted!"
            except IntegrityError as exc:
                session.rollback()
                print(f"  [PASS] Duplicate TestIteration strictly rejected by UniqueConstraint: {exc.orig}")

            # Verify that a different iteration number (iteration_number=2) is accepted
            valid_new_test_iter = TestIteration(
                id="ti-valid-new",
                test_run_id="run-1",
                test_case_id="tc-1",
                iteration_number=2,  # Different iteration number
                status="PASSED",
                duration_ms=18.5,
                execution_order=1,
            )
            session.add(valid_new_test_iter)
            session.commit()
            print("  [PASS] Distinct TestIteration (iteration_number=2) successfully inserted.")

            # --------------------------------------------------------------------------
            # STEP 6: Explicit Test of UniqueConstraint(test_run_id, iteration_number) on RunIteration
            # --------------------------------------------------------------------------
            print("\n--- STEP 6: Explicit test of RunIteration UniqueConstraint ---")
            run_iter_1 = RunIteration(
                id="ri-1",
                test_run_id="run-1",
                iteration_number=1,
                status="COMPLETED",
                duration_ms=450.0,
            )
            session.add(run_iter_1)
            session.commit()
            print("  [PASS] Inserted initial RunIteration (run-1, iteration_number=1).")

            # Attempt to insert duplicate RunIteration for same run and iteration_number
            dup_run_iter = RunIteration(
                id="ri-duplicate",
                test_run_id="run-1",
                iteration_number=1,  # Duplicate!
                status="RUNNING",
                duration_ms=0.0,
            )
            session.add(dup_run_iter)
            try:
                session.commit()
                assert False, "FAILED! Duplicate (test_run_id, iteration_number) was accepted!"
            except IntegrityError as exc:
                session.rollback()
                print(f"  [PASS] Duplicate RunIteration strictly rejected by UniqueConstraint: {exc.orig}")

        finally:
            session.close()
            engine.dispose()

    print("\n================================================================================")
    print("ALL MIGRATION AND CONSTRAINT VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("================================================================================")


if __name__ == "__main__":
    test_sqlite_phase1_migration_and_constraints()
