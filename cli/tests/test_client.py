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
        seen["params"] = httpx.QueryParams(request.url.query).multi_items()
        return httpx.Response(200, json=[])

    _client(handler).list_tasks(status="open", q="flaky", tags=["bug", "ui"])
    assert seen["params"] == [("status", "open"), ("q", "flaky"), ("tag", "bug"), ("tag", "ui")]


def test_list_tags():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json=[{"name": "bug", "count": 2}])

    tags = _client(handler).list_tags()
    assert seen["path"] == "/api/tags"
    assert tags == [{"name": "bug", "count": 2}]


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


def test_change_methods():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content) if request.content else None
        seen["params"] = httpx.QueryParams(request.url.query).multi_items()
        return httpx.Response(200, json={"id": "c1"})

    client = _client(handler)
    client.list_changes(task_id="t1", status="accepted")
    assert seen["path"] == "/api/changes"
    assert seen["params"] == [("task_id", "t1"), ("status", "accepted")]

    client.create_change(task_id="t1", title="T", change_class="bugfix", repository_id=None)
    assert seen["path"] == "/api/changes" and seen["body"] == {"task_id": "t1", "title": "T", "change_class": "bugfix"}

    client.transition_change("c1", "accepted")
    assert seen["path"] == "/api/changes/c1/status" and seen["body"] == {"status": "accepted"}

    client.add_intervention("c1", kind="correction", note="n")
    assert seen["path"] == "/api/changes/c1/interventions"
    assert seen["body"] == {"kind": "correction", "note": "n"}


def test_metrics_methods():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content) if request.content else None
        seen["params"] = httpx.QueryParams(request.url.query).multi_items()
        return httpx.Response(200, json={})

    client = _client(handler)
    client.get_metrics(window_days=30, observation_days=0, task_id="t1")
    assert seen["path"] == "/api/metrics"
    assert ("window_days", "30") in seen["params"]
    assert ("observation_days", "0") in seen["params"]
    assert ("task_id", "t1") in seen["params"]

    client.set_baseline("yield", 0.2, note="before")
    assert seen["method"] == "PUT" and seen["path"] == "/api/metrics/baselines/yield"
    assert seen["body"] == {"value": 0.2, "note": "before"}
