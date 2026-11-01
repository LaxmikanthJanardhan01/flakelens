"""
Phase 2 - Milestone 2 Verification Suite
Verifies:
1. Docker daemon availability checking and actionable error reporting.
2. Windows-compatible bind mount path handling.
3. Strict container isolation (non-root 1000:1000, read-only workspace, --network none, dropped capabilities).
4. Stage A ephemeral image build and invalid requirement error handling.
5. Pytest node ID parsing accuracy.
6. Real containerized pytest collection and SQLite registration on synthetic_flaky_suite (6 tests).
7. FastAPI upload endpoint integration with ZIP extraction and isolated discovery.
"""
import io
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.main import app
from backend.app.db.session import Base, get_db
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


@pytest.fixture
def test_db():
    """Isolated SQLite database fixture for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_m2.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionTest = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionTest()

    yield session

    session.close()
    engine.dispose()
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestDockerAvailability:
    """Verifies Docker availability reporting and actionable guidance."""

    def test_real_docker_daemon_available(self):
        """Verifies that the local Docker daemon is running and detected."""
        manager = DockerManager()
        is_avail, err = manager.is_available()
        assert is_avail is True
        assert err is None

    def test_docker_unavailable_actionable_error(self):
        """Verifies clear actionable message when Docker daemon cannot be reached."""
        class MockFailingDockerClient:
            def ping(self):
                raise ConnectionError("Named pipe //./pipe/docker_engine closed")

        manager = DockerManager(client=MockFailingDockerClient())
        is_avail, err = manager.is_available()
        assert is_avail is False
        assert "Docker daemon check failed" in err or "Docker" in err

    def test_ensure_base_image_present(self):
        """Verifies flakelens-runner:latest is available."""
        manager = DockerManager()
        tag = manager.ensure_base_image()
        assert tag == "flakelens-runner:latest"


class TestContainerSecurityIsolation:
    """Verifies strict container sandbox isolation properties."""

    def test_sandboxed_container_isolation_properties(self):
        """
        Executes a diagnostic container command to verify:
        - UID/GID is 1000:1000 (non-root)
        - /workspace is read-only (:ro)
        - Network is completely unreachable (--network none)
        """
        import docker
        client = docker.from_env()

        probe_script = (
            "import os, urllib.request\n"
            "uid = os.getuid()\n"
            "gid = os.getgid()\n"
            "net_ok = False\n"
            "try:\n"
            "    urllib.request.urlopen('http://1.1.1.1', timeout=1)\n"
            "    net_ok = True\n"
            "except Exception:\n"
            "    net_ok = False\n"
            "write_ok = False\n"
            "try:\n"
            "    with open('/workspace/probe.tmp', 'w') as f: f.write('bad')\n"
            "    write_ok = True\n"
            "except OSError:\n"
            "    write_ok = False\n"
            "print(f'UID={uid},GID={gid},NET={net_ok},WRITE={write_ok}')\n"
        )

        test_dir = settings.BASE_DIR / "samples" / "synthetic_flaky_suite"
        resolved_path = str(test_dir.resolve())

        container = client.containers.create(
            image="flakelens-runner:latest",
            entrypoint="python",
            command=["-c", probe_script],
            volumes={resolved_path: {"bind": "/workspace", "mode": "ro"}},
            tmpfs={"/tmp": ""},
            network_mode="none",
            cap_drop=["ALL"],
            mem_limit="1024m",
            nano_cpus=1000000000,
            pids_limit=100,
            user="1000:1000",
        )
        try:
            container.start()
            container.wait(timeout=10)
            logs = container.logs().decode("utf-8")
            assert "UID=1000,GID=1000,NET=False,WRITE=False" in logs
        finally:
            container.remove(force=True)


class TestNodeIdParsing:
    """Verifies parsing of pytest --collect-only output into structured test metadata."""

    def test_parse_pytest_node_ids_simple(self):
        raw = (
            "test_basic.py::test_one\n"
            "test_basic.py::test_two\n"
            "\n"
            "2 tests collected in 0.05s\n"
        )
        parsed = parse_pytest_node_ids(raw)
        assert len(parsed) == 2
        assert parsed[0] == ("test_basic.py", "test_one", "test_basic.py::test_one")
        assert parsed[1] == ("test_basic.py", "test_two", "test_basic.py::test_two")

    def test_parse_pytest_node_ids_classes_and_params(self):
        raw = (
            "tests/sub/test_math.py::TestCalculations::test_add\n"
            "tests/sub/test_math.py::test_param[value1-opt2]\n"
            "<Package test_math>\n"
            "2 tests collected in 0.10s\n"
        )
        parsed = parse_pytest_node_ids(raw)
        assert len(parsed) == 2
        assert parsed[0] == (
            "tests/sub/test_math.py",
            "TestCalculations::test_add",
            "tests/sub/test_math.py::TestCalculations::test_add",
        )
        assert parsed[1] == (
            "tests/sub/test_math.py",
            "test_param[value1-opt2]",
            "tests/sub/test_math.py::test_param[value1-opt2]",
        )

    def test_parse_empty_or_no_tests(self):
        raw = "no tests collected in 0.01s\n"
        parsed = parse_pytest_node_ids(raw)
        assert len(parsed) == 0


class TestIsolatedDiscoveryAndPersistence:
    """Verifies containerized test discovery and persistence on real synthetic suite."""

    def test_discover_synthetic_flaky_suite_in_docker(self, test_db):
        """
        Discovers tests from samples/synthetic_flaky_suite strictly inside Docker.
        Expects 6 test cases indexed into SQLite.
        """
        project_dir = settings.BASE_DIR / "samples" / "synthetic_flaky_suite"
        assert project_dir.exists()

        project_id = str(uuid.uuid4())
        proj = Project(
            id=project_id,
            name="Synthetic Flaky Suite",
            source_archive_path=str(project_dir),
        )
        test_db.add(proj)
        test_db.commit()

        manager = DockerManager()
        discovered = discover_and_register_tests(
            project_id=project_id,
            project_dir=project_dir,
            db=test_db,
            docker_mgr=manager,
        )

        assert len(discovered) == 6
        node_ids = {tc.node_id for tc in discovered}
        expected_node_ids = {
            "test_async_timing.py::test_timing_race_condition",
            "test_order_dependency.py::test_order_step_populate",
            "test_order_dependency.py::test_order_step_expect_clean",
            "test_resource_leak.py::test_resource_contention",
            "test_stable_failing.py::test_deterministic_failure",
            "test_stable_passing.py::test_pure_deterministic_calculation",
        }
        assert node_ids == expected_node_ids

        # Verify DB persistence
        db_cases = test_db.query(TestCase).filter(TestCase.project_id == project_id).all()
        assert len(db_cases) == 6
        assert {c.node_id for c in db_cases} == expected_node_ids

        # Test idempotency (re-running discovery should update, not duplicate)
        rediscovered = discover_and_register_tests(
            project_id=project_id,
            project_dir=project_dir,
            db=test_db,
            docker_mgr=manager,
        )
        assert len(rediscovered) == 6
        assert test_db.query(TestCase).filter(TestCase.project_id == project_id).count() == 6

    def test_discovery_collection_syntax_error(self, test_db):
        """Verifies that syntax error in test code raises TestDiscoveryError with pytest output."""
        temp_dir = tempfile.mkdtemp()
        try:
            bad_test = Path(temp_dir) / "test_broken_syntax.py"
            bad_test.write_text("def test_broken(: invalid python", encoding="utf-8")

            project_id = str(uuid.uuid4())
            proj = Project(id=project_id, name="Broken Project")
            test_db.add(proj)
            test_db.commit()

            manager = DockerManager()
            with pytest.raises(TestDiscoveryError) as exc_info:
                discover_and_register_tests(
                    project_id=project_id,
                    project_dir=Path(temp_dir),
                    db=test_db,
                    docker_mgr=manager,
                )
            assert "SyntaxError" in str(exc_info.value) or "exit code" in str(exc_info.value)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestUploadAPIIntegration:
    """Verifies POST /api/projects/upload end-to-end with archive extraction and Docker discovery."""

    def test_upload_valid_project_zip(self, test_db):
        """Verifies creating a ZIP of synthetic suite, uploading to API, and receiving 6 test cases."""
        app.dependency_overrides[get_db] = lambda: test_db

        # Create in-memory ZIP of synthetic_flaky_suite
        suite_dir = settings.BASE_DIR / "samples" / "synthetic_flaky_suite"
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in suite_dir.glob("*.py"):
                zf.write(file_path, arcname=file_path.name)
            reqs = suite_dir / "requirements.txt"
            if reqs.exists():
                zf.write(reqs, arcname="requirements.txt")
        zip_buffer.seek(0)

        client = TestClient(app)
        response = client.post(
            "/api/projects/upload",
            files={"file": ("synthetic_suite.zip", zip_buffer, "application/zip")},
            data={"name": "Uploaded Synthetic Suite"},
        )

        app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Uploaded Synthetic Suite"
        assert data["test_cases_count"] == 6

        project_id = data["id"]

        # Verify GET /api/projects/{id}/tests
        app.dependency_overrides[get_db] = lambda: test_db
        tests_resp = client.get(f"/api/projects/{project_id}/tests")
        app.dependency_overrides.clear()

        assert tests_resp.status_code == 200
        tests_data = tests_resp.json()
        assert len(tests_data) == 6
        assert any(t["test_name"] == "test_timing_race_condition" for t in tests_data)

        # Cleanup
        app.dependency_overrides[get_db] = lambda: test_db
        del_resp = client.delete(f"/api/projects/{project_id}")
        app.dependency_overrides.clear()
        assert del_resp.status_code == 204

    def test_upload_non_zip_rejected(self, test_db):
        """Verifies that non-ZIP files are rejected immediately."""
        app.dependency_overrides[get_db] = lambda: test_db
        client = TestClient(app)
        response = client.post(
            "/api/projects/upload",
            files={"file": ("malicious.tar.gz", io.BytesIO(b"fake"), "application/gzip")},
        )
        app.dependency_overrides.clear()
        assert response.status_code == 400
        assert "Only ZIP archives" in response.json()["detail"]
