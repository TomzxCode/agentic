import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from agentic import my_pulls
from agentic.main import app
from agentic.services import github, shell


def _node(**overrides):
    node = {
        "number": 12,
        "title": "Fix the thing",
        "url": "https://github.com/o/r/pull/12",
        "isDraft": False,
        "createdAt": "2026-10-01T00:00:00Z",
        "updatedAt": "2026-10-02T00:00:00Z",
        "reviewDecision": "APPROVED",
        "repository": {"nameWithOwner": "o/r"},
        "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}]},
        "reviewThreads": {"totalCount": 2, "nodes": [{"isResolved": False}, {"isResolved": True}]},
        "latestOpinionatedReviews": {"nodes": [{"author": {"login": "alice"}, "state": "APPROVED"}]},
    }
    node.update(overrides)
    return node


def _payload(nodes):
    return json.dumps({"data": {"search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}})


def test_search_my_open_pulls_reduces_a_search_node(monkeypatch):
    seen: dict = {}

    def fake(cmd, timeout=60):
        seen["cmd"] = cmd
        return _payload([_node()])

    monkeypatch.setattr(shell, "_run_cli", fake)
    pulls = github.search_my_open_pulls("tomzx")

    assert pulls is not None
    assert pulls[0]["repository"] == "o/r"
    assert pulls[0]["number"] == 12
    assert pulls[0]["approved"] is True
    assert pulls[0]["approvers"] == ["alice"]
    assert pulls[0]["ci"] == "success"
    assert pulls[0]["open_threads"] == 1
    assert pulls[0]["threads_total"] == 2
    # One GraphQL search through gh, filtered to the login's own open PRs.
    assert seen["cmd"][:3] == ["gh", "api", "graphql"]
    assert any("author:tomzx" in part for part in seen["cmd"])


def test_search_my_open_pulls_maps_check_states(monkeypatch):
    nodes = [
        _node(number=1, commits={"nodes": [{"commit": {"statusCheckRollup": {"state": "FAILURE"}}}]}),
        _node(number=2, commits={"nodes": [{"commit": {"statusCheckRollup": {"state": "PENDING"}}}]}),
        _node(number=3, commits={"nodes": [{"commit": {"statusCheckRollup": {"state": "EXPECTED"}}}]}),
        _node(number=4, commits={"nodes": [{"commit": {"statusCheckRollup": None}}]}),
        _node(number=5, commits={"nodes": []}),
    ]
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _payload(nodes))

    pulls = github.search_my_open_pulls("tomzx")

    assert pulls is not None
    assert [pull["ci"] for pull in pulls] == ["failure", "pending", "pending", "none", "none"]


def test_search_my_open_pulls_only_counts_approved_opinionated_reviews(monkeypatch):
    node = _node(
        reviewDecision="CHANGES_REQUESTED",
        latestOpinionatedReviews={
            "nodes": [
                {"author": {"login": "alice"}, "state": "APPROVED"},
                {"author": {"login": "bob"}, "state": "CHANGES_REQUESTED"},
                {"author": {"login": "carol"}, "state": "DISMISSED"},
            ]
        },
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _payload([node]))

    pulls = github.search_my_open_pulls("tomzx")
    assert pulls is not None
    pull = pulls[0]

    assert pull["approvers"] == ["alice"]
    assert pull["approved"] is False
    assert pull["review_decision"] == "CHANGES_REQUESTED"


def test_search_my_open_pulls_returns_none_when_github_fails(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.search_my_open_pulls("tomzx") is None
    assert github.search_my_open_pulls("") is None


def test_search_my_open_pulls_reports_reviews_and_requested_reviewers(monkeypatch):
    # A review by anyone but the author counts, a comment review included;
    # the requested reviewers ride along for the inbox's poke.
    node = _node(
        reviewDecision="REVIEW_REQUIRED",
        latestOpinionatedReviews={"nodes": []},
        reviews={
            "totalCount": 1,
            "nodes": [{"author": {"login": "carol"}}],
        },
        reviewRequests={
            "totalCount": 2,
            "nodes": [
                {"requestedReviewer": {"login": "alice"}},
                {"requestedReviewer": {"name": "platform"}},
            ],
        },
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _payload([node]))

    pulls = github.search_my_open_pulls("tomzx")
    assert pulls is not None
    assert pulls[0]["reviewed"] is True
    assert pulls[0]["requested_reviewers"] == ["alice", "platform"]


def test_search_my_open_pulls_ignores_the_author_s_own_reviews(monkeypatch):
    # GitHub lets an author leave comment reviews on their own pull request;
    # those are not a review the pull request received.
    node = _node(
        reviewDecision="REVIEW_REQUIRED",
        latestOpinionatedReviews={"nodes": []},
        reviews={"totalCount": 2, "nodes": [{"author": {"login": "tomzx"}}, {"author": {"login": "TOMZX"}}]},
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _payload([node]))

    pulls = github.search_my_open_pulls("tomzx")
    assert pulls is not None
    assert pulls[0]["reviewed"] is False


def test_search_my_open_pulls_counts_an_overflowing_review_page_as_reviewed(monkeypatch):
    node = _node(
        reviews={"totalCount": 40, "nodes": [{"author": {"login": "tomzx"}} for _ in range(30)]},
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _payload([node]))

    pulls = github.search_my_open_pulls("tomzx")
    assert pulls is not None
    assert pulls[0]["reviewed"] is True


def test_pull_counts_summarizes_the_list():
    counts = my_pulls.pull_counts(
        [
            {"ci": "failure", "review_decision": "", "approved": False, "open_threads": 2, "draft": False},
            {
                "ci": "success",
                "review_decision": "CHANGES_REQUESTED",
                "approved": False,
                "open_threads": 0,
                "draft": True,
            },
            {"ci": "success", "review_decision": "APPROVED", "approved": True, "open_threads": 0, "draft": False},
        ]
    )
    assert counts == {
        "total": 3,
        "attention": 2,
        "approved": 1,
        "failing": 1,
        "open_threads": 2,
        "draft": 1,
    }


def test_fetch_my_pulls_reuses_the_short_cache(monkeypatch):
    calls: list[str] = []

    def fake(login):
        calls.append(login)
        return [
            {
                "repository": "o/r",
                "number": 1,
                "title": "T",
                "url": "",
                "draft": False,
                "created_at": None,
                "updated_at": None,
                "review_decision": "APPROVED",
                "approved": True,
                "approvers": ["alice"],
                "ci": "success",
                "open_threads": 0,
                "threads_total": 0,
            }
        ]

    monkeypatch.setattr(my_pulls, "search_my_open_pulls", fake)
    my_pulls._cache.clear()

    first = my_pulls.fetch_my_pulls("tomzx")
    second = my_pulls.fetch_my_pulls("tomzx")
    my_pulls.fetch_my_pulls("tomzx", refresh=True)

    assert first["counts"]["total"] == 1
    assert second == first
    # A reload reuses the cache; an explicit refresh asks GitHub again.
    assert calls == ["tomzx", "tomzx"]


def test_fetch_my_pulls_reports_a_failed_lookup(monkeypatch):
    monkeypatch.setattr(my_pulls, "search_my_open_pulls", lambda login: None)
    my_pulls._cache.clear()

    report = my_pulls.fetch_my_pulls("tomzx")

    assert report["pulls"] == []
    assert report["error"] == my_pulls.UNREACHABLE_ERROR


def test_fetch_my_pulls_without_a_login():
    report = my_pulls.fetch_my_pulls("")

    assert report["login"] == ""
    assert report["pulls"] == []
    assert report["error"] == my_pulls.NO_LOGIN_ERROR


def test_my_pulls_endpoint(monkeypatch):
    row = {
        "repository": "o/r",
        "number": 12,
        "title": "Fix the thing",
        "url": "https://github.com/o/r/pull/12",
        "draft": False,
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-02T00:00:00Z",
        "review_decision": "APPROVED",
        "approved": True,
        "approvers": ["alice"],
        "ci": "success",
        "open_threads": 1,
        "threads_total": 2,
    }
    monkeypatch.setattr("agentic.routers.my_pulls.resolve_github_login", lambda session: "tomzx")
    monkeypatch.setattr(my_pulls, "search_my_open_pulls", lambda login: [row])
    my_pulls._cache.clear()

    with TestClient(app) as client:
        payload = client.get("/api/my-pulls").json()

    assert payload["login"] == "tomzx"
    assert payload["error"] is None
    assert payload["counts"]["total"] == 1
    assert payload["counts"]["open_threads"] == 1
    assert payload["pulls"][0]["number"] == 12
    assert payload["pulls"][0]["approvers"] == ["alice"]


def test_my_pulls_endpoint_without_a_login(monkeypatch):
    monkeypatch.setattr("agentic.routers.my_pulls.resolve_github_login", lambda session: "")

    with TestClient(app) as client:
        payload = client.get("/api/my-pulls").json()

    assert payload["pulls"] == []
    assert payload["error"] == my_pulls.NO_LOGIN_ERROR


def test_my_pulls_poke_dms_each_requested_reviewer_once(monkeypatch):
    person = SimpleNamespace(id="p1", name="Alice")
    sent: list[tuple[str, str]] = []

    def fake_person(session, login):
        return person if login.lower() == "alice" else None

    monkeypatch.setattr("agentic.routers.my_pulls.person_for_alias", fake_person)
    monkeypatch.setattr("agentic.routers.my_pulls.resolve_slack_user_id", lambda aliases: "U123")
    monkeypatch.setattr(
        "agentic.routers.my_pulls.slack_send_dm",
        lambda user_id, text, unfurl=True: sent.append((user_id, text)) or {"ts": "1.2"},
    )

    with TestClient(app) as client:
        payload = client.post(
            "/api/my-pulls/poke",
            json={
                "repository": "o/r",
                "number": 12,
                "title": "Fix the thing",
                "url": "https://github.com/o/r/pull/12",
                "logins": ["alice", "ALICE", "bob"],
            },
        ).json()

    # The login list is deduplicated, so one reviewer is DM'd once; the second
    # name has no person behind it and is reported instead of stopping the rest.
    assert [entry["login"] for entry in payload["poked"]] == ["alice"]
    assert payload["poked"][0]["name"] == "Alice"
    assert payload["poked"][0]["slack_user_id"] == "U123"
    assert payload["poked"][0]["ts"] == "1.2"
    assert len(sent) == 1
    assert sent[0][0] == "U123"
    assert "https://github.com/o/r/pull/12" in sent[0][1]
    assert "Fix the thing" in sent[0][1]
    assert len(payload["failed"]) == 1
    assert payload["failed"][0]["login"] == "bob"
    assert "No person carries the GitHub login @bob" in payload["failed"][0]["reason"]


def test_my_pulls_poke_reports_a_reviewer_without_slack(monkeypatch):
    person = SimpleNamespace(id="p1", name="Alice")
    monkeypatch.setattr("agentic.routers.my_pulls.person_for_alias", lambda session, login: person)
    monkeypatch.setattr("agentic.routers.my_pulls.resolve_slack_user_id", lambda aliases: None)

    with TestClient(app) as client:
        payload = client.post(
            "/api/my-pulls/poke",
            json={"repository": "o/r", "number": 12, "logins": ["alice"]},
        ).json()

    assert payload["poked"] == []
    assert "no Slack user id" in payload["failed"][0]["reason"]


def test_my_pulls_poke_without_logins_is_rejected():
    with TestClient(app) as client:
        response = client.post("/api/my-pulls/poke", json={"repository": "o/r", "number": 12, "logins": []})

    assert response.status_code == 400
