"""
Draft Test Pattern: Order Dependency / State Pollution
Unverified baseline fixture for Phase 2/3 validation.
"""

# Shared global state without fixture teardown
SHARED_DATABASE_CACHE = []


def test_order_step_populate():
    """Populates the shared cache."""
    SHARED_DATABASE_CACHE.append("user_session_token_123")
    assert len(SHARED_DATABASE_CACHE) >= 1


def test_order_step_expect_clean():
    """
    Expects cache to be empty on initialization.
    If run after test_order_step_populate without teardown, this fails.
    """
    assert len(SHARED_DATABASE_CACHE) == 0, (
        f"State pollution detected! Expected 0 items, found {len(SHARED_DATABASE_CACHE)}"
    )

