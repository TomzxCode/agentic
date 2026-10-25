from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from agentic.main import app
from agentic.process_flow import (
    BACKLOG,
    BLOCKED,
    DONE,
    IN_PROGRESS,
    TaskRecord,
    Transition,
    build_report,
    histogram_for,
    littles_law,
    quantile,
    stage_dwell,
    stage_flows,
    stage_inventory,
    stage_timeline,
)

NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=UTC)


def task(id, created, status):
    return TaskRecord(id=id, created_at=created, status=status)


def transition(task_id, at, from_stage, to_stage):
    return Transition(task_id=task_id, at=at, from_stage=from_stage, to_stage=to_stage)


def scenario_tasks():
    """Four tasks covering every station and a completion inside the window."""
    return [
        task("a", datetime(2026, 9, 1, 12, tzinfo=UTC), "done"),
        task("b", datetime(2026, 10, 20, 12, tzinfo=UTC), "open"),
        task("c", datetime(2026, 10, 1, 12, tzinfo=UTC), "blocked"),
        task("d", datetime(2026, 10, 15, 12, tzinfo=UTC), "in_progress"),
    ]


def scenario_transitions():
    return [
        transition("a", datetime(2026, 9, 3, 12, tzinfo=UTC), BACKLOG, IN_PROGRESS),
        transition("a", datetime(2026, 9, 10, 12, tzinfo=UTC), IN_PROGRESS, DONE),
        transition("c", datetime(2026, 10, 5, 12, tzinfo=UTC), BACKLOG, IN_PROGRESS),
        transition("c", datetime(2026, 10, 8, 12, tzinfo=UTC), IN_PROGRESS, BLOCKED),
        transition("d", datetime(2026, 10, 16, 12, tzinfo=UTC), BACKLOG, IN_PROGRESS),
    ]


def test_quantile_interpolates_between_order_statistics():
    values = [10.0, 20.0, 30.0, 40.0]
    assert quantile(values, 0.0) == 10.0
    assert quantile(values, 0.5) == 25.0
    assert quantile(values, 1.0) == 40.0
    assert quantile([], 0.5) is None
    assert quantile([7.0], 0.9) == 7.0


def test_stage_timeline_walks_forward_and_corrects_missing_history():
    task_record = task("a", datetime(2026, 9, 1, 12, tzinfo=UTC), "in_progress")
    transitions = [
        transition("a", datetime(2026, 9, 3, 12, tzinfo=UTC), BACKLOG, IN_PROGRESS),
        # A second open -> in_progress move from the task's earlier life: the
        # task is not in the backlog any more, so it must not apply.
        transition("a", datetime(2026, 9, 5, 12, tzinfo=UTC), BACKLOG, IN_PROGRESS),
    ]
    timeline = stage_timeline(task_record, transitions)
    assert [(at, stage) for at, stage in timeline] == [
        (datetime(2026, 9, 1, 12, tzinfo=UTC), BACKLOG),
        (datetime(2026, 9, 3, 12, tzinfo=UTC), IN_PROGRESS),
    ]

    # No recorded history at all: the whole timeline collapses to the current
    # station, entered at creation.
    bare = stage_timeline(task("b", datetime(2026, 10, 20, 12, tzinfo=UTC), "blocked"), [])
    assert bare == [(datetime(2026, 10, 20, 12, tzinfo=UTC), BLOCKED)]


def test_stage_inventory_counts_and_ages():
    stats = {stat.stage: stat for stat in stage_inventory(scenario_tasks(), scenario_transitions(), NOW)}
    assert {stage: stat.count for stage, stat in stats.items()} == {
        BACKLOG: 1,
        IN_PROGRESS: 1,
        BLOCKED: 1,
        DONE: 1,
        "archived": 0,
    }
    # b sits in the backlog since creation, five days before now.
    assert stats[BACKLOG].oldest_hours == 120.0
    assert stats[BACKLOG].median_age_hours == 120.0
    # c has been blocked since Oct 8, seventeen days before now.
    assert stats[BLOCKED].oldest_hours == 17 * 24.0
    # Empty stations carry no ages.
    assert stats["archived"].median_age_hours is None


def test_stage_flows_count_only_moves_inside_the_window():
    flows = stage_flows(scenario_transitions(), NOW - timedelta(days=90), NOW)
    counted = {(flow.from_stage, flow.to_stage): flow.count for flow in flows}
    assert counted == {
        (BACKLOG, IN_PROGRESS): 3,
        (IN_PROGRESS, DONE): 1,
        (IN_PROGRESS, BLOCKED): 1,
    }
    # A move older than the window drops out.
    recent = stage_flows(scenario_transitions(), datetime(2026, 10, 1, 12, tzinfo=UTC), NOW)
    assert {(flow.from_stage, flow.to_stage): flow.count for flow in recent}.get((BACKLOG, IN_PROGRESS)) == 2


def test_histogram_buckets_sum_to_the_sample():
    durations = [12.0, 30.0, 60.0, 60.0, 100.0, 200.0, 400.0, 800.0, 2000.0]
    buckets = histogram_for(durations)
    counts = {bucket.label: bucket.count for bucket in buckets}
    assert counts == {
        "<1d": 1,
        "1-2d": 1,
        "2-4d": 2,
        "4-7d": 1,
        "1-2w": 1,
        "2-4w": 1,
        "1-2mo": 1,
        ">2mo": 1,
    }
    assert sum(counts.values()) == len(durations)


def test_stage_dwell_accumulates_time_before_completion():
    completions = [(task("a", datetime(2026, 9, 1, 12, tzinfo=UTC), "done"), datetime(2026, 9, 10, 12, tzinfo=UTC))]
    dwell = {row.stage: row for row in stage_dwell(scenario_tasks(), scenario_transitions(), completions)}
    # a spent two days in the backlog and seven in progress; blocked never.
    assert dwell[BACKLOG].count == 1
    assert dwell[BACKLOG].median_hours == 48.0
    assert dwell[IN_PROGRESS].median_hours == 7 * 24.0
    assert dwell[BLOCKED].count == 0
    assert dwell[BLOCKED].median_hours is None


def test_littles_law_integrates_work_in_process():
    completions = [(task("a", datetime(2026, 9, 1, 12, tzinfo=UTC), "done"), datetime(2026, 9, 10, 12, tzinfo=UTC))]
    start = NOW - timedelta(days=90)
    law = littles_law(scenario_tasks(), scenario_transitions(), completions, start, NOW)
    window_hours = 90 * 24
    # Active-station time: a 2d backlog + 7d in progress, b 5d backlog,
    # c 4d backlog + 3d in progress + 17d blocked, d 1d backlog + 9d in progress.
    expected_wip = (2 * 24 + 7 * 24 + 5 * 24 + 4 * 24 + 3 * 24 + 17 * 24 + 1 * 24 + 9 * 24) / window_hours
    assert law.avg_wip == pytest.approx(expected_wip)
    assert law.throughput_per_day == pytest.approx(1 / 90)
    # Little's law: cycle time = WIP / throughput, in hours.
    assert law.projected_cycle_hours == pytest.approx(expected_wip * 90 * 24)


def test_build_report_end_to_end():
    report = build_report(scenario_tasks(), scenario_transitions(), NOW, window_days=90)
    assert report.arrivals == 4
    assert report.completions == 1
    assert report.cycle_time.count == 1
    # a: Sep 1 to Sep 10 is nine days, in the 1-2 week bucket.
    assert report.cycle_time.median_hours == 9 * 24.0
    assert next(bucket.count for bucket in report.histogram if bucket.label == "1-2w") == 1
    assert sum(bucket.count for bucket in report.histogram) == 1
    # Twelve whole weeks plus a six-day stub close the ninety-day window.
    assert len(report.weekly) == 13
    last = report.weekly[-1]
    assert (last.end - last.start) < timedelta(days=7)
    # b's arrival lands in the week of Oct 19.
    assert any(week.created == 1 and week.completed == 0 for week in report.weekly)
    assert any(week.created == 0 and week.completed == 1 for week in report.weekly)


def test_process_router_computes_from_recorded_status_changes():
    with TestClient(app) as client:
        first = client.post("/api/tasks", json={"title": "First line item"}).json()
        second = client.post("/api/tasks", json={"title": "Still queued"}).json()
        client.patch(f"/api/tasks/{first['id']}", json={"status": "in_progress"})
        client.patch(f"/api/tasks/{first['id']}", json={"status": "done"})

        report = client.get("/api/process", params={"days": 30}).json()

        stages = {stage["stage"]: stage for stage in report["stages"]}
        assert stages["backlog"]["count"] == 1
        assert stages["done"]["count"] == 1
        assert report["completions"] == 1
        assert report["cycle_time"]["count"] == 1
        flows = {(flow["from_stage"], flow["to_stage"]): flow["count"] for flow in report["flows"]}
        assert flows[("backlog", "in_progress")] == 1
        assert flows[("in_progress", "done")] == 1
        # All cycle-time samples fall in the fastest bucket; histogram sums to completions.
        assert sum(bucket["count"] for bucket in report["histogram"]) == 1
        assert report["littles"]["throughput_per_day"] > 0
        assert len(report["weekly"]) > 0

        client.delete(f"/api/tasks/{first['id']}")
        client.delete(f"/api/tasks/{second['id']}")
