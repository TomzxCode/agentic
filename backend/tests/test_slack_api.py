"""Slack user lookup: name the ids a caller passes, through slackx."""

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.services import slack


def test_users_names_the_ids_passed(monkeypatch):
    monkeypatch.setattr(slack, "slack_user_names", lambda: {"U0123ABCDEF": "Ada Lovelace"})
    with TestClient(app) as client:
        body = client.get("/api/slack/users", params={"ids": ["U0123ABCDEF", "ada", "U9999ZZZZZZ"]}).json()
        # Only the value that looks like a Slack user id is resolved; a handle is
        # passed over, and an id slackx does not know is left out.
        assert body == {"names": {"U0123ABCDEF": "Ada Lovelace"}}


def test_users_without_ids_returns_nothing(monkeypatch):
    calls: list = []
    monkeypatch.setattr(slack, "slack_user_names", lambda: calls.append(1) or {})
    with TestClient(app) as client:
        assert client.get("/api/slack/users").json() == {"names": {}}
        # Nothing that looks like a user id, so slackx is never read.
        assert client.get("/api/slack/users", params={"ids": ["ada", "ada@example.com"]}).json() == {"names": {}}
    assert calls == []
