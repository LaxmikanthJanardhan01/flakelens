"""
FLAKELENS Pytest Event Collection Plugin.

Captures real-time per-test execution lifecycle events:
- test_started: emitted immediately when test starts execution.
- test_finished: emitted immediately when test completes (setup, call, teardown aggregated).

Guarantees:
- Exactly one test_finished event per test item.
- Accurate handling of setup failure, call failure, skipped, and teardown failure.
- Immediate line-buffered flushing to JSONL event file.
- Safe post-mortem salvage by host watchdog if container is forcefully terminated.
"""
import json
import os
import time
from typing import Dict, List, Optional
import pytest


class FlakeLensEventPlugin:
    """
    Pytest plugin writing real-time test execution events to a line-delimited JSON (JSONL) file.
    """

    def __init__(self, event_file_path: str) -> None:
        self.event_file_path = event_file_path
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(os.path.abspath(event_file_path)), exist_ok=True)
        self._f = open(event_file_path, "a", encoding="utf-8")
        self._item_reports: Dict[str, List[pytest.TestReport]] = {}
        self._item_start_times: Dict[str, float] = {}

    def _write_event(self, data: dict) -> None:
        try:
            line = json.dumps(data) + "\n"
            self._f.write(line)
            self._f.flush()
            os.fsync(self._f.fileno())
        except Exception:
            pass

    def pytest_runtest_logstart(self, nodeid: str, location: tuple) -> None:
        """Called when a test item begins execution."""
        start_t = time.time()
        self._item_start_times[nodeid] = start_t
        self._write_event({
            "event": "test_started",
            "node_id": nodeid,
            "timestamp": start_t,
        })

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """Collect phase reports (setup, call, teardown) for the item."""
        nodeid = report.nodeid
        if nodeid not in self._item_reports:
            self._item_reports[nodeid] = []
        self._item_reports[nodeid].append(report)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: Optional[pytest.Item]):
        """Wraps entire setup, call, teardown lifecycle to emit exactly one test_finished event."""
        yield
        nodeid = item.nodeid
        start_t = self._item_start_times.get(nodeid, time.time())
        duration_ms = max(1, int((time.time() - start_t) * 1000))
        reports = self._item_reports.get(nodeid, [])

        status = "PASSED"
        error_msg = None
        traceback_str = None
        stdout_parts = []
        stderr_parts = []

        for rep in reports:
            # Capture stdout / stderr sections
            for sec_name, sec_content in rep.sections:
                sec_lower = sec_name.lower()
                if "stdout" in sec_lower:
                    stdout_parts.append(sec_content)
                elif "stderr" in sec_lower:
                    stderr_parts.append(sec_content)

            if rep.failed:
                status = "FAILED"
                if rep.longrepr:
                    traceback_str = str(rep.longrepr)
                    lines = traceback_str.strip().splitlines()
                    error_msg = lines[-1] if lines else "Test failed"
                break
            elif rep.skipped and status != "FAILED":
                status = "SKIPPED"
                if rep.longrepr:
                    error_msg = str(rep.longrepr)

        self._write_event({
            "event": "test_finished",
            "node_id": nodeid,
            "status": status,
            "duration_ms": duration_ms,
            "stdout": "\n".join(stdout_parts),
            "stderr": "\n".join(stderr_parts),
            "error_message": error_msg,
            "traceback": traceback_str,
            "timestamp": time.time(),
        })

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        """Close open file handles on normal session finish."""
        try:
            self._f.close()
        except Exception:
            pass


# Global hook registration when loaded via pytest -p flakelens_plugin
def pytest_addoption(parser):
    group = parser.getgroup("flakelens")
    group.addoption(
        "--flakelens-event-file",
        action="store",
        default=os.environ.get("FLAKELENS_EVENT_FILE", "/events/events.jsonl"),
        help="Target JSONL event file path for FLAKELENS test execution events",
    )


def pytest_configure(config):
    event_file = config.getoption("--flakelens-event-file") or os.environ.get(
        "FLAKELENS_EVENT_FILE", "/events/events.jsonl"
    )
    if event_file:
        plugin = FlakeLensEventPlugin(event_file)
        config.pluginmanager.register(plugin, "flakelens_event_plugin_inst")

