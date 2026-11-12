"""Checklist templates: rule matching, application, and task item editing."""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from agentic.checklists import merge_agent_items
from agentic.db import engine
from agentic.main import app
from agentic.models.checklists import ChecklistDismissal
from agentic.models.tasks import Task


def _task(client: TestClient, title: str = "Task", **fields) -> dict:
    return client.post("/api/tasks", json={"title": title, **fields}).json()


def _template(client: TestClient, **fields) -> dict:
    payload = {"name": "Feature checklist", "items": ["Announce the feature", "Write user documentation"]}
    payload.update(fields)
    return client.post("/api/checklist-templates", json=payload).json()


def _checklist(client: TestClient, task_id: str) -> list[dict]:
    return client.get(f"/api/tasks/{task_id}").json()["checklist"]


def test_tag_template_applies_once_and_tracks_matching():
    with TestClient(app) as client:
        template = _template(
            client,
            name="Feature",
            rules=[{"field": "tags", "op": "has_any", "values": ["feature"]}],
        )
        task = _task(client, "Ship the feature", tags=["feature"])

        items = _checklist(client, task["id"])
        assert [item["text"] for item in items] == ["Announce the feature", "Write user documentation"]
        assert all(item["applicable"] for item in items)
        assert {item["template_name"] for item in items} == {"Feature"}
        assert client.get("/api/checklist-templates").json()[0]["applied_count"] == 1

        # Checking an item off records when it was done.
        done = client.patch(f"/api/tasks/{task['id']}/checklist/{items[0]['id']}", json={"done": True}).json()
        assert done["done"] is True
        assert done["done_at"] is not None

        # Removing the tag keeps the items but disables them.
        client.patch(f"/api/tasks/{task['id']}", json={"tags": []})
        items = _checklist(client, task["id"])
        assert len(items) == 2
        assert not any(item["applicable"] for item in items)

        # Re-adding the tag enables them again without duplicating anything.
        client.patch(f"/api/tasks/{task['id']}", json={"tags": ["feature"]})
        items = _checklist(client, task["id"])
        assert len(items) == 2
        assert all(item["applicable"] for item in items)

        # A derived item deleted from the task stays deleted: the application
        # record stops the next matching pass from re-adding it.
        client.delete(f"/api/tasks/{task['id']}/checklist/{items[0]['id']}")
        client.patch(f"/api/tasks/{task['id']}", json={"tags": []})
        client.patch(f"/api/tasks/{task['id']}", json={"tags": ["feature"]})
        assert [item["text"] for item in _checklist(client, task["id"])] == ["Write user documentation"]

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/checklist-templates/{template['id']}")


def test_rules_match_status_priority_people_and_requesters():
    with TestClient(app) as client:
        person = client.post("/api/people", json={"name": "Ada"}).json()
        requester = client.post("/api/people", json={"name": "Grace"}).json()
        template = _template(
            client,
            name="Team feature",
            rules=[
                {"field": "status", "op": "is_any", "values": ["open"]},
                {"field": "priority", "op": "is_any", "values": ["2"]},
                {"field": "tags", "op": "has_all", "values": ["feature", "backend"]},
                {"field": "people", "op": "has_any", "values": [person["id"]]},
                {"field": "requested_by", "op": "has_any", "values": [requester["id"]]},
            ],
        )
        task = _task(client, "Feature with a team", tags=["feature", "backend"])
        client.post(f"/api/tasks/{task['id']}/people", json={"person_id": person["id"]})
        client.post(f"/api/tasks/{task['id']}/requesters", json={"person_id": requester["id"]})

        assert len(_checklist(client, task["id"])) == 2

        # A task missing one condition matches nothing.
        other = _task(client, "Feature alone", tags=["feature", "backend"])
        assert _checklist(client, other["id"]) == []

        # The operators reject non-matching values.
        client.patch(f"/api/tasks/{task['id']}", json={"priority": 0})
        assert not any(item["applicable"] for item in _checklist(client, task["id"]))

        for task_id in (task["id"], other["id"]):
            client.delete(f"/api/tasks/{task_id}")
        client.delete(f"/api/checklist-templates/{template['id']}")
        client.delete(f"/api/people/{person['id']}")
        client.delete(f"/api/people/{requester['id']}")


def test_waiting_on_and_exclusion_operators():
    with TestClient(app) as client:
        person = client.post("/api/people", json={"name": "Ada"}).json()
        set_template = _template(
            client,
            name="Waiting",
            rules=[{"field": "waiting_on", "op": "is_set"}],
        )
        not_template = _template(
            client,
            name="Not blocked",
            items=["Pick this up"],
            rules=[
                {"field": "status", "op": "is_not_any", "values": ["done", "archived"]},
                {"field": "tags", "op": "has_none", "values": ["skip"]},
            ],
        )
        task = _task(client, "Waiting on Ada", tags=["normal"])
        client.patch(f"/api/tasks/{task['id']}", json={"waiting_on_person_id": person["id"]})

        names = {item["template_name"] for item in _checklist(client, task["id"])}
        assert names == {"Waiting", "Not blocked"}

        # Marking it done fails the is_not_any rule; the items stay, disabled.
        client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
        checklist = _checklist(client, task["id"])
        assert {item["template_name"] for item in checklist if item["applicable"]} == {"Waiting"}

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/checklist-templates/{set_template['id']}")
        client.delete(f"/api/checklist-templates/{not_template['id']}")
        client.delete(f"/api/people/{person['id']}")


def test_before_after_and_related_rules():
    with TestClient(app) as client:
        prerequisite = _task(client, "Prerequisite")
        dependent = _task(client, "Dependent")
        related = _task(client, "Related")
        before_template = _template(
            client,
            name="Follow-up",
            items=["Check the prerequisite landed"],
            rules=[{"field": "before", "op": "has_any", "values": [prerequisite["id"]]}],
        )
        after_template = _template(
            client,
            name="Blocker done",
            items=["Ask for the dependency"],
            rules=[{"field": "after", "op": "has_any", "values": [dependent["id"]]}],
        )
        related_template = _template(
            client,
            name="Related work",
            items=["Read the related task"],
            rules=[{"field": "related", "op": "has_any", "values": [related["id"]]}],
        )

        # prerequisite -> dependent: dependent follows it, so it gets the
        # "before" template; prerequisite blocks it, so it gets the "after" one.
        client.post(
            f"/api/tasks/{prerequisite['id']}/dependencies",
            json={"related_id": dependent["id"], "relation": "after"},
        )
        assert {item["template_name"] for item in _checklist(client, dependent["id"])} == {"Follow-up"}
        assert {item["template_name"] for item in _checklist(client, prerequisite["id"])} == {"Blocker done"}

        client.post(
            f"/api/tasks/{prerequisite['id']}/dependencies",
            json={"related_id": related["id"], "relation": "related"},
        )
        assert "Related work" in {item["template_name"] for item in _checklist(client, prerequisite["id"])}

        for task in (prerequisite, dependent, related):
            client.delete(f"/api/tasks/{task['id']}")
        for template in (before_template, after_template, related_template):
            client.delete(f"/api/checklist-templates/{template['id']}")


def test_manual_item_lifecycle():
    with TestClient(app) as client:
        task = _task(client, "Manual checklist")

        added = client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "  Draft the release note  "}).json()
        assert added["text"] == "Draft the release note"
        assert added["template_id"] is None
        assert added["applicable"] is True

        edited = client.patch(
            f"/api/tasks/{task['id']}/checklist/{added['id']}", json={"text": "Publish the release note"}
        ).json()
        assert edited["text"] == "Publish the release note"

        checked = client.patch(f"/api/tasks/{task['id']}/checklist/{added['id']}", json={"done": True}).json()
        assert checked["done"] is True
        reopened = client.patch(f"/api/tasks/{task['id']}/checklist/{added['id']}", json={"done": False}).json()
        assert reopened["done"] is False
        assert reopened["done_at"] is None

        assert client.delete(f"/api/tasks/{task['id']}/checklist/{added['id']}").status_code == 204
        assert _checklist(client, task["id"]) == []

        # Empty text and an item from another task are refused.
        assert client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "  "}).status_code == 400
        other = _task(client, "Other")
        item = client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "Mine"}).json()
        assert client.patch(f"/api/tasks/{other['id']}/checklist/{item['id']}", json={"done": True}).status_code == 404

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/tasks/{other['id']}")


def test_reordering_items_rewrites_positions_and_keeps_unknown_ids_out():
    with TestClient(app) as client:
        task = _task(client, "Reorder checklist")
        ids = [
            client.post(f"/api/tasks/{task['id']}/checklist", json={"text": text}).json()["id"]
            for text in ("One", "Two", "Three")
        ]

        reordered = client.post(
            f"/api/tasks/{task['id']}/checklist/reorder", json={"item_ids": [ids[2], ids[0], ids[1]]}
        ).json()
        assert [item["text"] for item in reordered] == ["Three", "One", "Two"]
        assert [item["position"] for item in reordered] == [0, 1, 2]
        assert [item["text"] for item in _checklist(client, task["id"])] == ["Three", "One", "Two"]

        # A partial order moves the listed items to the front and leaves the
        # rest in place; ids from another task are ignored.
        other = _task(client, "Other")
        stray = client.post(f"/api/tasks/{other['id']}/checklist", json={"text": "Elsewhere"}).json()["id"]
        partial = client.post(f"/api/tasks/{task['id']}/checklist/reorder", json={"item_ids": [ids[1], stray]}).json()
        assert [item["text"] for item in partial] == ["Two", "Three", "One"]

        # A new item still lands at the end after a reorder.
        added = client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "Four"}).json()
        assert added["position"] == 3

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/tasks/{other['id']}")


def test_template_creation_and_apply_to_existing_tasks():
    with TestClient(app) as client:
        task = _task(client, "Existing feature", tags=["feature"])

        # A new matching template applies to existing tasks immediately.
        template = _template(
            client,
            name="Feature",
            rules=[{"field": "tags", "op": "has_any", "values": ["feature"]}],
        )
        assert len(_checklist(client, task["id"])) == 2

        # Adding an item to the template does not touch the task until applied.
        edited = client.patch(
            f"/api/checklist-templates/{template['id']}",
            json={"items": ["Announce the feature", "Write user documentation", "Update the changelog"]},
        ).json()
        assert len(edited["items"]) == 3
        assert len(_checklist(client, task["id"])) == 2

        applied = client.post(f"/api/checklist-templates/{template['id']}/apply").json()
        assert applied["applied"] == 1
        assert len(_checklist(client, task["id"])) == 3

        # Removing the template removes the items it put on the task.
        client.delete(f"/api/checklist-templates/{template['id']}")
        assert _checklist(client, task["id"]) == []
        client.delete(f"/api/tasks/{task['id']}")


def test_template_crud_and_validation():
    with TestClient(app) as client:
        assert client.post("/api/checklist-templates", json={"name": "  "}).status_code == 400
        assert (
            client.post(
                "/api/checklist-templates",
                json={"name": "Bad", "rules": [{"field": "nope", "op": "is_any", "values": ["x"]}]},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/checklist-templates",
                json={"name": "Bad", "rules": [{"field": "status", "op": "has_any", "values": ["x"]}]},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/checklist-templates",
                json={"name": "Bad", "rules": [{"field": "tags", "op": "has_any", "values": []}]},
            ).status_code
            == 400
        )

        # Items are trimmed and de-duplicated.
        template = client.post(
            "/api/checklist-templates",
            json={"name": "  Feature  ", "items": [" One ", "Two", "One", ""]},
        ).json()
        assert template["name"] == "Feature"
        assert template["items"] == ["One", "Two"]

        # A template with no rules matches nothing, even on a new task.
        task = _task(client, "Unmatched")
        assert _checklist(client, task["id"]) == []

        updated = client.patch(f"/api/checklist-templates/{template['id']}", json={"description": "  Notes  "}).json()
        assert updated["description"] == "Notes"

        assert client.delete(f"/api/checklist-templates/{template['id']}").status_code == 204
        assert client.get("/api/checklist-templates").json() == []
        client.delete(f"/api/tasks/{task['id']}")


def test_repository_rule_and_task_apply(tmp_path):
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()
        template = _template(
            client,
            name="Repository checklist",
            items=["Run the suite"],
            rules=[{"field": "repositories", "op": "has_any", "values": [repo["id"]]}],
        )
        task = _task(client, "Repo task", repository_ids=[repo["id"]])
        assert len(_checklist(client, task["id"])) == 1

        # A new template item reaches an already-applied task through the
        # task-side apply endpoint.
        client.patch(
            f"/api/checklist-templates/{template['id']}",
            json={"items": ["Run the suite", "Update docs"]},
        )
        applied = client.post(f"/api/tasks/{task['id']}/checklist/apply").json()
        assert applied["applied"] == 1
        assert len(_checklist(client, task["id"])) == 2

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/checklist-templates/{template['id']}")
        client.delete(f"/api/repositories/{repo['id']}")


def test_task_list_reports_open_checklist_items():
    with TestClient(app) as client:
        task = _task(client, "Checklist progress")
        first = client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "First"}).json()
        client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "Second"})
        client.patch(f"/api/tasks/{task['id']}/checklist/{first['id']}", json={"done": True})

        row = next(item for item in client.get("/api/tasks").json() if item["id"] == task["id"])
        assert row["checklist_open"] == 1
        assert row["next_checklist_item"] == "Second"

        client.delete(f"/api/tasks/{task['id']}")


def test_agent_merge_keeps_done_and_dismissed_items():
    with TestClient(app) as client:
        task = _task(client, "Agent checklist")
        done = client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "Finish the draft"}).json()
        client.patch(f"/api/tasks/{task['id']}/checklist/{done['id']}", json={"done": True})
        removed = client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "Delete me"}).json()
        client.delete(f"/api/tasks/{task['id']}/checklist/{removed['id']}")

        with Session(engine) as session:
            row = session.get(Task, task["id"])
            assert row is not None
            # Only the genuinely new action is added: the done item keeps its
            # state, the removed one stays removed, and duplicates collapse.
            added = merge_agent_items(
                session,
                row,
                ["finish the draft", "Delete me", "Publish the draft", "publish the draft"],
            )
            assert added == 1

        items = _checklist(client, task["id"])
        assert [item["text"] for item in items] == ["Finish the draft", "Publish the draft"]
        assert items[0]["done"] is True

        # Adding the removed text back by hand clears the dismissal.
        client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "Delete me"})
        with Session(engine) as session:
            assert (
                session.exec(
                    select(ChecklistDismissal).where(
                        ChecklistDismissal.task_id == task["id"],
                        ChecklistDismissal.text_key == "delete me",
                    )
                ).first()
                is None
            )
            row = session.get(Task, task["id"])
            assert row is not None
            assert merge_agent_items(session, row, ["Delete me"]) == 0

        client.delete(f"/api/tasks/{task['id']}")


def test_deleting_a_task_removes_its_checklist():
    with TestClient(app) as client:
        template = _template(
            client,
            name="Feature",
            rules=[{"field": "tags", "op": "has_any", "values": ["feature"]}],
        )
        task = _task(client, "Temporary", tags=["feature"])
        assert len(_checklist(client, task["id"])) == 2

        client.delete(f"/api/tasks/{task['id']}")
        assert client.get(f"/api/tasks/{task['id']}").status_code == 404
        assert client.get("/api/checklist-templates").json()[0]["applied_count"] == 0
        client.delete(f"/api/checklist-templates/{template['id']}")


def test_convert_checklist_item_into_a_child_task(tmp_path):
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()
        task = _task(client, "Ship the feature", repository_ids=[repo["id"]])
        item = client.post(f"/api/tasks/{task['id']}/checklist", json={"text": "Write the release note"}).json()

        created = client.post(f"/api/tasks/{task['id']}/checklist/{item['id']}/convert").json()
        assert created["title"] == "Write the release note"
        assert created["repository_ids"] == [repo["id"]]

        # The item stays, open, and points at the new task.
        items = _checklist(client, task["id"])
        assert len(items) == 1
        assert items[0]["done"] is False
        assert items[0]["converted_task_id"] == created["id"]
        assert items[0]["converted_task_title"] == created["title"]
        assert items[0]["converted_task_status"] == "open"

        # The new task is a child of the one it came from.
        assert [t["id"] for t in client.get(f"/api/tasks/{task['id']}/dependencies").json()["children"]] == [
            created["id"]
        ]
        assert [t["id"] for t in client.get(f"/api/tasks/{created['id']}/dependencies").json()["parents"]] == [
            task["id"]
        ]

        # Completing the task completes the checklist item it came from.
        client.patch(f"/api/tasks/{created['id']}", json={"status": "done"})
        item_done = _checklist(client, task["id"])[0]
        assert item_done["done"] is True
        assert item_done["done_at"] is not None
        assert item_done["converted_task_status"] == "done"

        # Reopening the task leaves the item alone: its own state is the record.
        client.patch(f"/api/tasks/{created['id']}", json={"status": "in_progress"})
        reopened = _checklist(client, task["id"])[0]
        assert reopened["done"] is True
        assert reopened["converted_task_status"] == "in_progress"

        # A second conversion is refused while the task exists.
        assert client.post(f"/api/tasks/{task['id']}/checklist/{item['id']}/convert").status_code == 400

        # Deleting the created task keeps the item but clears its link.
        client.delete(f"/api/tasks/{created['id']}")
        item_after = _checklist(client, task["id"])[0]
        assert item_after["converted_task_id"] is None

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/repositories/{repo['id']}")


def test_convert_an_item_from_another_task_is_not_found():
    with TestClient(app) as client:
        first = _task(client, "First")
        second = _task(client, "Second")
        item = client.post(f"/api/tasks/{first['id']}/checklist", json={"text": "A step"}).json()

        res = client.post(f"/api/tasks/{second['id']}/checklist/{item['id']}/convert")
        assert res.status_code == 404

        client.delete(f"/api/tasks/{first['id']}")
        client.delete(f"/api/tasks/{second['id']}")
