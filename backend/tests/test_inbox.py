from fastapi.testclient import TestClient

from agentic.inbox import (
    CLOSE_TASK_MERGED_PR,
    RECORD_CHANGE_MERGED_PR,
    REMOVE_WORKTREE_DONE_TASK,
    build_suggestions,
    is_merged_pr,
    is_pull_request,
)
from agentic.main import app
from agentic.models import Change, SourceItem, Task, TaskStatus, Worktree, WorktreeStatus

MERGED_AT = "2026-01-01T00:00:00+00:00"


def _task(task_id: str, status: TaskStatus = TaskStatus.open) -> Task:
    return Task(id=task_id, title=f"Task {task_id}", status=status)


def _pr(item_id: str, number: int, state: str = "MERGED") -> SourceItem:
    return SourceItem(
        id=item_id,
        source="github",
        kind="pull_request",
        title=f"PR {number}",
        url=f"https://github.com/o/r/pull/{number}",
        external_id=f"o/r#{number}",
        metadata_json={"state": state, "merged_at": MERGED_AT if state == "MERGED" else None},
    )


def _worktree(worktree_id: str, task_id: str, status: WorktreeStatus = WorktreeStatus.active) -> Worktree:
    return Worktree(
        id=worktree_id,
        task_id=task_id,
        repository_id="r1",
        branch="agentic/foo",
        path="/tmp/foo",
        status=status,
    )


def _run(tasks, items, links, worktrees=None, changes=None):
    return build_suggestions(
        tasks,
        {item.id: item for item in items},
        links,
        worktrees or {},
        changes or {},
    )


def test_single_merged_pr_offers_close_and_record_change():
    task = _task("t1")
    pr = _pr("i1", 5)
    suggestions = _run([task], [pr], {"t1": ["i1"]})

    kinds = [s["kind"] for s in suggestions]
    assert kinds == [CLOSE_TASK_MERGED_PR, RECORD_CHANGE_MERGED_PR]
    close = suggestions[0]
    assert close["task_id"] == "t1"
    assert close["task_title"] == "Task t1"
    action = close["actions"][0]
    assert action["kind"] == "set_task_status"
    assert action["status"] == "done"
    assert suggestions[1]["actions"][0]["kind"] == "create_change"


def test_recorded_change_suppresses_the_change_suggestion():
    task = _task("t1")
    pr = _pr("i1", 5)
    change = Change(task_id="t1", external_ref="https://github.com/o/r/pull/5")
    suggestions = _run([task], [pr], {"t1": ["i1"]}, changes={"t1": [change]})
    assert [s["kind"] for s in suggestions] == [CLOSE_TASK_MERGED_PR]


def test_two_linked_prs_are_not_offered_for_closing():
    task = _task("t1")
    a, b = _pr("i1", 5), _pr("i2", 6)
    suggestions = _run([task], [a, b], {"t1": ["i1", "i2"]})
    kinds = [s["kind"] for s in suggestions]
    assert CLOSE_TASK_MERGED_PR not in kinds
    # Each merged PR still asks for its own change record.
    assert kinds == [RECORD_CHANGE_MERGED_PR, RECORD_CHANGE_MERGED_PR]


def test_an_open_pull_request_is_not_merged():
    task = _task("t1")
    pr = _pr("i1", 5, state="OPEN")
    assert is_pull_request(pr) and not is_merged_pr(pr)
    assert _run([task], [pr], {"t1": ["i1"]}) == []


def test_done_task_is_not_offered_for_closing_but_still_records_a_change():
    task = _task("t1", status=TaskStatus.done)
    pr = _pr("i1", 5)
    kinds = [s["kind"] for s in _run([task], [pr], {"t1": ["i1"]})]
    assert kinds == [RECORD_CHANGE_MERGED_PR]


def test_archived_task_is_left_alone():
    task = _task("t1", status=TaskStatus.archived)
    pr = _pr("i1", 5)
    assert _run([task], [pr], {"t1": ["i1"]}) == []


def test_closed_task_with_an_active_worktree_is_offered_for_pruning():
    task = _task("t1", status=TaskStatus.done)
    worktrees = {"t1": [_worktree("w1", "t1")]}
    suggestions = _run([task], [], {}, worktrees)
    assert [s["kind"] for s in suggestions] == [REMOVE_WORKTREE_DONE_TASK]
    action = suggestions[0]["actions"][0]
    assert action["kind"] == "remove_worktree"
    assert action["worktree_id"] == "w1"

    # A removed worktree is no longer suggested.
    removed = {"t1": [_worktree("w1", "t1", status=WorktreeStatus.removed)]}
    assert _run([task], [], {}, removed) == []


def test_open_task_keeps_its_worktree():
    task = _task("t1")
    assert _run([task], [], {}, {"t1": [_worktree("w1", "t1")]}) == []


def test_suggestions_are_ordered_by_kind():
    done = _task("t1", status=TaskStatus.done)
    open_task = _task("t2")
    pr = _pr("i1", 5)
    suggestions = _run(
        [done, open_task],
        [pr],
        {"t2": ["i1"]},
        {"t1": [_worktree("w1", "t1")]},
    )
    assert [s["kind"] for s in suggestions] == [
        CLOSE_TASK_MERGED_PR,
        RECORD_CHANGE_MERGED_PR,
        REMOVE_WORKTREE_DONE_TASK,
    ]


def test_inbox_endpoint_lists_a_close_suggestion_for_a_merged_pr():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "Inbox merged PR"}).json()
        item = client.post(
            "/api/items",
            json={
                "source": "github",
                "kind": "pull_request",
                "title": "Merged PR",
                "url": "https://github.com/inbox-test/repo/pull/991",
                "metadata_json": {"state": "MERGED", "merged_at": MERGED_AT},
                "fetch": False,
            },
        ).json()
        client.post(f"/api/tasks/{task['id']}/items", json={"item_id": item["id"]})

        report = client.get("/api/inbox").json()
        mine = [s for s in report["suggestions"] if s["task_id"] == task["id"]]
        assert [s["kind"] for s in mine] == [CLOSE_TASK_MERGED_PR, RECORD_CHANGE_MERGED_PR]
        assert report["count"] == len(report["suggestions"])

        # Closing the task through the offered action drops the close suggestion,
        # leaving only the change to record.
        client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
        after = client.get("/api/inbox").json()["suggestions"]
        assert [s["kind"] for s in after if s["task_id"] == task["id"]] == [RECORD_CHANGE_MERGED_PR]

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/items/{item['id']}")
