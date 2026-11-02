"""In-process publish/subscribe used to stream agent events to the SPA over SSE."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from typing import Any


def _offer(queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
    with contextlib.suppress(asyncio.QueueFull):
        queue.put_nowait(event)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """Remember the app's loop so a worker thread can publish onto it."""
        self._loop = loop

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(topic, ())):
            _offer(queue, event)

    def publish_threadsafe(self, topic: str, event: dict[str, Any]) -> None:
        """Publish from any thread, for a sync endpoint running in the threadpool.

        A no-op when no loop is bound (the unit tests, a one-off script), so a
        caller does not have to know whether the app is running.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        for queue in list(self._subscribers.get(topic, ())):
            try:
                loop.call_soon_threadsafe(_offer, queue, event)
            except RuntimeError:
                # The loop shut down between the check and the call.
                return

    @contextlib.asynccontextmanager
    async def subscribe(self, topic: str) -> AsyncGenerator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._subscribers.setdefault(topic, set()).add(queue)
        try:
            yield queue
        finally:
            subs = self._subscribers.get(topic)
            if subs is not None:
                subs.discard(queue)
                if not subs:
                    self._subscribers.pop(topic, None)


bus = EventBus()
