"""Task and item links to people."""

from _people_helpers import _item, _person, _task
from fastapi.testclient import TestClient

from agentic.main import app


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
