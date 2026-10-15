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
