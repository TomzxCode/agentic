"""In-process publish/subscribe used to stream agent events to the SPA over SSE."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(topic, ())):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

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


class RunRegistry:
    """Tracks live run cancellation handles, keyed by run id."""

    def __init__(self) -> None:
        self._cancellers: dict[str, asyncio.Event] = {}

    def register(self, run_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._cancellers[run_id] = event
        return event

    def cancel(self, run_id: str) -> bool:
        event = self._cancellers.get(run_id)
        if event is None:
            return False
        event.set()
        return True

    def unregister(self, run_id: str) -> None:
        self._cancellers.pop(run_id, None)


runs = RunRegistry()
