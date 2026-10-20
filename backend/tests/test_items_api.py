"""Item endpoints: CRUD, upsert/dedupe, fetch, and task links."""

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.routers import items as items_router
from agentic.routers import items_refresh
from agentic.services import shell


def test_marking_a_slack_thread_done_flags_a_later_reply_without_reopening_it(monkeypatch):
    with TestClient(app) as client:
        item = client.post(
            "/api/items",
            json={
                "url": "https://acme.slack.com/archives/C6/p1700000000000000",
                "fetch": False,
                "metadata_json": {"latest_ts": "1700000000.000000"},
            },
        ).json()
        assert item["done"] is False and item["new_since_done"] is False

        marked = client.patch(f"/api/items/{item['id']}", json={"done": True}).json()
        assert marked["done"] is True and marked["done_at"] is not None
        assert marked["new_since_done"] is False

        # A fetch that sees a newer message flags it. The done state survives,
        # because the person has to choose to reopen the conversation.
        monkeypatch.setattr(
            items_router,
            "fetch_source",
            lambda *args, **kwargs: {
                "title": "acme - #general - 2023-11-14 22:13",
                "content": "ada: hello\nbob: a newer reply",
                "metadata": {"latest_ts": "1700000100.000000"},
            },
        )
        refreshed = client.post(f"/api/items/{item['id']}/refresh").json()
        assert refreshed["done"] is True
        assert refreshed["new_since_done"] is True
        assert refreshed["latest_message_at"] is not None

        reopened = client.patch(f"/api/items/{item['id']}", json={"done": False}).json()
        assert reopened["done"] is False and reopened["done_at"] is None
        assert reopened["new_since_done"] is False
        client.delete(f"/api/items/{item['id']}")


def test_a_thread_marked_done_before_its_first_fetch_takes_that_fetch_as_baseline(monkeypatch):
    with TestClient(app) as client:
        item = client.post(
            "/api/items",
            json={"url": "https://acme.slack.com/archives/C6/p1700000000000001", "fetch": False},
        ).json()
        assert client.patch(f"/api/items/{item['id']}", json={"done": True}).json()["done"] is True

        # The first fetch after the decision only records the watermark, so the
        # messages already in the thread are not reported as new.
        monkeypatch.setattr(
            items_router,
            "fetch_source",
            lambda *args, **kwargs: {
                "title": "t",
                "content": "ada: hello",
                "metadata": {"latest_ts": "1700000000.000000"},
            },
        )
        first = client.post(f"/api/items/{item['id']}/refresh").json()
        assert first["done"] is True and first["new_since_done"] is False

        monkeypatch.setattr(
            items_router,
            "fetch_source",
            lambda *args, **kwargs: {
                "title": "t",
                "content": "ada: hello\nbob: again",
                "metadata": {"latest_ts": "1700000200.000000"},
            },
        )
        second = client.post(f"/api/items/{item['id']}/refresh").json()
        assert second["done"] is True and second["new_since_done"] is True
        client.delete(f"/api/items/{item['id']}")


def test_marking_done_is_idempotent_and_keeps_the_original_watermark(monkeypatch):
    with TestClient(app) as client:
        item = client.post(
            "/api/items",
            json={
                "url": "https://acme.slack.com/archives/C6/p1700000000000002",
                "fetch": False,
                "metadata_json": {"latest_ts": "1700000000.000000"},
            },
        ).json()
        first = client.patch(f"/api/items/{item['id']}", json={"done": True}).json()
        monkeypatch.setattr(
            items_router,
            "fetch_source",
            lambda *args, **kwargs: {
                "title": "t",
                "content": "x",
                "metadata": {"latest_ts": "1700000300.000000"},
            },
        )
        client.post(f"/api/items/{item['id']}/refresh")

        # Marking the already done thread again does not move its watermark, so
        # the reply stays flagged.
        again = client.patch(f"/api/items/{item['id']}", json={"done": True}).json()
        assert again["done"] is True
        assert again["new_since_done"] is True
        assert again["done_at"] == first["done_at"]
        client.delete(f"/api/items/{item['id']}")


def test_marking_a_note_done_stores_the_decision(monkeypatch):
    # The flag is generic on the item model; the UI only offers it for Slack
    # threads, but the API records whatever the caller decides.
    with TestClient(app) as client:
        note = client.post("/api/items", json={"content": "remember this", "fetch": False}).json()
        marked = client.patch(f"/api/items/{note['id']}", json={"done": True}).json()
        assert marked["done"] is True and marked["new_since_done"] is False
        client.delete(f"/api/items/{note['id']}")


def test_create_item_dedupes_by_external_id_and_merges():
    with TestClient(app) as client:
        first = client.post("/api/items", json={"url": "https://github.com/o/r/issues/5", "fetch": False}).json()
        second = client.post(
            "/api/items", json={"url": "https://github.com/o/r/issues/5", "title": "Updated", "fetch": False}
        ).json()

        assert first["id"] == second["id"]  # same source + external id
        assert second["title"] == "Updated"
        client.delete(f"/api/items/{first['id']}")


def test_create_item_dedupes_by_url():
    with TestClient(app) as client:
        first = client.post("/api/items", json={"url": "https://example.com/page", "fetch": False}).json()
        second = client.post(
            "/api/items", json={"url": "https://example.com/page", "content": "added later", "fetch": False}
        ).json()
        assert first["id"] == second["id"]
        assert second["content"] == "added later"
        client.delete(f"/api/items/{first['id']}")


def test_create_item_respects_explicit_source_and_derives_title():
    with TestClient(app) as client:
        explicit = client.post(
            "/api/items",
            json={
                "source": "slack",
                "kind": "thread",
                "external_id": "C1:2",
                "title": "S",
                "content": "x",
                "fetch": False,
            },
        ).json()
        assert explicit["source"] == "slack" and explicit["kind"] == "thread" and explicit["external_id"] == "C1:2"

        derived = client.post("/api/items", json={"content": "first line\nsecond line", "fetch": False}).json()
        assert derived["title"] == "first line"

        client.delete(f"/api/items/{explicit['id']}")
        client.delete(f"/api/items/{derived['id']}")


def test_create_item_fetches_when_requested(monkeypatch):
    seen: dict = {}

    def fake_fetch(source, url, external_id, title):
        seen.update(source=source, url=url)
        return {"title": "Fetched", "content": "body", "metadata": {"k": "v"}}

    monkeypatch.setattr(items_router, "fetch_source", fake_fetch)
    with TestClient(app) as client:
        item = client.post("/api/items", json={"url": "https://example.com/x", "fetch": True}).json()
        assert seen["source"] == "url"
        assert item["title"] == "Fetched"
        assert item["content"] == "body"
        assert item["metadata_json"]["k"] == "v"
        assert item["fetched_at"] is not None
        client.delete(f"/api/items/{item['id']}")


def test_clearing_the_title_restores_the_source_title(monkeypatch):
    monkeypatch.setattr(
        items_router,
        "fetch_source",
        lambda *args, **kwargs: {"title": "From the source", "content": "", "metadata": {}},
    )
    with TestClient(app) as client:
        item = client.post(
            "/api/items", json={"url": "https://example.com/reset", "title": "Mine", "fetch": False}
        ).json()
        assert item["title"] == "Mine" and item["title_custom"] is True

        reset = client.patch(f"/api/items/{item['id']}", json={"title": ""}).json()
        assert reset["title"] == "From the source" and reset["title_custom"] is False
        client.delete(f"/api/items/{item['id']}")


def test_clearing_a_note_title_falls_back_to_its_content(monkeypatch):
    monkeypatch.setattr(
        items_router, "fetch_source", lambda *args, **kwargs: {"title": "", "content": "", "metadata": {}}
    )
    with TestClient(app) as client:
        item = client.post("/api/items", json={"content": "first line\nsecond line", "fetch": False}).json()
        assert client.patch(f"/api/items/{item['id']}", json={"title": "Custom"}).json()["title_custom"] is True

        reset = client.patch(f"/api/items/{item['id']}", json={"title": ""}).json()
        assert reset["title"] == "first line" and reset["title_custom"] is False
        client.delete(f"/api/items/{item['id']}")


def test_refresh_keeps_a_custom_title_but_rederives_an_auto_one(monkeypatch):
    monkeypatch.setattr(
        items_router,
        "fetch_source",
        lambda *args, **kwargs: {"title": "From the source", "content": "body", "metadata": {}},
    )
    with TestClient(app) as client:
        # No title given: the item takes the fetched title on refresh.
        auto = client.post("/api/items", json={"url": "https://example.com/auto", "fetch": False}).json()
        auto = client.post(f"/api/items/{auto['id']}/refresh").json()
        assert auto["title"] == "From the source" and auto["title_custom"] is False

        # A title given by a person survives the same refresh.
        custom = client.post(
            "/api/items", json={"url": "https://example.com/custom", "title": "Mine", "fetch": False}
        ).json()
        assert custom["title_custom"] is True
        custom = client.post(f"/api/items/{custom['id']}/refresh").json()
        assert custom["title"] == "Mine" and custom["title_custom"] is True

        client.delete(f"/api/items/{auto['id']}")
        client.delete(f"/api/items/{custom['id']}")


def test_patch_and_refresh_item(monkeypatch):
    monkeypatch.setattr(
        items_router,
        "fetch_source",
        lambda *args, **kwargs: {"title": "Refreshed", "content": "new body", "metadata": {"r": 1}},
    )
    with TestClient(app) as client:
        item = client.post("/api/items", json={"content": "note", "fetch": False}).json()

        patched = client.patch(f"/api/items/{item['id']}", json={"title": "T2", "content": "c2"}).json()
        assert patched["title"] == "T2" and patched["content"] == "c2"

        # A null metadata_json is ignored rather than clearing it.
        assert client.patch(f"/api/items/{item['id']}", json={"metadata_json": None}).json()["metadata_json"] == {}
        assert client.patch("/api/items/missing", json={"title": "x"}).status_code == 404

        refreshed = client.post(f"/api/items/{item['id']}/refresh").json()
        # The title was edited here, so a refresh keeps it and only merges content.
        assert refreshed["title"] == "T2" and refreshed["title_custom"] is True
        assert refreshed["content"] == "new body"
        assert client.post("/api/items/missing/refresh").status_code == 404

        assert client.delete(f"/api/items/{item['id']}").status_code == 204
        assert client.delete("/api/items/missing").status_code == 404


def test_create_item_reports_a_failed_fetch(monkeypatch):
    # A slackx that cannot run must surface, not read as a successful create.
    monkeypatch.setattr(shell, "_cli_available", lambda name: False)
    with TestClient(app) as client:
        item = client.post(
            "/api/items",
            json={"url": "https://acme.slack.com/archives/C7/p1700000000000000", "fetch": True},
        ).json()
        assert item["fetch_error"] == "slackx is not installed; install it to fetch Slack threads"
        client.delete(f"/api/items/{item['id']}")


def test_refresh_item_surfaces_a_failed_fetch(monkeypatch):
    monkeypatch.setattr(shell, "_cli_available", lambda name: False)
    with TestClient(app) as client:
        item = client.post(
            "/api/items",
            json={"url": "https://acme.slack.com/archives/C8/p1700000000000000", "fetch": False},
        ).json()
        assert item["fetched_at"] is None and item["fetch_error"] is None

        refreshed = client.post(f"/api/items/{item['id']}/refresh").json()
        assert refreshed["fetch_error"] == "slackx is not installed; install it to fetch Slack threads"
        # A failed fetch does not advance fetched_at, so the policy retries it.
        assert refreshed["fetched_at"] is None
        client.delete(f"/api/items/{item['id']}")


def test_refresh_due_records_a_failed_fetch(monkeypatch):
    from sqlmodel import Session

    from agentic.db import engine
    from agentic.models.system import Setting
    from agentic.settings_store import refresh_status_key

    monkeypatch.setattr(shell, "_cli_available", lambda name: False)
    with TestClient(app) as client:
        client.patch("/api/settings", json={"slack_refresh_policy": "1d=1h,*=7d"})
        item = client.post(
            "/api/items",
            json={"url": "https://acme.slack.com/archives/C9/p1700000000000000", "fetch": False},
        ).json()
        try:
            report = client.post("/api/items/refresh-due").json()
            entry = next(entry for entry in report["items"] if entry["item_id"] == item["id"])
            assert entry["refreshed"] is False
            assert entry["error"] == "slackx is not installed; install it to fetch Slack threads"
        finally:
            client.patch("/api/settings", json={"slack_refresh_policy": ""})
            client.delete(f"/api/items/{item['id']}")
            # Clear the run this test recorded so it does not leak into the
            # settings tests that assert an empty refresh status.
            with Session(engine) as session:
                row = session.get(Setting, refresh_status_key("slack"))
                if row is not None:
                    session.delete(row)
                    session.commit()


def test_item_links_read_list_and_delete():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "Linkable"}).json()
        association = client.post(
            f"/api/tasks/{task['id']}/items",
            json={"item": {"url": "https://github.com/psf/requests/issues/9", "fetch": False}},
        ).json()
        item_id = association["item"]["id"]

        fetched = client.get(f"/api/items/{item_id}").json()
        assert task["id"] in fetched["task_ids"]
        assert client.get("/api/items/missing").status_code == 404

        assert all(i["source"] == "github" for i in client.get("/api/items", params={"source": "github"}).json())
        assert any(i["id"] == item_id for i in client.get("/api/items", params={"q": "requests"}).json())

        # Deleting the item also removes the association to the task.
        client.delete(f"/api/items/{item_id}")
        assert client.get(f"/api/tasks/{task['id']}").json()["associations"] == []
        client.delete(f"/api/tasks/{task['id']}")


def test_refresh_due_refreshes_items_the_policy_says_are_due(monkeypatch):
    def fake_fetch(source, url, external_id, title):
        return {"title": "Fresh", "content": "updated body", "metadata": {}}

    monkeypatch.setattr(items_refresh, "fetch_source", fake_fetch)
    with TestClient(app) as client:
        client.patch("/api/settings", json={"github_refresh_policy": "1d=1h,7d=6h,30d=1d"})
        try:
            item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/9", "fetch": False}).json()
            assert item["fetched_at"] is None

            report = client.post("/api/items/refresh-due").json()
            assert report["checked"] >= 1
            assert any(entry["item_id"] == item["id"] and entry["refreshed"] for entry in report["items"])
            assert report["refreshed"] == report["due"]

            refreshed = client.get(f"/api/items/{item['id']}").json()
            assert refreshed["content"] == "updated body"
            assert refreshed["fetched_at"] is not None

            # A second pass leaves the just-refreshed item alone.
            again = client.post("/api/items/refresh-due").json()
            assert not any(entry["item_id"] == item["id"] for entry in again["items"])

            client.delete(f"/api/items/{item['id']}")
        finally:
            client.patch("/api/settings", json={"github_refresh_policy": ""})


def test_refresh_due_is_a_noop_without_a_policy(monkeypatch):
    monkeypatch.setattr(items_refresh, "fetch_source", lambda *args, **kwargs: {})
    with TestClient(app) as client:
        client.patch("/api/settings", json={"slack_refresh_policy": "", "github_refresh_policy": ""})
        client.post("/api/items", json={"url": "https://github.com/o/r/issues/10", "fetch": False})
        report = client.post("/api/items/refresh-due").json()
        assert report == {"checked": 0, "due": 0, "refreshed": 0, "failed": 0, "items": []}


def test_force_refresh_source_ignores_the_policy(monkeypatch):
    from sqlmodel import Session

    from agentic.db import engine
    from agentic.models.system import Setting

    def fake_fetch(source, url, external_id, title):
        # Only touch the item this test created; leave any other item alone.
        if "issues/13" not in (url or ""):
            raise RuntimeError("unexpected item")
        return {"title": "Fresh", "content": "updated body", "metadata": {}}

    monkeypatch.setattr(items_refresh, "fetch_source", fake_fetch)
    with TestClient(app) as client:
        # No policy is set, so a due refresh would do nothing; force still pulls.
        client.patch("/api/settings", json={"slack_refresh_policy": "", "github_refresh_policy": ""})
        item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/13", "fetch": False}).json()
        assert item["fetched_at"] is None

        report = client.post("/api/items/refresh-source/github").json()
        assert any(entry["item_id"] == item["id"] and entry["refreshed"] for entry in report["items"])

        # The forced run is recorded, so the Settings status line updates.
        status = client.get("/api/settings/refresh-status").json()["sources"]["github"]
        assert status["origin"] == "manual"
        assert status["last_run_at"] and status["refreshed"] >= 1

        refreshed = client.get(f"/api/items/{item['id']}").json()
        assert refreshed["content"] == "updated body" and refreshed["fetched_at"] is not None
        client.delete(f"/api/items/{item['id']}")

        assert client.post("/api/items/refresh-source/nope").status_code == 404

        with Session(engine) as session:
            row = session.get(Setting, "github_refresh_status")
            if row is not None:
                session.delete(row)
            session.commit()
