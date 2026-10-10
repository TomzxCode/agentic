import json

import httpx
import pytest

from agentic_cli.client import AgenticClient, ApiError


def _client(handler) -> AgenticClient:
    return AgenticClient("http://test.local", transport=httpx.MockTransport(handler))


def test_create_task_drops_none_and_posts_json():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "p1", "title": "T", "status": "open"})

    result = _client(handler).create_task(title="T", description=None, priority=1)
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/tasks"
    assert seen["body"] == {"title": "T", "priority": 1}  # None dropped
    assert result["id"] == "p1"


def test_list_tasks_passes_filters():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = dict(httpx.QueryParams(request.url.query))
        return httpx.Response(200, json=[])

    _client(handler).list_tasks(status="open", q="flaky")
    assert seen["query"] == {"status": "open", "q": "flaky"}


def test_associate_inline_item():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "a1", "item": {"id": "i1"}})

    _client(handler).associate("p1", item={"source": "note", "title": "n", "fetch": False})
    assert seen["path"] == "/api/tasks/p1/items"
    assert seen["body"]["item"] == {"source": "note", "title": "n", "fetch": False}


def test_delete_returns_none_on_204():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    assert _client(handler).delete_task("p1") is None


def test_error_raises_with_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Task not found"})

    with pytest.raises(ApiError) as excinfo:
        _client(handler).get_task("missing")
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Task not found"
