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
