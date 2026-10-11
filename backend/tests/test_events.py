"""The in-process event bus and run cancellation registry."""

import pytest

from agentic.events import EventBus, RunRegistry


@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber():
    bus = EventBus()
    async with bus.subscribe("t") as queue:
        await bus.publish("t", {"a": 1})
        assert await queue.get() == {"a": 1}
    # The subscription is cleaned up when the context exits.
    assert bus._subscribers == {}


@pytest.mark.asyncio
async def test_publish_without_subscribers_is_a_noop():
    bus = EventBus()
    await bus.publish("nobody-listening", {"a": 1})
    assert bus._subscribers == {}


@pytest.mark.asyncio
async def test_a_topic_reaches_every_subscriber():
    bus = EventBus()
    async with bus.subscribe("t") as first, bus.subscribe("t") as second:
        await bus.publish("t", {"a": 1})
        assert await first.get() == {"a": 1}
        assert await second.get() == {"a": 1}


@pytest.mark.asyncio
async def test_publish_drops_events_when_a_queue_is_full():
    bus = EventBus()
    async with bus.subscribe("t") as queue:
        for i in range(queue.maxsize):
            queue.put_nowait({"i": i})
        # Publishing to a full queue is dropped rather than raising.
        await bus.publish("t", {"overflow": True})
        assert queue.qsize() == queue.maxsize


@pytest.mark.asyncio
async def test_second_subscriber_is_removed_without_dropping_the_topic():
    bus = EventBus()
    async with bus.subscribe("t"):
        async with bus.subscribe("t"):
            pass
        # One subscriber remains, so the topic is kept.
        assert "t" in bus._subscribers
    assert bus._subscribers == {}


def test_run_registry_register_cancel_and_unregister():
    registry = RunRegistry()
    event = registry.register("r1")
    assert not event.is_set()

    assert registry.cancel("r1") is True
    assert event.is_set()

    # Cancelling an unknown run reports no handle.
    assert registry.cancel("missing") is False

    registry.unregister("r1")
    assert registry.cancel("r1") is False
    # Unregistering twice is harmless.
    registry.unregister("r1")


def test_run_registry_event_is_bound_to_its_run():
    registry = RunRegistry()
    first = registry.register("a")
    second = registry.register("b")
    registry.cancel("a")
    assert first.is_set() and not second.is_set()
