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
    TouchRecord,
    Transition,
    build_report,
    flow_samples,
    forecast_backlog,
    histogram_for,
    littles_law,
    outcomes,
    quantile,
    queue_pressure,
    stage_dwell,
    stage_flows,
    stage_inventory,
    stage_timeline,
    stage_wait_shares,
    touch_stats,
    wip_items,
)

NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=UTC)


def task(id, created, status, title=""):
    return TaskRecord(id=id, created_at=created, status=status, title=title)


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


def test_wait_shares_split_cycle_time_between_stations():
    completions = [(task("a", datetime(2026, 9, 1, 12, tzinfo=UTC), "done"), datetime(2026, 9, 10, 12, tzinfo=UTC))]
    shares = {row.stage: row for row in stage_wait_shares(scenario_tasks(), scenario_transitions(), completions)}
    # a's nine-day trip splits two days in the backlog and seven in progress.
    assert shares[BACKLOG].share == pytest.approx(48.0 / 216.0)
    assert shares[IN_PROGRESS].share == pytest.approx(168.0 / 216.0)
    assert shares[BLOCKED].share == 0.0
    assert sum(row.share for row in shares.values()) == pytest.approx(1.0)
    # Only stations something actually waited in carry a mean and a count.
    assert shares[BACKLOG].count == 1
    assert shares[BLOCKED].count == 0
    assert shares[BLOCKED].mean_hours is None


def test_queue_pressure_reads_net_flow_and_weekly_inventory():
    start = NOW - timedelta(days=90)
    pressure = {row.stage: row for row in queue_pressure(scenario_tasks(), scenario_transitions(), start, NOW)}
    # Backlog: four arrivals (every task was created in the window), three moves
    # out (a, c, d), so the queue nets +1 and holds b.
    assert pressure[BACKLOG].arrived == 4
    assert pressure[BACKLOG].departed == 3
    assert pressure[BACKLOG].count == 1
    assert pressure[BACKLOG].trend == "filling"
    # In progress: three in, two out (a to done, c to blocked); d is still there.
    assert pressure[IN_PROGRESS].arrived == 3
    assert pressure[IN_PROGRESS].departed == 2
    assert pressure[IN_PROGRESS].count == 1
    assert pressure[IN_PROGRESS].trend == "filling"
    # Blocked: c went in and never came out.
    assert pressure[BLOCKED].arrived == 1
    assert pressure[BLOCKED].departed == 0
    assert pressure[BLOCKED].count == 1
    assert pressure[BLOCKED].trend == "filling"
    # Thirteen weekly samples per station, ending at the current inventory.
    for row in pressure.values():
        assert len(row.weekly_wip) == 13
        assert row.weekly_wip[-1] == row.count
    # A station that loses items without new arrivals is draining; one that
    # takes them in without passing them on is filling.
    even = queue_pressure(
        [
            task("x", NOW - timedelta(days=10), "in_progress"),
            task("y", NOW - timedelta(days=100), "in_progress"),
        ],
        [
            transition("x", NOW - timedelta(days=5), BACKLOG, IN_PROGRESS),
            transition("y", NOW - timedelta(days=5), BACKLOG, IN_PROGRESS),
        ],
        NOW - timedelta(days=90),
        NOW,
    )
    pressure_by = {row.stage: row for row in even}
    # x was created in the window (an arrival); y predates it, so its move out
    # of the backlog has no matching arrival.
    assert pressure_by[BACKLOG].arrived == 1
    assert pressure_by[BACKLOG].departed == 2
    assert pressure_by[BACKLOG].trend == "draining"
    assert pressure_by[IN_PROGRESS].arrived == 2
    assert pressure_by[IN_PROGRESS].departed == 0
    assert pressure_by[IN_PROGRESS].trend == "filling"


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


def test_flow_samples_snapshot_every_day():
    samples = flow_samples(scenario_tasks(), scenario_transitions(), NOW - timedelta(days=90), NOW)
    # One sample per day, inclusive of both ends.
    assert len(samples) == 91
    # Cumulative completions only grow: a finished on Sep 10, nothing before.
    completed = [sample.completed for sample in samples]
    assert completed == sorted(completed)
    assert completed[0] == 0
    assert completed[-1] == 1
    # The final sample matches the current inventory: b, d on the line.
    last = samples[-1]
    assert (last.backlog, last.in_progress, last.blocked) == (1, 1, 1)


def test_wip_items_sort_longest_wait_first():
    items = wip_items(scenario_tasks(), scenario_transitions(), NOW)
    assert [(item.id, item.stage) for item in items] == [
        ("c", BLOCKED),
        ("d", IN_PROGRESS),
        ("b", BACKLOG),
    ]
    # c entered blocked on Oct 8: seventeen days before now.
    assert items[0].age_hours == pytest.approx(17 * 24)
    # Done and archived tasks are not on the line any more.
    assert all(item.id != "a" for item in items)


def test_touch_stats_counts_only_sessions_inside_the_trip():
    completions = [(task("a", datetime(2026, 9, 1, 12, tzinfo=UTC), "done"), datetime(2026, 9, 10, 12, tzinfo=UTC))]
    sessions = [
        TouchRecord(
            task_id="a",
            started_at=datetime(2026, 9, 5, 12, tzinfo=UTC),
            ended_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
        ),
        # An open session is clipped to the completion moment.
        TouchRecord(task_id="a", started_at=datetime(2026, 9, 9, 12, tzinfo=UTC), ended_at=None),
        # This one starts after the trip ended, so it does not count.
        TouchRecord(
            task_id="a",
            started_at=datetime(2026, 9, 12, 12, tzinfo=UTC),
            ended_at=datetime(2026, 9, 13, 12, tzinfo=UTC),
        ),
    ]
    stats = touch_stats(sessions, completions, NOW)
    assert stats.completions == 1
    assert stats.covered == 1
    assert stats.touch_hours == pytest.approx(3 * 24 + 24)
    assert stats.cycle_hours == pytest.approx(9 * 24)
    assert stats.efficiency == pytest.approx((3 * 24 + 24) / (9 * 24))
    assert stats.mean_touch_hours == pytest.approx(96.0)

    # No sessions at all: zero touch, not missing data.
    bare = touch_stats([], completions, NOW)
    assert bare.efficiency == 0.0
    assert bare.covered == 0

    # Nothing completed: no efficiency to compute.
    assert touch_stats(sessions, [], NOW).efficiency is None


def test_forecast_backlog_resamples_weekly_history():
    done = forecast_backlog(2, [1, 1, 1, 1], NOW, seed=0)
    # One completion every week: two items take exactly two weeks, every sim.
    assert done.p50_weeks == 2.0
    assert done.p85_weeks == 2.0
    assert done.p50_date == NOW + timedelta(weeks=2)
    assert done.weeks_observed == 4

    # No completion history supports no forecast.
    empty = forecast_backlog(2, [0, 0, 0], NOW)
    assert empty.p50_weeks is None
    assert empty.p85_weeks is None

    # Nothing on the line finishes now.
    clear = forecast_backlog(0, [1, 2], NOW)
    assert clear.p50_weeks == 0.0
    assert clear.p50_date == NOW


def test_outcomes_split_window_arrivals_by_disposition():
    counts = outcomes(scenario_tasks(), NOW - timedelta(days=90), NOW)
    assert counts.created == 4
    assert counts.done == 1
    assert counts.archived == 0
    assert counts.active == 3
    # Arrivals older than the window do not count.
    narrow = outcomes(scenario_tasks(), datetime(2026, 10, 1, 12, tzinfo=UTC), NOW)
    assert narrow.created == 3


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
    # The bottleneck sections: shares sum to one, pressure covers the active stations.
    assert sum(share.share for share in report.wait_shares) == pytest.approx(1.0)
    assert {pressure.stage for pressure in report.queue_pressure} == {BACKLOG, IN_PROGRESS, BLOCKED}
    # The new sections: daily samples, the aging list, touch, forecast, outcomes.
    assert len(report.flow_samples) == 91
    assert [item.id for item in report.wip_items] == ["c", "d", "b"]
    titled = build_report(
        [task("w", datetime(2026, 10, 20, 12, tzinfo=UTC), "open", title="Titled item")],
        [],
        NOW,
        window_days=90,
    )
    assert titled.wip_items[0].title == "Titled item"
    assert report.touch.completions == 1
    assert report.touch.efficiency == 0.0  # no sessions recorded in this scenario
    assert report.forecast.items == 3
    assert report.forecast.p50_weeks is not None
    assert report.outcomes.created == 4


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
        shares = {share["stage"]: share["share"] for share in report["wait_shares"]}
        assert sum(shares.values()) == pytest.approx(1.0)
        pressure = {row["stage"]: row for row in report["queue_pressure"]}
        assert pressure["in_progress"]["arrived"] == 1
        assert pressure["in_progress"]["departed"] == 1
        assert pressure["in_progress"]["trend"] == "steady"
        # Two tasks were created and only one left the backlog.
        assert pressure["backlog"]["trend"] == "filling"
        assert len(report["flow_samples"]) == 31
        assert all("age_hours" in item for item in report["wip_items"])
        assert report["touch"]["completions"] == 1
        assert report["forecast"]["items"] == 1
        assert report["forecast"]["p50_weeks"] is not None
        assert report["outcomes"] == {"created": 2, "done": 1, "archived": 0, "active": 1}
        assert all(len(row["weekly_wip"]) > 0 for row in pressure.values())

        client.delete(f"/api/tasks/{first['id']}")
        client.delete(f"/api/tasks/{second['id']}")
