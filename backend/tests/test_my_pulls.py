import json
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col

from agentic import my_pulls
from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.models.items import Association, SourceItem
from agentic.models.repositories import Repository
from agentic.models.tasks import Task
from agentic.services import github, shell


def _record(**overrides):
    record = {
        "number": 12,
        "title": "Fix the thing",
        "url": "https://github.com/o/r/pull/12",
        "isDraft": False,
        "createdAt": "2026-10-01T00:00:00Z",
        "updatedAt": "2026-10-02T00:00:00Z",
        "reviewDecision": "APPROVED",
        "author": {"login": "tomzx"},
        "checks": {"state": "SUCCESS", "total": 3},
        "reviewThreads": {"total": 2, "open": 1},
        "reviews": [{"author": {"login": "alice"}, "state": "APPROVED", "submittedAt": "2026-10-01T01:00:00Z"}],
        "reviewRequests": [],
    }
    record.update(overrides)
    return record


def _payload(records):
    return json.dumps(records)


def test_list_my_open_pulls_reduces_a_ghx_record(monkeypatch):
    seen: dict = {}

    def fake(cmd, timeout=60):
        seen["cmd"] = cmd
        return _payload([_record()])

    monkeypatch.setattr(shell, "_run_cli", fake)
    pulls = github.list_my_open_pulls(["o/r"], "tomzx")

    assert pulls is not None
    pull = pulls[0]
    assert pull["repository"] == "o/r"
    assert pull["number"] == 12
    assert pull["approved"] is True
    assert pull["approvers"] == ["alice"]
    assert pull["ci"] == "success"
    assert pull["open_threads"] == 1
    assert pull["threads_total"] == 2
    # One ghx listing per repository, kept to the login's own open PRs, with
    # the fields the row reads.
    assert seen["cmd"][:3] == ["ghx", "pr", "list"]
    assert "--author" in seen["cmd"] and "tomzx" in seen["cmd"]
    assert "--state" in seen["cmd"] and "open" in seen["cmd"]
    assert "reviewThreads" in seen["cmd"][-1]
    assert "checks" in seen["cmd"][-1]


def test_list_my_open_pulls_maps_check_states(monkeypatch):
    records = [
        _record(number=1, checks={"state": "FAILURE", "total": 1}),
        _record(number=2, checks={"state": "PENDING", "total": 1}),
        _record(number=3, checks={"state": "EXPECTED", "total": 1}),
        _record(number=4, checks={"state": "ERROR", "total": 1}),
        _record(number=5, checks=None),
    ]
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _payload(records))

    pulls = github.list_my_open_pulls(["o/r"], "tomzx")

    assert pulls is not None
    assert [pull["ci"] for pull in pulls] == ["failure", "pending", "pending", "failure", "none"]


def test_list_my_open_pulls_only_counts_approved_decisive_reviews(monkeypatch):
    record = _record(
        reviewDecision="CHANGES_REQUESTED",
        reviews=[
            {"author": {"login": "alice"}, "state": "APPROVED"},
            {"author": {"login": "bob"}, "state": "CHANGES_REQUESTED"},
            # A later plain comment does not drop the approval.
            {"author": {"login": "alice"}, "state": "COMMENTED"},
            {"author": {"login": "carol"}, "state": "DISMISSED"},
            # The latest decisive review wins.
            {"author": {"login": "carol"}, "state": "APPROVED"},
        ],
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _payload([record]))

    pulls = github.list_my_open_pulls(["o/r"], "tomzx")
    assert pulls is not None
    pull = pulls[0]

    assert pull["approvers"] == ["alice", "carol"]
    assert pull["approved"] is False
    assert pull["review_decision"] == "CHANGES_REQUESTED"


def test_list_my_open_pulls_returns_none_when_every_repository_fails(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.list_my_open_pulls(["o/r"], "tomzx") is None
    assert github.list_my_open_pulls(["o/r"], "") is None
    # No repositories is an empty read, not a failure.
    assert github.list_my_open_pulls([], "tomzx") == []


def test_list_my_open_pulls_keeps_a_failed_repository_out_of_the_rows(monkeypatch):
    def fake(cmd, timeout=60):
        if "o/broken" in cmd:
            return None
        return _payload([_record(number=1)])

    monkeypatch.setattr(shell, "_run_cli", fake)
    pulls = github.list_my_open_pulls(["o/broken", "o/r"], "tomzx")

    assert pulls is not None
    assert [pull["number"] for pull in pulls] == [1]
    assert pulls[0]["repository"] == "o/r"


def test_list_my_open_pulls_merges_repositories_newest_update_first(monkeypatch):
    seen: list[str] = []
    lock = threading.Lock()

    def fake(cmd, timeout=60):
        repo = cmd[cmd.index("--repo") + 1]
        with lock:
            seen.append(repo)
        if repo == "o/first":
            return _payload([_record(number=1, updatedAt="2026-10-05T00:00:00Z")])
        return _payload([_record(number=2, updatedAt="2026-10-09T00:00:00Z")])

    monkeypatch.setattr(shell, "_run_cli", fake)
    pulls = github.list_my_open_pulls(["o/first", "o/second"], "tomzx")

    assert pulls is not None
    assert [pull["number"] for pull in pulls] == [2, 1]
    assert sorted(seen) == ["o/first", "o/second"]


def test_list_my_open_pulls_reports_reviews_and_requested_reviewers(monkeypatch):
    # A review by anyone but the author counts, a comment review included; a
    # pending review is not a submission yet; the requested reviewers ride along
    # for the inbox's poke.
    record = _record(
        reviewDecision="REVIEW_REQUIRED",
        reviews=[
            {"author": {"login": "carol"}, "state": "COMMENTED"},
            {"author": {"login": "dave"}, "state": "PENDING"},
        ],
        reviewRequests=[
            {"type": "User", "login": "alice"},
            {"type": "Team", "name": "platform"},
        ],
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _payload([record]))

    pulls = github.list_my_open_pulls(["o/r"], "tomzx")
    assert pulls is not None
    assert pulls[0]["reviewed"] is True
    assert pulls[0]["requested_reviewers"] == ["alice", "platform"]


def test_list_my_open_pulls_ignores_the_author_s_own_reviews(monkeypatch):
    # GitHub lets an author leave comment reviews on their own pull request;
    # those are not a review the pull request received.
    record = _record(
        reviewDecision="REVIEW_REQUIRED",
        reviews=[
            {"author": {"login": "tomzx"}, "state": "COMMENTED"},
            {"author": {"login": "TOMZX"}, "state": "COMMENTED"},
        ],
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: _payload([record]))

    pulls = github.list_my_open_pulls(["o/r"], "tomzx")
    assert pulls is not None
    assert pulls[0]["reviewed"] is False


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


def _row(number=1, repository="o/r"):
    return {
        "repository": repository,
        "number": number,
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


def test_fetch_my_pulls_reuses_the_short_cache(monkeypatch):
    calls: list[tuple[tuple[str, ...], str]] = []
    refreshed: list[list[str]] = []

    def fake(repositories, login):
        calls.append((tuple(repositories), login))
        return [_row()]

    monkeypatch.setattr(my_pulls, "list_my_open_pulls", fake)
    monkeypatch.setattr(my_pulls, "_refresh_repositories", lambda repositories: refreshed.append(list(repositories)))
    my_pulls._cache.clear()

    first = my_pulls.fetch_my_pulls("tomzx", ["o/r"])
    second = my_pulls.fetch_my_pulls("tomzx", ["o/r"])
    my_pulls.fetch_my_pulls("tomzx", ["o/r"], refresh=True)

    assert first["counts"]["total"] == 1
    assert second == first
    # A reload reuses the cache; an explicit refresh reads again. Both read
    # paths refresh the repositories' ghx caches first.
    assert calls == [(("o/r",), "tomzx")] * 2
    assert refreshed == [["o/r"], ["o/r"]]


def _warm_calls(monkeypatch, cached):
    """Record cache refreshes and report *cached* as the warmable repositories."""
    calls: list[dict] = []

    def fake(owner, repo, timeout=300, types="both"):
        calls.append({"repository": f"{owner}/{repo}", "timeout": timeout, "types": types})
        return True

    monkeypatch.setattr(my_pulls, "refresh_github_cache", fake)
    monkeypatch.setattr(my_pulls, "list_cached_repositories", lambda: cached)
    monkeypatch.setattr(my_pulls, "list_my_open_pulls", lambda repositories, login: [])
    my_pulls._cache.clear()
    my_pulls._cache_refreshed.clear()
    return calls


def test_fetch_my_pulls_refreshes_a_completed_cache_without_forcing(monkeypatch):
    calls = _warm_calls(monkeypatch, {"o/r"})

    my_pulls.fetch_my_pulls("tomzx", ["o/r"])

    # A page load reads a pull-request delta, not a full fetch.
    assert calls == [{"repository": "o/r", "timeout": my_pulls.CACHE_REFRESH_TIMEOUT, "types": "prs"}]


def test_fetch_my_pulls_leaves_a_repository_without_a_cache_alone(monkeypatch):
    calls = _warm_calls(monkeypatch, set())

    my_pulls.fetch_my_pulls("tomzx", ["o/r"])

    # `ghx cache` on this repository would walk its whole history, so the
    # listing's own API read has to cover it.
    assert calls == []


def test_fetch_my_pulls_skips_the_refresh_when_the_caches_cannot_be_listed(monkeypatch):
    calls = _warm_calls(monkeypatch, None)

    my_pulls.fetch_my_pulls("tomzx", ["o/r"])

    assert calls == []


def test_fetch_my_pulls_refreshes_one_repository_once_per_window(monkeypatch):
    calls = _warm_calls(monkeypatch, {"o/r", "o/s"})

    my_pulls.fetch_my_pulls("tomzx", ["o/r", "o/s"])
    my_pulls.fetch_my_pulls("tomzx", ["o/r", "o/s"], refresh=True)

    # The page cache is bypassed, the repository window still holds, so one
    # reload does not run a delta per repository again.
    assert sorted(call["repository"] for call in calls) == ["o/r", "o/s"]


def test_fetch_my_pulls_waits_longer_after_a_failed_refresh(monkeypatch):
    _warm_calls(monkeypatch, {"o/r"})
    monkeypatch.setattr(my_pulls, "refresh_github_cache", lambda *args, **kwargs: False)

    my_pulls.fetch_my_pulls("tomzx", ["o/r"])

    wait = my_pulls._cache_refreshed["o/r"] - time.monotonic()
    assert wait > my_pulls.CACHE_REFRESH_INTERVAL
    assert wait <= my_pulls.CACHE_REFRESH_RETRY


def test_fetch_my_pulls_keeps_a_changed_repository_set_apart(monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake(repositories, login):
        calls.append(tuple(repositories))
        return [_row()]

    monkeypatch.setattr(my_pulls, "list_my_open_pulls", fake)
    monkeypatch.setattr(my_pulls, "_refresh_repositories", lambda repositories: None)
    my_pulls._cache.clear()

    my_pulls.fetch_my_pulls("tomzx", ["o/r"])
    my_pulls.fetch_my_pulls("tomzx", ["o/r", "o/s"])

    # Registering a repository must not answer from the previous list.
    assert calls == [("o/r",), ("o/r", "o/s")]


def test_fetch_my_pulls_reports_a_failed_lookup(monkeypatch):
    monkeypatch.setattr(my_pulls, "list_my_open_pulls", lambda repositories, login: None)
    monkeypatch.setattr(my_pulls, "_refresh_repositories", lambda repositories: None)
    my_pulls._cache.clear()

    report = my_pulls.fetch_my_pulls("tomzx", ["o/r"])

    assert report["pulls"] == []
    assert report["error"] == my_pulls.UNREACHABLE_ERROR


def test_fetch_my_pulls_without_a_login():
    report = my_pulls.fetch_my_pulls("", ["o/r"])

    assert report["login"] == ""
    assert report["pulls"] == []
    assert report["error"] == my_pulls.NO_LOGIN_ERROR


def test_fetch_my_pulls_without_repositories():
    report = my_pulls.fetch_my_pulls("tomzx", [])

    assert report["pulls"] == []
    assert report["error"] == my_pulls.NO_REPOSITORIES_ERROR


def test_known_github_repositories_reads_registered_remotes():
    create_db_and_tables()
    repositories = [
        Repository(name="one", path="/tmp/one", remote_url="git@github.com:o/r.git"),
        Repository(name="again", path="/tmp/again", remote_url="https://github.com/O/R"),
        Repository(name="other", path="/tmp/other", remote_url="https://gitlab.com/o/s.git"),
        Repository(name="plain", path="/tmp/plain"),
    ]
    with Session(engine) as session:
        for repository in repositories:
            session.add(repository)
        session.commit()
        try:
            names = my_pulls.known_github_repositories(session)
        finally:
            for repository in repositories:
                session.delete(repository)
            session.commit()

    assert names == ["o/r"]


def _endpoint_row(number=12, repository="o/r"):
    return {
        "repository": repository,
        "number": number,
        "title": "Fix the thing",
        "url": f"https://github.com/{repository}/pull/{number}",
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


def _with_my_pulls(monkeypatch, rows):
    """Point the endpoint at one login and one known repository."""
    monkeypatch.setattr("agentic.routers.my_pulls.resolve_github_login", lambda session: "tomzx")
    monkeypatch.setattr("agentic.routers.my_pulls.known_github_repositories", lambda session: ["o/r"])
    monkeypatch.setattr(my_pulls, "list_my_open_pulls", lambda repositories, login: rows)
    monkeypatch.setattr(my_pulls, "_refresh_repositories", lambda repositories: None)
    my_pulls._cache.clear()


def test_my_pulls_endpoint(monkeypatch):
    _with_my_pulls(monkeypatch, [_endpoint_row()])

    with TestClient(app) as client:
        payload = client.get("/api/my-pulls").json()

    assert payload["login"] == "tomzx"
    assert payload["error"] is None
    assert payload["counts"]["total"] == 1
    assert payload["counts"]["open_threads"] == 1
    assert payload["pulls"][0]["number"] == 12
    assert payload["pulls"][0]["approvers"] == ["alice"]


def test_my_pulls_endpoint_links_each_pull_to_its_tasks(monkeypatch):
    """A tracked PR shows the tasks its item is associated with.

    The links are resolved per request, so linking a task after the GitHub read
    was cached shows without a refresh. The item's casing need not match
    GitHub's ``nameWithOwner`` casing.
    """
    create_db_and_tables()
    _with_my_pulls(monkeypatch, [_endpoint_row(repository="O/R")])

    with Session(engine) as session:
        task = Task(title="Fix the thing")
        item = SourceItem(
            source="github",
            kind="pull_request",
            external_id="o/r#12",
            url="https://github.com/o/r/pull/12",
        )
        session.add(task)
        session.add(item)
        session.commit()
        session.refresh(task)
        session.refresh(item)
        task_id = task.id
        item_id = item.id

    try:
        with TestClient(app) as client:
            # Nothing links the pull request yet, even though the read is cached now.
            assert client.get("/api/my-pulls").json()["pulls"][0]["tasks"] == []

            with Session(engine) as session:
                session.add(Association(task_id=task_id, item_id=item_id))
                session.commit()

            payload = client.get("/api/my-pulls").json()

        assert payload["pulls"][0]["tasks"] == [{"id": task_id, "title": "Fix the thing", "status": "open"}]
    finally:
        with Session(engine) as session:
            session.exec(sa_delete(Association).where(col(Association.task_id) == task_id))
            session.exec(sa_delete(SourceItem).where(col(SourceItem.id) == item_id))
            session.exec(sa_delete(Task).where(col(Task.id) == task_id))
            session.commit()


def test_my_pulls_endpoint_without_a_login(monkeypatch):
    monkeypatch.setattr("agentic.routers.my_pulls.resolve_github_login", lambda session: "")

    with TestClient(app) as client:
        payload = client.get("/api/my-pulls").json()

    assert payload["pulls"] == []
    assert payload["error"] == my_pulls.NO_LOGIN_ERROR


def test_my_pulls_endpoint_without_repositories(monkeypatch):
    monkeypatch.setattr("agentic.routers.my_pulls.resolve_github_login", lambda session: "tomzx")
    monkeypatch.setattr("agentic.routers.my_pulls.known_github_repositories", lambda session: [])

    with TestClient(app) as client:
        payload = client.get("/api/my-pulls").json()

    assert payload["pulls"] == []
    assert payload["error"] == my_pulls.NO_REPOSITORIES_ERROR


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


def _checks_payload(checks, rollup="FAILURE", total=None):
    return json.dumps({"state": rollup, "total": len(checks) if total is None else total, "checks": checks})


def test_fetch_pull_checks_lists_failing_checks_first(monkeypatch):
    seen: dict = {}
    checks = [
        {
            "type": "CheckRun",
            "name": "lint",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "url": "https://github.com/o/r/runs/1",
        },
        {
            "type": "CheckRun",
            "name": "build",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "url": "https://github.com/o/r/runs/2",
        },
        {
            "type": "CheckRun",
            "name": "integration",
            "status": "IN_PROGRESS",
            "conclusion": "",
            "url": "",
        },
        {
            "type": "StatusContext",
            "name": "ci/verify",
            "state": "ERROR",
            "description": "Verification failed",
            "url": "https://ci.example/verify",
        },
        {"type": "StatusContext", "name": "ci/docs", "state": "SUCCESS", "description": "", "url": ""},
        {"type": "CheckRun", "name": "", "status": "COMPLETED", "conclusion": "FAILURE"},
    ]

    def fake(cmd, timeout=60):
        seen["cmd"] = cmd
        return _checks_payload(checks, total=8)

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
    # The checks read goes through ghx, not gh.
    assert seen["cmd"][:3] == ["ghx", "pr", "checks"]
    assert "o/r" in seen["cmd"]


def test_fetch_pull_checks_returns_none_when_ghx_fails(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.fetch_pull_checks("o", "r", 12) is None

    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: "not json")
    assert github.fetch_pull_checks("o", "r", 12) is None

    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: json.dumps([1, 2]))
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
