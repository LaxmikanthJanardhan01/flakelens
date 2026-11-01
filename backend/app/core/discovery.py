"""
Isolated Pytest Discovery for FLAKELENS.

Executes test collection strictly inside Docker containers with dropped capabilities
and zero network access, parsing discovered test node IDs into SQLite database records.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session

from backend.app.core.docker_manager import (
    DockerManager,
    TestDiscoveryError,
    TestDiscoveryTimeoutError,
    DockerUnavailableError,
)
from backend.app.db.models import TestCase, Project


def parse_pytest_node_ids(raw_output: str) -> List[Tuple[str, str, str]]:
    """
    Parses the output of 'pytest --collect-only -q' into structured test metadata.

    Each valid test node ID follows the convention:
    path/to/test_file.py::test_function_or_class[::test_method]

    Returns:
        List[Tuple[str, str, str]]: List of (file_path, test_name, full_node_id).
    """
    discovered: List[Tuple[str, str, str]] = []
    seen_nodes = set()

    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue

        # Pytest node IDs contain '::'
        if "::" in line:
            # Avoid summary lines that might accidentally contain colons
            if line.startswith("<") or line.endswith(">"):
                continue

            parts = line.split("::")
            if len(parts) >= 2:
                file_path = parts[0].strip()
                test_name = "::".join(parts[1:]).strip()
                node_id = line

                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    discovered.append((file_path, test_name, node_id))

    return discovered


def discover_and_register_tests(
    project_id: str,
    project_dir: Path,
    db: Session,
    docker_mgr: Optional[DockerManager] = None,
    timeout_seconds: int = 30,
) -> List[TestCase]:
    """
    Discovers all pytest test cases in project_dir by running collection strictly inside Docker,
    and registers them in the database associated with the given project_id.

    Args:
        project_id: The UUID of the project.
        project_dir: Path to the extracted project directory on the host.
        db: Active SQLAlchemy database session.
        docker_mgr: Optional DockerManager instance (created if None).

    Returns:
        List[TestCase]: List of registered TestCase database entities.

    Raises:
        DockerUnavailableError: If Docker daemon is not accessible.
        TestDiscoveryError: If pytest collection encounters syntax or runtime errors.
        TestDiscoveryTimeoutError: If pytest collection times out.
    """
    mgr = docker_mgr or DockerManager()

    # Verify Docker availability
    available, error_msg = mgr.is_available()
    if not available:
        raise DockerUnavailableError(error_msg or "Docker daemon is not accessible.")

    # Stage A: Prepare execution image (ephemeral if requirements exist)
    image_tag = mgr.prepare_project_image(project_dir, project_id)

    # Stage B: Run sandboxed discovery inside Docker container with --network none
    exit_code, output = mgr.run_sandboxed_discovery(
        image_tag=image_tag,
        project_dir=project_dir,
        timeout_seconds=timeout_seconds,
    )

    # Exit code 5 in pytest means no tests collected (not an execution failure)
    if exit_code not in (0, 5):
        raise TestDiscoveryError(
            f"Pytest collection failed with exit code {exit_code}:\n{output}"
        )

    parsed_tests = parse_pytest_node_ids(output)

    # Synchronize database records with discovered tests
    existing_records = db.query(TestCase).filter(TestCase.project_id == project_id).all()
    existing_map = {tc.node_id: tc for tc in existing_records}
    current_node_ids = set()

    registered_cases: List[TestCase] = []

    for file_path, test_name, node_id in parsed_tests:
        current_node_ids.add(node_id)
        if node_id in existing_map:
            # Existing test case
            tc = existing_map[node_id]
            tc.file_path = file_path
            tc.test_name = test_name
            registered_cases.append(tc)
        else:
            # New test case
            new_tc = TestCase(
                project_id=project_id,
                file_path=file_path,
                test_name=test_name,
                node_id=node_id,
                discovered_at=datetime.now(timezone.utc),
            )
            db.add(new_tc)
            registered_cases.append(new_tc)

    # Clean up any previously stored test cases that no longer exist
    for node_id, tc in existing_map.items():
        if node_id not in current_node_ids:
            db.delete(tc)

    db.commit()

    # Refresh instances
    for tc in registered_cases:
        db.refresh(tc)

    return registered_cases
