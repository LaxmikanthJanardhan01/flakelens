import logging
from sqlalchemy import inspect, text, Engine
from backend.app.db.session import Base

logger = logging.getLogger("flakelens.db.migrate")


class MigrationDuplicateDataError(Exception):
    """Raised when existing database records violate a new unique constraint, preventing unsafe migration."""
    pass


def migrate_db(engine: Engine):
    """
    Safely and idempotently migrates the SQLite database schema to Milestone 1 specifications.
    Preserves all existing tables and rows without recreating or dropping the database.
    Aborts cleanly without modifying or deleting data if duplicate records are detected.
    """
    # 1. Create any missing tables (e.g. run_iterations, execution_locks)
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    with engine.begin() as conn:
        # 2. Check for duplicate data in test_iterations BEFORE applying unique index
        if "test_iterations" in tables:
            dup_check = conn.execute(
                text(
                    "SELECT test_run_id, test_case_id, iteration_number, COUNT(*) as cnt "
                    "FROM test_iterations "
                    "GROUP BY test_run_id, test_case_id, iteration_number "
                    "HAVING cnt > 1"
                )
            ).fetchall()

            if dup_check:
                dup_details = [
                    f"(run={r[0]}, test={r[1]}, iter={r[2]}, count={r[3]})"
                    for r in dup_check
                ]
                error_msg = (
                    f"Migration aborted! Found {len(dup_check)} duplicate test iteration record group(s) "
                    f"in existing database: {', '.join(dup_details)}. "
                    "Cannot apply unique index without data corruption. Original database left untouched."
                )
                logger.error(error_msg)
                raise MigrationDuplicateDataError(error_msg)

            # Check if run_iteration_id column needs to be added
            columns = [c["name"] for c in inspector.get_columns("test_iterations")]
            if "run_iteration_id" not in columns:
                logger.info("Migrating test_iterations: adding column 'run_iteration_id'")
                conn.execute(
                    text(
                        "ALTER TABLE test_iterations "
                        "ADD COLUMN run_iteration_id VARCHAR(36) "
                        "REFERENCES run_iterations(id) ON DELETE CASCADE"
                    )
                )

            # Ensure index on run_iteration_id
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_test_iterations_run_iteration_id "
                    "ON test_iterations(run_iteration_id)"
                )
            )

            # Enforce multi-column unique constraint via SQLite Unique Index
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_test_run_case_iteration "
                    "ON test_iterations(test_run_id, test_case_id, iteration_number)"
                )
            )

        # 3. Check for duplicate data in run_iterations BEFORE applying unique index
        if "run_iterations" in tables:
            run_iter_dups = conn.execute(
                text(
                    "SELECT test_run_id, iteration_number, COUNT(*) as cnt "
                    "FROM run_iterations "
                    "GROUP BY test_run_id, iteration_number "
                    "HAVING cnt > 1"
                )
            ).fetchall()

            if run_iter_dups:
                dup_details = [
                    f"(run={r[0]}, iter={r[1]}, count={r[2]})"
                    for r in run_iter_dups
                ]
                error_msg = (
                    f"Migration aborted! Found {len(run_iter_dups)} duplicate run iteration record group(s) "
                    f"in existing database: {', '.join(dup_details)}. "
                    "Cannot apply unique index without data corruption. Original database left untouched."
                )
                logger.error(error_msg)
                raise MigrationDuplicateDataError(error_msg)

            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_run_iteration_number "
                    "ON run_iterations(test_run_id, iteration_number)"
                )
            )

        # 4. Milestone 4 & 6 Migration: test_runs columns
        if "test_runs" in tables:
            test_run_cols = [c["name"] for c in inspector.get_columns("test_runs")]
            if "insufficient_data_count" not in test_run_cols:
                logger.info("Migrating test_runs: adding column 'insufficient_data_count'")
                conn.execute(
                    text(
                        "ALTER TABLE test_runs "
                        "ADD COLUMN insufficient_data_count INTEGER NOT NULL DEFAULT 0"
                    )
                )

            if "run_type" not in test_run_cols:
                logger.info("Migrating test_runs: adding column 'run_type'")
                conn.execute(
                    text(
                        "ALTER TABLE test_runs "
                        "ADD COLUMN run_type VARCHAR(50) NOT NULL DEFAULT 'STANDARD'"
                    )
                )

            if "baseline_run_id" not in test_run_cols:
                logger.info("Migrating test_runs: adding column 'baseline_run_id'")
                conn.execute(
                    text(
                        "ALTER TABLE test_runs "
                        "ADD COLUMN baseline_run_id VARCHAR(36) "
                        "REFERENCES test_runs(id) ON DELETE SET NULL"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_test_runs_baseline_run_id "
                        "ON test_runs(baseline_run_id)"
                    )
                )

            if "target_test_case_id" not in test_run_cols:
                logger.info("Migrating test_runs: adding column 'target_test_case_id'")
                conn.execute(
                    text(
                        "ALTER TABLE test_runs "
                        "ADD COLUMN target_test_case_id VARCHAR(36) "
                        "REFERENCES test_cases(id) ON DELETE SET NULL"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_test_runs_target_test_case_id "
                        "ON test_runs(target_test_case_id)"
                    )
                )

        # 5. Milestone 4 Migration: flakiness_reports unique index
        if "flakiness_reports" in tables:
            report_dups = conn.execute(
                text(
                    "SELECT test_run_id, test_case_id, COUNT(*) as cnt "
                    "FROM flakiness_reports "
                    "GROUP BY test_run_id, test_case_id "
                    "HAVING cnt > 1"
                )
            ).fetchall()

            if report_dups:
                dup_details = [
                    f"(run={r[0]}, test={r[1]}, count={r[2]})"
                    for r in report_dups
                ]
                error_msg = (
                    f"Migration aborted! Found {len(report_dups)} duplicate flakiness report record group(s) "
                    f"in existing database: {', '.join(dup_details)}. "
                    "Cannot apply unique index without data corruption. Original database left untouched."
                )
                logger.error(error_msg)
                raise MigrationDuplicateDataError(error_msg)

            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_flakiness_reports_run_case "
                    "ON flakiness_reports(test_run_id, test_case_id)"
                )
            )

            # Check if supporting_evidence column needs to be added (Milestone 5)
            report_cols = [c["name"] for c in inspector.get_columns("flakiness_reports")]
            if "supporting_evidence" not in report_cols:
                logger.info("Migrating flakiness_reports: adding column 'supporting_evidence'")
                conn.execute(
                    text(
                        "ALTER TABLE flakiness_reports "
                        "ADD COLUMN supporting_evidence TEXT"
                    )
                )

    logger.info("Database migration completed successfully.")
