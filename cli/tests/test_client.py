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


def test_people_methods():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(200, json={"id": "p1", "name": "Ada"})

    client = _client(handler)
    assert client.list_people() == {"id": "p1", "name": "Ada"}
    assert seen["path"] == "/api/people"

    client.create_person(name="Ada", aliases=["ada"])
    assert seen["method"] == "POST" and seen["body"] == {"name": "Ada", "aliases": ["ada"]}

    client.link_person("p1", task_id="t1")
    assert seen["path"] == "/api/tasks/t1/people" and seen["body"] == {"person_id": "p1"}

    client.link_person("p1", item_id="i1")
    assert seen["path"] == "/api/items/i1/people"

    client.unlink_person("p1", task_id="t1")
    assert seen["method"] == "DELETE" and seen["path"] == "/api/tasks/t1/people/p1"

    client.unlink_person("p1", item_id="i1")
    assert seen["path"] == "/api/items/i1/people/p1"

    client.link_requester("p1", "t1")
    assert seen["method"] == "POST" and seen["path"] == "/api/tasks/t1/requesters"
    assert seen["body"] == {"person_id": "p1"}

    client.unlink_requester("p1", "t1")
    assert seen["method"] == "DELETE" and seen["path"] == "/api/tasks/t1/requesters/p1"

    client.merge_person("p1", "p2")
    assert seen["method"] == "POST" and seen["path"] == "/api/people/p2/merge"
    assert seen["body"] == {"source_id": "p1"}


def test_provenance_headers_default_to_cli_and_human(monkeypatch):
    monkeypatch.delenv("AGENTIC_ACTOR", raising=False)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["client"] = request.headers.get("X-Agentic-Client")
        seen["actor"] = request.headers.get("X-Agentic-Actor")
        return httpx.Response(200, json={"status": "ok"})

    _client(handler).health()
    assert seen == {"client": "cli", "actor": "human"}


def test_actor_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("AGENTIC_ACTOR", "agent")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["actor"] = request.headers.get("X-Agentic-Actor")
        return httpx.Response(200, json={"status": "ok"})

    _client(handler).health()
    assert seen["actor"] == "agent"


def test_list_operations_passes_filters():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = httpx.QueryParams(request.url.query).multi_items()
        return httpx.Response(200, json=[])

    _client(handler).list_operations(client="cli", actor="agent", limit=5)
    assert seen["path"] == "/api/operations"
    assert seen["params"] == [("client", "cli"), ("actor", "agent"), ("limit", "5")]


def test_dependency_methods():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content) if request.content else None
        seen["params"] = httpx.QueryParams(request.url.query).multi_items()
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"task_id": "t1", "before": [], "after": []})

    client = _client(handler)
    client.task_dependencies("t1")
    assert seen["path"] == "/api/tasks/t1/dependencies"

    client.add_dependency("t1", "t2", "before")
    assert seen["method"] == "POST" and seen["path"] == "/api/tasks/t1/dependencies"
    assert seen["body"] == {"related_id": "t2", "relation": "before"}

    assert client.remove_dependency("t1", "t2") is None
    assert seen["method"] == "DELETE" and seen["path"] == "/api/tasks/t1/dependencies/t2"

    client.get_graph()
    assert seen["path"] == "/api/graph" and seen["params"] == []
    client.get_graph(include_done=True)
    assert seen["params"] == [("include_done", "true")]


def test_session_methods():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content) if request.content else None
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"id": "s1", "session_id": "ses_1"})

    client = _client(handler)
    client.list_sessions("t1")
    assert seen["path"] == "/api/tasks/t1/sessions"

    client.get_session("t1", "s1")
    assert seen["path"] == "/api/tasks/t1/sessions/s1"

    client.create_session("t1", "ses_1", cwd=None, label="first")
    assert seen["method"] == "POST" and seen["path"] == "/api/tasks/t1/sessions"
    assert seen["body"] == {"session_id": "ses_1", "label": "first"}

    client.update_session("t1", "s1", label="renamed", cwd=None)
    assert seen["method"] == "PATCH" and seen["path"] == "/api/tasks/t1/sessions/s1"
    assert seen["body"] == {"label": "renamed"}

    assert client.delete_session("t1", "s1") is None
    assert seen["method"] == "DELETE" and seen["path"] == "/api/tasks/t1/sessions/s1"


def test_stack_methods():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content) if request.content else None
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json=[])

    client = _client(handler)
    client.list_stack()
    assert seen["path"] == "/api/stack"

    client.stack_history()
    assert seen["path"] == "/api/stack/history"

    client.stack_current()
    assert seen["path"] == "/api/stack/current"

    # task_id=None is dropped so the API creates a new task from the title.
    client.push_stack(title="T", description="", position="next", task_id=None)
    assert seen["method"] == "POST" and seen["path"] == "/api/stack"
    assert seen["body"] == {"title": "T", "description": "", "position": "next"}

    client.pop_stack()
    assert seen["path"] == "/api/stack/pop"

    client.reorder_stack("s1", 2)
    assert seen["path"] == "/api/stack/reorder" and seen["body"] == {"entry_id": "s1", "position": 2}

    client.promote_stack("s1")
    assert seen["path"] == "/api/stack/s1/promote"

    client.update_stack_entry("s1", title="T2", description=None)
    assert seen["method"] == "PATCH" and seen["path"] == "/api/stack/s1" and seen["body"] == {"title": "T2"}

    assert client.remove_stack_entry("s1") is None
    assert seen["method"] == "DELETE" and seen["path"] == "/api/stack/s1"
