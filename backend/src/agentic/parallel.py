"""Run independent blocking calls at the same time.

The helper CLIs the app shells out to (``ghx``, ``slackx``) answer one
invocation at a time, and a caller that needs several of them paid their
latency one after another. Each call is mostly a subprocess wait, so a small
thread pool overlaps them instead of adding them up.

ghx caches through a SQLite database opened in WAL mode with a busy timeout, so
two of its processes may run at once: the second waits for the first's write
rather than failing with ``database is locked``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

#: How many calls run at once. Small on purpose: each is a subprocess that
#: talks to a network API, so a wider burst buys little over the wait and only
#: invites a secondary rate limit.
MAX_WORKERS = 6


def run_parallel[T](calls: Sequence[Callable[[], T]], workers: int | None = None) -> list[T]:
    """Run *calls* at the same time, returning their results in the given order.

    An exception from one call propagates once the pool has drained, so the
    other calls are not left half-run. One call (or none) runs inline, so a
    single fetch does not pay for a thread.
    """
    if len(calls) <= 1:
        return [call() for call in calls]
    with ThreadPoolExecutor(max_workers=workers or min(len(calls), MAX_WORKERS)) as pool:
        return list(pool.map(lambda call: call(), calls))
