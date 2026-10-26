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


def _checks_payload(nodes, rollup="FAILURE", total=None):
    return json.dumps(
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "commits": {
                            "nodes": [
                                {
                                    "commit": {
                                        "statusCheckRollup": {
                                            "state": rollup,
                                            "contexts": {
                                                "totalCount": len(nodes) if total is None else total,
                                                "nodes": nodes,
                                            },
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        }
    )


def test_fetch_pull_checks_lists_failing_checks_first(monkeypatch):
    seen: dict = {}
    nodes = [
        {
            "__typename": "CheckRun",
            "name": "lint",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "detailsUrl": "https://github.com/o/r/runs/1",
        },
        {
            "__typename": "CheckRun",
            "name": "build",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "detailsUrl": "https://github.com/o/r/runs/2",
        },
        {
            "__typename": "CheckRun",
            "name": "integration",
            "status": "IN_PROGRESS",
            "conclusion": None,
            "detailsUrl": "",
        },
        {
            "__typename": "StatusContext",
            "context": "ci/verify",
            "state": "ERROR",
            "description": "Verification failed",
            "targetUrl": "https://ci.example/verify",
        },
        {"__typename": "StatusContext", "context": "ci/docs", "state": "SUCCESS", "description": "", "targetUrl": ""},
        {"__typename": "CheckRun", "name": "", "status": "COMPLETED", "conclusion": "FAILURE"},
    ]

    def fake(cmd, timeout=60):
        seen["cmd"] = cmd
        return _checks_payload(nodes, total=8)

    monkeypatch.setattr(shell, "_run_cli", fake)
    report = github.fetch_pull_checks("o", "r", 12)

    assert report is not None
    assert report["rollup"] == "failure"
    assert report["total"] == 8
    assert [(check["name"], check["state"]) for check in report["checks"]] == [
        ("build", "failure"),
        ("ci/verify", "failure"),
        ("integration", "pending"),
        ("lint", "success"),
        ("ci/docs", "success"),
    ]
    verify = report["checks"][1]
    assert verify["description"] == "Verification failed"
    assert verify["url"] == "https://ci.example/verify"
    # A status context with no description falls back to a label; a check run
    # names its detail page.
    assert report["checks"][4]["description"] == "passed"
    assert report["checks"][0]["url"] == "https://github.com/o/r/runs/2"
    # gh needs a typed literal for the Int, not the string -f would send.
    assert "-F" in seen["cmd"]
    assert "number=12" in seen["cmd"]


def test_fetch_pull_checks_returns_none_when_github_fails(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.fetch_pull_checks("o", "r", 12) is None

    payload = json.dumps({"data": {"repository": {"pullRequest": None}}})
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)
    assert github.fetch_pull_checks("o", "r", 12) is None


def test_fetch_my_pull_checks_caches_and_reports_failure(monkeypatch):
    calls: list[tuple[str, str, int]] = []

    def fake(owner, repo, number):
        calls.append((owner, repo, number))
        return {
            "rollup": "failure",
            "checks": [{"name": "build", "state": "failure", "description": "failed", "url": ""}],
            "total": 1,
        }

    monkeypatch.setattr(my_pulls, "fetch_pull_checks", fake)
    my_pulls._checks_cache.clear()

    first = my_pulls.fetch_my_pull_checks("o", "r", 12)
    second = my_pulls.fetch_my_pull_checks("O", "R", 12)

    assert first["error"] is None
    assert first["checks"][0]["name"] == "build"
    assert second == first
    # The second read answers from the cache, casing aside; a refresh asks again.
    assert calls == [("o", "r", 12)]

    refreshed = my_pulls.fetch_my_pull_checks("o", "r", 12, refresh=True)
    assert refreshed["rollup"] == "failure"
    assert calls == [("o", "r", 12), ("o", "r", 12)]

    monkeypatch.setattr(my_pulls, "fetch_pull_checks", lambda owner, repo, number: None)
    my_pulls._checks_cache.clear()
    failed = my_pulls.fetch_my_pull_checks("o", "r", 12)
    assert failed["checks"] == []
    assert failed["error"] == my_pulls.CHECKS_UNREACHABLE_ERROR


def test_my_pull_checks_endpoint(monkeypatch):
    calls: list[bool] = []
    report = {
        "rollup": "failure",
        "checks": [{"name": "build", "state": "failure", "description": "failed", "url": "https://ci/1"}],
        "total": 1,
        "error": None,
    }

    def fake(owner, repo, number, refresh=False):
        calls.append(refresh)
        return report

    monkeypatch.setattr("agentic.routers.my_pulls.fetch_my_pull_checks", fake)

    with TestClient(app) as client:
        payload = client.get("/api/my-pulls/checks", params={"repository": "o/r", "number": 12}).json()
        refreshed = client.get(
            "/api/my-pulls/checks", params={"repository": "o/r", "number": 12, "refresh": "true"}
        ).json()

    assert payload["repository"] == "o/r"
    assert payload["number"] == 12
    assert payload["rollup"] == "failure"
    assert payload["checks"][0]["name"] == "build"
    assert payload["error"] is None
    assert refreshed["checks"] == payload["checks"]
    assert calls == [False, True]


def test_my_pull_checks_endpoint_rejects_bad_coordinates(monkeypatch):
    called: list[tuple] = []
    monkeypatch.setattr(
        "agentic.routers.my_pulls.fetch_my_pull_checks",
        lambda owner, repo, number, refresh=False: called.append((owner, repo, number)) or {},
    )

    with TestClient(app) as client:
        missing_repo = client.get("/api/my-pulls/checks", params={"repository": "", "number": 12})
        bad_repo = client.get("/api/my-pulls/checks", params={"repository": "not-a-repo", "number": 12})
        bad_number = client.get("/api/my-pulls/checks", params={"repository": "o/r", "number": 0})

    assert missing_repo.status_code == 400
    assert bad_repo.status_code == 400
    assert bad_number.status_code == 400
    assert called == []


def test_my_pull_checks_endpoint_reports_a_failed_read(monkeypatch):
    report = {"rollup": "none", "checks": [], "total": 0, "error": my_pulls.CHECKS_UNREACHABLE_ERROR}
    monkeypatch.setattr(
        "agentic.routers.my_pulls.fetch_my_pull_checks",
        lambda owner, repo, number, refresh=False: report,
    )

    with TestClient(app) as client:
        payload = client.get("/api/my-pulls/checks", params={"repository": "o/r", "number": 12}).json()

    assert payload["checks"] == []
    assert payload["error"] == my_pulls.CHECKS_UNREACHABLE_ERROR
