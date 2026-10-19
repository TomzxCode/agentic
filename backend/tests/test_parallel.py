"""Running independent helper-CLI calls at the same time."""

import threading

import pytest

from agentic.parallel import run_parallel


def test_run_parallel_keeps_the_call_order():
    assert run_parallel([lambda: 1, lambda: 2, lambda: 3]) == [1, 2, 3]


def test_run_parallel_runs_no_call_and_a_single_call_inline():
    here = threading.current_thread()
    assert run_parallel([]) == []
    # A single call does not pay for a pool thread.
    assert run_parallel([threading.current_thread]) == [here]


def test_run_parallel_overlaps_the_calls():
    # Both calls must be in flight at once for the barrier to release.
    barrier = threading.Barrier(2, timeout=5)
    assert run_parallel([barrier.wait, barrier.wait]) == [0, 1]


def test_run_parallel_propagates_a_failure():
    def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        run_parallel([boom, lambda: 1])
