"""The in-process event bus."""

import pytest

from agentic.events import EventBus


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
