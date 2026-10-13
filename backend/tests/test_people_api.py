"""People endpoints: directory CRUD, task and item links, events, and cascades."""

import json

from fastapi.testclient import TestClient

from agentic import services
from agentic.main import app


def _task(client: TestClient, title: str = "Task") -> str:
    return client.post("/api/tasks", json={"title": title}).json()["id"]


def _item(client: TestClient, title: str = "Item") -> str:
    return client.post("/api/items", json={"title": title, "content": "x", "fetch": False}).json()["id"]


def _person(client: TestClient, name: str = "Ada Lovelace") -> str:
    return client.post("/api/people", json={"name": name}).json()["id"]


def test_create_and_list_people_with_counts():
    with TestClient(app) as client:
        person = _person(client)
        empty = _person(client, "Grace Hopper")
        task = _task(client)
        item = _item(client)

        assert client.post(f"/api/tasks/{task}/people", json={"person_id": person}).status_code == 201
        assert client.post(f"/api/items/{item}/people", json={"person_id": person}).status_code == 201

        people = {p["id"]: p for p in client.get("/api/people").json()}
        assert people[person]["task_count"] == 1
        assert people[person]["item_count"] == 1
        assert people[empty]["task_count"] == 0 and people[empty]["item_count"] == 0

        client.delete(f"/api/people/{person}")
        client.delete(f"/api/people/{empty}")
        client.delete(f"/api/tasks/{task}")
        client.delete(f"/api/items/{item}")


def test_name_is_required():
    with TestClient(app) as client:
        assert client.post("/api/people", json={"name": "   "}).status_code == 400


def test_update_person_fields_and_reject_blank_name():
    with TestClient(app) as client:
        person = _person(client)
        updated = client.patch(f"/api/people/{person}", json={"handle": "ada", "email": "ada@example.com"}).json()
        assert updated["handle"] == "ada" and updated["email"] == "ada@example.com"
        assert client.patch(f"/api/people/{person}", json={"name": ""}).status_code == 400
        client.delete(f"/api/people/{person}")


def test_linking_a_person_is_idempotent():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        assert client.post(f"/api/tasks/{task}/people", json={"person_id": person}).status_code == 201
        again = client.post(f"/api/tasks/{task}/people", json={"person_id": person})
        assert again.status_code == 201

        detail = client.get(f"/api/tasks/{task}").json()
        assert [p["id"] for p in detail["people"]] == [person]

        # Only the first link writes a timeline event.
        types = [event["type"] for event in detail["timeline"]]
        assert types.count("person_added") == 1

        client.delete(f"/api/people/{person}")
        client.delete(f"/api/tasks/{task}")


def test_link_creates_a_new_person_from_a_name():
    with TestClient(app) as client:
        task = _task(client)
        person = client.post(f"/api/tasks/{task}/people", json={"name": "Alan Turing"}).json()
        assert person["name"] == "Alan Turing"
        detail = client.get(f"/api/tasks/{task}").json()
        assert [p["id"] for p in detail["people"]] == [person["id"]]

        client.delete(f"/api/tasks/{task}")
        client.delete(f"/api/people/{person['id']}")


def test_unlink_records_a_timeline_event_and_removes_the_link():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        client.post(f"/api/tasks/{task}/people", json={"person_id": person})
        assert client.delete(f"/api/tasks/{task}/people/{person}").status_code == 204

        detail = client.get(f"/api/tasks/{task}").json()
        assert detail["people"] == []
        assert "person_removed" in [event["type"] for event in detail["timeline"]]

        client.delete(f"/api/people/{person}")
        client.delete(f"/api/tasks/{task}")


def test_task_people_are_exposed_on_the_task_list():
    """The task list carries linked person ids, so a client can filter by person."""
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        client.post(f"/api/tasks/{task}/people", json={"person_id": person})

        listed = {t["id"]: t for t in client.get("/api/tasks").json()}
        assert listed[task]["person_ids"] == [person]

        assert client.delete(f"/api/tasks/{task}/people/{person}").status_code == 204
        listed = {t["id"]: t for t in client.get("/api/tasks").json()}
        assert listed[task]["person_ids"] == []

        client.delete(f"/api/people/{person}")
        client.delete(f"/api/tasks/{task}")


def test_item_people_are_exposed_on_the_item():
    with TestClient(app) as client:
        person = _person(client)
        item = _item(client)
        client.post(f"/api/items/{item}/people", json={"person_id": person})

        assert client.get(f"/api/items/{item}").json()["person_ids"] == [person]
        assert client.delete(f"/api/items/{item}/people/{person}").status_code == 204
        assert client.get(f"/api/items/{item}").json()["person_ids"] == []

        client.delete(f"/api/people/{person}")
        client.delete(f"/api/items/{item}")


def test_deleting_a_person_detaches_it_everywhere():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        item = _item(client)
        client.post(f"/api/tasks/{task}/people", json={"person_id": person})
        client.post(f"/api/items/{item}/people", json={"person_id": person})

        assert client.delete(f"/api/people/{person}").status_code == 204
        assert client.get(f"/api/people/{person}").status_code == 404
        assert client.get(f"/api/tasks/{task}").json()["people"] == []
        assert client.get(f"/api/items/{item}").json()["person_ids"] == []

        client.delete(f"/api/tasks/{task}")
        client.delete(f"/api/items/{item}")


def test_deleting_a_task_keeps_the_person():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        client.post(f"/api/tasks/{task}/people", json={"person_id": person})

        client.delete(f"/api/tasks/{task}")
        remaining = {p["id"]: p for p in client.get("/api/people").json()}
        assert remaining[person]["task_count"] == 0

        client.delete(f"/api/people/{person}")


def test_link_unknown_ids_return_404():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        assert client.post("/api/tasks/missing/people", json={"person_id": person}).status_code == 404
        assert client.post(f"/api/tasks/{task}/people", json={"person_id": "missing"}).status_code == 404
        assert client.post(f"/api/items/{task}/people", json={"person_id": person}).status_code == 404
        assert client.post(f"/api/tasks/{task}/people", json={}).status_code == 400

        client.delete(f"/api/people/{person}")
        client.delete(f"/api/tasks/{task}")


def _stub_fetch(monkeypatch, people):
    from agentic.routers import items as items_router

    monkeypatch.setattr(
        items_router,
        "fetch_source",
        lambda *args, **kwargs: {"metadata": {}, "content": "body", "title": "T", "people": people},
    )


def test_github_people_extraction_dedupes_by_login():
    data = {
        "author": {"login": "a"},
        "assignees": [{"login": "b"}, {"login": "a"}],
        "comments": [{"author": {"login": "a"}}, {"author": {"login": "c"}}],
    }
    assert [person["handle"] for person in services.github_people(data)] == ["a", "b", "c"]


def test_slack_people_extraction_uses_resolved_names_and_handles():
    payload = json.dumps(
        {
            "messages": [
                {"user": "U1", "user_name": "Ada (ada)"},
                {"user": "U2", "user_name": "Bob (bob)"},
                {"user": "U1", "user_name": "Ada (ada)"},
            ]
        }
    )
    people = services.slack_people(payload, {"U1": "Ada Lovelace"})
    assert people == [
        {"name": "Ada Lovelace", "handle": "U1", "source": "slack"},
        {"name": "Bob", "handle": "bob", "source": "slack"},
    ]


def test_fetch_github_issue_includes_people(monkeypatch):
    payload = json.dumps(
        {
            "number": 7,
            "title": "Bug",
            "author": {"login": "a"},
            "assignees": [{"login": "b"}],
            "comments": [{"author": {"login": "c"}}],
        }
    )
    monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: payload)
    issue = services.fetch_github_issue("o", "r", 7)
    assert issue is not None
    assert [person["handle"] for person in issue["people"]] == ["a", "b", "c"]


def test_item_fetch_auto_populates_people(monkeypatch):
    _stub_fetch(
        monkeypatch,
        [
            {"name": "ada", "handle": "ada", "source": "github"},
            {"name": "ada", "handle": "ada", "source": "github"},
        ],
    )
    with TestClient(app) as client:
        item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/1", "fetch": True}).json()
        assert len(item["person_ids"]) == 1
        person = client.get(f"/api/people/{item['person_ids'][0]}").json()
        assert person["handle"] == "ada" and person["name"] == "ada"

        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/people/{person['id']}")


def test_associating_an_item_links_its_people_to_the_task(monkeypatch):
    _stub_fetch(monkeypatch, [{"name": "ada", "handle": "ada", "source": "github"}])
    with TestClient(app) as client:
        item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/2", "fetch": True}).json()
        task = _task(client)
        client.post(f"/api/tasks/{task}/items", json={"item_id": item["id"]})

        detail = client.get(f"/api/tasks/{task}").json()
        assert [person["handle"] for person in detail["people"]] == ["ada"]
        assert "person_added" in [event["type"] for event in detail["timeline"]]

        client.delete(f"/api/tasks/{task}")
        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/people/{item['person_ids'][0]}")
