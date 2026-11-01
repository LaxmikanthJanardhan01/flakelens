"""
Docker Container Lifecycle Management for FLAKELENS.

Enforces strict isolation, resource boundaries, and non-root execution
for untrusted test repositories.
"""
import io
import os
import tarfile
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List, Callable
import docker
from docker.errors import DockerException, APIError, BuildError

from backend.app.config import settings


class DockerManagerError(Exception):
    """Base exception for Docker operations."""
    pass


class DockerUnavailableError(DockerManagerError):
    """Raised when Docker daemon is not running or accessible."""
    pass


class ProjectBuildError(DockerManagerError):
    """Raised when Stage A project dependency installation fails."""
    pass


class TestDiscoveryError(DockerManagerError):
    """Raised when pytest collection fails inside the container."""
    __test__ = False


class TestDiscoveryTimeoutError(DockerManagerError):
    """Raised when pytest collection exceeds time limits."""
    __test__ = False


class DockerManager:
    """
    Manages container lifecycles, ephemeral project images, and sandboxed test execution.
    """

    BASE_IMAGE_TAG = "flakelens-runner:latest"

    def __init__(self, client: Optional[docker.DockerClient] = None) -> None:
        self._client = client

    def _get_client(self) -> docker.DockerClient:
        """
        Lazily initialize and return the Docker client, raising actionable error if unavailable.
        """
        if self._client is not None:
            return self._client

        try:
            client = docker.from_env()
            client.ping()
            self._client = client
            return self._client
        except DockerException as e:
            raise DockerUnavailableError(
                "Docker daemon is not running or not accessible. "
                "Please verify that Docker Desktop is installed, started, and the Docker engine is running. "
                f"Underlying error: {str(e)}"
            )
        except Exception as e:
            raise DockerUnavailableError(
                f"Failed to connect to Docker service: {str(e)}. "
                "Ensure Docker Desktop is running and user permissions allow access to the Docker pipe/socket."
            )

    def is_available(self) -> Tuple[bool, Optional[str]]:
        """
        Check if the Docker daemon is accessible and responsive.

        Returns:
            Tuple[bool, Optional[str]]: (True, None) if available, or (False, error_message).
        """
        try:
            client = self._get_client()
            client.ping()
            return True, None
        except DockerUnavailableError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Docker daemon check failed: {str(e)}"

    def ensure_base_image(self) -> str:
        """
        Ensures the base runner image (flakelens-runner:latest) is built and available.

        Returns:
            str: Tag of the base image.
        """
        client = self._get_client()
        try:
            client.images.get(self.BASE_IMAGE_TAG)
            return self.BASE_IMAGE_TAG
        except docker.errors.ImageNotFound:
            dockerfile_path = settings.BASE_DIR / "backend" / "Dockerfile.runner"
            context_path = settings.BASE_DIR / "backend"
            if not dockerfile_path.exists():
                raise DockerManagerError(f"Base Dockerfile not found at {dockerfile_path}")

            try:
                client.images.build(
                    path=str(context_path),
                    dockerfile="Dockerfile.runner",
                    tag=self.BASE_IMAGE_TAG,
                    rm=True,
                )
                return self.BASE_IMAGE_TAG
            except BuildError as e:
                build_logs = "\n".join(
                    line.get("stream", "").strip() for line in e.build_log if isinstance(line, dict) and "stream" in line
                )
                raise DockerManagerError(f"Failed to build base runner image: {build_logs}")
            except Exception as e:
                raise DockerManagerError(f"Error building base runner image: {str(e)}")

    def prepare_project_image(self, project_dir: Path, project_id: str) -> str:
        """
        Stage A: Prepares the execution image for a project.
        If requirements.txt exists and specifies custom dependencies, builds an ephemeral
        image tagged flakelens-project-{project_id}:latest.
        Otherwise, returns the base runner image.

        Returns:
            str: The Docker image tag to use for running tests.
        """
        client = self._get_client()
        self.ensure_base_image()

        reqs_file = Path(project_dir) / "requirements.txt"
        if not reqs_file.exists():
            return self.BASE_IMAGE_TAG

        try:
            reqs_content = reqs_file.read_text(encoding="utf-8")
        except Exception as e:
            raise ProjectBuildError(f"Unable to read requirements.txt: {str(e)}")

        # Check if requirements contain anything beyond comments, blank lines, or standard base packages
        meaningful_lines = [
            line.strip()
            for line in reqs_content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        if not meaningful_lines:
            return self.BASE_IMAGE_TAG

        # Check if all requirements are already included in the base image (pytest, pytest-json-report, pytest-random-order)
        base_pkgs = {"pytest", "pytest-json-report", "pytest-random-order"}
        custom_needed = False
        for line in meaningful_lines:
            pkg_name = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("!=")[0].strip()
            if pkg_name.lower() not in base_pkgs:
                custom_needed = True
                break

        if not custom_needed:
            return self.BASE_IMAGE_TAG

        # Build ephemeral image using in-memory tar stream to avoid polluting project directory
        ephemeral_tag = f"flakelens-project-{project_id}:latest"
        dockerfile_content = (
            f"FROM {self.BASE_IMAGE_TAG}\n"
            "USER root\n"
            "COPY requirements.txt /tmp/requirements.txt\n"
            "RUN pip install --no-cache-dir -r /tmp/requirements.txt\n"
            "USER 1000:1000\n"
        ).encode("utf-8")

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            df_info = tarfile.TarInfo(name="Dockerfile")
            df_info.size = len(dockerfile_content)
            tar.addfile(df_info, io.BytesIO(dockerfile_content))

            rf_bytes = reqs_content.encode("utf-8")
            rf_info = tarfile.TarInfo(name="requirements.txt")
            rf_info.size = len(rf_bytes)
            tar.addfile(rf_info, io.BytesIO(rf_bytes))
        tar_stream.seek(0)

        try:
            client.images.build(
                fileobj=tar_stream,
                custom_context=True,
                tag=ephemeral_tag,
                rm=True,
                timeout=settings.DOCKER_BUILD_TIMEOUT,
            )
            return ephemeral_tag
        except BuildError as e:
            log_lines = []
            for item in e.build_log:
                if isinstance(item, dict):
                    if "stream" in item:
                        log_lines.append(item["stream"].strip())
                    elif "error" in item:
                        log_lines.append(item["error"].strip())
            error_details = "\n".join([line for line in log_lines if line])
            raise ProjectBuildError(
                f"Stage A dependency installation failed for project '{project_id}':\n{error_details}"
            )
        except Exception as e:
            raise ProjectBuildError(f"Failed to prepare project container image: {str(e)}")

    def run_sandboxed_discovery(
        self,
        image_tag: str,
        project_dir: Path,
        timeout_seconds: int = 30,
    ) -> Tuple[int, str]:
        """
        Executes 'pytest --collect-only -q' inside a strictly isolated Docker container.

        Enforces:
        - Non-root execution (user 1000:1000)
        - Dropped Linux capabilities (--cap-drop ALL)
        - No network access (--network none)
        - Read-only workspace bind mount (:ro)
        - Memory and CPU limits
        - PID limit to prevent fork bombs
        - /tmp tmpfs mount for safe cache writing

        Returns:
            Tuple[int, str]: (exit_code, combined_stdout_and_stderr)
        """
        client = self._get_client()
        resolved_project_path = str(Path(project_dir).resolve())

        # Build volumes and tmpfs configuration
        # Note: on Windows host, resolve() provides canonical absolute path
        volumes = {
            resolved_project_path: {
                "bind": "/workspace",
                "mode": "ro",
            }
        }
        tmpfs = {"/tmp": ""}

        container_cmd = [
            "--collect-only",
            "-q",
            "-o", "cache_dir=/tmp/.pytest_cache",
        ]

        container = None
        try:
            container = client.containers.create(
                image=image_tag,
                command=container_cmd,
                volumes=volumes,
                tmpfs=tmpfs,
                network_mode="none",
                cap_drop=["ALL"],
                mem_limit=settings.DOCKER_MEMORY_LIMIT,
                nano_cpus=int(settings.DOCKER_CPU_LIMIT * 1e9),
                pids_limit=settings.DOCKER_PIDS_LIMIT,
                security_opt=["no-new-privileges:true"],
                user="1000:1000",
                working_dir="/workspace",
            )

            container.start()

            try:
                result = container.wait(timeout=timeout_seconds)
                exit_code = result.get("StatusCode", -1)
            except Exception as e:
                # Timed out or wait error
                try:
                    container.kill()
                except Exception:
                    pass
                raise TestDiscoveryTimeoutError(
                    f"Test discovery timed out after {timeout_seconds} seconds inside isolated Docker container."
                )

            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            return exit_code, logs

        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def run_sandboxed_iteration(
        self,
        image_tag: str,
        project_dir: Path,
        events_dir: Path,
        seed: int,
        shuffle_order: bool = True,
        test_node_ids: Optional[List[str]] = None,
        timeout_seconds: int = 60,
        cancel_event: Optional[Any] = None,
        on_container_started: Optional[Callable[[Optional[Any]], None]] = None,
    ) -> Tuple[int, str, bool]:
        """
        Executes a test iteration inside a strictly isolated Docker container with the
        FLAKELENS pytest event collection plugin attached.

        Enforces:
        - Non-root execution (user 1000:1000)
        - Dropped Linux capabilities (--cap-drop ALL)
        - No network access (--network none)
        - Read-only workspace bind mount (:ro)
        - Writable events directory (:rw) for streaming telemetry
        - Memory and CPU limits
        - PID limit (100)
        - Deterministic random order seed
        - Immediate cancellation awareness and cleanup

        Returns:
            Tuple[int, str, bool]: (exit_code, combined_logs, timed_out)
        """
        if cancel_event and cancel_event.is_set():
            return 137, "Execution cancelled before container start.", False

        client = self._get_client()
        plugin_path = settings.BASE_DIR / "backend" / "app" / "runner" / "flakelens_plugin.py"
        resolved_project_path = str(Path(project_dir).resolve())
        resolved_events_path = str(Path(events_dir).resolve())
        resolved_plugin_path = str(Path(plugin_path).resolve())

        volumes = {
            resolved_project_path: {"bind": "/workspace", "mode": "ro"},
            resolved_plugin_path: {"bind": "/opt/flakelens/flakelens_plugin.py", "mode": "ro"},
            resolved_events_path: {"bind": "/events", "mode": "rw"},
        }
        tmpfs = {"/tmp": ""}
        environment = {
            "PYTHONPATH": "/opt/flakelens",
            "FLAKELENS_EVENT_FILE": "/events/events.jsonl",
        }

        container_cmd = [
            "-p", "flakelens_plugin",
            "-o", "cache_dir=/tmp/.pytest_cache",
        ]
        if shuffle_order:
            container_cmd.append(f"--random-order-seed={seed}")
        else:
            container_cmd.append("--random-order-bucket=none")

        if test_node_ids:
            container_cmd.extend(test_node_ids)

        container = None
        timed_out = False
        logs = ""

        try:
            container = client.containers.create(
                image=image_tag,
                command=container_cmd,
                volumes=volumes,
                tmpfs=tmpfs,
                environment=environment,
                network_mode="none",
                cap_drop=["ALL"],
                mem_limit=settings.DOCKER_MEMORY_LIMIT,
                nano_cpus=int(settings.DOCKER_CPU_LIMIT * 1e9),
                pids_limit=settings.DOCKER_PIDS_LIMIT,
                security_opt=["no-new-privileges:true"],
                user="1000:1000",
                working_dir="/workspace",
            )

            if cancel_event and cancel_event.is_set():
                return 137, "Execution cancelled before container launch.", False

            container.start()
            if on_container_started:
                try:
                    on_container_started(container)
                except Exception:
                    pass

            try:
                result = container.wait(timeout=timeout_seconds)
                exit_code = result.get("StatusCode", -1)
            except Exception:
                if cancel_event and cancel_event.is_set():
                    timed_out = False
                else:
                    timed_out = True
                try:
                    container.kill()
                except Exception:
                    pass
                exit_code = -1

            if cancel_event and cancel_event.is_set():
                timed_out = False

            try:
                logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            except Exception:
                logs = ""

            return exit_code, logs, timed_out

        finally:
            if on_container_started:
                try:
                    on_container_started(None)
                except Exception:
                    pass
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def cleanup_project_image(self, project_id: str) -> None:
        """
        Safely removes an ephemeral project image if one was created.
        """
        try:
            client = self._get_client()
            tag = f"flakelens-project-{project_id}:latest"
            client.images.remove(tag, force=True)
        except Exception:
            pass
