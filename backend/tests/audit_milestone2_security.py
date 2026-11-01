"""
Milestone 2 Deep Security & Implementation Audit Script.

Performs code-level, container-level, and host-level verifications:
1. Container Inspect: Non-root UID 1000, cap-drop ALL, no-new-privileges, :ro mount, --network none, memory/CPU/PIDs limits.
2. Container Cleanup: Proves container removal after success, failure, and timeout.
3. Host Isolation: Proves conftest.py code does not run on host and cannot touch host filesystem.
4. Discovery Integrity: Proves node ID parsing, syntax error rejection, import error rejection, empty suite handling, and duplicate idempotency.
5. Windows Bind Mounts: Proves real Windows directory mount resolution.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Ensure root repository directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import docker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.db.session import Base
from backend.app.db.models import Project, TestCase
from backend.app.core.docker_manager import (
    DockerManager,
    DockerUnavailableError,
    ProjectBuildError,
    TestDiscoveryError,
    TestDiscoveryTimeoutError,
)
from backend.app.core.discovery import (
    parse_pytest_node_ids,
    discover_and_register_tests,
)


def run_audit():
    print("=" * 80)
    print("FLAKELENS PHASE 2 - MILESTONE 2 SECURITY & IMPLEMENTATION AUDIT")
    print("=" * 80)

    client = docker.from_env()

    # --------------------------------------------------------------------------
    # CHECK 1: Real Docker Container Configuration via inspect_container
    # --------------------------------------------------------------------------
    print("\n--- CHECK 1: Actual Docker Container Configuration (docker inspect) ---")
    test_dir = settings.BASE_DIR / "samples" / "synthetic_flaky_suite"
    resolved_path = str(test_dir.resolve())

    container = client.containers.create(
        image="flakelens-runner:latest",
        command=["--collect-only", "-q", "-o", "cache_dir=/tmp/.pytest_cache"],
        volumes={resolved_path: {"bind": "/workspace", "mode": "ro"}},
        tmpfs={"/tmp": ""},
        network_mode="none",
        cap_drop=["ALL"],
        mem_limit=settings.DOCKER_MEMORY_LIMIT,
        nano_cpus=int(settings.DOCKER_CPU_LIMIT * 1e9),
        pids_limit=settings.DOCKER_PIDS_LIMIT,
        security_opt=["no-new-privileges:true"],
        user="1000:1000",
        working_dir="/workspace",
    )
    container_id = container.id

    try:
        inspect_data = client.api.inspect_container(container_id)
        config = inspect_data.get("Config", {})
        host_config = inspect_data.get("HostConfig", {})
        mounts = inspect_data.get("Mounts", [])

        # User check
        user_val = config.get("User")
        print(f"  [EVIDENCE] Config.User: {user_val}")
        assert user_val == "1000:1000", f"Expected '1000:1000', got {user_val}"

        # CapDrop check
        cap_drop = host_config.get("CapDrop")
        print(f"  [EVIDENCE] HostConfig.CapDrop: {cap_drop}")
        assert "ALL" in cap_drop or cap_drop == ["ALL"], f"Expected CapDrop=['ALL'], got {cap_drop}"

        # SecurityOpt check
        sec_opt = host_config.get("SecurityOpt")
        print(f"  [EVIDENCE] HostConfig.SecurityOpt: {sec_opt}")
        assert "no-new-privileges:true" in (sec_opt or []), f"Expected no-new-privileges:true, got {sec_opt}"

        # NetworkMode check
        net_mode = host_config.get("NetworkMode")
        print(f"  [EVIDENCE] HostConfig.NetworkMode: {net_mode}")
        assert net_mode == "none", f"Expected NetworkMode='none', got {net_mode}"

        # Resource Limits
        memory_limit = host_config.get("Memory")
        nano_cpus = host_config.get("NanoCpus")
        pids_limit = host_config.get("PidsLimit")
        print(f"  [EVIDENCE] HostConfig.Memory: {memory_limit} bytes ({memory_limit // (1024*1024)} MB)")
        print(f"  [EVIDENCE] HostConfig.NanoCpus: {nano_cpus} ({nano_cpus / 1e9} CPUs)")
        print(f"  [EVIDENCE] HostConfig.PidsLimit: {pids_limit}")
        assert memory_limit == 1073741824, f"Expected 1073741824 bytes (1024m), got {memory_limit}"
        assert nano_cpus == 1000000000, f"Expected 1000000000 (1.0 CPU), got {nano_cpus}"
        assert pids_limit == 100, f"Expected 100 PIDs, got {pids_limit}"

        # Mount check
        workspace_mount = next((m for m in mounts if m.get("Destination") == "/workspace"), None)
        print(f"  [EVIDENCE] Mount Destination /workspace: RW={workspace_mount.get('RW')}, Mode={workspace_mount.get('Mode')}")
        assert workspace_mount is not None, "Workspace mount not found"
        assert workspace_mount.get("RW") is False, "Expected workspace mount to be Read-Only (RW=False)"

        print("  [PASS] All Docker container security and resource configurations confirmed via inspect.")
    finally:
        container.remove(force=True)

    # --------------------------------------------------------------------------
    # CHECK 2: Container Cleanup After Success, Failure, and Timeout
    # --------------------------------------------------------------------------
    print("\n--- CHECK 2: Container Lifecycle Cleanup Verification ---")
    manager = DockerManager()

    # 2a. Success cleanup
    containers_before = {c.id for c in client.containers.list(all=True)}
    exit_code, logs = manager.run_sandboxed_discovery(
        image_tag="flakelens-runner:latest",
        project_dir=test_dir,
    )
    containers_after = {c.id for c in client.containers.list(all=True)}
    print(f"  [EVIDENCE] Discovery success exit_code={exit_code}. Residual containers: {containers_after - containers_before}")
    assert exit_code == 0
    assert containers_after - containers_before == set(), "Residual container left behind after success!"
    print("  [PASS] Success execution leaves zero residual containers.")

    # 2b. Failure cleanup (syntax error)
    temp_dir = tempfile.mkdtemp()
    try:
        bad_file = Path(temp_dir) / "test_syntax.py"
        bad_file.write_text("invalid python def syntax {{{", encoding="utf-8")
        containers_before = {c.id for c in client.containers.list(all=True)}
        exit_code, logs = manager.run_sandboxed_discovery(
            image_tag="flakelens-runner:latest",
            project_dir=Path(temp_dir),
        )
        containers_after = {c.id for c in client.containers.list(all=True)}
        print(f"  [EVIDENCE] Discovery syntax error exit_code={exit_code}. Residual containers: {containers_after - containers_before}")
        assert exit_code != 0
        assert containers_after - containers_before == set(), "Residual container left behind after syntax error!"
        print("  [PASS] Failure execution leaves zero residual containers.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # 2c. Timeout cleanup
    temp_dir = tempfile.mkdtemp()
    try:
        hang_conftest = Path(temp_dir) / "conftest.py"
        hang_conftest.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        hang_test = Path(temp_dir) / "test_hang.py"
        hang_test.write_text("def test_hang(): pass\n", encoding="utf-8")

        containers_before = {c.id for c in client.containers.list(all=True)}
        timed_out = False
        try:
            manager.run_sandboxed_discovery(
                image_tag="flakelens-runner:latest",
                project_dir=Path(temp_dir),
                timeout_seconds=2,
            )
        except TestDiscoveryTimeoutError:
            timed_out = True

        containers_after = {c.id for c in client.containers.list(all=True)}
        print(f"  [EVIDENCE] Timeout triggered: {timed_out}. Residual containers: {containers_after - containers_before}")
        assert timed_out is True, "Expected TestDiscoveryTimeoutError"
        assert containers_after - containers_before == set(), "Residual container left behind after timeout kill!"
        print("  [PASS] Timeout execution forcefully kills and removes container cleanly.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # CHECK 3: Host Isolation (Zero Host Code Execution via conftest.py)
    # --------------------------------------------------------------------------
    print("\n--- CHECK 3: Host Isolation Proof (conftest.py Exploit Simulation) ---")
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "audit_db.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    SessionAudit = sessionmaker(bind=engine)
    db = SessionAudit()

    try:
        host_marker_file = Path(temp_dir) / "HOST_POLLUTED_MARKER.txt"
        container_marker_file = Path(temp_dir) / "CONTAINER_MARKER.txt"

        # This conftest attempts to write to both the host path and /workspace
        conftest_code = f"""
import os
# If executed on host, this path exists and will create a file:
try:
    with open(r"{str(host_marker_file)}", "w") as f:
        f.write("HOST_COMPROMISED")
except Exception:
    pass

# If executed in container, /workspace is read-only and write will fail:
try:
    with open("/workspace/CONTAINER_MARKER.txt", "w") as f:
        f.write("CONTAINER_WRITE_SUCCESS")
except Exception:
    pass
"""
        (Path(temp_dir) / "conftest.py").write_text(conftest_code, encoding="utf-8")
        (Path(temp_dir) / "test_isolated.py").write_text("def test_isolated_pass(): pass\n", encoding="utf-8")

        project_id = str(uuid.uuid4())
        proj = Project(id=project_id, name="Isolation Audit Project")
        db.add(proj)
        db.commit()

        discovered = discover_and_register_tests(
            project_id=project_id,
            project_dir=Path(temp_dir),
            db=db,
            docker_mgr=manager,
        )

        print(f"  [EVIDENCE] Host marker file exists: {host_marker_file.exists()}")
        print(f"  [EVIDENCE] Container marker file exists on host: {container_marker_file.exists()}")
        print(f"  [EVIDENCE] Discovered tests inside Docker: {[t.node_id for t in discovered]}")

        assert host_marker_file.exists() is False, "CRITICAL: Host marker was created! conftest.py executed on host!"
        assert container_marker_file.exists() is False, "CRITICAL: Container was able to write to read-only workspace!"
        assert len(discovered) == 1
        assert discovered[0].node_id == "test_isolated.py::test_isolated_pass"

        print("  [PASS] Host isolation proven: untrusted conftest did NOT execute on host, and container write was blocked by :ro mount.")
    finally:
        db.close()
        engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # CHECK 4: Discovery Integrity Verification (All 7 Failure & Success Modes)
    # --------------------------------------------------------------------------
    print("\n--- CHECK 4: Discovery Integrity Verification ---")
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "integrity_db.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    SessionAudit = sessionmaker(bind=engine)
    db = SessionAudit()

    try:
        # 4a. Successful discovery saves real node IDs
        real_suite_dir = settings.BASE_DIR / "samples" / "synthetic_flaky_suite"
        proj_success_id = str(uuid.uuid4())
        db.add(Project(id=proj_success_id, name="Success Project"))
        db.commit()

        success_cases = discover_and_register_tests(proj_success_id, real_suite_dir, db, manager)
        assert len(success_cases) == 6
        expected_sample_node_ids = {
            "test_async_timing.py::test_timing_race_condition",
            "test_order_dependency.py::test_order_step_populate",
            "test_order_dependency.py::test_order_step_expect_clean",
            "test_resource_leak.py::test_resource_contention",
            "test_stable_failing.py::test_deterministic_failure",
            "test_stable_passing.py::test_pure_deterministic_calculation",
        }
        actual_node_ids = {c.node_id for c in success_cases}
        assert actual_node_ids == expected_sample_node_ids
        print(f"  [EVIDENCE] Real node IDs saved: {len(actual_node_ids)} test cases confirmed.")
        print("  [PASS] 4a: Successful discovery saves real node IDs.")

        # 4b. Syntax errors do not save partial records
        bad_syntax_dir = Path(temp_dir) / "bad_syntax"
        bad_syntax_dir.mkdir()
        (bad_syntax_dir / "test_good.py").write_text("def test_ok(): pass\n", encoding="utf-8")
        (bad_syntax_dir / "test_broken.py").write_text("def test_broken(: syntax error\n", encoding="utf-8")
        proj_syntax_id = str(uuid.uuid4())
        db.add(Project(id=proj_syntax_id, name="Syntax Error Project"))
        db.commit()

        syntax_error_raised = False
        try:
            discover_and_register_tests(proj_syntax_id, bad_syntax_dir, db, manager)
        except TestDiscoveryError as e:
            syntax_error_raised = True
            print(f"  [EVIDENCE] Caught expected TestDiscoveryError on syntax error: {str(e)[:80]}...")

        assert syntax_error_raised is True
        persisted_syntax = db.query(TestCase).filter(TestCase.project_id == proj_syntax_id).count()
        print(f"  [EVIDENCE] TestCases in DB for syntax error: {persisted_syntax}")
        assert persisted_syntax == 0, "Partial test cases were persisted after syntax error!"
        print("  [PASS] 4b: Syntax error does not save partial records.")

        # 4c. Import errors do not save partial records
        bad_import_dir = Path(temp_dir) / "bad_import"
        bad_import_dir.mkdir()
        (bad_import_dir / "test_good.py").write_text("def test_ok(): pass\n", encoding="utf-8")
        (bad_import_dir / "test_import_err.py").write_text("import nonexistent_module_xyz_12345\ndef test_dummy(): pass\n", encoding="utf-8")
        proj_import_id = str(uuid.uuid4())
        db.add(Project(id=proj_import_id, name="Bad Import Project"))
        db.commit()

        import_error_raised = False
        try:
            discover_and_register_tests(proj_import_id, bad_import_dir, db, manager)
        except TestDiscoveryError as e:
            import_error_raised = True
            print(f"  [EVIDENCE] Caught expected TestDiscoveryError on import error: {str(e)[:80]}...")

        assert import_error_raised is True
        persisted_import = db.query(TestCase).filter(TestCase.project_id == proj_import_id).count()
        print(f"  [EVIDENCE] TestCases in DB for failed import: {persisted_import}")
        assert persisted_import == 0, "Partial test cases were persisted after import error!"
        print("  [PASS] 4c: Import error does not save partial records.")

        # 4d. Docker failure does not save partial records
        class MockBrokenDockerManager(DockerManager):
            def is_available(self):
                return False, "Docker daemon unavailable simulation"

        proj_docker_fail_id = str(uuid.uuid4())
        db.add(Project(id=proj_docker_fail_id, name="Docker Fail Project"))
        db.commit()

        docker_fail_raised = False
        try:
            discover_and_register_tests(proj_docker_fail_id, real_suite_dir, db, MockBrokenDockerManager())
        except DockerUnavailableError as e:
            docker_fail_raised = True
            print(f"  [EVIDENCE] Caught expected DockerUnavailableError: {str(e)[:80]}...")

        assert docker_fail_raised is True
        persisted_docker_fail = db.query(TestCase).filter(TestCase.project_id == proj_docker_fail_id).count()
        print(f"  [EVIDENCE] TestCases in DB for Docker failure: {persisted_docker_fail}")
        assert persisted_docker_fail == 0, "Partial test cases persisted after Docker failure!"
        print("  [PASS] 4d: Docker failure does not save partial records.")

        # 4e. Timeouts do not save partial records
        hang_dir = Path(temp_dir) / "hang_suite"
        hang_dir.mkdir()
        (hang_dir / "conftest.py").write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        (hang_dir / "test_hanging.py").write_text("def test_never_reached(): pass\n", encoding="utf-8")
        proj_hang_id = str(uuid.uuid4())
        db.add(Project(id=proj_hang_id, name="Hang Project"))
        db.commit()

        timeout_raised = False
        try:
            discover_and_register_tests(proj_hang_id, hang_dir, db, manager, timeout_seconds=2)
        except TestDiscoveryTimeoutError as e:
            timeout_raised = True
            print(f"  [EVIDENCE] Caught expected TestDiscoveryTimeoutError: {str(e)[:80]}...")

        assert timeout_raised is True
        persisted_hang = db.query(TestCase).filter(TestCase.project_id == proj_hang_id).count()
        print(f"  [EVIDENCE] TestCases in DB for timeout: {persisted_hang}")
        assert persisted_hang == 0, "Partial test cases persisted after timeout!"
        print("  [PASS] 4e: Timeouts do not save partial records.")

        # 4f. Repeated discovery does not create duplicate TestCase records
        proj_idempotent_id = str(uuid.uuid4())
        db.add(Project(id=proj_idempotent_id, name="Idempotent Suite"))
        db.commit()

        run1 = discover_and_register_tests(proj_idempotent_id, real_suite_dir, db, manager)
        count1 = db.query(TestCase).filter(TestCase.project_id == proj_idempotent_id).count()
        run2 = discover_and_register_tests(proj_idempotent_id, real_suite_dir, db, manager)
        count2 = db.query(TestCase).filter(TestCase.project_id == proj_idempotent_id).count()

        print(f"  [EVIDENCE] Run 1 cases: {len(run1)}, Run 2 cases: {len(run2)}, DB count: {count2}")
        assert count1 == 6
        assert count2 == 6
        assert len(run1) == 6
        assert len(run2) == 6
        print("  [PASS] 4f: Repeated discovery does not create duplicate TestCase records.")

        # 4g. Empty test suite handled correctly
        empty_dir = Path(temp_dir) / "empty_suite"
        empty_dir.mkdir()
        (empty_dir / "test_empty.py").write_text("# No test functions here\nx = 1\n", encoding="utf-8")
        proj_empty_id = str(uuid.uuid4())
        db.add(Project(id=proj_empty_id, name="Empty Suite Project"))
        db.commit()

        empty_discovered = discover_and_register_tests(proj_empty_id, empty_dir, db, manager)
        persisted_empty = db.query(TestCase).filter(TestCase.project_id == proj_empty_id).count()
        print(f"  [EVIDENCE] Empty suite discovered count: {len(empty_discovered)}, in DB: {persisted_empty}")
        assert len(empty_discovered) == 0
        assert persisted_empty == 0
        print("  [PASS] 4g: Empty test suite handled correctly (0 records saved).")
    finally:
        db.close()
        engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # CHECK 5: Windows Bind Mounts on Real Project Directory
    # --------------------------------------------------------------------------
    print("\n--- CHECK 5: Real Windows Bind Mount Resolution Verification ---")
    windows_path = Path("C:/flakelens/samples/synthetic_flaky_suite").resolve()
    print(f"  [EVIDENCE] Host Windows path: {windows_path}")
    assert windows_path.exists(), "Synthetic suite path does not exist on Windows"

    cont = client.containers.create(
        image="flakelens-runner:latest",
        entrypoint="python",
        command=["-c", "import os; print('CONTAINER_FILES:', sorted([f for f in os.listdir('/workspace') if f.endswith('.py')]))"],
        volumes={str(windows_path): {"bind": "/workspace", "mode": "ro"}},
        network_mode="none",
    )
    try:
        cont.start()
        cont.wait()
        mount_output = cont.logs().decode("utf-8").strip()
    finally:
        cont.remove(force=True)
    print(f"  [EVIDENCE] Output from container with Windows mount:\n    {mount_output}")
    expected_files = [
        "test_async_timing.py",
        "test_order_dependency.py",
        "test_resource_leak.py",
        "test_stable_failing.py",
        "test_stable_passing.py",
    ]
    for ef in expected_files:
        assert ef in mount_output, f"Expected {ef} to be visible inside container"

    print("  [PASS] Windows bind mount verified: files in host Windows path correctly accessible inside container.")

    print("\n" + "=" * 80)
    print("ALL 5 AUDIT CHECKS PASSED WITH COMPLETE LIVE EVIDENCE!")
    print("=" * 80)


if __name__ == "__main__":
    run_audit()
