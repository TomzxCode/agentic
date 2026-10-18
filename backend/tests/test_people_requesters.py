"""Task requesters, a link set distinct from the people involved."""

from _people_helpers import _person, _task
from fastapi.testclient import TestClient

from agentic.main import app


def test_task_requesters_are_separate_from_the_people_involved():
    """Requesting a task and being involved in it are distinct link sets."""
    with TestClient(app) as client:
        requester = _person(client, "Requester")
        involved = _person(client, "Involved")
        task = _task(client)

        assert client.post(f"/api/tasks/{task}/requesters", json={"person_id": requester}).status_code == 201
        client.post(f"/api/tasks/{task}/people", json={"person_id": involved})

        detail = client.get(f"/api/tasks/{task}").json()
        assert [p["id"] for p in detail["requesters"]] == [requester]
        assert [p["id"] for p in detail["people"]] == [involved]
        assert detail["requester_ids"] == [requester]

        # Unlinking the requester leaves the involved person untouched.
        assert client.delete(f"/api/tasks/{task}/requesters/{requester}").status_code == 204
        detail = client.get(f"/api/tasks/{task}").json()
        assert detail["requesters"] == []
        assert [p["id"] for p in detail["people"]] == [involved]
        assert "requester_added" in [event["type"] for event in detail["timeline"]]
        assert "requester_removed" in [event["type"] for event in detail["timeline"]]

        client.delete(f"/api/tasks/{task}")
        client.delete(f"/api/people/{requester}")
        client.delete(f"/api/people/{involved}")


def test_linking_a_requester_is_idempotent_and_creates_a_person_by_name():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        assert client.post(f"/api/tasks/{task}/requesters", json={"person_id": person}).status_code == 201
        assert client.post(f"/api/tasks/{task}/requesters", json={"person_id": person}).status_code == 201

        detail = client.get(f"/api/tasks/{task}").json()
        assert [p["id"] for p in detail["requesters"]] == [person]
        assert [event["type"] for event in detail["timeline"]].count("requester_added") == 1

        named = client.post(f"/api/tasks/{task}/requesters", json={"name": "Grace Hopper"}).json()
        assert named["name"] == "Grace Hopper"

        client.delete(f"/api/tasks/{task}")
        client.delete(f"/api/people/{person}")
        client.delete(f"/api/people/{named['id']}")


def test_a_requester_counts_as_a_task_for_the_person():
    """A person who only requested a task still shows it on their page."""
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        client.post(f"/api/tasks/{task}/requesters", json={"person_id": person})

        listed = {p["id"]: p for p in client.get("/api/people").json()}
        assert listed[person]["task_count"] == 1
        detail = client.get(f"/api/people/{person}").json()
        assert detail["task_ids"] == [task]
        assert detail["involved_task_ids"] == []
        assert detail["requester_task_ids"] == [task]

        client.delete(f"/api/tasks/{task}")
        listed = {p["id"]: p for p in client.get("/api/people").json()}
        assert listed[person]["task_count"] == 0
        client.delete(f"/api/people/{person}")


def test_person_detail_splits_involved_and_requested_tasks():
    """The person page can tell a task they are a person on from one they asked for."""
    with TestClient(app) as client:
        person = _person(client)
        involved = _task(client, "Involved")
        requested = _task(client, "Requested")
        both = _task(client, "Both")
        client.post(f"/api/tasks/{involved}/people", json={"person_id": person})
        client.post(f"/api/tasks/{requested}/requesters", json={"person_id": person})
        client.post(f"/api/tasks/{both}/people", json={"person_id": person})
        client.post(f"/api/tasks/{both}/requesters", json={"person_id": person})

        detail = client.get(f"/api/people/{person}").json()
        assert set(detail["task_ids"]) == {involved, requested, both}
        assert set(detail["involved_task_ids"]) == {involved, both}
        assert set(detail["requester_task_ids"]) == {requested, both}
        assert detail["task_count"] == 3

        for task_id in (involved, requested, both):
            client.delete(f"/api/tasks/{task_id}")
        client.delete(f"/api/people/{person}")


def test_deleting_a_person_detaches_it_as_a_requester():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        client.post(f"/api/tasks/{task}/requesters", json={"person_id": person})

        assert client.delete(f"/api/people/{person}").status_code == 204
        assert client.get(f"/api/tasks/{task}").json()["requesters"] == []

        client.delete(f"/api/tasks/{task}")
