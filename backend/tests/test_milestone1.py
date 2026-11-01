import io
import os
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from backend.app.config import settings
from backend.app.db.session import init_db, engine, SessionLocal
from backend.app.db.models import (
    Project,
    TestCase,
    TestRun,
    RunIteration,
    TestIteration,
    ExecutionLock,
)
from backend.app.core.archive import (
    validate_and_extract_zip,
    ArchiveSecurityException,
    ArchiveValidationException,
)


def test_database_models_and_constraints():
    print("--- 1. Testing Database Models & Schema Extensions ---")
    init_db()
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    assert "run_iterations" in tables, "Table 'run_iterations' missing from DB!"
    assert "execution_locks" in tables, "Table 'execution_locks' missing from DB!"
    print("[PASS] Verified 'run_iterations' and 'execution_locks' exist in SQLite.")

    # Check columns of run_iterations
    run_iter_cols = [c["name"] for c in inspector.get_columns("run_iterations")]
    for expected_col in ["id", "test_run_id", "iteration_number", "status", "random_order_seed", "duration_ms"]:
        assert expected_col in run_iter_cols, f"Column '{expected_col}' missing from run_iterations!"
    print(f"[PASS] Verified 'run_iterations' columns: {run_iter_cols}")

    # Check columns of execution_locks
    lock_cols = [c["name"] for c in inspector.get_columns("execution_locks")]
    for expected_col in ["lock_name", "locked_by_run_id", "acquired_at", "last_heartbeat_at", "expires_at"]:
        assert expected_col in lock_cols, f"Column '{expected_col}' missing from execution_locks!"
    print(f"[PASS] Verified 'execution_locks' columns: {lock_cols}")

    # Test uniqueness constraint on RunIteration (test_run_id, iteration_number)
    db = SessionLocal()
    try:
        proj = Project(name="Constraint Test Project")
        db.add(proj)
        db.commit()

        run = TestRun(project_id=proj.id, iteration_count=5)
        db.add(run)
        db.commit()

        iter_1 = RunIteration(test_run_id=run.id, iteration_number=1, status="COMPLETED")
        db.add(iter_1)
        db.commit()

        # Attempt to insert duplicate iteration_number for same test_run_id
        iter_dup = RunIteration(test_run_id=run.id, iteration_number=1, status="RUNNING")
        db.add(iter_dup)
        try:
            db.commit()
            assert False, "Failed! Expected IntegrityError on duplicate (test_run_id, iteration_number)"
        except IntegrityError:
            db.rollback()
            print("[PASS] Verified UniqueConstraint('test_run_id', 'iteration_number') prevents duplicate iterations.")
    finally:
        db.close()


def test_configuration_defaults():
    print("\n--- 2. Testing Configurable Settings & Conservative Defaults ---")
    assert settings.DOCKER_MEMORY_LIMIT == "1024m", f"Expected 1024m, got {settings.DOCKER_MEMORY_LIMIT}"
    assert settings.DOCKER_CPU_LIMIT == 1.0, f"Expected 1.0, got {settings.DOCKER_CPU_LIMIT}"
    assert settings.DOCKER_PIDS_LIMIT == 100, f"Expected 100, got {settings.DOCKER_PIDS_LIMIT}"
    assert settings.MAX_ARCHIVE_FILES == 1000, f"Expected 1000, got {settings.MAX_ARCHIVE_FILES}"
    assert settings.MAX_ARCHIVE_UNCOMPRESSED_SIZE == 50 * 1024 * 1024, "Expected 50MB uncompressed limit"
    assert settings.MAX_ARCHIVE_COMPRESSION_RATIO == 100.0, "Expected 100:1 ratio limit"
    print("[PASS] Verified all conservative resource and archive security limits.")


def test_secure_zip_extraction():
    print("\n--- 3. Testing Secure Archive Extraction & Exploits Rejection ---")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Valid safe archive
        valid_buf = io.BytesIO()
        with zipfile.ZipFile(valid_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("test_module.py", "def test_ok(): assert True\n")
            zf.writestr("sub/helper.py", "# helper module\n")
        valid_buf.seek(0)

        out_dir, count = validate_and_extract_zip(valid_buf, tmp_path / "valid")
        assert count == 2
        assert (out_dir / "test_module.py").exists()
        assert (out_dir / "sub" / "helper.py").exists()
        print("  [PASS] Valid archive successfully extracted.")

        # 2. Zip-Slip directory traversal attack
        slip_buf = io.BytesIO()
        with zipfile.ZipFile(slip_buf, "w") as zf:
            zf.writestr("../../evil.py", "# malicious traversal content\n")
        slip_buf.seek(0)

        try:
            validate_and_extract_zip(slip_buf, tmp_path / "slip")
            assert False, "Expected ArchiveSecurityException for Zip-Slip attack!"
        except ArchiveSecurityException as e:
            print(f"  [PASS] Blocked Zip-Slip attack: {e}")

        # 3. Absolute path attack
        abs_buf = io.BytesIO()
        with zipfile.ZipFile(abs_buf, "w") as zf:
            zf.writestr("/etc/passwd", "root:x:0:0...\n")
        abs_buf.seek(0)

        try:
            validate_and_extract_zip(abs_buf, tmp_path / "abs")
            assert False, "Expected ArchiveSecurityException for absolute path!"
        except ArchiveSecurityException as e:
            print(f"  [PASS] Blocked absolute path attack: {e}")

        # 4. Symlink entry attack
        sym_buf = io.BytesIO()
        with zipfile.ZipFile(sym_buf, "w") as zf:
            sym_info = zipfile.ZipInfo("symlink_target")
            sym_info.create_system = 3  # UNIX
            sym_info.external_attr = stat.S_IFLNK << 16  # Symlink mode
            zf.writestr(sym_info, "/etc/shadow")
        sym_buf.seek(0)

        try:
            validate_and_extract_zip(sym_buf, tmp_path / "sym")
            assert False, "Expected ArchiveSecurityException for symlink!"
        except ArchiveSecurityException as e:
            print(f"  [PASS] Blocked symlink attack: {e}")

        # 5. Excessive file count limit (simulate archive with > 1000 files)
        many_buf = io.BytesIO()
        with zipfile.ZipFile(many_buf, "w") as zf:
            for i in range(1005):
                zf.writestr(f"file_{i}.txt", "x")
        many_buf.seek(0)

        try:
            validate_and_extract_zip(many_buf, tmp_path / "many")
            assert False, "Expected ArchiveSecurityException for file count limit!"
        except ArchiveSecurityException as e:
            print(f"  [PASS] Blocked excessive file count: {e}")

        # 6. Zip Bomb compression ratio attack
        # Create a compressed entry of 100,000 zeros that compresses down to ~100 bytes (ratio ~ 1000:1)
        bomb_buf = io.BytesIO()
        with zipfile.ZipFile(bomb_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bomb.txt", b"0" * 300000)
        bomb_buf.seek(0)

        try:
            validate_and_extract_zip(bomb_buf, tmp_path / "bomb")
            assert False, "Expected ArchiveSecurityException for Zip Bomb compression ratio!"
        except ArchiveSecurityException as e:
            print(f"  [PASS] Blocked Zip Bomb attack: {e}")


if __name__ == "__main__":
    test_database_models_and_constraints()
    test_configuration_defaults()
    test_secure_zip_extraction()
    print("\nALL MILESTONE 1 VERIFICATION TESTS PASSED SUCCESSFULLY!")

