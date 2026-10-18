"""Fetched people: extraction, auto-linking, and suggestions."""

import json

from _people_helpers import _stub_fetch, _task
from fastapi.testclient import TestClient

from agentic.main import app
from agentic.services import github, shell, slack


def test_github_people_extraction_dedupes_by_login():
    data = {
        "author": {"login": "a"},
        "assignees": [{"login": "b"}, {"login": "a"}],
        "comments": [{"author": {"login": "a"}}, {"author": {"login": "c"}}],
    }
    assert [person["handle"] for person in github.github_people(data)] == ["a", "b", "c"]


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
    people = slack.slack_people(payload, {"U1": "Ada Lovelace"})
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
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)
    issue = github.fetch_github_issue("o", "r", 7)
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
    from agentic.routers import task_service as tasks_router

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
