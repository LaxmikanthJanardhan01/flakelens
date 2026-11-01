"""
Baseline Control: Deterministic Pass
Should pass consistently in 100% of iterations (P = 1.0).
"""


def test_pure_deterministic_calculation():
    """Deterministic arithmetic addition."""
    operand_a = 40
    operand_b = 2
    assert operand_a + operand_b == 42

