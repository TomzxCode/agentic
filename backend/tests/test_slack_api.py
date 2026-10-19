"""Slack user lookup: name the ids a caller passes, through slackx."""

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.services import slack


def test_users_names_the_ids_passed(monkeypatch):
    monkeypatch.setattr(slack, "slack_user_names", lambda: {"U0123ABCDEF": "Ada Lovelace"})
    monkeypatch.setattr(slack, "slack_user_name", lambda user_id: "Grace Hopper" if user_id == "U0COLDCOLD" else None)
    with TestClient(app) as client:
        body = client.get(
            "/api/slack/users", params={"ids": ["U0123ABCDEF", "ada", "U0COLDCOLD", "U9999ZZZZZZ"]}
        ).json()
        # The cached id comes from the bulk read, the other is fetched on its own,
        # a handle is passed over, and an id that cannot be named is left out.
        assert body == {"names": {"U0123ABCDEF": "Ada Lovelace", "U0COLDCOLD": "Grace Hopper"}}


def test_users_without_ids_returns_nothing(monkeypatch):
    calls: list = []
    monkeypatch.setattr(slack, "slack_user_names", lambda: calls.append(1) or {})
    monkeypatch.setattr(slack, "slack_user_name", lambda user_id: calls.append(user_id))
    with TestClient(app) as client:
        assert client.get("/api/slack/users").json() == {"names": {}}
        # Nothing that looks like a user id, so slackx is never read.
        assert client.get("/api/slack/users", params={"ids": ["ada", "ada@example.com"]}).json() == {"names": {}}
    assert calls == []
