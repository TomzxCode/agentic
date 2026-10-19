from fastapi.testclient import TestClient

from agentic.inbox import (
    CLOSE_TASK_FINISHED_ITEMS,
    RECORD_CHANGE_MERGED_PR,
    REMOVE_WORKTREE_DONE_TASK,
    build_suggestions,
    is_finished_item,
    is_issue,
    is_merged_pr,
    is_pull_request,
)
from agentic.main import app
from agentic.models.base import TaskStatus, WorktreeStatus
from agentic.models.changes import Change
from agentic.models.items import SourceItem
from agentic.models.repositories import Worktree
from agentic.models.tasks import Task

MERGED_AT = "2026-01-01T00:00:00+00:00"


def _task(task_id: str, status: TaskStatus = TaskStatus.open) -> Task:
    return Task(id=task_id, title=f"Task {task_id}", status=status)


def _pr(item_id: str, number: int, state: str = "MERGED", author: str | None = None) -> SourceItem:
    return SourceItem(
        id=item_id,
        source="github",
        kind="pull_request",
        title=f"PR {number}",
        url=f"https://github.com/o/r/pull/{number}",
        external_id=f"o/r#{number}",
        metadata_json={"state": state, "merged_at": MERGED_AT if state == "MERGED" else None, "author": author},
    )


def _issue(item_id: str, number: int, state: str = "CLOSED") -> SourceItem:
    return SourceItem(
        id=item_id,
        source="github",
        kind="issue",
        title=f"Issue {number}",
        url=f"https://github.com/o/r/issues/{number}",
        external_id=f"o/r#{number}",
        metadata_json={"state": state},
    )


def _note(item_id: str) -> SourceItem:
    return SourceItem(id=item_id, source="note", kind="", title="Scratch note", content="remember this")


def _worktree(worktree_id: str, task_id: str, status: WorktreeStatus = WorktreeStatus.active) -> Worktree:
    return Worktree(
        id=worktree_id,
        task_id=task_id,
        repository_id="r1",
        branch="agentic/foo",
        path="/tmp/foo",
        status=status,
    )


def _run(tasks, items, links, worktrees=None, changes=None, viewer_login=None):
    return build_suggestions(
        tasks,
        {item.id: item for item in items},
        links,
        worktrees or {},
        changes or {},
        viewer_login=viewer_login,
    )


def test_single_merged_pr_offers_close_and_record_change():
    task = _task("t1")
    pr = _pr("i1", 5)
    suggestions = _run([task], [pr], {"t1": ["i1"]})

    kinds = [s["kind"] for s in suggestions]
    assert kinds == [CLOSE_TASK_FINISHED_ITEMS, RECORD_CHANGE_MERGED_PR]
    close = suggestions[0]
    assert close["task_id"] == "t1"
    assert close["task_title"] == "Task t1"
    assert close["reason"] == "PR #5 is merged."
    action = close["actions"][0]
    assert action["kind"] == "set_task_status"
    assert action["status"] == "done"
    assert suggestions[1]["actions"][0]["kind"] == "create_change"


def test_recorded_change_suppresses_the_change_suggestion():
    task = _task("t1")
    pr = _pr("i1", 5)
    change = Change(task_id="t1", external_ref="https://github.com/o/r/pull/5")
    suggestions = _run([task], [pr], {"t1": ["i1"]}, changes={"t1": [change]})
    assert [s["kind"] for s in suggestions] == [CLOSE_TASK_FINISHED_ITEMS]


def test_two_merged_prs_are_offered_for_closing():
    task = _task("t1")
    a, b = _pr("i1", 5), _pr("i2", 6)
    suggestions = _run([task], [a, b], {"t1": ["i1", "i2"]})
    kinds = [s["kind"] for s in suggestions]
    assert kinds == [CLOSE_TASK_FINISHED_ITEMS, RECORD_CHANGE_MERGED_PR, RECORD_CHANGE_MERGED_PR]
    assert suggestions[0]["reason"] == "All 2 linked issues and pull requests are closed or merged."


def test_a_closed_issue_offers_close():
    task = _task("t1")
    issue = _issue("i1", 7)
    suggestions = _run([task], [issue], {"t1": ["i1"]})
    assert [s["kind"] for s in suggestions] == [CLOSE_TASK_FINISHED_ITEMS]
    assert suggestions[0]["reason"] == "Issue #7 is closed."


def test_an_open_issue_keeps_the_task_out_of_the_close_suggestion():
    task = _task("t1")
    issue = _issue("i1", 7, state="OPEN")
    assert is_issue(issue) and not is_finished_item(issue)
    assert _run([task], [issue], {"t1": ["i1"]}) == []


def test_a_closed_unmerged_pr_offers_close():
    task = _task("t1")
    pr = _pr("i1", 5, state="CLOSED")
    # A PR closed without merging still counts: GitHub reports it as closed.
    assert is_finished_item(pr)
    suggestions = _run([task], [pr], {"t1": ["i1"]})
    assert [s["kind"] for s in suggestions] == [CLOSE_TASK_FINISHED_ITEMS]
    assert suggestions[0]["reason"] == "PR #5 is closed."


def test_a_closed_issue_and_a_merged_pr_are_offered_for_closing():
    task = _task("t1")
    merged, closed = _pr("i1", 5), _issue("i2", 7)
    suggestions = _run([task], [merged, closed], {"t1": ["i1", "i2"]})
    kinds = [s["kind"] for s in suggestions]
    assert kinds == [CLOSE_TASK_FINISHED_ITEMS, RECORD_CHANGE_MERGED_PR]
    assert suggestions[0]["reason"] == "All 2 linked issues and pull requests are closed or merged."


def test_a_task_with_no_github_item_is_left_alone():
    task = _task("t1")
    note = _note("i1")
    assert _run([task], [note], {"t1": ["i1"]}) == []


def test_only_the_viewers_merged_prs_are_offered_a_change():
    task = _task("t1")
    mine, theirs = _pr("i1", 5, author="Me"), _pr("i2", 6, author="someone")
    suggestions = _run([task], [mine, theirs], {"t1": ["i1", "i2"]}, viewer_login="me")

    # Both PRs are merged, so the task is offered for closing; only the PR the
    # viewer authored is offered a change, the other author's is not.
    assert [s["kind"] for s in suggestions] == [CLOSE_TASK_FINISHED_ITEMS, RECORD_CHANGE_MERGED_PR]
    assert suggestions[1]["actions"][0]["item_id"] == "i1"


def test_an_unknown_viewer_does_not_filter_by_author():
    task = _task("t1")
    pr = _pr("i1", 5, author="someone")
    kinds = [s["kind"] for s in _run([task], [pr], {"t1": ["i1"]}, viewer_login="")]
    assert kinds == [CLOSE_TASK_FINISHED_ITEMS, RECORD_CHANGE_MERGED_PR]


def test_a_pr_with_no_stored_author_is_not_the_viewers():
    task = _task("t1")
    pr = _pr("i1", 5)
    assert [s["kind"] for s in _run([task], [pr], {"t1": ["i1"]}, viewer_login="me")] == [CLOSE_TASK_FINISHED_ITEMS]


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
        CLOSE_TASK_FINISHED_ITEMS,
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
        assert [s["kind"] for s in mine] == [CLOSE_TASK_FINISHED_ITEMS, RECORD_CHANGE_MERGED_PR]
        assert report["count"] == len(report["suggestions"])

        # Closing the task through the offered action drops the close suggestion,
        # leaving only the change to record.
        client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
        after = client.get("/api/inbox").json()["suggestions"]
        assert [s["kind"] for s in after if s["task_id"] == task["id"]] == [RECORD_CHANGE_MERGED_PR]

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/items/{item['id']}")


def test_inbox_endpoint_hides_a_change_for_a_pr_the_viewer_did_not_author():
    with TestClient(app) as client:
        client.patch("/api/settings", json={"github_login": "me"})
        try:
            task = client.post("/api/tasks", json={"title": "Inbox author filter"}).json()
            theirs = client.post(
                "/api/items",
                json={
                    "source": "github",
                    "kind": "pull_request",
                    "title": "Someone else's merged PR",
                    "url": "https://github.com/inbox-test/repo/pull/992",
                    "metadata_json": {"state": "MERGED", "merged_at": MERGED_AT, "author": "someone"},
                    "fetch": False,
                },
            ).json()
            client.post(f"/api/tasks/{task['id']}/items", json={"item_id": theirs["id"]})

            mine = [s for s in client.get("/api/inbox").json()["suggestions"] if s["task_id"] == task["id"]]
            # The close suggestion stays; the change offer is hidden because the
            # viewer did not author the PR.
            assert [s["kind"] for s in mine] == [CLOSE_TASK_FINISHED_ITEMS]

            client.delete(f"/api/tasks/{task['id']}")
            client.delete(f"/api/items/{theirs['id']}")
        finally:
            client.patch("/api/settings", json={"github_login": ""})
