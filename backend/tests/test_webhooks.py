"""The event bus: trigger nodes, webhook ingestion, matching, and deliveries."""

import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlmodel import Session

from agentic import graphs
from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.models.agents import AgentEvent, AgentRun
from agentic.models.graphs import ExecutionGraph, GraphExecution
from agentic.models.tasks import Task, TimelineEvent
from agentic.models.webhooks import EventDelivery, EventSubscription, WebhookEndpoint, WebhookEvent

POLL = 0.01

# The command lines the fake CLI runner saw, across the tests that use it.
CLI_CALLS: list[list[str]] = []


def _clear() -> None:
    with Session(engine) as session:
        session.exec(sa_delete(EventDelivery))
        session.exec(sa_delete(WebhookEvent))
        session.exec(sa_delete(EventSubscription))
        session.exec(sa_delete(WebhookEndpoint))
        session.exec(sa_delete(AgentEvent))
        session.exec(sa_delete(AgentRun))
        session.exec(sa_delete(GraphExecution))
        session.exec(sa_delete(ExecutionGraph))
        session.exec(sa_delete(TimelineEvent))
        session.exec(sa_delete(Task))
        session.commit()


def _wait_for(predicate, timeout: float = 10.0, message: str = "condition never held"):
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError(message)


def trigger_node(outputs: list[dict], **extra) -> dict:
    return {
        "id": "t",
        "kind": "trigger",
        "title": "event",
        "position": {"x": 0, "y": 0},
        "outputs": outputs,
        **extra,
    }


def output(output_id: str, name: str, path: str) -> dict:
    return {"id": output_id, "name": name, "path": path}


def cli_node(command: str, inputs: list[str] | None = None) -> dict:
    return {
        "id": "c",
        "kind": "cli",
        "title": "command",
        "position": {"x": 0, "y": 0},
        "command": command,
        "inputs": [{"id": name, "name": name} for name in inputs or []],
    }


def edge(source: str, target: str, *, source_field: str = "", target_input: str = "") -> dict:
    return {
        "id": f"edge-{source}-{target}",
        "source": source,
        "sourceFieldId": source_field,
        "target": target,
        "targetInputId": target_input,
        "targetFieldId": "",
    }


def definition(nodes: list[dict], edges: list[dict] | None = None) -> dict:
    return {"nodes": nodes, "edges": edges or []}


def _execution(execution_id: str) -> GraphExecution:
    with Session(engine) as session:
        execution = session.get(GraphExecution, execution_id)
        assert execution is not None
        session.expunge(execution)
        return execution


def _make_graph(definition_: dict, **fields) -> str:
    create_db_and_tables()
    fields.setdefault("name", "workflow")
    with Session(engine) as session:
        graph = ExecutionGraph(definition=definition_, **fields)
        session.add(graph)
        session.commit()
        session.refresh(graph)
        return graph.id


def _endpoint(client: TestClient, **body) -> dict:
    body.setdefault("name", "endpoint")
    response = client.post("/api/webhooks/endpoints", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _subscribe(client: TestClient, endpoint_id: str, graph_id: str, **body) -> dict:
    body.setdefault("graph_id", graph_id)
    response = client.post(f"/api/webhooks/endpoints/{endpoint_id}/subscriptions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --- trigger nodes ---------------------------------------------------------
def test_trigger_node_loads_payload_paths():
    raw = trigger_node(
        [
            output("o1", "title", "pull_request.title"),
            output("o2", "author", "pull_request.user.login"),
            output("o3", "", ""),  # dropped: no path
        ]
    )
    normalized = graphs.normalize_definition(definition([raw]))
    node = normalized["nodes"][0]
    assert node["kind"] == "trigger"
    assert [item["id"] for item in node["outputs"]] == ["o1", "o2"]

    payload = {
        "pull_request": {"title": "Fix the bug", "user": {"login": "octocat"}, "labels": [{"name": "bug"}]},
        "number": 42,
        "draft": False,
    }
    assert graphs.resolve_event_path(payload, "pull_request.title") == "Fix the bug"
    assert graphs.resolve_event_path(payload, "pull_request.user.login") == "octocat"
    assert graphs.resolve_event_path(payload, "pull_request.labels[0].name") == "bug"
    assert graphs.resolve_event_path(payload, "number") == "42"
    assert graphs.resolve_event_path(payload, "draft") == "false"
    assert graphs.resolve_event_path(payload, "missing.path") == ""
    assert graphs.resolve_event_path(payload, "payload.pull_request.title") == "Fix the bug"
    # A whole object is exposed as JSON, so a step can print or forward it.
    assert json.loads(graphs.resolve_event_path(payload, "pull_request.user")) == {"login": "octocat"}
    # No event means every output is empty (a manual run still works).
    assert graphs.trigger_values(node, {}) == {"o1": "", "o2": ""}


def test_trigger_definition_validation():
    run = {
        "id": "a",
        "kind": "run",
        "title": "step",
        "position": {"x": 0, "y": 0},
        "promptTemplate": "Handle {{title}}",
        "inputs": [{"id": "title", "name": "title"}],
    }
    valid = definition(
        [trigger_node([output("o1", "title", "pull_request.title")]), run],
        [edge("t", "a", source_field="o1", target_input="title")],
    )
    assert graphs.validate_definition(graphs.normalize_definition(valid)) == []

    empty = graphs.validate_definition(definition([trigger_node([])]))
    assert any("needs at least one event field" in issue for issue in empty)

    twice = graphs.validate_definition(
        definition(
            [
                trigger_node([output("o1", "title", "title")]),
                trigger_node([output("o2", "title", "title")], id="t2", title="event 2"),
            ]
        )
    )
    assert any("at most one event trigger" in issue for issue in twice)

    incoming = graphs.validate_definition(
        definition(
            [trigger_node([output("o1", "title", "title")]), run],
            [edge("a", "t"), edge("t", "a", source_field="o1", target_input="title")],
        )
    )
    assert any("cannot take a connection" in issue for issue in incoming)


# --- generic webhooks ------------------------------------------------------
def test_generic_webhook_starts_a_matching_workflow(monkeypatch):
    create_db_and_tables()
    _clear()
    CLI_CALLS.clear()
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    monkeypatch.setattr(graphs, "_run_cli", _recording_cli())
    graph_id = _make_graph(
        definition(
            [
                trigger_node([output("o1", "title", "issue.title")]),
                cli_node('task create --title "{{title}}"', ["title"]),
            ],
            [edge("t", "c", source_field="o1", target_input="title")],
        ),
        name="on-issue",
    )

    with TestClient(app) as client:
        endpoint = _endpoint(client)
        _subscribe(
            client,
            endpoint["id"],
            graph_id,
            events=["issues"],
            filters=[{"path": "action", "equals": "opened"}],
        )

        matched = client.post(
            f"/api/hooks/{endpoint['id']}?event=issues",
            json={"action": "opened", "issue": {"title": "Fix the bug"}},
        )
        assert matched.status_code == 202, matched.text
        body = matched.json()
        assert body["event_type"] == "issues"
        assert [delivery["status"] for delivery in body["deliveries"]] == ["started"]
        execution_id = body["deliveries"][0]["graph_execution_id"]

        execution = _wait_for(
            lambda: _execution(execution_id).status.value == "succeeded" and _execution(execution_id),
            message="event-driven execution never succeeded",
        )
        assert execution.trigger == "event:issues"
        assert execution.state["trigger"]["payload"]["issue"]["title"] == "Fix the bug"
        assert execution.state["triggerValues"]["t"] == {"o1": "Fix the bug"}
        assert execution.state["outputs"]["c"] == "ok\n"
        assert any("Fix the bug" in " ".join(argv) for argv in CLI_CALLS)

        # A different action and a different event type match nothing.
        for query, payload in (("issues", {"action": "closed"}), ("push", {"action": "opened"})):
            skipped = client.post(f"/api/hooks/{endpoint['id']}?event={query}", json=payload)
            assert skipped.status_code == 202
            assert skipped.json()["deliveries"] == []

        events = client.get("/api/webhooks/events").json()
        assert len(events) == 3
        detail = client.get(f"/api/webhooks/events/{body['id']}").json()
        assert detail["deliveries"][0]["status"] == "started"
        assert detail["deliveries"][0]["graph_name"] == "on-issue"

        # Replaying a stored event starts the workflow again.
        replayed = client.post(f"/api/webhooks/events/{body['id']}/replay")
        assert replayed.status_code == 200
        assert [delivery["status"] for delivery in replayed.json()["deliveries"]] == ["started"]
        second_execution = replayed.json()["deliveries"][0]["graph_execution_id"]
        assert second_execution != execution_id
        _wait_for(
            lambda: _execution(second_execution).status.value == "succeeded",
            message="replayed execution never succeeded",
        )
    _clear()


def _recording_cli():
    async def fake_run_cli(argv, cwd, env):
        CLI_CALLS.append(argv)
        return 0, "ok\n"

    return fake_run_cli


def test_generic_secret_and_disabled_endpoint(monkeypatch):
    create_db_and_tables()
    _clear()
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    graph_id = _make_graph(definition([trigger_node([output("o1", "title", "title")])]), name="secret")
    with TestClient(app) as client:
        endpoint = _endpoint(client, secret="shared-token")
        _subscribe(client, endpoint["id"], graph_id)
        url = f"/api/hooks/{endpoint['id']}"

        assert client.post(url, json={"title": "x"}).status_code == 401
        assert client.post(url, json={"title": "x"}, headers={"X-Webhook-Secret": "wrong"}).status_code == 401
        accepted = client.post(url, json={"title": "x"}, headers={"X-Webhook-Secret": "shared-token"})
        assert accepted.status_code == 202
        assert (
            client.post(url, json={"title": "x"}, headers={"Authorization": "Bearer shared-token"}).status_code == 202
        )

        client.patch(f"/api/webhooks/endpoints/{endpoint['id']}", json={"enabled": False})
        assert client.post(url, json={"title": "x"}, headers={"X-Webhook-Secret": "shared-token"}).status_code == 403
    _clear()


def test_paused_workflow_skips_delivery(monkeypatch):
    create_db_and_tables()
    _clear()
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    graph_id = _make_graph(definition([trigger_node([output("o1", "title", "title")])]), name="paused", enabled=False)
    with TestClient(app) as client:
        endpoint = _endpoint(client)
        _subscribe(client, endpoint["id"], graph_id)
        response = client.post(f"/api/hooks/{endpoint['id']}", json={"title": "x"})
        assert response.status_code == 202
        delivery = response.json()["deliveries"][0]
        assert delivery["status"] == "skipped"
        assert "paused" in delivery["error"]
        assert delivery["graph_execution_id"] is None
    _clear()


# --- GitHub webhooks -------------------------------------------------------
def test_github_webhook_verifies_the_signature(monkeypatch):
    create_db_and_tables()
    _clear()
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    graph_id = _make_graph(definition([trigger_node([output("o1", "title", "pull_request.title")])]), name="pr")
    payload = {"action": "opened", "pull_request": {"title": "Fix"}}
    raw = json.dumps(payload).encode()
    secret = "s3cret"
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

    with TestClient(app) as client:
        endpoint = _endpoint(client, kind="github", secret=secret)
        _subscribe(client, endpoint["id"], graph_id, events=["pull_request"])
        url = f"/api/hooks/github/{endpoint['id']}"
        headers = {"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "abc-123"}

        assert (
            client.post(url, content=raw, headers={**headers, "X-Hub-Signature-256": "sha256=nope"}).status_code == 401
        )
        missing = client.post(url, content=raw, headers=headers)
        assert missing.status_code == 401

        accepted = client.post(url, content=raw, headers={**headers, "X-Hub-Signature-256": signature})
        assert accepted.status_code == 202, accepted.text
        body = accepted.json()
        assert body["event_type"] == "pull_request"
        assert [delivery["status"] for delivery in body["deliveries"]] == ["started"]

        stored = client.get(f"/api/webhooks/events/{body['id']}").json()
        assert stored["source"] == "github"
        assert stored["delivery_id"] == "abc-123"
        assert stored["payload"]["pull_request"]["title"] == "Fix"

        # A GitHub endpoint without a secret cannot verify anything.
        client.patch(f"/api/webhooks/endpoints/{endpoint['id']}", json={"secret": ""})
        assert client.post(url, content=raw, headers={**headers, "X-Hub-Signature-256": signature}).status_code == 400
    _clear()


# --- management API --------------------------------------------------------
def test_deleting_a_graph_removes_its_subscriptions():
    create_db_and_tables()
    _clear()
    graph_id = _make_graph(definition([trigger_node([output("o1", "title", "title")])]), name="doomed")
    with TestClient(app) as client:
        endpoint = _endpoint(client)
        _subscribe(client, endpoint["id"], graph_id)
        assert client.delete(f"/api/graphs/{graph_id}").status_code == 204
        assert client.get(f"/api/webhooks/endpoints/{endpoint['id']}/subscriptions").json() == []
        assert len(client.get("/api/webhooks/endpoints").json()) == 1
    _clear()


def test_webhook_endpoint_crud_and_delete_cascades():
    create_db_and_tables()
    _clear()
    graph_id = _make_graph(definition([trigger_node([output("o1", "title", "title")])]), name="kept")
    with TestClient(app) as client:
        endpoint = _endpoint(client, name="inbound", description="from a service")
        assert endpoint["subscription_count"] == 0
        subscription = _subscribe(client, endpoint["id"], graph_id, name="all", events=[])
        assert subscription["graph_name"] == "kept"

        listed = client.get("/api/webhooks/endpoints").json()
        assert listed[0]["id"] == endpoint["id"]
        assert listed[0]["subscription_count"] == 1

        # A matching event starts the workflow; wait for it to settle so the
        # next one does not collide with a still-running execution.
        first = client.post(f"/api/hooks/{endpoint['id']}", json={"hello": "world"})
        assert first.status_code == 202
        first_execution = first.json()["deliveries"][0]["graph_execution_id"]
        _wait_for(
            lambda: _execution(first_execution).status.value != "running",
            message="first execution never settled",
        )
        assert len(client.get("/api/webhooks/events").json()) == 1

        # The test route bypasses the secret and starts the workflow.
        tested = client.post(f"/api/webhooks/endpoints/{endpoint['id']}/test", json={"payload": {"a": 1}})
        assert tested.status_code == 200
        assert tested.json()["deliveries"][0]["status"] == "started"

        assert client.delete(f"/api/webhooks/subscriptions/{subscription['id']}").status_code == 204
        assert client.get(f"/api/webhooks/endpoints/{endpoint['id']}/subscriptions").json() == []

        assert client.delete(f"/api/webhooks/endpoints/{endpoint['id']}").status_code == 204
        assert client.get("/api/webhooks/endpoints").json() == []
        assert client.get("/api/webhooks/events").json() == []
        # The graph itself is untouched.
        assert client.get(f"/api/graphs/{graph_id}").status_code == 200
    _clear()
