"""On-call: resolving a thread stores one item under the canonical Slack id."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from agentic.db import engine
from agentic.main import app
from agentic.models.items import SourceItem
from agentic.routers import on_call

WORKSPACE = "https://acme.slack.com/"
HELP_CHANNEL_ID = "C0893LXNXMJ"
HELP_CHANNEL_TS = "1791578010.079819"
# Items these tests create share the suite's database, so they are pruned after.
TEST_MARKERS = ("CONCALL", "help-ml-infrastructure", HELP_CHANNEL_ID)


@pytest.fixture(autouse=True)
def _clean_on_call_items():
    yield
    with Session(engine) as session:
        for item in session.exec(select(SourceItem).where(SourceItem.source == "slack")).all():
            if any(marker in (item.url or "") or marker in (item.external_id or "") for marker in TEST_MARKERS):
                session.delete(item)
        session.commit()


@pytest.fixture(autouse=True)
def _workspace(monkeypatch):
    monkeypatch.setattr(on_call.slack_service, "slack_workspace_url", lambda: WORKSPACE)


def _slack_items(client) -> list[dict]:
    return client.get("/api/items", params={"source": "slack"}).json()


def test_resolving_a_thread_creates_an_item_with_its_canonical_external_id():
    channel, thread_ts = "CONCALL1", "1700000000.123456"
    slack_url = f"{WORKSPACE}archives/{channel}/p1700000000123456"

    with TestClient(app) as client:
        response = client.post(
            "/api/on-call/resolve",
            json={"channel": channel, "thread_ts": thread_ts, "resolved_through_ts": thread_ts},
        )
        assert response.status_code == 200

        matches = [item for item in _slack_items(client) if item["url"] == slack_url]
        assert len(matches) == 1
        item = matches[0]
        assert item["external_id"] == "CONCALL1:1700000000123456"
        assert item["done"] is True
        with Session(engine) as session:
            stored = session.get(SourceItem, item["id"])
            assert stored is not None
            assert stored.done_message_ts == thread_ts

        # Marking it resolved again finds the same item rather than a second one.
        assert client.post("/api/on-call/resolve", json={"channel": channel, "thread_ts": thread_ts}).status_code == 200
        assert len([entry for entry in _slack_items(client) if entry["url"] == slack_url]) == 1


def test_resolving_a_named_channel_keys_the_item_by_the_channel_id(monkeypatch):
    def fake_cli(cmd, timeout=60):
        assert cmd[1:3] == ["channels", "get"]
        return json.dumps({"channels": [{"id": HELP_CHANNEL_ID}]})

    monkeypatch.setattr(on_call.shell, "_run_cli", fake_cli)
    slack_url = f"{WORKSPACE}archives/{HELP_CHANNEL_ID}/p1791578010079819"

    with TestClient(app) as client:
        response = client.post(
            "/api/on-call/resolve",
            json={"channel": "#help-ml-infrastructure", "thread_ts": HELP_CHANNEL_TS},
        )
        assert response.status_code == 200

        matches = [item for item in _slack_items(client) if item["url"] == slack_url]
        assert len(matches) == 1
        assert matches[0]["external_id"] == f"{HELP_CHANNEL_ID}:1791578010079819"


def test_resolving_heals_an_item_stored_under_the_configured_channel_name(monkeypatch):
    def fake_cli(cmd, timeout=60):
        return json.dumps({"channels": [{"id": HELP_CHANNEL_ID}]})

    monkeypatch.setattr(on_call.shell, "_run_cli", fake_cli)
    # What the pre-fix resolve stored: the channel as configured, and a URL
    # whose "#" turns the channel into a fragment.
    legacy_url = "https://slack.com/archives/#help-ml-infrastructure/p1791578010079819"
    with Session(engine) as session:
        legacy = SourceItem(
            source="slack",
            kind="thread",
            url=legacy_url,
            external_id="#help-ml-infrastructure:1791578010079819",
            title="Slack thread",
        )
        session.add(legacy)
        session.commit()
        session.refresh(legacy)
        legacy_id = legacy.id

    with TestClient(app) as client:
        response = client.post(
            "/api/on-call/resolve",
            json={"channel": "#help-ml-infrastructure", "thread_ts": HELP_CHANNEL_TS},
        )
        assert response.status_code == 200

        matches = [
            item
            for item in _slack_items(client)
            if item["external_id"] == f"{HELP_CHANNEL_ID}:1791578010079819"
            or "help-ml-infrastructure" in (item["url"] or "")
        ]
        assert len(matches) == 1
        assert matches[0]["id"] == legacy_id
        assert matches[0]["external_id"] == f"{HELP_CHANNEL_ID}:1791578010079819"
        assert matches[0]["url"] == f"{WORKSPACE}archives/{HELP_CHANNEL_ID}/p1791578010079819"
        assert matches[0]["done"] is True


def test_resolving_heals_an_item_stored_under_the_bare_thread_ts():
    channel, thread_ts = "CONCALL2", "1700000001.123456"
    legacy_url = f"https://slack.com/archives/{channel}/p1700000001123456"
    with Session(engine) as session:
        legacy = SourceItem(source="slack", kind="thread", url=legacy_url, external_id=thread_ts, title="Slack thread")
        session.add(legacy)
        session.commit()
        session.refresh(legacy)
        legacy_id = legacy.id

    with TestClient(app) as client:
        assert client.post("/api/on-call/resolve", json={"channel": channel, "thread_ts": thread_ts}).status_code == 200

        matches = [
            item
            for item in _slack_items(client)
            if item["external_id"] == "CONCALL2:1700000001123456" or "CONCALL2" in (item["url"] or "")
        ]
        assert len(matches) == 1
        assert matches[0]["id"] == legacy_id
        assert matches[0]["external_id"] == "CONCALL2:1700000001123456"
        assert matches[0]["url"] == f"{WORKSPACE}archives/{channel}/p1700000001123456"
        assert matches[0]["done"] is True


def test_scan_heals_an_item_stored_under_the_configured_channel_name(monkeypatch):
    payload = {
        "channel": HELP_CHANNEL_ID,
        "channel_name": "help-ml-infrastructure",
        "message_count": 1,
        "messages": [{"ts": HELP_CHANNEL_TS, "text": "Anyone around?", "user": "U1", "user_name": "ada"}],
    }
    monkeypatch.setattr(on_call.shell, "_cli_run", lambda cmd, timeout=60: (0, json.dumps(payload), ""))
    with Session(engine) as session:
        legacy = SourceItem(
            source="slack",
            kind="thread",
            url="https://slack.com/archives/#help-ml-infrastructure/p1791578010079819",
            external_id="#help-ml-infrastructure:1791578010079819",
            title="Slack thread",
        )
        session.add(legacy)
        session.commit()
        session.refresh(legacy)
        legacy_id = legacy.id

    with TestClient(app) as client:
        scanned = client.post("/api/on-call/scan", json={"channel": "#help-ml-infrastructure"})
        assert scanned.status_code == 200

        matches = [item for item in _slack_items(client) if item["id"] == legacy_id]
        assert len(matches) == 1
        assert matches[0]["external_id"] == f"{HELP_CHANNEL_ID}:1791578010079819"
        # The "#" in the old URL made it a fragment; the scan restores a permalink.
        assert matches[0]["url"] == f"{WORKSPACE}archives/{HELP_CHANNEL_ID}/p1791578010079819"


def test_scan_finds_a_resolved_thread_by_its_canonical_external_id(monkeypatch):
    channel, thread_ts, reply_ts = "CONCALL3", "1700000002.123456", "1700000003.000000"
    payload = {
        "channel": channel,
        "channel_name": "help",
        "message_count": 2,
        "messages": [
            {"ts": thread_ts, "text": "Is the API down?", "user": "U1", "user_name": "ada"},
            {
                "ts": reply_ts,
                "thread_ts": thread_ts,
                "text": "Looking into it",
                "user": "U2",
                "user_name": "bob",
                "is_thread_reply": True,
            },
        ],
    }
    monkeypatch.setattr(on_call.shell, "_cli_run", lambda cmd, timeout=60: (0, json.dumps(payload), ""))

    with TestClient(app) as client:
        client.post("/api/on-call/resolve", json={"channel": channel, "thread_ts": thread_ts})

        scanned = client.post("/api/on-call/scan", json={"channel": channel})
        assert scanned.status_code == 200
        threads = scanned.json()["threads"]
        assert len(threads) == 1
        assert threads[0]["resolved"] is True
        # A reply after the resolved watermark shows as new activity.
        assert threads[0]["has_new_activity"] is True
        assert len([item for item in _slack_items(client) if "CONCALL3" in (item["url"] or "")]) == 1
