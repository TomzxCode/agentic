"""HTTP client for the Agentic API, used by the CLI.

Talks to a running server over HTTP so the same CLI works locally and against a
remote instance. Base URL comes from ``--api-url`` or ``AGENTIC_API_URL``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8600"

# Declare the CLI, and whether a person or a coding agent is running it. The
# harness sets AGENTIC_ACTOR=agent for the agent process it spawns.
CLIENT_HEADER = "X-Agentic-Client"
ACTOR_HEADER = "X-Agentic-Actor"


class ApiError(RuntimeError):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class AgenticClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        actor: str | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_API_URL).rstrip("/")
        self.actor = actor or os.environ.get("AGENTIC_ACTOR", "human")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers={CLIENT_HEADER: "cli", ACTOR_HEADER: self.actor},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AgenticClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        if response.status_code == 204:
            return None
        try:
            data: Any = response.json()
        except ValueError:
            data = response.text
        if response.status_code >= 400:
            detail = data.get("detail") if isinstance(data, dict) else data
            raise ApiError(response.status_code, detail)
        return data

    # --- health -----------------------------------------------------------
    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/health")

    # --- tasks ---------------------------------------------------------
    def list_tasks(self, status: str | None = None, q: str | None = None, tags: list[str] | None = None) -> list[dict]:
        params: list[tuple[str, str]] = []
        if status:
            params.append(("status", status))
        if q:
            params.append(("q", q))
        for tag in tags or []:
            params.append(("tag", tag))
        return self._request("GET", "/api/tasks", params=params)

    def get_task(self, task_id: str) -> dict:
        return self._request("GET", f"/api/tasks/{task_id}")

    def create_task(self, **fields: Any) -> dict:
        return self._request("POST", "/api/tasks", json=_compact(fields))

    def update_task(self, task_id: str, **fields: Any) -> dict:
        return self._request("PATCH", f"/api/tasks/{task_id}", json=_compact(fields))

    def set_task_deadline(self, task_id: str, deadline: str | None) -> dict:
        """Set or clear a task's deadline; pass ``None`` to clear it."""
        return self._request("PATCH", f"/api/tasks/{task_id}", json={"deadline": deadline})

    def set_task_waiting(self, task_id: str, person_id: str | None, follow_up_at: str | None = None) -> dict:
        """Set or clear who a task waits on; clearing also clears the follow-up date."""
        body: dict[str, Any] = {"waiting_on_person_id": person_id}
        if person_id is not None:
            body["follow_up_at"] = follow_up_at
        return self._request("PATCH", f"/api/tasks/{task_id}", json=body)

    def set_task_snooze(self, task_id: str, snoozed_until: str | None) -> dict:
        """Set or clear a task's snooze date; pass ``None`` to clear it."""
        return self._request("PATCH", f"/api/tasks/{task_id}", json={"snoozed_until": snoozed_until})

    def list_deadlines(self, within_days: int = 7) -> list[dict]:
        """In-flight tasks with a deadline in the next ``within_days`` (overdue included)."""
        return self._request("GET", "/api/tasks/deadlines", params={"within_days": within_days})

    def delete_task(self, task_id: str) -> None:
        self._request("DELETE", f"/api/tasks/{task_id}")

    def task_timeline(self, task_id: str) -> list[dict]:
        return self._request("GET", f"/api/tasks/{task_id}/timeline")

    def send_event_to_slack(self, event_id: str, body: dict | None = None) -> dict:
        return self._request("POST", f"/api/events/{event_id}/slack", json=body or {})

    def send_events_to_slack(self, body: dict | None = None) -> dict:
        return self._request("POST", "/api/slack/events", json=body or {})

    def associate(
        self,
        task_id: str,
        *,
        item_id: str | None = None,
        item: dict | None = None,
        note: str = "",
    ) -> dict:
        body: dict[str, Any] = {"note": note}
        if item_id:
            body["item_id"] = item_id
        if item is not None:
            body["item"] = _compact(item)
        return self._request("POST", f"/api/tasks/{task_id}/items", json=body)

    def unassociate(self, task_id: str, item_id: str) -> None:
        self._request("DELETE", f"/api/tasks/{task_id}/items/{item_id}")

    def task_dependencies(self, task_id: str) -> dict:
        """The tasks linked before and after this one."""
        return self._request("GET", f"/api/tasks/{task_id}/dependencies")

    def add_dependency(self, task_id: str, related_id: str, relation: str = "after") -> dict:
        """Link a related task before or after this one (relation: before | after)."""
        return self._request(
            "POST", f"/api/tasks/{task_id}/dependencies", json={"related_id": related_id, "relation": relation}
        )

    def remove_dependency(self, task_id: str, related_id: str) -> None:
        self._request("DELETE", f"/api/tasks/{task_id}/dependencies/{related_id}")

    def get_graph(self, include_done: bool = False) -> dict:
        """The whole before/after graph: every task and the edges between them."""
        params = {"include_done": "true"} if include_done else None
        return self._request("GET", "/api/graph", params=params)

    # --- items ------------------------------------------------------------
    def list_items(self, source: str | None = None) -> list[dict]:
        params = {"source": source} if source else {}
        return self._request("GET", "/api/items", params=params)

    def get_item(self, item_id: str) -> dict:
        return self._request("GET", f"/api/items/{item_id}")

    def create_item(self, **fields: Any) -> dict:
        return self._request("POST", "/api/items", json=_compact(fields))

    def update_item(self, item_id: str, **fields: Any) -> dict:
        return self._request("PATCH", f"/api/items/{item_id}", json=_compact(fields))

    def refresh_item(self, item_id: str) -> dict:
        return self._request("POST", f"/api/items/{item_id}/refresh")

    def refresh_due_items(self) -> dict:
        return self._request("POST", "/api/items/refresh-due")

    def refresh_source(self, source: str) -> dict:
        return self._request("POST", f"/api/items/refresh-source/{source}")

    def delete_item(self, item_id: str) -> None:
        self._request("DELETE", f"/api/items/{item_id}")

    # --- repositories -----------------------------------------------------
    def list_repositories(self) -> list[dict]:
        return self._request("GET", "/api/repositories")

    def add_repository(self, path: str, name: str | None = None) -> dict:
        return self._request("POST", "/api/repositories", json=_compact({"path": path, "name": name}))

    def remove_repository(self, repository_id: str) -> None:
        self._request("DELETE", f"/api/repositories/{repository_id}")

    # --- harnesses --------------------------------------------------------
    def list_harnesses(self, full: bool = False) -> list[dict]:
        return self._request("GET", "/api/harnesses/full" if full else "/api/harnesses")

    def create_harness(self, **fields: Any) -> dict:
        return self._request("POST", "/api/harnesses", json=_compact(fields))

    def update_harness(self, harness_id: str, **fields: Any) -> dict:
        return self._request("PATCH", f"/api/harnesses/{harness_id}", json=_compact(fields))

    def delete_harness(self, harness_id: str) -> None:
        self._request("DELETE", f"/api/harnesses/{harness_id}")

    # --- worktrees --------------------------------------------------------
    def list_worktrees(self, task_id: str) -> list[dict]:
        return self._request("GET", f"/api/tasks/{task_id}/worktrees")

    def create_worktree(
        self,
        task_id: str,
        repository_id: str | None = None,
        branch: str | None = None,
        base: str | None = None,
    ) -> dict:
        return self._request(
            "POST",
            f"/api/tasks/{task_id}/worktrees",
            json=_compact({"repository_id": repository_id, "branch": branch, "base": base}),
        )

    def remove_worktree(self, task_id: str, worktree_id: str) -> None:
        self._request("DELETE", f"/api/tasks/{task_id}/worktrees/{worktree_id}")

    # --- runs -------------------------------------------------------------
    def list_runs(self, task_id: str) -> list[dict]:
        return self._request("GET", f"/api/tasks/{task_id}/runs")

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/api/runs/{run_id}")

    def run_events(self, run_id: str) -> list[dict]:
        return self._request("GET", f"/api/runs/{run_id}/events")

    def create_run(
        self,
        task_id: str,
        prompt: str,
        harness_id: str | None = None,
        worktree_id: str | None = None,
        cwd: str | None = None,
        model: str | None = None,
    ) -> dict:
        return self._request(
            "POST",
            f"/api/tasks/{task_id}/runs",
            json=_compact(
                {
                    "prompt": prompt,
                    "harness_id": harness_id,
                    "worktree_id": worktree_id,
                    "cwd": cwd,
                    "model": model,
                }
            ),
        )

    def cancel_run(self, run_id: str) -> dict:
        return self._request("POST", f"/api/runs/{run_id}/cancel")

    def stream_run(self, run_id: str) -> Iterator[dict]:
        """Yield agent events for a run as they arrive (server-sent events)."""
        import json

        with self._client.stream("GET", f"/api/runs/{run_id}/stream") as response:
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if payload:
                    yield json.loads(payload)

    # --- sessions ---------------------------------------------------------
    def list_sessions(self, task_id: str) -> list[dict]:
        return self._request("GET", f"/api/tasks/{task_id}/sessions")

    def get_session(self, task_id: str, session_id: str) -> dict:
        return self._request("GET", f"/api/tasks/{task_id}/sessions/{session_id}")

    def create_session(
        self,
        task_id: str,
        session_id: str,
        harness_id: str | None = None,
        cwd: str | None = None,
        label: str = "",
    ) -> dict:
        return self._request(
            "POST",
            f"/api/tasks/{task_id}/sessions",
            json=_compact({"session_id": session_id, "harness_id": harness_id, "cwd": cwd, "label": label}),
        )

    def update_session(self, task_id: str, session_id: str, **fields: Any) -> dict:
        return self._request("PATCH", f"/api/tasks/{task_id}/sessions/{session_id}", json=_compact(fields))

    def delete_session(self, task_id: str, session_id: str) -> None:
        self._request("DELETE", f"/api/tasks/{task_id}/sessions/{session_id}")

    # --- context ----------------------------------------------------------
    def get_context(self, task_id: str) -> dict:
        return self._request("GET", f"/api/tasks/{task_id}/context")

    def refresh_context(self, task_id: str) -> dict:
        return self._request("POST", f"/api/tasks/{task_id}/context/refresh")

    # --- settings ---------------------------------------------------------
    def get_settings(self) -> dict:
        return self._request("GET", "/api/settings")

    def refresh_status(self) -> dict:
        return self._request("GET", "/api/settings/refresh-status")

    def update_settings(self, **fields: Any) -> dict:
        return self._request("PATCH", "/api/settings", json=_compact(fields))

    # --- tags -------------------------------------------------------------
    def list_tags(self) -> list[dict]:
        return self._request("GET", "/api/tags")

    # --- people -----------------------------------------------------------
    def list_people(self) -> list[dict]:
        return self._request("GET", "/api/people")

    def get_person(self, person_id: str) -> dict:
        return self._request("GET", f"/api/people/{person_id}")

    def create_person(self, **fields: Any) -> dict:
        return self._request("POST", "/api/people", json=_compact(fields))

    def update_person(self, person_id: str, **fields: Any) -> dict:
        return self._request("PATCH", f"/api/people/{person_id}", json=_compact(fields))

    def delete_person(self, person_id: str) -> None:
        self._request("DELETE", f"/api/people/{person_id}")

    def merge_person(self, source_id: str, target_id: str) -> dict:
        return self._request("POST", f"/api/people/{target_id}/merge", json={"source_id": source_id})

    def link_person(self, person_id: str, *, task_id: str | None = None, item_id: str | None = None) -> dict:
        if task_id:
            return self._request("POST", f"/api/tasks/{task_id}/people", json={"person_id": person_id})
        return self._request("POST", f"/api/items/{item_id}/people", json={"person_id": person_id})

    def unlink_person(self, person_id: str, *, task_id: str | None = None, item_id: str | None = None) -> None:
        if task_id:
            self._request("DELETE", f"/api/tasks/{task_id}/people/{person_id}")
        else:
            self._request("DELETE", f"/api/items/{item_id}/people/{person_id}")

    def link_requester(self, person_id: str, task_id: str) -> dict:
        return self._request("POST", f"/api/tasks/{task_id}/requesters", json={"person_id": person_id})

    def unlink_requester(self, person_id: str, task_id: str) -> None:
        self._request("DELETE", f"/api/tasks/{task_id}/requesters/{person_id}")

    # --- changes ----------------------------------------------------------
    def list_changes(
        self,
        task_id: str | None = None,
        status: str | None = None,
        change_class: str | None = None,
    ) -> list[dict]:
        params = {
            key: value
            for key, value in {"task_id": task_id, "status": status, "change_class": change_class}.items()
            if value
        }
        return self._request("GET", "/api/changes", params=params)

    def get_change(self, change_id: str) -> dict:
        return self._request("GET", f"/api/changes/{change_id}")

    def create_change(self, **fields: Any) -> dict:
        return self._request("POST", "/api/changes", json=_compact(fields))

    def update_change(self, change_id: str, **fields: Any) -> dict:
        return self._request("PATCH", f"/api/changes/{change_id}", json=_compact(fields))

    def transition_change(self, change_id: str, status: str) -> dict:
        return self._request("POST", f"/api/changes/{change_id}/status", json={"status": status})

    def add_intervention(self, change_id: str, kind: str = "other", note: str = "") -> dict:
        return self._request("POST", f"/api/changes/{change_id}/interventions", json={"kind": kind, "note": note})

    def delete_change(self, change_id: str) -> None:
        self._request("DELETE", f"/api/changes/{change_id}")

    # --- metrics ----------------------------------------------------------
    def get_metrics(
        self,
        window_days: int | None = None,
        observation_days: int | None = None,
        tolerance: float | None = None,
        task_id: str | None = None,
        change_class: str | None = None,
    ) -> dict:
        params: list[tuple[str, Any]] = []
        for key, value in (
            ("window_days", window_days),
            ("observation_days", observation_days),
            ("tolerance", tolerance),
            ("task_id", task_id),
            ("change_class", change_class),
        ):
            if value is not None:
                params.append((key, value))
        return self._request("GET", "/api/metrics", params=params)

    def get_cycle_time(
        self,
        days: int | None = None,
        bucket_days: int | None = None,
        repository_id: str | None = None,
        refresh: bool | None = None,
    ) -> dict:
        params: list[tuple[str, Any]] = []
        for key, value in (
            ("days", days),
            ("bucket_days", bucket_days),
            ("repository_id", repository_id),
            ("refresh", "true" if refresh else None),
        ):
            if value is not None:
                params.append((key, value))
        return self._request("GET", "/api/metrics/cycle-time", params=params)

    def list_baselines(self) -> list[dict]:
        return self._request("GET", "/api/metrics/baselines")

    def set_baseline(self, metric: str, value: float, **fields: Any) -> dict:
        return self._request("PUT", f"/api/metrics/baselines/{metric}", json={"value": value, **_compact(fields)})

    def delete_baseline(self, metric: str) -> None:
        self._request("DELETE", f"/api/metrics/baselines/{metric}")

    # --- stack (focus queue) ----------------------------------------------
    def list_stack(self) -> list[dict]:
        return self._request("GET", "/api/stack")

    def stack_history(self) -> list[dict]:
        return self._request("GET", "/api/stack/history")

    def stack_current(self) -> dict | None:
        return self._request("GET", "/api/stack/current")

    def push_stack(self, **fields: Any) -> list[dict]:
        return self._request("POST", "/api/stack", json=_compact(fields))

    def pop_stack(self) -> list[dict]:
        return self._request("POST", "/api/stack/pop")

    def reorder_stack(self, entry_id: str, position: int) -> list[dict]:
        return self._request("POST", "/api/stack/reorder", json={"entry_id": entry_id, "position": position})

    def promote_stack(self, entry_id: str) -> list[dict]:
        return self._request("POST", f"/api/stack/{entry_id}/promote")

    def update_stack_entry(self, entry_id: str, **fields: Any) -> list[dict]:
        return self._request("PATCH", f"/api/stack/{entry_id}", json=_compact(fields))

    def remove_stack_entry(self, entry_id: str) -> None:
        self._request("DELETE", f"/api/stack/{entry_id}")

    # --- scheduled shell tasks --------------------------------------------
    def list_schedules(self) -> list[dict]:
        return self._request("GET", "/api/schedules")

    def get_schedule(self, schedule_id: str) -> dict:
        return self._request("GET", f"/api/schedules/{schedule_id}")

    def create_schedule(
        self,
        name: str,
        command: str,
        schedule: str,
        cwd: str | None = None,
        timezone: str | None = None,
        enabled: bool | None = None,
    ) -> dict:
        return self._request(
            "POST",
            "/api/schedules",
            json=_compact(
                {
                    "name": name,
                    "command": command,
                    "schedule": schedule,
                    "cwd": cwd,
                    "timezone": timezone,
                    "enabled": enabled,
                }
            ),
        )

    def update_schedule(self, schedule_id: str, **fields: Any) -> dict:
        return self._request("PATCH", f"/api/schedules/{schedule_id}", json=_compact(fields))

    def delete_schedule(self, schedule_id: str) -> None:
        self._request("DELETE", f"/api/schedules/{schedule_id}")

    def run_schedule(self, schedule_id: str) -> dict:
        """Start a scheduled task now; returns the run row (initially running)."""
        return self._request("POST", f"/api/schedules/{schedule_id}/run")

    def schedule_runs(self, schedule_id: str, limit: int = 20) -> list[dict]:
        return self._request("GET", f"/api/schedules/{schedule_id}/runs", params={"limit": limit})

    def schedule_executions(self, limit: int = 100) -> list[dict]:
        """Every scheduled task's runs, newest first."""
        return self._request("GET", "/api/schedules/runs", params={"limit": limit})

    # --- operations (provenance audit log) --------------------------------
    def list_operations(
        self,
        *,
        client: str | None = None,
        actor: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        params = {
            key: value for key, value in {"client": client, "actor": actor, "limit": limit}.items() if value is not None
        }
        return self._request("GET", "/api/operations", params=params)


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None so the API applies its own defaults."""
    return {key: value for key, value in data.items() if value is not None}
