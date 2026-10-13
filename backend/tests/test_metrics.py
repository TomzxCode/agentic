from datetime import timedelta

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.metrics import (
    compute_autonomy_rate,
    compute_counts,
    compute_metrics,
    compute_yield,
    direction,
)
from agentic.models import Change, ChangeStatus, utcnow


def _change(**fields) -> Change:
    fields.setdefault("task_id", "t")
    return Change(**fields)


def test_autonomy_rate_counts_touchless_over_accepted():
    now = utcnow()
    changes = [
        _change(status=ChangeStatus.accepted, accepted_at=now - timedelta(days=5)),
        _change(status=ChangeStatus.accepted, accepted_at=now - timedelta(days=5), human_intervened=True),
    ]
    result = compute_autonomy_rate(changes, now, 30)
    assert result.value == 0.5
    assert result.numerator == 1 and result.denominator == 2


def test_autonomy_rate_is_none_without_accepted_changes():
    result = compute_autonomy_rate([_change()], utcnow(), 30)
    assert result.value is None and result.denominator == 0


def test_yield_counts_survivors_over_observed():
    now = utcnow()
    changes = [
        _change(status=ChangeStatus.reverted, accepted_at=now - timedelta(days=40)),
        _change(status=ChangeStatus.accepted, accepted_at=now - timedelta(days=40)),
    ]
    result = compute_yield(changes, now, 90, 14)
    assert result.value == 0.5
    assert result.denominator == 2


def test_yield_excludes_changes_still_in_the_observation_window():
    now = utcnow()
    changes = [
        _change(status=ChangeStatus.accepted, accepted_at=now - timedelta(days=40)),
        _change(status=ChangeStatus.accepted, accepted_at=now - timedelta(days=1)),
    ]
    result = compute_yield(changes, now, 90, 14)
    assert result.value == 1.0
    assert result.denominator == 1
    counts = compute_counts(changes, now, 90, 14)
    assert counts.pending_observation == 1
    assert counts.accepted == 2


def test_reverted_change_is_observed_even_when_recent():
    now = utcnow()
    changes = [_change(status=ChangeStatus.reverted, accepted_at=now - timedelta(days=1))]
    result = compute_yield(changes, now, 90, 14)
    assert result.value == 0.0
    assert result.denominator == 1


def test_direction():
    assert direction(0.5, 0.2) == "improving"
    assert direction(0.2, 0.5) == "worsening"
    assert direction(0.5, 0.5) == "flat"
    assert direction(0.51, 0.5) == "flat"  # inside the tolerance band
    assert direction(0.5, None) == "no-baseline"
    assert direction(None, 0.5) == "no-data"


def test_compute_metrics_is_deterministic():
    now = utcnow()
    changes = [
        _change(status=ChangeStatus.accepted, accepted_at=now - timedelta(days=40)),
        _change(status=ChangeStatus.reverted, accepted_at=now - timedelta(days=40), human_intervened=True),
    ]
    first = compute_metrics(changes, now, 90, 14)
    second = compute_metrics(changes, now, 90, 14)
    assert first == second


def test_change_lifecycle_and_metrics_api():
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "Metrics API"}).json()["id"]

        created = client.post("/api/changes", json={"task_id": task_id, "title": "Fix bug", "change_class": "bugfix"})
        assert created.status_code == 201
        change_id = created.json()["id"]
        assert created.json()["status"] == "proposed"

        # The task detail embeds its changes, so the task page can render them.
        task_detail = client.get(f"/api/tasks/{task_id}").json()
        assert [c["id"] for c in task_detail["changes"]] == [change_id]

        # A same-status transition is a no-op.
        assert client.post(f"/api/changes/{change_id}/status", json={"status": "proposed"}).status_code == 200

        # An unknown status is a 400, an invalid transition a 409.
        assert client.post(f"/api/changes/{change_id}/status", json={"status": "nope"}).status_code == 400
        assert client.post(f"/api/changes/{change_id}/status", json={"status": "reverted"}).status_code == 409

        assert (
            client.post(f"/api/changes/{change_id}/status", json={"status": "accepted"}).json()["status"] == "accepted"
        )
        assert client.get(f"/api/changes/{change_id}").json()["accepted_at"] is not None

        intervention = client.post(
            f"/api/changes/{change_id}/interventions", json={"kind": "correction", "note": "manual edit"}
        )
        assert intervention.status_code == 201
        detail = client.get(f"/api/changes/{change_id}").json()
        assert detail["human_intervened"] is True
        assert detail["intervention_count"] == 1
        assert len(detail["interventions"]) == 1

        # An unknown intervention kind is rejected.
        assert client.post(f"/api/changes/{change_id}/interventions", json={"kind": "nope"}).status_code == 400

        report = client.get("/api/metrics", params={"task_id": task_id, "observation_days": 0}).json()
        metrics = {entry["metric"]: entry for entry in report["metrics"]}
        assert metrics["autonomy_rate"]["value"] == 0.0
        assert metrics["autonomy_rate"]["denominator"] == 1
        assert metrics["yield"]["value"] == 1.0
        assert report["counts"]["accepted"] == 1
        assert report["counts"]["touchless"] == 0

        # A baseline turns the direction from no-baseline into improving.
        assert metrics["yield"]["direction"] == "no-baseline"
        assert client.put("/api/metrics/baselines/yield", json={"value": 0.0}).status_code == 200
        report = client.get("/api/metrics", params={"task_id": task_id, "observation_days": 0}).json()
        assert {e["metric"]: e for e in report["metrics"]}["yield"]["direction"] == "improving"

        # A rejection in the window is counted.
        other = client.post("/api/changes", json={"task_id": task_id, "title": "Nope"}).json()["id"]
        client.post(f"/api/changes/{other}/status", json={"status": "rejected"})
        report = client.get("/api/metrics", params={"task_id": task_id}).json()
        assert report["counts"]["rejected"] == 1

        assert client.delete("/api/metrics/baselines/yield").status_code == 204
        assert client.delete(f"/api/changes/{change_id}").status_code == 204
        assert client.get(f"/api/changes/{change_id}").status_code == 404

        client.delete(f"/api/tasks/{task_id}")


def test_change_can_be_created_already_accepted():
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "Imported PR"}).json()["id"]
        merged_at = (utcnow() - timedelta(days=2)).isoformat()

        created = client.post(
            "/api/changes",
            json={
                "task_id": task_id,
                "title": "Fix the thing",
                "external_ref": "https://github.com/o/r/pull/3",
                "status": "accepted",
                "opened_at": merged_at,
                "accepted_at": merged_at,
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "accepted"
        assert body["accepted_at"] is not None

        # An imported merged PR counts in the metrics right away.
        report = client.get("/api/metrics", params={"task_id": task_id, "observation_days": 0}).json()
        assert report["counts"]["accepted"] == 1

        # A change cannot be born rejected or reverted.
        assert client.post("/api/changes", json={"task_id": task_id, "status": "reverted"}).status_code == 400

        client.delete(f"/api/tasks/{task_id}")


def test_task_delete_removes_changes_and_interventions():
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "Cascade"}).json()["id"]
        change_id = client.post("/api/changes", json={"task_id": task_id}).json()["id"]
        client.post(f"/api/changes/{change_id}/interventions", json={"kind": "rerun"})

        assert client.delete(f"/api/tasks/{task_id}").status_code == 204
        assert client.get(f"/api/changes/{change_id}").status_code == 404
        assert client.get("/api/changes", params={"task_id": task_id}).json() == []


def test_repository_delete_clears_change_reference(tmp_path):
    import subprocess

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "Repo ref"}).json()["id"]
        repo_id = client.post("/api/repositories", json={"path": str(repo_path)}).json()["id"]
        change_id = client.post("/api/changes", json={"task_id": task_id, "repository_id": repo_id}).json()["id"]

        assert client.delete(f"/api/repositories/{repo_id}").status_code == 204
        assert client.get(f"/api/changes/{change_id}").json()["repository_id"] is None
        client.delete(f"/api/tasks/{task_id}")


def test_baseline_validation():
    with TestClient(app) as client:
        assert client.put("/api/metrics/baselines/unknown", json={"value": 0.5}).status_code == 404
        assert client.put("/api/metrics/baselines/yield", json={"value": 2.0}).status_code == 400
        baselines = client.get("/api/metrics/baselines").json()
        assert all(b["metric"] in {"autonomy_rate", "yield"} for b in baselines)
