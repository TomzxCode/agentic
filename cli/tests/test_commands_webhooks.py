"""Webhook commands."""

import json

from agentic_cli.commands import webhooks


def test_webhook_commands(text_format, fake_client):
    assert "e1" in webhooks.webhook_list()
    assert "secret: set" in webhooks.webhook_get("e1")
    assert "created" in webhooks.webhook_create("New", kind="github", secret="x")
    assert "GitHub" in webhooks.webhook_update("e1", name="GitHub")
    assert "deleted e1" in webhooks.webhook_delete("e1")

    subscribed = webhooks.webhook_subscribe("e1", "g1", name="PR", event=["pull_request"], filter=["action=opened"])
    assert "subscribed" in subscribed and "action equals opened" in subscribed
    assert "On PR" in webhooks.webhook_subscriptions()
    assert "On PR" in webhooks.webhook_subscriptions("e1")
    assert "removed s1" in webhooks.webhook_unsubscribe("s1")

    assert "pull_request" in webhooks.webhook_events()
    assert "pull_request" in webhooks.webhook_events("e1", "pull_request", 10)
    detail = webhooks.webhook_event("ev1")
    assert "action" in detail and "started" in detail and "execution x1" in detail
    assert "replayed ev1" in webhooks.webhook_replay("ev1")
    assert "sent test" in webhooks.webhook_test("e1")


def test_webhook_test_accepts_a_payload_file(text_format, fake_client, tmp_path):
    path = tmp_path / "payload.json"
    path.write_text(json.dumps({"action": "opened"}))
    assert "sent pull_request" in webhooks.webhook_test("e1", "pull_request", str(path))
