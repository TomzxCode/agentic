from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agentic.cycle_time import (
    ISSUE_CLOSE,
    REVIEW_TO_MERGE,
    REVIEW_WAIT,
    Interval,
    IssueRecord,
    PullRecord,
    Review,
    ReviewRequest,
    bucket_intervals,
    build_series_for,
    issue_close_intervals,
    review_to_merge_intervals,
    review_wait_intervals,
)
from agentic.main import app

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _hours(value: float) -> timedelta:
    return timedelta(hours=value)


def test_issue_close_uses_only_issues_closed_in_the_window():
    issues = [
        IssueRecord(number=1, created_at=NOW - _hours(10), closed_at=NOW - _hours(4)),
        IssueRecord(number=2, created_at=NOW - _hours(100), closed_at=NOW - _hours(90)),
    ]
    intervals = issue_close_intervals(issues, since=NOW - _hours(24))
    assert [interval.hours for interval in intervals] == [6]


def test_review_wait_runs_from_the_first_request_to_the_first_review():
    pulls = [
        PullRecord(
            number=1,
            created_at=NOW - _hours(10),
            merged_at=NOW,
            review_requests=(
                ReviewRequest(reviewer="bob", requested_at=NOW - _hours(8)),
                ReviewRequest(reviewer="carol", requested_at=NOW - _hours(9)),
            ),
            reviews=(
                Review(author="bob", submitted_at=NOW - _hours(5)),
                Review(author="carol", submitted_at=NOW - _hours(7)),
            ),
        )
    ]
    intervals = review_wait_intervals(pulls)
    assert [interval.hours for interval in intervals] == [2]


def test_review_wait_uses_the_first_review_after_the_request():
    pulls = [
        PullRecord(
            number=1,
            created_at=NOW - _hours(12),
            merged_at=NOW,
            review_requests=(ReviewRequest("bob", requested_at=NOW - _hours(6)),),
            reviews=(
                Review("carol", NOW - _hours(8)),
                Review("bob", NOW - _hours(2)),
            ),
        )
    ]
    intervals = review_wait_intervals(pulls)
    assert [interval.hours for interval in intervals] == [4]


def test_review_wait_skips_pulls_without_a_request_or_a_review():
    pulls = [
        PullRecord(number=1, created_at=NOW, reviews=(Review("bob", NOW),)),
        PullRecord(
            number=2,
            created_at=NOW,
            review_requests=(ReviewRequest("bob", NOW - _hours(3)),),
        ),
    ]
    assert review_wait_intervals(pulls) == []


def test_review_to_merge_runs_from_the_first_review_to_the_merge():
    pulls = [
        PullRecord(
            number=1,
            created_at=NOW - _hours(30),
            merged_at=NOW,
            reviews=(Review("bob", NOW - _hours(10)), Review("carol", NOW - _hours(2))),
        ),
        PullRecord(number=2, created_at=NOW, merged_at=NOW, reviews=()),
        PullRecord(number=3, created_at=NOW, reviews=(Review("bob", NOW),)),
    ]
    intervals = review_to_merge_intervals(pulls)
    assert [interval.hours for interval in intervals] == [10]


def test_buckets_keep_empty_periods_and_take_medians():
    start = NOW - timedelta(days=4)
    intervals = [
        Interval(start=start, end=start + timedelta(hours=1)),
        Interval(start=start, end=start + timedelta(hours=3)),
        Interval(start=start, end=start + timedelta(days=3)),
    ]
    buckets = bucket_intervals(intervals, start, NOW, bucket_days=1)
    assert len(buckets) == 4
    assert buckets[0].count == 2
    assert buckets[0].median_hours == 2
    assert buckets[1].count == 0 and buckets[1].median_hours is None
    assert buckets[2].count == 0
    assert buckets[3].count == 1 and buckets[3].median_hours == 72


def test_build_series_for_returns_every_metric():
    issues = [IssueRecord(number=1, created_at=NOW - _hours(5), closed_at=NOW - _hours(1))]
    pulls = [
        PullRecord(
            number=1,
            created_at=NOW - _hours(20),
            merged_at=NOW,
            review_requests=(ReviewRequest("bob", requested_at=NOW - _hours(8)),),
            reviews=(Review("bob", submitted_at=NOW - _hours(6)),),
        )
    ]
    series = {item.metric: item for item in build_series_for(issues, pulls, NOW - timedelta(days=7), NOW)}
    assert series[ISSUE_CLOSE].median_hours == 4
    assert series[REVIEW_WAIT].median_hours == 2
    assert series[REVIEW_TO_MERGE].median_hours == 6


def test_cycle_time_api_reads_github_and_buckets_it(monkeypatch, tmp_path):
    payload = {
        "issues": [
            {"number": 1, "created_at": NOW - _hours(30), "closed_at": NOW - _hours(6)},
        ],
        "pulls": [
            {
                "number": 2,
                "created_at": NOW - _hours(20),
                "merged_at": NOW - _hours(2),
                "reviews": [{"author": "bob", "state": "APPROVED", "submitted_at": NOW - _hours(4)}],
                "review_requests": [{"reviewer": "bob", "requested_at": NOW - _hours(10)}],
            }
        ],
    }
    monkeypatch.setattr("agentic.routers.metrics.fetch_github_cycle_time", lambda *args, **kwargs: payload)

    import subprocess

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q", str(repo_path)], check=True)

    with TestClient(app) as client:
        repository = client.post(
            "/api/repositories",
            json={"path": str(repo_path), "remote_url": "https://github.com/acme/api.git"},
        ).json()
        report = client.get("/api/metrics/cycle-time", params={"repository_id": repository["id"], "days": 30}).json()

        assert report["window_days"] == 30
        assert len(report["repositories"]) == 1
        entry = report["repositories"][0]
        assert entry["full_name"] == "acme/api"
        series = {item["metric"]: item for item in entry["series"]}
        assert series[ISSUE_CLOSE]["median_hours"] == 24
        assert series[REVIEW_WAIT]["median_hours"] == 6
        assert series[REVIEW_TO_MERGE]["median_hours"] == 2
        assert len(series[ISSUE_CLOSE]["buckets"]) > 0

        assert client.delete(f"/api/repositories/{repository['id']}").status_code == 204


def test_cycle_time_api_rejects_a_repository_without_a_github_remote(tmp_path):
    import subprocess

    repo_path = tmp_path / "local-only"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q", str(repo_path)], check=True)

    with TestClient(app) as client:
        repository = client.post("/api/repositories", json={"path": str(repo_path)}).json()
        response = client.get("/api/metrics/cycle-time", params={"repository_id": repository["id"]})
        assert response.status_code == 400
        assert "no GitHub remote" in response.json()["detail"]

        client.delete(f"/api/repositories/{repository['id']}")
