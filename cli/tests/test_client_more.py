"""Coverage for the remaining HTTP client methods and error handling."""

import json

import httpx
import pytest

from agentic_cli.client import AgenticClient, ApiError, _compact


def _client(handler) -> AgenticClient:
    return AgenticClient("http://test.local", transport=httpx.MockTransport(handler))


def test_compact_drops_none():
    assert _compact({"a": 1, "b": None, "c": ""}) == {"a": 1, "c": ""}


def test_context_manager_round_trip():
    def handler(request):
        return httpx.Response(200, json={"status": "ok"})

    with AgenticClient("http://test.local", transport=httpx.MockTransport(handler)) as client:
        assert client.health() == {"status": "ok"}


def test_read_methods_hit_expected_paths():
    seen: list = []

    def handler(request):
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={})

    client = _client(handler)
    client.get_item("i1")
    client.list_items()
    client.list_repositories()
    client.get_context("t1")
    client.get_settings()
    client.get_run("r1")
    client.run_events("r1")
    client.list_runs("t1")
    client.list_worktrees("t1")
    client.list_harnesses()
    client.list_harnesses(full=True)
    client.refresh_item("i1")
    client.refresh_context("t1")
    client.cancel_run("r1")

    assert ("GET", "/api/items/i1") in seen
    assert ("GET", "/api/harnesses/full") in seen
    assert ("POST", "/api/items/i1/refresh") in seen
    assert ("POST", "/api/tasks/t1/context/refresh") in seen
    assert ("POST", "/api/runs/r1/cancel") in seen


def test_delete_methods_return_none_on_204():
    def handler(request):
        assert request.method == "DELETE"
        return httpx.Response(204)

    client = _client(handler)
    assert client.delete_task("t1") is None
    assert client.delete_item("i1") is None
    assert client.remove_repository("r1") is None
    assert client.delete_harness("h1") is None
    assert client.remove_worktree("t1", "w1") is None
    assert client.unassociate("t1", "i1") is None


def test_write_methods_send_compacted_bodies():
    seen: dict = {}

    def handler(request):
        seen[(request.method, request.url.path)] = json.loads(request.content) if request.content else None
        return httpx.Response(200, json={})

    client = _client(handler)
    client.update_task("t1", title="T", priority=None)
    client.create_item(url="u", fetch=False)
    client.update_item("i1", title="T")
    client.add_repository("/p", name=None)
    client.create_harness(name="n", command="c")
    client.update_harness("h1", name="n2")
    client.create_worktree("t1", repository_id=None, branch="b")
    client.create_run("t1", "prompt", harness_id=None)
    client.update_settings(openchamber_url="x")
    client.associate("t1", item_id="i1")

    assert seen[("PATCH", "/api/tasks/t1")] == {"title": "T"}
    assert seen[("POST", "/api/items")] == {"url": "u", "fetch": False}
    assert seen[("POST", "/api/tasks/t1/runs")] == {"prompt": "prompt"}
    assert seen[("PATCH", "/api/settings")] == {"openchamber_url": "x"}
    assert seen[("POST", "/api/tasks/t1/items")] == {"note": "", "item_id": "i1"}


def test_request_falls_back_to_text_for_non_json():
    def handler(request):
        return httpx.Response(200, text="plain text")

    assert _client(handler).health() == "plain text"


def test_error_with_plain_text_detail():
    def handler(request):
        return httpx.Response(500, text="server exploded")

    with pytest.raises(ApiError) as excinfo:
        _client(handler).health()
    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "server exploded"


def test_stream_run_parses_data_lines():
    body = 'event: message\ndata: {"seq": 1, "type": "message"}\n\ndata: {"type": "run_finished"}\n'

    def handler(request):
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    events = list(_client(handler).stream_run("r1"))
    assert events[0]["seq"] == 1
    assert events[-1]["type"] == "run_finished"
