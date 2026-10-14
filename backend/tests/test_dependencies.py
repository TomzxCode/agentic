from fastapi.testclient import TestClient

from agentic.main import app


def _task(client: TestClient, title: str) -> str:
    return client.post("/api/tasks", json={"title": title}).json()["id"]


def test_link_before_and_after_are_symmetric():
    with TestClient(app) as client:
        a = _task(client, "Design the schema")
        b = _task(client, "Write the migration")

        # B comes after A.
        deps = client.post(f"/api/tasks/{a}/dependencies", json={"related_id": b, "relation": "after"}).json()
        assert [t["id"] for t in deps["after"]] == [b]
        assert deps["before"] == []

        # Read from the other side: A comes before B.
        other = client.get(f"/api/tasks/{b}/dependencies").json()
        assert [t["id"] for t in other["before"]] == [a]
        assert other["after"] == []

        client.delete(f"/api/tasks/{a}")
        client.delete(f"/api/tasks/{b}")


def test_link_before_relation():
    with TestClient(app) as client:
        a = _task(client, "First")
        b = _task(client, "Second")

        deps = client.post(f"/api/tasks/{b}/dependencies", json={"related_id": a, "relation": "before"}).json()
        assert [t["id"] for t in deps["before"]] == [a]

        client.delete(f"/api/tasks/{a}")
        client.delete(f"/api/tasks/{b}")


def test_duplicate_link_is_idempotent():
    with TestClient(app) as client:
        a = _task(client, "A")
        b = _task(client, "B")
        body = {"related_id": b, "relation": "after"}

        client.post(f"/api/tasks/{a}/dependencies", json=body)
        client.post(f"/api/tasks/{a}/dependencies", json=body)

        assert len(client.get(f"/api/tasks/{a}/dependencies").json()["after"]) == 1

        client.delete(f"/api/tasks/{a}")
        client.delete(f"/api/tasks/{b}")


def test_self_link_is_rejected():
    with TestClient(app) as client:
        a = _task(client, "Only one")
        res = client.post(f"/api/tasks/{a}/dependencies", json={"related_id": a, "relation": "after"})
        assert res.status_code == 400
        client.delete(f"/api/tasks/{a}")


def test_cycle_is_rejected():
    with TestClient(app) as client:
        a = _task(client, "A")
        b = _task(client, "B")
        c = _task(client, "C")

        client.post(f"/api/tasks/{a}/dependencies", json={"related_id": b, "relation": "after"})
        client.post(f"/api/tasks/{b}/dependencies", json={"related_id": c, "relation": "after"})

        # Closing the loop A -> C would make a cycle.
        res = client.post(f"/api/tasks/{c}/dependencies", json={"related_id": a, "relation": "after"})
        assert res.status_code == 400
        assert "cycle" in res.json()["detail"]

        # The two-step relation still holds and nothing was written.
        assert [t["id"] for t in client.get(f"/api/tasks/{a}/dependencies").json()["after"]] == [b]

        for task in (a, b, c):
            client.delete(f"/api/tasks/{task}")


def test_remove_dependency_from_either_side():
    with TestClient(app) as client:
        a = _task(client, "A")
        b = _task(client, "B")
        client.post(f"/api/tasks/{a}/dependencies", json={"related_id": b, "relation": "after"})

        # Removing from B's side drops the same edge.
        assert client.delete(f"/api/tasks/{b}/dependencies/{a}").status_code == 204
        assert client.get(f"/api/tasks/{a}/dependencies").json()["after"] == []

        # A second removal finds nothing.
        assert client.delete(f"/api/tasks/{b}/dependencies/{a}").status_code == 404

        client.delete(f"/api/tasks/{a}")
        client.delete(f"/api/tasks/{b}")


def test_dependency_records_timeline_on_both_tasks():
    with TestClient(app) as client:
        a = _task(client, "A")
        b = _task(client, "B")
        client.post(f"/api/tasks/{a}/dependencies", json={"related_id": b, "relation": "after"})

        a_events = client.get(f"/api/tasks/{a}/timeline").json()
        b_events = client.get(f"/api/tasks/{b}/timeline").json()
        assert any(e["type"] == "dependency_added" for e in a_events)
        assert any(e["type"] == "dependency_added" for e in b_events)

        client.delete(f"/api/tasks/{a}")
        client.delete(f"/api/tasks/{b}")


def test_deleting_a_task_drops_its_links():
    with TestClient(app) as client:
        a = _task(client, "A")
        b = _task(client, "B")
        client.post(f"/api/tasks/{a}/dependencies", json={"related_id": b, "relation": "after"})

        client.delete(f"/api/tasks/{a}")
        # B survives, with no dangling before link.
        assert client.get(f"/api/tasks/{b}/dependencies").json()["before"] == []
        client.delete(f"/api/tasks/{b}")


def test_graph_returns_nodes_and_edges():
    with TestClient(app) as client:
        a = _task(client, "Graph A")
        b = _task(client, "Graph B")
        client.post(f"/api/tasks/{a}/dependencies", json={"related_id": b, "relation": "after"})

        graph = client.get("/api/graph").json()
        ids = {node["id"] for node in graph["nodes"]}
        assert {a, b} <= ids
        assert {"before_id": a, "after_id": b} in graph["edges"]

        client.delete(f"/api/tasks/{a}")
        client.delete(f"/api/tasks/{b}")


def test_graph_hides_done_and_their_edges():
    with TestClient(app) as client:
        a = _task(client, "Active")
        b = _task(client, "Finished")
        client.post(f"/api/tasks/{a}/dependencies", json={"related_id": b, "relation": "after"})
        client.patch(f"/api/tasks/{b}", json={"status": "done"})

        graph = client.get("/api/graph").json()
        ids = {node["id"] for node in graph["nodes"]}
        assert a in ids
        assert b not in ids
        # The edge to the hidden task is gone too, so nothing dangles.
        assert all(edge["after_id"] != b for edge in graph["edges"])

        client.delete(f"/api/tasks/{a}")
        client.delete(f"/api/tasks/{b}")
