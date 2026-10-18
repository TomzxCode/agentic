from fastapi.testclient import TestClient

from agentic import provenance
from agentic.agents.runner import harness_env
from agentic.main import app
from agentic.models.agents import Harness
from agentic.models.base import OperationActor, OperationClient


def test_resolve_maps_declared_values_and_falls_back():
    assert provenance.resolve("web", "agent") == (OperationClient.web, OperationActor.agent)
    assert provenance.resolve(" CLI ", "HUMAN") == (OperationClient.cli, OperationActor.human)
    # Missing or unknown values fall back to the raw API and a human.
    assert provenance.resolve(None, None) == (OperationClient.api, OperationActor.human)
    assert provenance.resolve("desktop", "robot") == (OperationClient.api, OperationActor.human)


def test_using_sets_and_restores_the_context():
    assert provenance.current() == (OperationClient.api, OperationActor.human)
    with provenance.using(OperationClient.cli, OperationActor.agent):
        assert provenance.current() == (OperationClient.cli, OperationActor.agent)
    assert provenance.current() == (OperationClient.api, OperationActor.human)


def test_harness_env_marks_the_process_as_an_agent():
    env = harness_env(Harness(name="opencode", command="opencode", env={"FOO": "bar"}))
    assert env == {"FOO": "bar", "AGENTIC_ACTOR": "agent"}
    assert harness_env(Harness(name="opencode", command="opencode"))["AGENTIC_ACTOR"] == "agent"


def test_declared_provenance_reaches_the_timeline_and_the_audit_log():
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Provenance"},
            headers={"X-Agentic-Client": "cli", "X-Agentic-Actor": "agent"},
        )
        task_id = created.json()["id"]
        client.patch(
            f"/api/tasks/{task_id}",
            json={"status": "in_progress"},
            headers={"X-Agentic-Client": "web", "X-Agentic-Actor": "human"},
        )

        timeline = client.get(f"/api/tasks/{task_id}/timeline").json()
        by_type = {event["type"]: event for event in timeline}
        assert (by_type["created"]["client"], by_type["created"]["actor"]) == ("cli", "agent")
        assert (by_type["updated"]["client"], by_type["updated"]["actor"]) == ("web", "human")

        agent_ops = client.get("/api/operations", params={"actor": "agent", "limit": 500}).json()
        assert any(op["method"] == "POST" and op["path"] == "/api/tasks" and op["client"] == "cli" for op in agent_ops)

        web_ops = client.get("/api/operations", params={"client": "web", "limit": 500}).json()
        assert any(op["method"] == "PATCH" and op["path"] == f"/api/tasks/{task_id}" for op in web_ops)

        client.delete(f"/api/tasks/{task_id}")


def test_undeclared_provenance_defaults_to_api_and_human():
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "Defaults"}).json()["id"]
        timeline = client.get(f"/api/tasks/{task_id}/timeline").json()
        assert all(event["client"] == "api" and event["actor"] == "human" for event in timeline)
        client.delete(f"/api/tasks/{task_id}")


def test_reads_are_not_recorded_as_operations():
    with TestClient(app) as client:
        client.get("/api/tasks")
        before = client.get("/api/operations", params={"limit": 500}).json()
        client.get("/api/tasks")
        client.get("/api/operations", params={"limit": 500})
        after = client.get("/api/operations", params={"limit": 500}).json()
        # The only new entries would come from a GET, which is never recorded.
        assert len(after) == len(before)
