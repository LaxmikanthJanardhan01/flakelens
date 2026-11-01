"""
Draft Test Pattern: Shared Resource / Static File Contention
Unverified baseline fixture for Phase 2/3 validation.
"""
import os
import tempfile

STATIC_LOCK_FILE = os.path.join(tempfile.gettempdir(), "flakelens_synthetic_shared_lock.tmp")


def test_resource_contention():
    """
    Attempts to write to a static temporary lock file without cleanup.
    Can fail with FileExistsError or PermissionError if previous run did not clean up.
    """
    # Flawed: Does not use pytest tmp_path fixture or clean up properly
    if os.path.exists(STATIC_LOCK_FILE):
        os.remove(STATIC_LOCK_FILE)

    with open(STATIC_LOCK_FILE, "w", encoding="utf-8") as f:
        f.write("active_lock")

    assert os.path.exists(STATIC_LOCK_FILE)
    # Intentionally omitted cleanup to simulate resource leakage

