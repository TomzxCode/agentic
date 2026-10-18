"""Shared test doubles for the CLI command tests."""


class FakeClient:
    """A stand-in for AgenticClient returning plausible shapes per method."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def health(self):
        return {"status": "ok", "service": "agentic"}

    def list_tasks(self, status=None, q=None, tags=None):
        return [{"id": "t1", "status": "open", "priority": 1, "title": "T", "tags": ["bug"]}]

    def list_deadlines(self, within_days=7):
        return [
            {
                "id": "t1",
                "status": "open",
                "priority": 1,
                "title": "T",
                "tags": [],
                "deadline": "2026-01-02T00:00:00",
            }
        ]

    def list_tags(self):
        return [{"name": "bug", "count": 1}]

    def list_people(self):
        return [{"id": "p1", "name": "Ada", "task_count": 1, "item_count": 0}]

    def get_person(self, person_id):
        return {
            "id": person_id,
            "name": "Ada",
            "task_count": 1,
            "item_count": 1,
            "aliases": ["ada", "ada@example.com"],
            "notes": "n",
            "task_ids": ["t1"],
            "item_ids": ["i1"],
        }

    def create_person(self, **fields):
        return {"id": "p2", "name": fields.get("name"), "task_count": 0, "item_count": 0}

    def update_person(self, person_id, **fields):
        return {"id": person_id, "name": fields.get("name") or "Ada", "task_count": 0, "item_count": 0}

    def delete_person(self, person_id):
        return None

    def link_person(self, person_id, **kwargs):
        return {"id": person_id, "name": "Ada", "task_count": 1, "item_count": 0}

    def unlink_person(self, person_id, **kwargs):
        return None

    def link_requester(self, person_id, task_id):
        return {"id": person_id, "name": "Ada", "task_count": 1, "item_count": 0}

    def unlink_requester(self, person_id, task_id):
        return None

    def merge_person(self, source_id, target_id):
        return {"id": target_id, "name": "Grace", "task_count": 1, "item_count": 0}

    def list_changes(self, task_id=None, status=None, change_class=None):
        return [{"id": "c1", "status": "proposed", "change_class": "feature", "title": "C", "human_intervened": False}]

    def get_change(self, change_id):
        return {
            "id": change_id,
            "status": "accepted",
            "change_class": "bugfix",
            "title": "C",
            "human_intervened": True,
            "external_ref": "https://example/pr/1",
            "opened_at": "2026-01-01T00:00:00",
            "accepted_at": "2026-01-02T00:00:00",
            "interventions": [{"kind": "correction", "note": "n"}],
        }

    def create_change(self, **fields):
        return {
            "id": "c2",
            "status": "proposed",
            "change_class": fields.get("change_class"),
            "title": fields.get("title"),
        }

    def transition_change(self, change_id, status):
        return {"id": change_id, "status": status, "change_class": "feature", "title": "C"}

    def add_intervention(self, change_id, kind="other", note=""):
        return {"id": "i1", "kind": kind, "note": note}

    def delete_change(self, change_id):
        return None

    def get_metrics(self, **kwargs):
        return {
            "window_days": 30,
            "observation_days": 14,
            "tolerance": 0.02,
            "metrics": [
                {
                    "label": "Autonomy rate",
                    "value": 0.5,
                    "baseline": 0.2,
                    "delta": 0.3,
                    "direction": "improving",
                    "numerator": 1,
                    "denominator": 2,
                }
            ],
            "counts": {
                "accepted": 2,
                "touchless": 1,
                "reverted": 0,
                "rejected": 0,
                "pending_observation": 0,
                "open": 0,
            },
        }

    def list_baselines(self):
        return [{"metric": "autonomy_rate", "value": 0.2, "captured_at": "2026-01-01T00:00:00"}]

    def set_baseline(self, metric, value, **fields):
        return {"metric": metric, "value": value}

    def delete_baseline(self, metric):
        return None

    def get_task(self, task_id):
        return {
            "id": task_id,
            "status": "open",
            "priority": 1,
            "title": "T",
            "summary": "s",
            "next_steps": [{"text": "a", "done": False}],
            "requesters": [{"id": "p1", "name": "Ada"}],
        }

    def create_task(self, **fields):
        return {"id": "t2", "title": fields.get("title")}

    def update_task(self, task_id, **fields):
        return {"id": task_id, "status": "open", "priority": 1, "title": "T"}

    def set_task_deadline(self, task_id, deadline):
        return {"id": task_id, "status": "open", "priority": 1, "title": "T", "deadline": deadline}

    def delete_task(self, task_id):
        return None

    def task_timeline(self, task_id):
        return [{"created_at": "2026-01-01T00:00:00", "type": "created", "message": "m"}]

    def task_dependencies(self, task_id):
        return {
            "task_id": task_id,
            "before": [{"id": "t0", "status": "done", "priority": 1, "title": "First"}],
            "after": [],
        }

    def add_dependency(self, task_id, related_id, relation="after"):
        return {
            "task_id": task_id,
            "before": [],
            "after": [{"id": related_id, "status": "open", "priority": 1, "title": "Next"}],
        }

    def remove_dependency(self, task_id, related_id):
        return None

    def get_graph(self, include_done=False):
        return {"nodes": [{"id": "t1"}, {"id": "t2"}], "edges": [{"before_id": "t1", "after_id": "t2"}]}

    def associate(self, task_id, **kwargs):
        return {"item": {"id": "i1"}}

    def unassociate(self, task_id, item_id):
        return None

    def list_items(self, source=None):
        return [{"id": "i1", "source": "note", "title": "N"}]

    def get_item(self, item_id):
        return {"id": item_id, "source": "note", "title": "N"}

    def create_item(self, **fields):
        return {"id": "i2", "source": "note", "title": "N"}

    def update_item(self, item_id, **fields):
        return {"id": item_id, "source": "note", "title": "N"}

    def refresh_item(self, item_id):
        return {"id": item_id, "source": "note", "title": "N"}

    def delete_item(self, item_id):
        return None

    def list_repositories(self):
        return [{"id": "r1", "name": "r", "path": "/p"}]

    def add_repository(self, path, name=None):
        return {"id": "r2", "name": "r", "path": path}

    def remove_repository(self, repository_id):
        return None

    def list_harnesses(self, full=False):
        return [{"id": "opencode", "available": True, "detail": "/usr/bin/opencode"}]

    def create_harness(self, **fields):
        return {"id": "h1", "command": fields.get("command")}

    def update_harness(self, harness_id, **fields):
        return {"id": harness_id, "command": "c"}

    def delete_harness(self, harness_id):
        return None

    def list_worktrees(self, task_id):
        return [{"id": "w1", "status": "active", "branch": "b", "path": "/w"}]

    def create_worktree(self, task_id, repository_id=None, branch=None, base=None):
        return {"id": "w2", "branch": "b", "path": "/w"}

    def remove_worktree(self, task_id, worktree_id):
        return None

    def list_runs(self, task_id):
        return [{"id": "r1", "status": "queued", "kind": "chat", "prompt": "p"}]

    def get_run(self, run_id):
        return {
            "id": run_id,
            "status": "succeeded",
            "kind": "chat",
            "prompt": "p",
            "session_id": "s",
            "cwd": "/w",
            "links": [{"label": "L", "url": "u"}],
        }

    def run_events(self, run_id):
        return [{"type": "message", "text": "hi"}]

    def create_run(self, task_id, prompt, **kwargs):
        return {"id": "r3", "status": "queued", "cwd": "/w"}

    def cancel_run(self, run_id):
        return {"id": run_id, "status": "cancelled"}

    def list_sessions(self, task_id):
        return [{"id": "s1", "task_id": task_id, "session_id": "ses_1", "label": "first"}]

    def get_session(self, task_id, session_id):
        return {
            "id": session_id,
            "task_id": task_id,
            "session_id": "ses_1",
            "label": "first",
            "harness_id": "opencode",
            "cwd": "/w",
            "links": [{"label": "L", "command": "c"}],
        }

    def create_session(self, task_id, session_id, harness_id=None, cwd=None, label=""):
        return {"id": "s2", "task_id": task_id, "session_id": session_id, "label": label}

    def update_session(self, task_id, session_id, **fields):
        return {"id": session_id, "task_id": task_id, "session_id": "ses_1", "label": fields.get("label") or "first"}

    def delete_session(self, task_id, session_id):
        return None

    def get_context(self, task_id):
        return {"summary": "s", "next_steps": [{"text": "a", "done": True}]}

    def refresh_context(self, task_id):
        return {"id": "r4"}

    def get_settings(self):
        return {"effective": {"openchamber_url": "x"}}

    def update_settings(self, **fields):
        return {"effective": {"openchamber_url": "x"}}

    def stream_run(self, run_id):
        return iter([{"type": "message", "text": "hi"}, {"type": "run_finished", "text": ""}])

    def list_operations(self, client=None, actor=None, limit=100):
        return [
            {
                "id": "o1",
                "method": "POST",
                "path": "/api/tasks",
                "status_code": 201,
                "client": "cli",
                "actor": "agent",
                "created_at": "2026-01-01T00:00:00",
            }
        ]

    def list_stack(self):
        return [
            {
                "id": "s1",
                "task_id": "t1",
                "task": {"title": "T"},
                "position": 0,
                "is_current": True,
                "execution_count": 2,
                "duration": 90,
                "created_at": "2026-01-01T00:00:00",
                "deleted_at": None,
            }
        ]

    def stack_history(self):
        return [
            {
                "id": "s0",
                "task_id": "t0",
                "task": {"title": "Old"},
                "position": 0,
                "is_current": False,
                "execution_count": 1,
                "duration": 10,
                "created_at": "2026-01-01T00:00:00",
                "deleted_at": "2026-01-02T00:00:00",
            }
        ]

    def stack_current(self):
        return {
            "id": "s1",
            "task_id": "t1",
            "task": {"title": "T"},
            "position": 0,
            "is_current": True,
            "execution_count": 2,
            "duration": 90,
        }

    def push_stack(self, **fields):
        return [
            {
                "id": "s2",
                "task_id": "t2",
                "task": {"title": fields.get("title") or "existing"},
                "position": 0,
                "is_current": True,
                "execution_count": 1,
                "duration": 0,
            }
        ]

    def pop_stack(self):
        return []

    def reorder_stack(self, entry_id, position):
        return [
            {
                "id": entry_id,
                "task_id": "t1",
                "task": {"title": "T"},
                "position": position,
                "is_current": position == 0,
                "execution_count": 1,
                "duration": 0,
            }
        ]

    def promote_stack(self, entry_id):
        return self.reorder_stack(entry_id, 0)

    def update_stack_entry(self, entry_id, **fields):
        return [
            {
                "id": entry_id,
                "task_id": "t1",
                "task": {"title": fields.get("title") or "T"},
                "position": 0,
                "is_current": True,
                "execution_count": 1,
                "duration": 0,
            }
        ]

    def remove_stack_entry(self, entry_id):
        return None

    def list_schedules(self):
        return [
            {
                "id": "s1",
                "name": "N",
                "command": "echo hi",
                "schedule": "0 9 * * *",
                "cwd": None,
                "timezone": "Europe/Paris",
                "enabled": True,
                "next_run_at": "2026-01-02T09:00:00Z",
                "last_status": "succeeded",
            }
        ]

    def get_schedule(self, schedule_id):
        return self.list_schedules()[0]

    def create_schedule(self, name, command, schedule, cwd=None, timezone=None, enabled=None):
        return {
            **self.list_schedules()[0],
            "id": "s2",
            "name": name,
            "command": command,
            "schedule": schedule,
            "timezone": timezone or self.list_schedules()[0]["timezone"],
        }

    def update_schedule(self, schedule_id, **fields):
        # Mirror the real client, which drops None so the API keeps its defaults.
        fields = {key: value for key, value in fields.items() if value is not None}
        return {**self.list_schedules()[0], **fields}

    def delete_schedule(self, schedule_id):
        return None

    def run_schedule(self, schedule_id):
        return {"id": "r1", "scheduled_task_id": schedule_id, "status": "running"}

    def schedule_runs(self, schedule_id, limit=20):
        return [
            {
                "id": "r1",
                "scheduled_task_id": schedule_id,
                "status": "succeeded",
                "exit_code": 0,
                "output": "hi\n",
                "started_at": "2026-01-02T09:00:00",
            }
        ]

    def schedule_executions(self, limit=100):
        run = self.schedule_runs("s1")[0]
        return [{**run, "task_name": "Nightly", "task_command": "echo hi"}]
