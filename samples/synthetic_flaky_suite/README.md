# Synthetic Flaky Test Suite (Draft Baseline Fixtures)

> ⚠️ **Status: Unverified Draft Test Patterns**  
> These test cases are initial draft fixtures representing common causes of test flakiness. They are **not yet validated as reproducible flakes** and serve as baseline test inputs to be executed, measured, and verified by the containerized runner in Phase 2 and Phase 3.

## Candidate Test Patterns

1. **`test_order_dependency.py`**:
   - Models shared mutable module state without explicit fixture cleanup (`yield` teardown).
   - Expected behavior: If executed in one sequence it passes; if execution order is shuffled by `pytest-random-order`, test outcomes may vary depending on execution order.

2. **`test_async_timing.py`**:
   - Models an asynchronous callback with a hardcoded sleep wait (`time.sleep`) vs a variable simulated task delay.
   - Expected behavior: Under variable host load, the sleep window may occasionally expire before state updates, simulating timing-based flakiness.

3. **`test_resource_leak.py`**:
   - Models a test that writes to a shared, hardcoded temporary file without proper isolation or cleanup.
   - Expected behavior: Multiple iterations or overlapping executions may encounter file contention.

4. **`test_stable_passing.py`**:
   - Baseline control test: Deterministically performs a pure unit assertion ($P = 1.0$).
   - Must be classified by FLAKELENS as `CONSISTENTLY_PASSING`.

5. **`test_stable_failing.py`**:
   - Baseline control test: Deterministically fails an assertion ($F = 1.0$).
   - Must be classified by FLAKELENS as `CONSISTENTLY_FAILING` (Deterministic Bug, **never** stable).

