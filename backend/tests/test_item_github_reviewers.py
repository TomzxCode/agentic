"""A PR item's GitHub reviewers, and the Slack poke that asks for a review."""

import json

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.routers import items as items_router
from agentic.services import github, shell, slack


def _reviews_payload() -> str:
    return json.dumps(
        {
            "reviews": [
                {"state": "APPROVED", "submittedAt": "2026-01-02T00:00:00Z", "author": {"login": "alice"}},
                {"state": "COMMENTED", "submittedAt": "2026-01-01T00:00:00Z", "author": {"login": "bob"}},
            ],
            "reviewRequests": [
                {"__typename": "User", "login": "carol"},
                # A team request names a team, not a person to poke.
                {"__typename": "Team", "name": "core"},
            ],
        }
    )


def _pr(client: TestClient, number: int = 42) -> dict:
    return client.post(
        "/api/items",
        json={"url": f"https://github.com/acme/api/pull/{number}", "title": "Fix the parser", "fetch": False},
    ).json()


def test_fetch_pull_reviewers_parses_states_and_pending_requests(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _reviews_payload())
    reviews = github.fetch_github_pull_reviewers("acme", "api", 42)
    assert reviews == [
        {"login": "alice", "state": "APPROVED", "submitted_at": "2026-01-02T00:00:00Z", "requested": False},
        {"login": "bob", "state": "COMMENTED", "submitted_at": "2026-01-01T00:00:00Z", "requested": False},
        {"login": "carol", "state": "PENDING", "submitted_at": None, "requested": True},
    ]


def test_fetch_pull_reviewers_lists_each_reviewer_once(monkeypatch):
    payload = json.dumps(
        {
            "reviews": [
                {"state": "COMMENTED", "submittedAt": "2026-01-01T00:00:00Z", "author": {"login": "alice"}},
                {"state": "APPROVED", "submittedAt": "2026-01-02T00:00:00Z", "author": {"login": "bob"}},
                {"state": "APPROVED", "submittedAt": "2026-01-03T00:00:00Z", "author": {"login": "alice"}},
                {"state": "COMMENTED", "submittedAt": "2026-01-04T00:00:00Z", "author": {"login": "alice"}},
                {"state": "CHANGES_REQUESTED", "submittedAt": "2026-01-05T00:00:00Z", "author": {"login": "bob"}},
            ],
            "reviewRequests": [{"__typename": "User", "login": "carol"}],
        }
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)
    assert github.fetch_github_pull_reviewers("acme", "api", 42) == [
        # A later plain comment does not undo Alice's approval; Bob's newest
        # decisive state replaces his earlier one; each keeps their last time.
        {"login": "alice", "state": "APPROVED", "submitted_at": "2026-01-04T00:00:00Z", "requested": False},
        {"login": "bob", "state": "CHANGES_REQUESTED", "submitted_at": "2026-01-05T00:00:00Z", "requested": False},
        {"login": "carol", "state": "PENDING", "submitted_at": None, "requested": True},
    ]


def test_fetch_pull_reviewers_marks_a_re_requested_reviewer_pending(monkeypatch):
    payload = json.dumps(
        {
            "reviews": [
                {"state": "APPROVED", "submittedAt": "2026-01-02T00:00:00Z", "author": {"login": "alice"}},
            ],
            "reviewRequests": [{"__typename": "User", "login": "alice"}],
        }
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)
    # The reviewer reviewed before and is asked again: one row says they owe a
    # review, and still carries when they last reviewed.
    assert github.fetch_github_pull_reviewers("acme", "api", 42) == [
        {"login": "alice", "state": "PENDING", "submitted_at": "2026-01-02T00:00:00Z", "requested": True},
    ]


def test_fetch_pull_reviewers_is_none_when_gh_cannot_run(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.fetch_github_pull_reviewers("acme", "api", 42) is None


def test_github_reviewers_endpoint_lists_reviews(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _reviews_payload())
    with TestClient(app) as client:
        item = _pr(client)
        body = client.get(f"/api/items/{item['id']}/reviewers").json()
        assert [review["login"] for review in body["reviewers"]] == ["alice", "bob", "carol"]
        assert body["reviewers"][2]["requested"] is True
        assert body["error"] is None

        issue = client.post("/api/items", json={"url": "https://github.com/acme/api/issues/7", "fetch": False}).json()
        assert client.get(f"/api/items/{issue['id']}/reviewers").json() == {"reviewers": [], "error": None}

        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/items/{issue['id']}")


def test_github_reviewers_endpoint_reports_a_failed_read(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    with TestClient(app) as client:
        item = _pr(client)
        body = client.get(f"/api/items/{item['id']}/reviewers").json()
        assert body["reviewers"] == []
        assert "gh" in body["error"]
        client.delete(f"/api/items/{item['id']}")


def test_poke_sends_the_review_request_to_the_mapped_slack_user(monkeypatch):
    sent: dict = {}

    def fake_send(user_id, text, **kwargs):
        sent.update(user_id=user_id, text=text, **kwargs)
        return {"ok": True, "ts": "1700000000.000000"}

    monkeypatch.setattr(items_router, "slack_send_dm", fake_send)
    with TestClient(app) as client:
        item = _pr(client)
        person = client.post(
            "/api/people",
            json={"name": "Alice Poke", "aliases": ["alice-poke", "U0123ABCDEF"]},
        ).json()["id"]
        body = client.post(f"/api/items/{item['id']}/poke", json={"login": "alice-poke"}).json()
        assert body == {
            "login": "alice-poke",
            "slack_user_id": "U0123ABCDEF",
            "name": "Alice Poke",
            "ts": "1700000000.000000",
        }
        assert sent["user_id"] == "U0123ABCDEF"
        # The PR link is the message, so Slack is told not to expand it.
        assert sent["unfurl"] is False
        assert sent["text"] == (
            ":wave::robot_face: I would love your review on this PR: "
            "<https://github.com/acme/api/pull/42|Fix the parser>"
        )
        client.delete(f"/api/people/{person}")
        client.delete(f"/api/items/{item['id']}")


def test_poke_resolves_a_slack_handle_alias(monkeypatch):
    monkeypatch.setattr(
        shell,
        "_run_cli",
        lambda cmd, timeout=60: json.dumps({"users": [{"id": "U0HANDLE1", "name": "alice-slack-handle"}]}),
    )
    monkeypatch.setattr(items_router, "slack_send_dm", lambda user_id, text, **kwargs: {"ok": True, "ts": "1.0"})
    with TestClient(app) as client:
        item = _pr(client)
        person = client.post(
            "/api/people",
            json={"name": "Alice Handle", "aliases": ["alice-gh-handle", "alice-slack-handle"]},
        ).json()["id"]
        body = client.post(f"/api/items/{item['id']}/poke", json={"login": "alice-gh-handle"}).json()
        assert body["slack_user_id"] == "U0HANDLE1"
        client.delete(f"/api/people/{person}")
        client.delete(f"/api/items/{item['id']}")


def test_poke_explains_what_is_missing(monkeypatch):
    # Keep the Slack handle fallback off the network: no cached user matches.
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: json.dumps({"users": []}))
    with TestClient(app) as client:
        item = _pr(client)
        # Nobody carries the login.
        missing_person = client.post(f"/api/items/{item['id']}/poke", json={"login": "ghost-missing"})
        assert missing_person.status_code == 400
        assert "No person carries" in missing_person.json()["detail"]

        # A person exists, but no Slack id or handle among their aliases.
        bob = client.post("/api/people", json={"name": "Bob Missing", "aliases": ["bob-missing"]}).json()["id"]
        missing_slack = client.post(f"/api/items/{item['id']}/poke", json={"login": "bob-missing"})
        assert missing_slack.status_code == 400
        assert "Slack user id" in missing_slack.json()["detail"]

        # An issue is not a PR, so there is no review to ask for.
        issue = client.post("/api/items", json={"url": "https://github.com/acme/api/issues/7", "fetch": False}).json()
        assert client.post(f"/api/items/{issue['id']}/poke", json={"login": "ghost"}).status_code == 400

        client.delete(f"/api/people/{bob}")
        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/items/{issue['id']}")


def test_poke_reports_slack_refusing_the_message(monkeypatch):
    monkeypatch.setattr(
        items_router,
        "slack_send_dm",
        lambda user_id, text, **kwargs: (_ for _ in ()).throw(
            slack.SlackError("Slack refused the message: channel_not_found")
        ),
    )
    with TestClient(app) as client:
        item = _pr(client)
        person = client.post(
            "/api/people", json={"name": "Alice Refused", "aliases": ["alice-refused", "U0123ABCDEG"]}
        ).json()["id"]
        response = client.post(f"/api/items/{item['id']}/poke", json={"login": "alice-refused"})
        assert response.status_code == 502
        assert "channel_not_found" in response.json()["detail"]
        client.delete(f"/api/people/{person}")
        client.delete(f"/api/items/{item['id']}")
