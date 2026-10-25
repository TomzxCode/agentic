"""Execution graphs: definitions, validation, templates, CRUD, and the executor."""

import asyncio
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from agentic import graphs
from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.models.agents import AgentEvent, AgentRun
from agentic.models.base import RunStatus, utcnow
from agentic.models.graphs import ExecutionGraph, GraphExecution
from agentic.models.tasks import Task

# The executor polls at 1 Hz; a fast tick keeps the tests quick.
POLL = 0.01


def _clear() -> None:
    from agentic.models.tasks import TimelineEvent

    with Session(engine) as session:
        session.exec(sa_delete(AgentEvent))
        session.exec(sa_delete(AgentRun))
        session.exec(sa_delete(GraphExecution))
        session.exec(sa_delete(ExecutionGraph))
        session.exec(sa_delete(TimelineEvent))
        session.exec(sa_delete(Task))
        session.commit()


def _harness() -> str:
    from agentic.models.agents import Harness

    with Session(engine) as session:
        harness = session.exec(select(Harness)).first()
        if harness is not None:
            return harness.id
        harness = Harness(name="test", command="true", is_default=True)
        session.add(harness)
        session.commit()
        session.refresh(harness)
        return harness.id


def run_node(node_id: str, prompt: str, inputs: list[str] | None = None, **extra) -> dict:
    return {
        "id": node_id,
        "kind": "run",
        "title": node_id,
        "position": {"x": 0, "y": 0},
        "promptTemplate": prompt,
        # The input's id doubles as its name, so tests can wire edges by name.
        "inputs": [{"id": name, "name": name} for name in inputs or []],
        **extra,
    }


def form_node(node_id: str, fields: list[dict], **extra) -> dict:
    return {
        "id": node_id,
        "kind": "form",
        "title": node_id,
        "position": {"x": 0, "y": 0},
        "fields": fields,
        **extra,
    }


def field(field_id: str, title: str, type_: str = "text", **extra) -> dict:
    return {"id": field_id, "title": title, "type": type_, **extra}


def edge(source: str, target: str, *, source_field: str = "", target_input: str = "", target_field: str = "") -> dict:
    return {
        "id": f"edge-{source}-{target}-{target_input or target_field}",
        "source": source,
        "sourceFieldId": source_field,
        "target": target,
        "targetInputId": target_input,
        "targetFieldId": target_field,
    }


def _definition(nodes: list[dict], edges: list[dict]) -> dict:
    return {"nodes": nodes, "edges": edges}


def _make_graph(definition: dict, **fields) -> str:
    create_db_and_tables()
    fields.setdefault("name", "graph")
    with Session(engine) as session:
        graph = ExecutionGraph(definition=definition, **fields)
        session.add(graph)
        session.commit()
        session.refresh(graph)
        return graph.id


def _wait_for(predicate, timeout: float = 10.0, message: str = "condition never held"):
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError(message)


async def _await_for(predicate, timeout: float = 10.0, message: str = "condition never held"):
    """``_wait_for`` for async tests: sleeping must not block the executor's loop."""
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(0.02)
    raise AssertionError(message)


def _execution(execution_id: str) -> GraphExecution:
    with Session(engine) as session:
        execution = session.get(GraphExecution, execution_id)
        assert execution is not None
        session.expunge(execution)
        return execution


def _running_run() -> AgentRun | None:
    with Session(engine) as session:
        run = session.exec(
            select(AgentRun).where(col(AgentRun.kind) == "graph").order_by(col(AgentRun.created_at).desc())
        ).first()
        if run is not None:
            session.expunge(run)
        return run


def _settle_run(run_id: str, output: str) -> None:
    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        run.status = RunStatus.succeeded
        run.ended_at = utcnow()
        session.add(run)
        session.add(AgentEvent(run_id=run_id, seq=0, type="message", text=output))
        session.commit()


def _no_enqueue(monkeypatch) -> None:
    async def fake_enqueue(run_id: str) -> None:
        return None

    monkeypatch.setattr("agentic.jobs.enqueue_run", fake_enqueue)


# --- pure helpers ----------------------------------------------------------
def test_normalize_definition_drops_garbage():
    raw = {
        "nodes": [
            {"id": "a", "kind": "run", "title": "A", "promptTemplate": "hi", "bogus": 1},
            {"id": "b", "kind": "wat"},
            "not-a-node",
            {
                "id": "c",
                "kind": "form",
                "title": "C",
                "fields": [
                    {"id": "f1", "title": "Pick", "type": "select", "options": ["x", "", 3]},
                    {"id": "f2", "title": "Scale", "type": "slider", "min": "0", "max": "5", "step": "1"},
                    {"id": "f3", "title": "Weird", "type": "quantum"},
                ],
            },
        ],
        "edges": [{"id": "e1", "source": "a", "target": "b", "junk": True}],
    }
    definition = graphs.normalize_definition(raw)
    kinds = {node["id"]: node["kind"] for node in definition["nodes"]}
    assert kinds == {"a": "run", "c": "form"}
    select_field = definition["nodes"][1]["fields"][0]
    assert select_field["options"] == ["x", "3"]
    slider = definition["nodes"][1]["fields"][1]
    assert slider["min"] == 0.0 and slider["max"] == 5.0
    assert len(definition["nodes"][1]["fields"]) == 2
    edge = definition["edges"][0]
    assert edge == {
        "id": "e1",
        "source": "a",
        "sourceFieldId": "",
        "target": "b",
        "targetInputId": "",
        "targetFieldId": "",
    }


def test_validate_definition_reports_problems():
    issues = graphs.validate_definition(
        _definition(
            [
                run_node("a", ""),  # no prompt
                run_node("b", "{{nope}}", ["other"]),  # unknown placeholder
                run_node("b", "dup"),  # duplicate id
                form_node("f", [field("f1", "Pick", "select")]),  # select without options
                form_node("g", []),  # no fields
            ],
            [
                edge("a", "b", target_input="missing"),  # no such input
                edge("a", "missing"),  # dangling target
                {"id": "e", "source": "f", "sourceFieldId": "wat", "target": "g", "targetFieldId": "f1"},
            ],
        )
    )
    joined = "\n".join(issues)
    assert "needs a prompt" in joined
    assert "no input named 'nope'" in joined
    assert "Duplicate node id 'b'" in joined
    assert "needs options" in joined
    assert "needs at least one field" in joined
    assert "no input for one incoming connection" in joined
    assert "missing node" in joined
    assert "no field for one connection" in joined

    cycle = graphs.validate_definition(
        _definition(
            [run_node("a", "x"), run_node("b", "y", ["v"])],
            [edge("a", "b", target_input="v"), edge("b", "a")],
        )
    )
    assert any("circular" in issue for issue in cycle)

    # A placeholder nothing feeds would fail at render time; catch it here.
    unconnected = graphs.validate_definition(_definition([run_node("a", "hi {{topic}}", ["topic"])], []))
    assert unconnected == ["'a' uses {{topic}} but nothing feeds the input 'topic'"]


def test_topological_order_and_cycles():
    nodes = [run_node("a", "x"), run_node("b", "y", ["v"]), run_node("c", "z")]
    edges = [edge("a", "b", target_input="v"), edge("a", "c")]
    assert graphs.topological_order(nodes, edges) == ["a", "b", "c"]
    cycle = edges + [edge("b", "a")]
    assert graphs.topological_order(nodes, cycle) is None


def test_render_template():
    render = graphs.render_template
    assert render("Hello {{name}}", {"name": ["x"]}) == ("Hello x", [])
    assert render("{{name}}", {"name": ["a", "b"]}) == ("a\nb", [])
    assert render("{{name[1]}}", {"name": ["a", "b"]}) == ("b", [])
    assert render('{{name.join(", ")}}', {"name": ["a", "b"]}) == ("a, b", [])
    text, errors = render("{{missing}} and {{name[5]}}", {"name": ["a"]})
    assert text == "{{missing}} and {{name[5]}}"
    assert errors == ["Unknown input 'missing'", "Input 'name' has 1 value(s), asked for [5]"]


# --- CRUD and validation over the API ---------------------------------------
def test_graph_crud_api():
    create_db_and_tables()
    _clear()
    definition = _definition(
        [run_node("a", "Do things"), run_node("b", "Then {{draft}}", ["draft"])],
        [edge("a", "b", target_input="draft")],
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/graphs",
            json={"name": "pipeline", "description": "two steps", "schedule": "*/5 * * * *", "definition": definition},
        )
        assert created.status_code == 201
        graph = created.json()
        assert graph["next_run_at"] is not None
        assert graph["definition"]["nodes"][0]["promptTemplate"] == "Do things"

        # An empty definition is fine at create time (that is the "new graph"
        # flow: create a shell, then build it in the editor), but running one
        # fails with the reasons.
        created_empty = client.post("/api/graphs", json={"name": "shell", "definition": _definition([], [])})
        assert created_empty.status_code == 201
        refused = client.post(f"/api/graphs/{created_empty.json()['id']}/run")
        assert refused.status_code == 400
        assert "at least one node" in refused.json()["detail"]
        client.delete(f"/api/graphs/{created_empty.json()['id']}")

        # A definition with problems can be stored (work in progress) and is
        # still reported by validate and by run.
        broken = _definition(
            [run_node("a", "x"), run_node("b", "{{v}}", ["v"])],
            [edge("a", "b", target_input="v"), edge("b", "a")],
        )
        stored = client.post("/api/graphs", json={"name": "wip", "definition": broken})
        assert stored.status_code == 201
        wip_id = stored.json()["id"]
        assert client.post(f"/api/graphs/{wip_id}/run").status_code == 400
        checked = client.post("/api/graphs/validate", json={"name": "wip", "definition": broken})
        assert any("circular" in issue for issue in checked.json()["issues"])
        client.delete(f"/api/graphs/{wip_id}")

        # Blank names and bad schedules are still rejected.
        assert client.post("/api/graphs", json={"name": " ", "definition": definition}).status_code == 400
        bad_cron = client.post("/api/graphs", json={"name": "bad-cron", "schedule": "nope", "definition": definition})
        assert bad_cron.status_code == 400

        # The editor's validate action reports issues without saving.
        checked = client.post("/api/graphs/validate", json={"name": "v", "definition": _definition([], [])})
        assert checked.status_code == 200
        assert checked.json()["issues"]

        listing = client.get("/api/graphs")
        assert [row["id"] for row in listing.json()] == [graph["id"]]

        # Disabling clears the next occurrence; renaming keeps everything else.
        updated = client.patch(f"/api/graphs/{graph['id']}", json={"enabled": False, "name": "renamed"}).json()
        assert updated["enabled"] is False
        assert updated["next_run_at"] is None
        assert updated["name"] == "renamed"

        assert client.get(f"/api/graphs/{graph['id']}").status_code == 200
        assert client.delete(f"/api/graphs/{graph['id']}").status_code == 204
        assert client.get("/api/graphs").json() == []
    _clear()


# --- the executor -----------------------------------------------------------
def test_two_node_graph_renders_downstream_prompt(monkeypatch):
    create_db_and_tables()
    _clear()
    _harness()
    _no_enqueue(monkeypatch)
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    definition = _definition(
        [run_node("a", "First"), run_node("b", "Second: {{draft}}", ["draft"])],
        [edge("a", "b", target_input="draft")],
    )
    # The view's flow: create a shell, save the definition from the editor,
    # then run.
    graph_id = _make_graph(_definition([], []), name="chain")
    with TestClient(app) as client:
        assert client.patch(f"/api/graphs/{graph_id}", json={"definition": definition}).status_code == 200
        started = client.post(f"/api/graphs/{graph_id}/run")
        assert started.status_code == 201
        execution_id = started.json()["id"]

        # The execution created a task that groups the runs.
        first = _wait_for(_running_run, message="first run never started")
        with Session(engine) as session:
            task = session.get(Task, first.task_id)
            assert task is not None and task.title == "[Graph] chain"
            assert first.prompt == "First"
            assert first.graph_execution_id == execution_id

        _settle_run(first.id, "DRAFT TEXT")
        second = _wait_for(
            lambda: (run := _running_run()) and run.id != first.id and run,
            message="second run never started",
        )
        assert second.prompt == "Second: DRAFT TEXT"

        _settle_run(second.id, "done")
        row = _wait_for(
            lambda: _execution(execution_id).status.value == "succeeded" and _execution(execution_id),
            message="execution never succeeded",
        )
        assert row.error == ""
        with Session(engine) as session:
            state = session.get(GraphExecution, execution_id).state
        assert state["outputs"]["a"] == "DRAFT TEXT"

        # The execution detail reports every node, with outputs.
        detail = client.get(f"/api/graphs/executions/{execution_id}").json()
        assert detail["status"] == "succeeded"
        assert [node["status"] for node in detail["nodes"]] == ["done", "done"]
        assert detail["nodes"][0]["output"] == "DRAFT TEXT"
        assert client.get("/api/graphs/executions").json()[0]["id"] == execution_id
    _clear()


def test_form_flow_pauses_and_answers(monkeypatch):
    create_db_and_tables()
    _clear()
    _harness()
    _no_enqueue(monkeypatch)
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    definition = _definition(
        [
            run_node("a", "Prepare"),
            form_node("f", [field("f1", "Approve?", "select", options=["yes", "no"], required=True)]),
            run_node("b", "Verdict: {{approve}}", ["approve"]),
        ],
        [edge("f", "b", source_field="f1", target_input="approve")],
    )
    graph_id = _make_graph(definition, name="gated")
    with TestClient(app) as client:
        execution_id = client.post(f"/api/graphs/{graph_id}/run").json()["id"]

        first = _wait_for(_running_run, message="first run never started")
        _settle_run(first.id, "prepared")

        pending = _wait_for(
            lambda: client.get(f"/api/graphs/executions/{execution_id}").json()["pending_form"] or None,
            message="form never became pending",
        )
        assert pending["node_id"] == "f"
        assert pending["title"] == "f"
        # The select's default fills the dialog (empty here), and its fields travel
        # with the request so the UI can render them.
        assert pending["defaults"] == {"f1": ""}
        assert [item["id"] for item in pending["fields"]] == ["f1"]

        answered = client.post(f"/api/graphs/executions/{execution_id}/forms/f", json={"values": {"f1": "yes"}})
        assert answered.status_code == 200

        second = _wait_for(
            lambda: (run := _running_run()) and run.id != first.id and run,
            message="second run never started",
        )
        assert second.prompt == "Verdict: yes"
        _settle_run(second.id, "ok")
        row = _wait_for(
            lambda: _execution(execution_id).status.value == "succeeded" and _execution(execution_id),
            message="execution never succeeded",
        )
        assert row.state["formValues"]["f"] == {"f1": "yes"}
    _clear()


def test_form_cancel_fails_downstream(monkeypatch):
    create_db_and_tables()
    _clear()
    _harness()
    _no_enqueue(monkeypatch)
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    definition = _definition(
        [
            run_node("a", "Prepare"),
            form_node("f", [field("f1", "Approve?", "select", options=["yes", "no"])]),
            run_node("b", "Verdict: {{approve}}", ["approve"]),
        ],
        [edge("f", "b", source_field="f1", target_input="approve")],
    )
    graph_id = _make_graph(definition, name="gated-cancel")
    with TestClient(app) as client:
        execution_id = client.post(f"/api/graphs/{graph_id}/run").json()["id"]
        first = _wait_for(_running_run, message="first run never started")
        _settle_run(first.id, "prepared")
        _wait_for(
            lambda: client.get(f"/api/graphs/executions/{execution_id}").json()["pending_form"],
            message="form never became pending",
        )
        assert client.post(f"/api/graphs/executions/{execution_id}/forms/f", json={"cancel": True}).status_code == 200
        row = _wait_for(
            lambda: _execution(execution_id).status.value == "failed" and _execution(execution_id),
            message="execution never failed",
        )
        statuses = {node_id: entry["status"] for node_id, entry in row.state["nodes"].items()}
        assert statuses == {"a": "done", "f": "failed", "b": "skipped"}
    _clear()


def test_unused_form_is_skipped_and_duplicate_run_conflicts(monkeypatch):
    create_db_and_tables()
    _clear()
    _harness()
    _no_enqueue(monkeypatch)
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    definition = _definition(
        [run_node("a", "Only"), form_node("f", [field("f1", "Who?")])],
        [],
    )
    graph_id = _make_graph(definition, name="lonely-form")
    with TestClient(app) as client:
        execution_id = client.post(f"/api/graphs/{graph_id}/run").json()["id"]
        # A second run while the first is in flight is rejected.
        conflict = client.post(f"/api/graphs/{graph_id}/run")
        assert conflict.status_code == 409

        only = _wait_for(_running_run, message="run never started")
        _settle_run(only.id, "done")
        row = _wait_for(
            lambda: _execution(execution_id).status.value == "succeeded" and _execution(execution_id),
            message="execution never succeeded",
        )
        statuses = {node_id: entry["status"] for node_id, entry in row.state["nodes"].items()}
        assert statuses == {"a": "done", "f": "skipped"}

        assert client.post(f"/api/graphs/executions/{execution_id}/forms/f", json={"values": {}}).status_code == 409

        # A graph whose definition no longer validates refuses to run.
        with Session(engine) as session:
            graph = session.get(ExecutionGraph, graph_id)
            graph.definition = _definition([], [])
            session.add(graph)
            session.commit()
        assert client.post(f"/api/graphs/{graph_id}/run").status_code == 400

        assert client.post(f"/api/graphs/executions/{execution_id}/cancel").status_code == 409
    _clear()


def test_cancel_execution_aborts(monkeypatch):
    create_db_and_tables()
    _clear()
    _harness()
    _no_enqueue(monkeypatch)
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    definition = _definition([run_node("a", "Working")], [])
    graph_id = _make_graph(definition, name="cancellable")
    with TestClient(app) as client:
        execution_id = client.post(f"/api/graphs/{graph_id}/run").json()["id"]
        _wait_for(_running_run, message="run never started")
        cancelled = client.post(f"/api/graphs/executions/{execution_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        row = _wait_for(
            lambda: _execution(execution_id).status.value == "cancelled" and _execution(execution_id),
            message="execution never cancelled",
        )
        statuses = {node_id: entry["status"] for node_id, entry in row.state["nodes"].items()}
        assert statuses == {"a": "skipped"}
    _clear()


# --- cron scheduling and reconciliation --------------------------------------
@pytest.mark.asyncio
async def test_scheduler_fires_due_graph_once(monkeypatch):
    create_db_and_tables()
    _clear()
    _harness()
    _no_enqueue(monkeypatch)
    monkeypatch.setattr(graphs, "POLL_SECONDS", POLL)
    definition = _definition([run_node("a", "Tick")], [])
    graph_id = _make_graph(definition, name="scheduled", schedule="* * * * *", enabled=True)
    with Session(engine) as session:
        graph = session.get(ExecutionGraph, graph_id)
        graph.next_run_at = utcnow() - timedelta(minutes=1)
        session.add(graph)
        session.commit()

    assert await graphs.run_due_once() == 1
    # The occurrence advanced, so a second tick does not fire again.
    with Session(engine) as session:
        graph = session.get(ExecutionGraph, graph_id)
        assert graph.next_run_at > utcnow()
        execution = session.exec(select(GraphExecution)).first()
        assert execution is not None and execution.trigger == "schedule"
    assert await graphs.run_due_once() == 0  # the busy execution suppresses a second fire

    run = await _await_for(_running_run, message="scheduled run never started")
    _settle_run(run.id, "done")
    execution_id = run.graph_execution_id
    await _await_for(
        lambda: _execution(execution_id).status.value == "succeeded",
        message="execution never succeeded",
    )
    _clear()


def test_reconcile_marks_stale_executions_failed():
    create_db_and_tables()
    _clear()
    with Session(engine) as session:
        graph = ExecutionGraph(name="stale", definition=_definition([run_node("a", "x")], []))
        task = Task(title="stale task")
        session.add(graph)
        session.add(task)
        session.flush()
        execution = GraphExecution(graph_id=graph.id, task_id=task.id, state={})
        session.add(execution)
        session.commit()
        session.refresh(execution)
        execution_id = execution.id
    assert graphs.reconcile_graph_executions() == 1
    row = _execution(execution_id)
    assert row.status.value == "failed"
    assert "restart" in row.error
    assert row.ended_at is not None
    assert graphs.reconcile_graph_executions() == 0
    _clear()
