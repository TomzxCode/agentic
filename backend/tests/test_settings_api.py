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
            "ghx_url",
            "slackx_url",
        }

        patched = client.patch("/api/settings", json={"terminal_url_template": "warp://{session}"}).json()
        assert patched["effective"]["terminal_url_template"] == "warp://{session}"
        assert patched["overrides"]["terminal_url_template"] == "warp://{session}"

        # An empty string disables the override but records it.
        reset = client.patch("/api/settings", json={"terminal_url_template": ""}).json()
        assert reset["effective"]["terminal_url_template"] == ""

        tools = client.patch(
            "/api/settings", json={"ghx_url": "http://localhost:8080", "slackx_url": "http://localhost:8280"}
        ).json()
        assert tools["effective"]["ghx_url"] == "http://localhost:8080"
        assert tools["overrides"]["slackx_url"] == "http://localhost:8280"

        client.patch("/api/settings", json={"ghx_url": "", "slackx_url": ""})


def test_transport_setting_validates_and_applies():
    from sqlmodel import Session

    from agentic.db import engine
    from agentic.models.system import Setting

    keys = (
        "ghx_backend",
        "ghx_rpc_url",
        "ghx_rpc_token",
        "slackx_backend",
        "slackx_rpc_url",
        "slackx_rpc_token",
    )

    def clear_rows():
        with Session(engine) as session:
            for key in keys:
                row = session.get(Setting, key)
                if row is not None:
                    session.delete(row)
            session.commit()

    try:
        with TestClient(app) as client:
            initial = client.get("/api/settings").json()
            assert set(keys) <= set(initial["effective"])

            rejected = client.patch("/api/settings", json={"ghx_backend": "jsonrpc"})
            assert rejected.status_code == 422
            rejected = client.patch("/api/settings", json={"ghx_rpc_url": "127.0.0.1:8090"})
            assert rejected.status_code == 422

            saved = client.patch(
                "/api/settings",
                json={"ghx_backend": "rpc", "ghx_rpc_url": "http://127.0.0.1:18090", "ghx_rpc_token": "t0ken"},
            ).json()
            assert saved["effective"]["ghx_backend"] == "rpc"
            assert saved["overrides"]["ghx_rpc_url"] == "http://127.0.0.1:18090"
            assert saved["effective"]["ghx_rpc_token"] == "t0ken"
    finally:
        # Stored rows would leak into this worker's other tests, which expect
        # the environment-driven transport.
        clear_rows()


def test_managed_transport_syncs_the_tool_servers(monkeypatch):
    from sqlmodel import Session

    from agentic.db import engine
    from agentic.models.system import Setting
    from agentic.routers import settings as settings_router

    synced = []
    monkeypatch.setattr(settings_router.managed_tools, "sync", lambda: synced.append(True))

    try:
        with TestClient(app) as client:
            # The lifespan syncs once at startup; only the patches matter here.
            synced.clear()
            saved = client.patch("/api/settings", json={"slackx_backend": "managed"}).json()
            assert saved["effective"]["slackx_backend"] == "managed"
            # A switch to managed starts the tool's serve process right away.
            assert synced == [True]

            # The old "serve" spelling is gone, and a refused value changes nothing.
            rejected = client.patch("/api/settings", json={"slackx_backend": "serve"})
            assert rejected.status_code == 422
            assert synced == [True]

            # A change that is not a transport leaves the running tools alone.
            client.patch("/api/settings", json={"ghx_url": ""})
            assert synced == [True]
    finally:
        # Stored rows would leak into this worker's other tests, which expect
        # the environment-driven transport.
        with Session(engine) as session:
            row = session.get(Setting, "slackx_backend")
            if row is not None:
                session.delete(row)
                session.commit()


def test_managed_transport_supplies_the_web_ui_url(monkeypatch):
    from sqlmodel import Session

    from agentic.db import engine
    from agentic.models.system import Setting
    from agentic.routers import settings as settings_router

    # Never start a real serve process from a test.
    monkeypatch.setattr(settings_router.managed_tools, "sync", lambda: None)

    try:
        with TestClient(app) as client:
            client.patch("/api/settings", json={"ghx_url": "", "slackx_url": "", "slackx_backend": "cli"})
            saved = client.patch("/api/settings", json={"ghx_backend": "managed"}).json()
            # The server runs ghx itself, so the URL it answers on stands in for
            # the one a user would type, and items link into it.
            assert saved["effective"]["ghx_url"] == "http://127.0.0.1:8080"
            # The transport is per tool: slackx is still the CLI's business.
            assert saved["effective"]["slackx_url"] == ""

            # An explicit URL still supplies the host, but the port follows the
            # process this server runs (8080 is the preferred one here).
            explicit = client.patch("/api/settings", json={"ghx_url": "http://ghx.local:9000"}).json()
            assert explicit["effective"]["ghx_url"] == "http://ghx.local:8080"
            assert explicit["overrides"]["ghx_url"] == "http://ghx.local:9000"
    finally:
        with Session(engine) as session:
            for key in ("ghx_backend", "ghx_url", "slackx_backend", "slackx_url"):
                row = session.get(Setting, key)
                if row is not None:
                    session.delete(row)
            session.commit()


def test_restart_tool_route(monkeypatch):
    from agentic.routers import settings as settings_router

    restarted = []
    monkeypatch.setattr(settings_router.managed_tools, "restart", lambda tool: restarted.append(tool) or True)

    with TestClient(app) as client:
        started = client.post("/api/settings/tools/ghx/restart")
        assert started.status_code == 200
        assert started.json() == {
            "tool": "ghx",
            "running": True,
            "port": 8080,
            "url": "http://127.0.0.1:8080",
        }
        assert restarted == ["ghx"]

        # A tool this server does not know, and one it does not run, are
        # different refusals.
        assert client.post("/api/settings/tools/nope/restart").status_code == 404

        monkeypatch.setattr(settings_router.managed_tools, "restart", lambda tool: None)
        assert client.post("/api/settings/tools/slackx/restart").status_code == 409


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


def test_review_scan_setting_validates():
    with TestClient(app) as client:
        assert {"review_scan_interval", "review_scan_default", "review_slo"} <= set(
            client.get("/api/settings").json()["effective"]
        )

        # A cadence is a duration; a blank one switches the scan off.
        assert client.patch("/api/settings", json={"review_scan_interval": "nonsense"}).status_code == 422
        saved = client.patch("/api/settings", json={"review_scan_interval": "30m"}).json()
        assert saved["effective"]["review_scan_interval"] == "30m"
        blank = client.patch("/api/settings", json={"review_scan_interval": ""}).json()
        assert blank["effective"]["review_scan_interval"] == ""

        # The review SLO is a duration too, and a blank one turns it off.
        assert client.patch("/api/settings", json={"review_slo": "soon"}).status_code == 422
        slo = client.patch("/api/settings", json={"review_slo": "8h"}).json()
        assert slo["effective"]["review_slo"] == "8h"
        assert client.patch("/api/settings", json={"review_slo": ""}).json()["effective"]["review_slo"] == ""

        # The nudge SLO accepts a combination such as 1h30m, and a blank turns
        # it off.
        assert client.patch("/api/settings", json={"review_nudge_slo": "soon"}).status_code == 422
        nudge = client.patch("/api/settings", json={"review_nudge_slo": "1h30m"}).json()
        assert nudge["effective"]["review_nudge_slo"] == "1h30m"
        cleared = client.patch("/api/settings", json={"review_nudge_slo": ""}).json()
        assert cleared["effective"]["review_nudge_slo"] == ""

        # The default is one of the two policies a repository can fall back to.
        assert client.patch("/api/settings", json={"review_scan_default": "sometimes"}).status_code == 422
        excluded = client.patch("/api/settings", json={"review_scan_default": "exclude"}).json()
        assert excluded["effective"]["review_scan_default"] == "exclude"

        client.patch("/api/settings", json={"review_scan_interval": "1h", "review_scan_default": "include"})


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
        # The fixed date is well outside the trailing window, so the 24h sum is 0.
        assert status["slack"]["refreshed_24h"] == 0
        assert "github" not in status

        with Session(engine) as session:
            session.delete(session.get(Setting, "slack_refresh_status"))
            session.commit()


def test_refresh_status_sums_runs_in_the_last_24h():
    from datetime import UTC, datetime, timedelta

    from sqlmodel import Session

    from agentic.db import engine
    from agentic.models.system import Setting
    from agentic.settings_store import record_refresh_run

    now = datetime.now(UTC)
    with TestClient(app) as client:
        with Session(engine) as session:
            # A run from two days ago and one from outside the window (30h),
            # then two inside it.
            record_refresh_run(session, "github", last_run_at=now - timedelta(days=2), refreshed=100)
            record_refresh_run(session, "github", last_run_at=now - timedelta(hours=30), refreshed=50)
            record_refresh_run(session, "github", last_run_at=now - timedelta(hours=2), refreshed=4)
            record_refresh_run(session, "github", last_run_at=now, refreshed=3)

        status = client.get("/api/settings/refresh-status").json()["sources"]["github"]
        # The newest run is the last one; the 24h sum covers only the recent two.
        assert status["refreshed"] == 3
        assert status["refreshed_24h"] == 7

        with Session(engine) as session:
            session.delete(session.get(Setting, "github_refresh_status"))
            session.commit()


def test_refresh_status_counts_a_legacy_last_run_in_the_window():
    import json
    from datetime import UTC, datetime, timedelta

    from sqlmodel import Session

    from agentic.db import engine
    from agentic.models.system import Setting
    from agentic.settings_store import get_refresh_status

    now = datetime.now(UTC)
    with Session(engine) as session:
        # A row written before histories were kept has none; its last run still
        # counts when it falls inside the window.
        session.add(
            Setting(
                key="slack_refresh_status",
                value=json.dumps({"last_run_at": now.isoformat(), "refreshed": 5, "failed": 0}),
            )
        )
        session.commit()
        assert get_refresh_status(session)["slack"]["refreshed_24h"] == 5

        # And it counts zero once that run is older than the window.
        setting = session.get(Setting, "slack_refresh_status")
        assert setting is not None
        setting.value = json.dumps(
            {"last_run_at": (now - timedelta(hours=30)).isoformat(), "refreshed": 5, "failed": 0}
        )
        session.commit()
        assert get_refresh_status(session)["slack"]["refreshed_24h"] == 0

        session.delete(session.get(Setting, "slack_refresh_status"))
        session.commit()


def test_background_run_records_status_per_source(monkeypatch):
    from sqlmodel import Session

    from agentic import main
    from agentic.db import engine
    from agentic.models.system import Setting
    from agentic.routers import items_refresh

    monkeypatch.setattr(items_refresh, "fetch_source", lambda *args, **kwargs: {"title": "x", "content": "y"})
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
    from agentic.routers import items_refresh

    def boom(*args, **kwargs):
        raise RuntimeError("ghx: authentication required")

    monkeypatch.setattr(items_refresh, "fetch_source", boom)
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
