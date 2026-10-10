"""HTTP client for the Agentic API, used by the CLI.

Talks to a running server over HTTP so the same CLI works locally and against a
remote instance. Base URL comes from ``--api-url`` or ``AGENTIC_API_URL``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8600"


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
    ) -> None:
        self.base_url = (base_url or DEFAULT_API_URL).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)

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

    # --- problems ---------------------------------------------------------
    def list_problems(self, status: str | None = None, q: str | None = None) -> list[dict]:
        params = {k: v for k, v in {"status": status, "q": q}.items() if v}
        return self._request("GET", "/api/problems", params=params)

    def get_problem(self, problem_id: str) -> dict:
        return self._request("GET", f"/api/problems/{problem_id}")

    def create_problem(self, **fields: Any) -> dict:
        return self._request("POST", "/api/problems", json=_compact(fields))

    def update_problem(self, problem_id: str, **fields: Any) -> dict:
        return self._request("PATCH", f"/api/problems/{problem_id}", json=_compact(fields))

    def delete_problem(self, problem_id: str) -> None:
        self._request("DELETE", f"/api/problems/{problem_id}")

    def problem_timeline(self, problem_id: str) -> list[dict]:
        return self._request("GET", f"/api/problems/{problem_id}/timeline")

    def associate(
        self,
        problem_id: str,
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
        return self._request("POST", f"/api/problems/{problem_id}/items", json=body)

    def unassociate(self, problem_id: str, item_id: str) -> None:
        self._request("DELETE", f"/api/problems/{problem_id}/items/{item_id}")

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
    def list_worktrees(self, problem_id: str) -> list[dict]:
        return self._request("GET", f"/api/problems/{problem_id}/worktrees")

    def create_worktree(
        self,
        problem_id: str,
        repository_id: str | None = None,
        branch: str | None = None,
        base: str | None = None,
    ) -> dict:
        return self._request(
            "POST",
            f"/api/problems/{problem_id}/worktrees",
            json=_compact({"repository_id": repository_id, "branch": branch, "base": base}),
        )

    def remove_worktree(self, problem_id: str, worktree_id: str) -> None:
        self._request("DELETE", f"/api/problems/{problem_id}/worktrees/{worktree_id}")

    # --- runs -------------------------------------------------------------
    def list_runs(self, problem_id: str) -> list[dict]:
        return self._request("GET", f"/api/problems/{problem_id}/runs")

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/api/runs/{run_id}")

    def run_events(self, run_id: str) -> list[dict]:
        return self._request("GET", f"/api/runs/{run_id}/events")

    def create_run(
        self,
        problem_id: str,
        prompt: str,
        harness_id: str | None = None,
        worktree_id: str | None = None,
        cwd: str | None = None,
    ) -> dict:
        return self._request(
            "POST",
            f"/api/problems/{problem_id}/runs",
            json=_compact({"prompt": prompt, "harness_id": harness_id, "worktree_id": worktree_id, "cwd": cwd}),
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

    # --- context ----------------------------------------------------------
    def get_context(self, problem_id: str) -> dict:
        return self._request("GET", f"/api/problems/{problem_id}/context")

    def refresh_context(self, problem_id: str) -> dict:
        return self._request("POST", f"/api/problems/{problem_id}/context/refresh")

    # --- settings ---------------------------------------------------------
    def get_settings(self) -> dict:
        return self._request("GET", "/api/settings")

    def update_settings(self, **fields: Any) -> dict:
        return self._request("PATCH", "/api/settings", json=_compact(fields))


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None so the API applies its own defaults."""
    return {key: value for key, value in data.items() if value is not None}
