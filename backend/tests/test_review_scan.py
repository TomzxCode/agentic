"""The review scan: which pull requests await the user's review."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from agentic import review_scan
from agentic.config import settings
from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.models.repositories import Repository, ReviewScanPolicy
from agentic.models.reviews import ReviewRequest
from agentic.services import shell


def _entry(repository: str, number: int, author: str = "alice", **over) -> dict:
    """One ``ghx search prs --json`` result."""
    return {
        "number": number,
        "title": over.get("title", f"PR {number}"),
        "url": f"https://github.com/{repository}/pull/{number}",
        "state": over.get("state", "OPEN"),
        "isDraft": over.get("isDraft", False),
        "repository": {"name": repository.split("/")[-1], "nameWithOwner": repository},
        "author": {"login": author},
        "createdAt": over.get("createdAt", "2026-10-01T00:00:00Z"),
    }


def _fake_search(requested: list[dict], reviewed: list[dict]):
    """A ``shell._run_cli`` stand-in that answers the two searches."""

    def fake(cmd: list[str], timeout: int = 60) -> str | None:
        if "--review-requested" in cmd:
            return json.dumps(requested)
        if "--reviewed-by" in cmd:
            return json.dumps(reviewed)
        return None

    return fake


@pytest.fixture
def session():
    """A session with the scan tables emptied, so a test starts from nothing."""
    create_db_and_tables()
    with Session(engine) as session:
        for row in session.exec(select(ReviewRequest)).all():
            session.delete(row)
        # Only the repositories this module creates carry the "scan-" prefix, so
        # other suites' fixtures are left alone.
        for repository in session.exec(select(Repository)).all():
            if repository.name.startswith("scan-"):
                session.delete(repository)
        session.commit()
        yield session


def _repository(session: Session, owner_repo: str, policy: str) -> Repository:
    repository = Repository(
        name=f"scan-{owner_repo.replace('/', '-')}",
        path=f"/tmp/{owner_repo.replace('/', '-')}",
        remote_url=f"https://github.com/{owner_repo}.git",
        review_scan=policy,
    )
    session.add(repository)
    session.commit()
    return repository


def test_scan_interval_parsing():
    assert review_scan.scan_interval("1h") == timedelta(hours=1)
    assert review_scan.scan_interval("30m") == timedelta(minutes=30)
    assert review_scan.scan_interval("") is None
    assert review_scan.scan_interval("   ") is None
    assert review_scan.scan_interval("off") is None
    assert review_scan.scan_interval("nonsense") is None


def test_scan_due():
    now = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    assert review_scan.scan_due(None, timedelta(hours=1), now) is True
    assert review_scan.scan_due(now - timedelta(minutes=30), timedelta(hours=1), now) is False
    assert review_scan.scan_due(now - timedelta(hours=2), timedelta(hours=1), now) is True
    # No cadence means the scan never becomes due.
    assert review_scan.scan_due(None, None, now) is False


def test_include_repository():
    include = ReviewScanPolicy.include.value
    exclude = ReviewScanPolicy.exclude.value
    default = ReviewScanPolicy.default.value
    policies = {"o/a": include, "o/b": exclude, "o/d": default}

    # A repository's own policy wins over the app-wide default, in both directions.
    assert review_scan.include_repository("O/A", policies, exclude) is True
    assert review_scan.include_repository("o/b", policies, include) is False
    # No policy (or an explicit "default") follows the app-wide default.
    assert review_scan.include_repository("o/c", policies, include) is True
    assert review_scan.include_repository("o/c", policies, exclude) is False
    assert review_scan.include_repository("o/d", policies, include) is True
    assert review_scan.include_repository("o/d", policies, exclude) is False


def test_search_awaiting_reviews_merges_and_filters(monkeypatch):
    requested = [
        _entry("o/a", 1),
        _entry("o/a", 2),
        _entry("o/b", 3, author="dependabot[bot]"),
        {"number": None},  # no pull request named
    ]
    reviewed = [_entry("o/a", 2, title="seen twice"), _entry("o/c", 4, isDraft=True)]
    monkeypatch.setattr(shell, "_run_cli", _fake_search(requested, reviewed))

    rows = review_scan.search_awaiting_reviews(50, review_scan.parse_exclude_authors("dependabot[bot]"))
    assert rows is not None
    assert [(row["repository"], row["number"], row["source"]) for row in rows] == [
        ("o/a", 1, "requested"),
        ("o/a", 2, "requested"),
        ("o/c", 4, "reviewed"),
    ]
    # The requested search wins for a pull request both searches return.
    assert rows[1]["title"] == "PR 2"
    assert rows[2]["draft"] is True
    assert rows[0]["state"] == "OPEN"
    assert rows[0]["url"] == "https://github.com/o/a/pull/1"


def test_search_awaiting_reviews_tolerates_one_failing_search(monkeypatch):
    def fake(cmd: list[str], timeout: int = 60) -> str | None:
        return json.dumps([_entry("o/a", 1)]) if "--review-requested" in cmd else None

    monkeypatch.setattr(shell, "_run_cli", fake)
    rows = review_scan.search_awaiting_reviews(50, set())
    assert rows is not None and [row["number"] for row in rows] == [1]


def test_search_awaiting_reviews_is_none_when_ghx_cannot_run(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert review_scan.search_awaiting_reviews(50, set()) is None


def test_run_review_scan_stores_the_filtered_set_and_removes_the_rest(session, monkeypatch):
    _repository(session, "o/a", ReviewScanPolicy.include.value)
    _repository(session, "o/b", ReviewScanPolicy.exclude.value)
    _repository(session, "o/c", ReviewScanPolicy.default.value)
    monkeypatch.setattr(
        shell,
        "_run_cli",
        _fake_search([_entry("o/a", 1), _entry("o/b", 2), _entry("o/c", 3)], []),
    )

    report = review_scan.run_review_scan(session, origin="manual", force=True)
    assert report == {"found": 3, "stored": 2, "removed": 0}
    stored = {(row.repository, row.number, row.source) for row in session.exec(select(ReviewRequest)).all()}
    assert stored == {("o/a", 1, "requested"), ("o/c", 3, "requested")}

    state = review_scan.review_scan_state(session)
    assert state["stored"] == 2 and state["found"] == 3 and state["kept"] == 2
    assert state["last_run_at"] is not None and state["origin"] == "manual"
    assert state["error"] is None

    # A pull request that is no longer awaiting a review is dropped, and the one
    # that stays keeps the time it was first seen.
    first_seen = {row.repository: row.first_seen_at for row in session.exec(select(ReviewRequest)).all()}
    monkeypatch.setattr(shell, "_run_cli", _fake_search([_entry("o/a", 1)], []))
    assert review_scan.run_review_scan(session, force=True) == {"found": 1, "stored": 1, "removed": 1}
    rows = session.exec(select(ReviewRequest)).all()
    assert [(row.repository, row.number) for row in rows] == [("o/a", 1)]
    assert rows[0].first_seen_at == first_seen["o/a"]


def test_run_review_scan_keeps_the_set_when_ghx_fails(session, monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", _fake_search([_entry("o/a", 1)], []))
    review_scan.run_review_scan(session, force=True)

    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    report = review_scan.run_review_scan(session, force=True)
    assert "error" in report
    # The stored set survives, so a broken ghx never empties the queue.
    assert [row.number for row in session.exec(select(ReviewRequest)).all()] == [1]
    assert review_scan.review_scan_state(session)["error"]


def test_run_review_scan_skips_when_the_cadence_is_off(session, monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", _fake_search([_entry("o/a", 1)], []))
    from agentic.models.system import Setting
    from agentic.settings_store import update_settings

    update_settings(session, {"review_scan_interval": ""})
    try:
        assert review_scan.run_review_scan(session) == {"skipped": "off"}
        assert review_scan.run_due_review_scan(session) == {"skipped": "not-due"}
        # force bypasses the cadence, which is what "Scan now" does.
        assert review_scan.run_review_scan(session, force=True)["stored"] == 1
    finally:
        row = session.get(Setting, "review_scan_interval")
        if row is not None:
            session.delete(row)
            session.commit()


def test_scan_endpoints_and_queue_union(session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    monkeypatch.setattr(shell, "_run_cli", _fake_search([_entry("o/a", 1, title="Awaiting review")], []))
    with TestClient(app) as client:
        state = client.get("/api/reviews/scan").json()
        assert state["enabled"] is True and state["stored"] == 0

        scanned = client.post("/api/reviews/scan").json()
        assert scanned["stored"] == 1 and scanned["found"] == 1

        queue = client.get("/api/reviews").json()
        assert queue["counts"]["total"] == 1
        row = queue["prs"][0]
        assert (row["repository"], row["number"]) == ("o/a", 1)
        assert row["title"] == "Awaiting review"
        assert row["request_source"] == "requested"
        assert row["steps"] == {} and row["head_commit"] == ""
        assert row["readiness"] == "yellow"


def test_repository_review_scan_policy_patch(session, monkeypatch, tmp_path):
    """A repository's scan policy is editable, and only with a known value."""
    (tmp_path / ".git").mkdir()
    with TestClient(app) as client:
        repository = client.post("/api/repositories", json={"path": str(tmp_path)}).json()
        assert repository["review_scan"] == "default"

        patched = client.patch(f"/api/repositories/{repository['id']}", json={"review_scan": "exclude"}).json()
        assert patched["review_scan"] == "exclude"
        assert (
            client.patch(f"/api/repositories/{repository['id']}", json={"review_scan": "include"}).json()["review_scan"]
            == "include"
        )
        assert (
            client.patch(f"/api/repositories/{repository['id']}", json={"review_scan": "sometimes"}).status_code == 422
        )
        assert client.patch("/api/repositories/missing", json={"review_scan": "include"}).status_code == 404

        client.delete(f"/api/repositories/{repository['id']}")


def test_scan_endpoint_records_a_gh_failure(session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    with TestClient(app) as client:
        result = client.post("/api/reviews/scan").json()
    assert result["error"] and result["stored"] == 0
