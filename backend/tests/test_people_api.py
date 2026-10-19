"""People directory: create/update/delete, aliases, and merge."""

from _people_helpers import _item, _person, _task
from fastapi.testclient import TestClient

from agentic.main import app
from agentic.services import slack


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
        updated = client.patch(f"/api/people/{person}", json={"aliases": ["ada", "ada@example.com"]}).json()
        assert updated["aliases"] == ["ada", "ada@example.com"]
        assert client.patch(f"/api/people/{person}", json={"name": ""}).status_code == 400
        client.delete(f"/api/people/{person}")


def test_a_person_carries_many_aliases():
    with TestClient(app) as client:
        person = client.post(
            "/api/people",
            json={"name": "Ada", "aliases": ["ada", "ada@example.com", "U123", "ada"]},
        ).json()
        # Blank and duplicate aliases are dropped on the way in.
        assert person["aliases"] == ["ada", "ada@example.com", "U123"]

        updated = client.patch(
            f"/api/people/{person['id']}", json={"aliases": ["ada", "a.lovelace@example.com"]}
        ).json()
        assert updated["aliases"] == ["ada", "a.lovelace@example.com"]

        client.delete(f"/api/people/{person['id']}")


def test_merge_moves_aliases_and_links_and_deletes_the_source():
    with TestClient(app) as client:
        target = client.post("/api/people", json={"name": "Ada Lovelace", "aliases": ["ada"]}).json()["id"]
        source = client.post("/api/people", json={"name": "ada", "aliases": ["ada-l", "U1"]}).json()["id"]
        shared = _task(client, "Shared")
        source_only = _task(client, "Source only")
        item = _item(client)

        # Both people are on one task; the source also holds a task and an item alone.
        client.post(f"/api/tasks/{shared}/people", json={"person_id": target})
        client.post(f"/api/tasks/{shared}/people", json={"person_id": source})
        client.post(f"/api/tasks/{source_only}/people", json={"person_id": source})
        client.post(f"/api/items/{item}/people", json={"person_id": source})

        merged = client.post(f"/api/people/{target}/merge", json={"source_id": source})
        assert merged.status_code == 200
        body = merged.json()
        assert body["id"] == target and body["name"] == "Ada Lovelace"
        # The target keeps its own alias and gains the source's, without duplicating.
        assert set(body["aliases"]) == {"ada", "ada-l", "U1"}
        assert body["task_count"] == 2 and body["item_count"] == 1

        assert client.get(f"/api/people/{source}").status_code == 404

        # The shared task keeps exactly one link, to the survivor.
        shared_detail = client.get(f"/api/tasks/{shared}").json()
        assert [person["id"] for person in shared_detail["people"]] == [target]
        # The source-only task now links the survivor and recorded the gain.
        source_detail = client.get(f"/api/tasks/{source_only}").json()
        assert [person["id"] for person in source_detail["people"]] == [target]
        assert "person_added" in [event["type"] for event in source_detail["timeline"]]
        # The item link moved too.
        assert client.get(f"/api/items/{item}").json()["person_ids"] == [target]

        for task_id in (shared, source_only):
            client.delete(f"/api/tasks/{task_id}")
        client.delete(f"/api/items/{item}")
        client.delete(f"/api/people/{target}")


def test_merge_into_self_is_rejected():
    with TestClient(app) as client:
        person = _person(client)
        assert client.post(f"/api/people/{person}/merge", json={"source_id": person}).status_code == 400
        client.delete(f"/api/people/{person}")


def test_merge_unknown_ids_return_404():
    with TestClient(app) as client:
        person = _person(client)
        assert client.post(f"/api/people/{person}/merge", json={"source_id": "missing"}).status_code == 404
        assert client.post("/api/people/missing/merge", json={"source_id": person}).status_code == 404
        client.delete(f"/api/people/{person}")


def test_merge_moves_requester_links():
    with TestClient(app) as client:
        target = client.post("/api/people", json={"name": "Ada Lovelace"}).json()["id"]
        source = client.post("/api/people", json={"name": "ada"}).json()["id"]
        shared = _task(client, "Shared")
        source_only = _task(client, "Source only")

        client.post(f"/api/tasks/{shared}/requesters", json={"person_id": target})
        client.post(f"/api/tasks/{shared}/requesters", json={"person_id": source})
        client.post(f"/api/tasks/{source_only}/requesters", json={"person_id": source})

        client.post(f"/api/people/{target}/merge", json={"source_id": source})

        shared_detail = client.get(f"/api/tasks/{shared}").json()
        assert [p["id"] for p in shared_detail["requesters"]] == [target]
        source_detail = client.get(f"/api/tasks/{source_only}").json()
        assert [p["id"] for p in source_detail["requesters"]] == [target]
        assert "requester_added" in [event["type"] for event in source_detail["timeline"]]

        for task_id in (shared, source_only):
            client.delete(f"/api/tasks/{task_id}")
        client.delete(f"/api/people/{target}")


def test_slack_user_id_aliases_are_named_through_slackx(monkeypatch):
    monkeypatch.setattr(slack, "slack_user_names", lambda: {"U0123ABCDEF": "Ada Lovelace"})
    with TestClient(app) as client:
        person = client.post("/api/people", json={"name": "Ada", "aliases": ["ada", "U0123ABCDEF"]}).json()
        # Only the alias that looks like a Slack user id is resolved; a plain
        # handle is not sent to slackx.
        assert client.get("/api/people/slack-aliases").json() == {"names": {"U0123ABCDEF": "Ada Lovelace"}}
        client.delete(f"/api/people/{person['id']}")


def test_slack_alias_lookup_survives_an_unavailable_slackx(monkeypatch):
    monkeypatch.setattr(slack, "slack_user_names", lambda: {})
    with TestClient(app) as client:
        person = client.post("/api/people", json={"name": "Ada", "aliases": ["U0123ABCDEF"]}).json()
        assert client.get("/api/people/slack-aliases").json() == {"names": {}}
        client.delete(f"/api/people/{person['id']}")
