"""App settings: effective values, overrides, and environment defaults."""

from fastapi.testclient import TestClient

from agentic.main import app


def test_settings_read_and_patch_round_trip():
    with TestClient(app) as client:
        initial = client.get("/api/settings").json()
        assert {"effective", "overrides", "defaults"} <= set(initial)
        assert set(initial["effective"]) >= {
            "openchamber_url",
            "openchamber_session_path",
            "terminal_url_template",
            "editor_url_template",
        }

        patched = client.patch("/api/settings", json={"terminal_url_template": "warp://{session}"}).json()
        assert patched["effective"]["terminal_url_template"] == "warp://{session}"
        assert patched["overrides"]["terminal_url_template"] == "warp://{session}"

        # An empty string disables the override but records it.
        reset = client.patch("/api/settings", json={"terminal_url_template": ""}).json()
        assert reset["effective"]["terminal_url_template"] == ""


def test_refresh_policy_setting_validates_and_previews():
    with TestClient(app) as client:
        initial = client.get("/api/settings").json()
        assert {"slack_refresh_policy", "github_refresh_policy"} <= set(initial["effective"])

        preview = client.post("/api/settings/refresh-policy/preview", json={"value": "1d=1h,7d=6h,*=7d"}).json()
        assert preview["valid"] is True and preview["enabled"] is True
        assert preview["tiers"][0] == {"max_age_seconds": 86400.0, "interval_seconds": 3600.0}
        assert preview["fallback_seconds"] == 604800.0

        # A malformed policy is reported rather than raised, so the UI can show it.
        broken = client.post("/api/settings/refresh-policy/preview", json={"value": "7d=1h,1d=2h"}).json()
        assert broken["valid"] is False and broken["error"]

        # Saving a malformed policy is rejected, and names the field.
        rejected = client.patch("/api/settings", json={"slack_refresh_policy": "nonsense"})
        assert rejected.status_code == 422
        assert "slack_refresh_policy" in rejected.json()["detail"]

        saved = client.patch(
            "/api/settings", json={"slack_refresh_policy": "1d=1h,*=never", "github_refresh_policy": "1d=1h"}
        ).json()
        assert saved["effective"]["slack_refresh_policy"] == "1d=1h,*=never"
        assert saved["effective"]["github_refresh_policy"] == "1d=1h"
        assert saved["overrides"]["slack_refresh_policy"] == "1d=1h,*=never"

        client.patch("/api/settings", json={"slack_refresh_policy": "", "github_refresh_policy": ""})


def test_agent_prompts_default_and_validation():
    import json

    from sqlmodel import Session

    from agentic.db import engine
    from agentic.models.system import Setting

    with TestClient(app) as client:
        initial = client.get("/api/settings").json()
        # The seeded defaults are served when nothing is overridden.
        defaults = json.loads(initial["defaults"]["agent_prompts"])
        assert {prompt["kind"] for prompt in defaults} == {"issue", "pull_request"}
        assert json.loads(initial["effective"]["agent_prompts"]) == defaults

        # A valid list round-trips and is stored as an override.
        prompts = [{"kind": "issue", "label": "Triage", "template": "triage {number} {owner}/{repository}"}]
        saved = client.patch("/api/settings", json={"agent_prompts": json.dumps(prompts)}).json()
        assert json.loads(saved["overrides"]["agent_prompts"]) == prompts

        # A malformed list is rejected and names the field.
        for bad in (
            "not json",
            json.dumps({"kind": "issue"}),
            json.dumps([{"kind": "nope", "template": "x"}]),
            json.dumps([{"kind": "issue", "template": "   "}]),
        ):
            rejected = client.patch("/api/settings", json={"agent_prompts": bad})
            assert rejected.status_code == 422
            assert "agent_prompts" in rejected.json()["detail"]

        # An empty list is a valid override (no buttons in the panel).
        empty = client.patch("/api/settings", json={"agent_prompts": "[]"}).json()
        assert empty["effective"]["agent_prompts"] == "[]"

    with Session(engine) as session:
        row = session.get(Setting, "agent_prompts")
        if row is not None:
            session.delete(row)
            session.commit()


def test_github_login_setting_falls_back_to_detection(monkeypatch):
    from agentic import settings_store

    with TestClient(app) as client:
        # An explicit login is stored as an override and served as effective.
        saved = client.patch("/api/settings", json={"github_login": "me"}).json()
        assert saved["effective"]["github_login"] == "me"
        assert saved["overrides"]["github_login"] == "me"

        # Clearing it falls back to the login the authenticated `gh` reports.
        monkeypatch.setattr(settings_store, "detect_github_login", lambda: "detected")
        client.patch("/api/settings", json={"github_login": ""})
        fallback = client.get("/api/settings").json()
        assert fallback["effective"]["github_login"] == "detected"
        assert fallback["overrides"]["github_login"] == ""

        # With nothing configured and nothing detected, the login is empty.
        monkeypatch.setattr(settings_store, "detect_github_login", lambda: "")
        assert client.get("/api/settings").json()["effective"]["github_login"] == ""


def test_refresh_status_reports_the_last_run():
    from datetime import UTC, datetime

    from sqlmodel import Session

    from agentic.db import engine
    from agentic.models.system import Setting
    from agentic.settings_store import record_refresh_run

    with TestClient(app) as client:
        assert client.get("/api/settings/refresh-status").json() == {"sources": {}}

        with Session(engine) as session:
            record_refresh_run(
                session,
                "slack",
                last_run_at=datetime(2026, 10, 15, 12, 0, tzinfo=UTC),
                refreshed=3,
                failed=1,
                error="slackx: rate limited",
                origin="manual",
            )

        status = client.get("/api/settings/refresh-status").json()["sources"]
        assert status["slack"]["refreshed"] == 3
        assert status["slack"]["failed"] == 1
        assert status["slack"]["error"] == "slackx: rate limited"
        assert status["slack"]["origin"] == "manual"
        assert status["slack"]["last_run_at"].startswith("2026-10-15T12:00")
        assert "github" not in status

        with Session(engine) as session:
            session.delete(session.get(Setting, "slack_refresh_status"))
            session.commit()


def test_background_run_records_status_per_source(monkeypatch):
    from sqlmodel import Session

    from agentic import main
    from agentic.db import engine
    from agentic.models.system import Setting
    from agentic.routers import items as items_router

    monkeypatch.setattr(items_router, "fetch_source", lambda *args, **kwargs: {"title": "x", "content": "y"})
    with TestClient(app) as client:
        client.patch("/api/settings", json={"slack_refresh_policy": "1d=1h", "github_refresh_policy": "1d=1h"})
        try:
            item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/11", "fetch": False}).json()
            main._refresh_due_once()

            sources = client.get("/api/settings/refresh-status").json()["sources"]
            assert sources["github"]["last_run_at"] and sources["github"]["refreshed"] >= 1
            assert sources["github"]["origin"] == "background"
            # Every active source records a run, even when nothing was due.
            assert sources["slack"]["last_run_at"]

            client.delete(f"/api/items/{item['id']}")
        finally:
            client.patch("/api/settings", json={"slack_refresh_policy": "", "github_refresh_policy": ""})
            with Session(engine) as session:
                for key in ("slack_refresh_status", "github_refresh_status"):
                    row = session.get(Setting, key)
                    if row is not None:
                        session.delete(row)
                session.commit()


def test_background_run_records_failures(monkeypatch):
    from sqlmodel import Session

    from agentic import main
    from agentic.db import engine
    from agentic.models.system import Setting
    from agentic.routers import items as items_router

    def boom(*args, **kwargs):
        raise RuntimeError("ghx: authentication required")

    monkeypatch.setattr(items_router, "fetch_source", boom)
    with TestClient(app) as client:
        client.patch("/api/settings", json={"github_refresh_policy": "1d=1h"})
        try:
            item = client.post("/api/items", json={"url": "https://github.com/o/r/issues/12", "fetch": False}).json()
            main._refresh_due_once()

            status = client.get("/api/settings/refresh-status").json()["sources"]["github"]
            assert status["refreshed"] == 0
            assert status["failed"] >= 1
            assert "authentication" in status["error"]

            client.delete(f"/api/items/{item['id']}")
        finally:
            client.patch("/api/settings", json={"github_refresh_policy": ""})
            with Session(engine) as session:
                for key in ("slack_refresh_status", "github_refresh_status"):
                    row = session.get(Setting, key)
                    if row is not None:
                        session.delete(row)
                session.commit()
