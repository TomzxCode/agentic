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
        assert person["aliases"] == ["ada"] and person["name"] == "ada"

        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/people/{person['id']}")


def test_associating_an_item_links_its_people_to_the_task(monkeypatch):
    _stub_fetch(monkeypatch, [{"name": "ada", "handle": "ada", "source": "github"}])
    with TestClient(app) as client:
        item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/2", "fetch": True}).json()
        task = _task(client)
        client.post(f"/api/tasks/{task}/items", json={"item_id": item["id"]})

        detail = client.get(f"/api/tasks/{task}").json()
        assert [person["aliases"] for person in detail["people"]] == [["ada"]]
        assert "person_added" in [event["type"] for event in detail["timeline"]]

        client.delete(f"/api/tasks/{task}")
        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/people/{item['person_ids'][0]}")


def test_upsert_matches_an_existing_person_by_alias(monkeypatch):
    """A fetched person whose alias already belongs to someone joins them."""
    with TestClient(app) as client:
        existing = client.post("/api/people", json={"name": "Ada", "aliases": ["ada@example.com"]}).json()
        _stub_fetch(monkeypatch, [{"name": "Ada L", "email": "ada@example.com", "source": "github"}])
        item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/9", "fetch": True}).json()

        assert item["person_ids"] == [existing["id"]]
        detail = client.get(f"/api/people/{existing['id']}").json()
        assert "ada@example.com" in detail["aliases"]

        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/people/{existing['id']}")


def test_associating_a_github_item_fetches_its_people(monkeypatch):
    """An item stored without a fetch still names its author when linked."""
    from agentic.routers import tasks as tasks_router

    monkeypatch.setattr(
        tasks_router,
        "fetch_source",
        lambda *args, **kwargs: {
            "metadata": {},
            "content": "",
            "title": "T",
            "people": [{"name": "bob", "handle": "bob", "source": "github"}],
        },
    )
    with TestClient(app) as client:
        item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/4", "fetch": False}).json()
        assert item["person_ids"] == []

        task = _task(client)
        client.post(f"/api/tasks/{task}/items", json={"item_id": item["id"]})

        detail = client.get(f"/api/tasks/{task}").json()
        assert [person["aliases"] for person in detail["people"]] == [["bob"]]

        person_id = detail["people"][0]["id"]
        client.delete(f"/api/tasks/{task}")
        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/people/{person_id}")


def test_task_detail_suggests_item_people_not_linked(monkeypatch):
    """People an item names but the task does not link are offered as suggestions."""
    _stub_fetch(monkeypatch, [{"name": "ada", "handle": "ada", "source": "github"}])
    with TestClient(app) as client:
        item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/5", "fetch": True}).json()
        person_id = item["person_ids"][0]
        task = _task(client)
        client.post(f"/api/tasks/{task}/items", json={"item_id": item["id"]})
        # Drop the auto-linked person to stand in for a task linked before the
        # items brought their people.
        client.delete(f"/api/tasks/{task}/people/{person_id}")

        detail = client.get(f"/api/tasks/{task}").json()
        assert detail["people"] == []
        assert [person["id"] for person in detail["suggested_people"]] == [person_id]

        # Linking the suggestion clears it.
        client.post(f"/api/tasks/{task}/people", json={"person_id": person_id})
        detail = client.get(f"/api/tasks/{task}").json()
        assert detail["suggested_people"] == []
        assert [person["id"] for person in detail["people"]] == [person_id]

        client.delete(f"/api/tasks/{task}")
        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/people/{person_id}")


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
