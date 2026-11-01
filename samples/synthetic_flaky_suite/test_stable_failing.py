"""
Baseline Control: Deterministic Failure (Broken Test)
Should fail consistently in 100% of iterations (F = 1.0).
Must be classified as CONSISTENTLY_FAILING (Deterministic Bug, NOT stable).
"""


def test_deterministic_failure():
    """Deterministic failure asserting false equality."""
    actual_value = 100
    expected_value = 999
    assert actual_value == expected_value, (
        f"Deterministic bug: expected {expected_value}, got {actual_value}"
    )

