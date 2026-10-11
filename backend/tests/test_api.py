from fastapi.testclient import TestClient

from agentic.main import app


def test_task_lifecycle():
    with TestClient(app) as client:
        created = client.post("/api/tasks", json={"title": "Investigate flakiness", "priority": 2})
        assert created.status_code == 201
        task_id = created.json()["id"]

        listed = client.get("/api/tasks").json()
        assert any(p["id"] == task_id for p in listed)

        associated = client.post(
            f"/api/tasks/{task_id}/items",
            json={"item": {"source": "note", "title": "A note", "content": "hello", "fetch": False}},
        )
        assert associated.status_code == 201

        detail = client.get(f"/api/tasks/{task_id}").json()
        assert len(detail["associations"]) == 1
        assert detail["associations"][0]["item"]["title"] == "A note"
        assert detail["timeline"]

        updated = client.patch(f"/api/tasks/{task_id}", json={"status": "in_progress"})
        assert updated.json()["status"] == "in_progress"

        assert client.delete(f"/api/tasks/{task_id}").status_code == 204
        assert client.get(f"/api/tasks/{task_id}").status_code == 404


def test_timeline_records_before_and_after():
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "T", "priority": 1}).json()["id"]

        client.patch(f"/api/tasks/{task_id}", json={"title": "T2", "priority": 3})
        updated = [e for e in client.get(f"/api/tasks/{task_id}/timeline").json() if e["type"] == "updated"]
        assert len(updated) == 1
        changes = updated[0]["data_json"]["changes"]
        assert changes["title"] == {"from": "T", "to": "T2"}
        assert changes["priority"] == {"from": 1, "to": 3}

        # A no-op update records nothing.
        client.patch(f"/api/tasks/{task_id}", json={"title": "T2"})
        updated = [e for e in client.get(f"/api/tasks/{task_id}/timeline").json() if e["type"] == "updated"]
        assert len(updated) == 1

        client.delete(f"/api/tasks/{task_id}")


def test_timeline_labels_relationships(tmp_path):
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()

        task_id = client.post("/api/tasks", json={"title": "T"}).json()["id"]
        client.patch(f"/api/tasks/{task_id}", json={"repository_ids": [repo["id"]]})

        event = next(e for e in client.get(f"/api/tasks/{task_id}/timeline").json() if e["type"] == "updated")
        assert event["message"] == "Updated: repositories"
        change = event["data_json"]["changes"]["repositories"]
        assert change["to"] == [repo["id"]]
        assert change["to_label"] == repo["name"]  # resolved name, not just an id

        # removing it again is also recorded
        client.patch(f"/api/tasks/{task_id}", json={"repository_ids": []})
        detail = client.get(f"/api/tasks/{task_id}").json()
        assert detail["repository_ids"] == []

        client.delete(f"/api/tasks/{task_id}")
        client.delete(f"/api/repositories/{repo['id']}")


def test_task_repositories_many_to_many(tmp_path):
    with TestClient(app) as client:
        repos = []
        for name in ("alpha", "beta"):
            path = tmp_path / name
            (path / ".git").mkdir(parents=True)
            repos.append(client.post("/api/repositories", json={"path": str(path)}).json())

        task = client.post("/api/tasks", json={"title": "T", "repository_ids": [repos[0]["id"], repos[1]["id"]]}).json()
        assert sorted(task["repository_ids"]) == sorted([repos[0]["id"], repos[1]["id"]])
        # unknown ids are ignored
        updated = client.patch(f"/api/tasks/{task['id']}", json={"repository_ids": [repos[0]["id"], "nope"]}).json()
        assert updated["repository_ids"] == [repos[0]["id"]]

        client.delete(f"/api/tasks/{task['id']}")
        for repo in repos:
            client.delete(f"/api/repositories/{repo['id']}")


def test_item_source_is_inferred():
    with TestClient(app) as client:
        item = client.post(
            "/api/items", json={"url": "https://github.com/psf/requests/issues/1", "fetch": False}
        ).json()
        assert item["source"] == "github"
        assert item["kind"] == "issue"
        assert item["external_id"] == "psf/requests#1"

        note = client.post("/api/items", json={"content": "just a note", "fetch": False}).json()
        assert note["source"] == "note"

        # Plain text pasted into the URL field is stored as a note, not a url.
        plain = client.post("/api/items", json={"url": "User doesn't know what they want."}).json()
        assert plain["source"] == "note"
        assert plain["url"] is None
        assert plain["content"] == "User doesn't know what they want."
        assert plain["title"] == "User doesn't know what they want."

        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/items/{note['id']}")
        client.delete(f"/api/items/{plain['id']}")


def test_harnesses_are_seeded():
    with TestClient(app) as client:
        harnesses = client.get("/api/harnesses").json()
        names = {h["name"] for h in harnesses}
        assert "OpenCode" in names
        assert "pi" in names


def test_health():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
