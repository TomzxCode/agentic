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


def test_items_list_includes_task_links_and_search():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "Linkable"}).json()
        link = "https://github.com/psf/requests/issues/1"
        client.post(f"/api/tasks/{task['id']}/items", json={"item": {"url": link, "fetch": False}})

        items = client.get("/api/items").json()
        item = next(i for i in items if i["url"] == link)
        assert task["id"] in item["task_ids"]

        assert all(
            "requests" in (i["url"] or "") or "requests" in i["title"]
            for i in client.get("/api/items", params={"q": "requests"}).json()
        )
        assert client.get("/api/items", params={"source": "github"})

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/items/{item['id']}")


def test_tags_are_normalized_filtered_and_listed():
    with TestClient(app) as client:
        # Tags are trimmed, emptied out, and de-duplicated on the way in.
        first = client.post("/api/tasks", json={"title": "Tagged A", "tags": ["bug", " bug ", "", "ui"]}).json()
        assert first["tags"] == ["bug", "ui"]

        second = client.post("/api/tasks", json={"title": "Tagged B", "tags": ["bug"]}).json()
        third = client.post("/api/tasks", json={"title": "Tagged C", "tags": ["infra"]}).json()

        bug_tasks = client.get("/api/tasks", params={"tag": "bug"}).json()
        assert {t["id"] for t in bug_tasks} >= {first["id"], second["id"]}
        assert third["id"] not in {t["id"] for t in bug_tasks}

        # Several tags narrow the result: a task must carry all of them.
        both = client.get("/api/tasks", params=[("tag", "bug"), ("tag", "ui")]).json()
        assert {t["id"] for t in both} == {first["id"]}

        # The tag list is derived from the tasks and carries counts.
        tags = {t["name"]: t["count"] for t in client.get("/api/tags").json()}
        assert tags["bug"] >= 2
        assert tags["ui"] >= 1

        # Changing a task's tags is recorded on its timeline.
        client.patch(f"/api/tasks/{first['id']}", json={"tags": ["bug", "urgent"]})
        event = next(e for e in client.get(f"/api/tasks/{first['id']}/timeline").json() if e["type"] == "updated")
        assert event["data_json"]["changes"]["tags"]["to"] == ["bug", "urgent"]

        for task in (first, second, third):
            client.delete(f"/api/tasks/{task['id']}")


def test_bulk_update_tasks_changes_status_and_tags():
    with TestClient(app) as client:
        first = client.post("/api/tasks", json={"title": "Bulk A", "tags": ["bug"]}).json()
        second = client.post("/api/tasks", json={"title": "Bulk B", "tags": ["bug", "ui"]}).json()

        result = client.post(
            "/api/tasks/bulk",
            json={
                "ids": [first["id"], second["id"], "missing"],
                "status": "done",
                "add_tags": ["shipped", " ui "],
                "remove_tags": ["bug"],
            },
        )
        assert result.status_code == 200
        body = result.json()
        assert body["missing"] == ["missing"]
        assert {t["id"] for t in body["updated"]} == {first["id"], second["id"]}

        # Tags are added/removed, not replaced; the second task keeps "ui".
        assert client.get(f"/api/tasks/{first['id']}").json()["tags"] == ["shipped", "ui"]
        detail = client.get(f"/api/tasks/{second['id']}").json()
        assert detail["tags"] == ["ui", "shipped"]
        assert detail["status"] == "done"

        # Each task records its own timeline event.
        event = next(e for e in detail["timeline"] if e["type"] == "updated")
        assert set(event["data_json"]["changes"]) == {"status", "tags"}

        # A bulk edit with nothing to change is rejected.
        assert client.post("/api/tasks/bulk", json={"ids": [first["id"]]}).status_code == 400
        assert client.post("/api/tasks/bulk", json={"ids": [], "status": "done"}).status_code == 400

        for task in (first, second):
            client.delete(f"/api/tasks/{task['id']}")


def test_harnesses_are_seeded():
    with TestClient(app) as client:
        harnesses = client.get("/api/harnesses").json()
        names = {h["name"] for h in harnesses}
        assert "OpenCode" in names
        assert "pi" in names


def test_health():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
