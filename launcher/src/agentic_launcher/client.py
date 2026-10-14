"""HTTP client for the parts of the Agentic API the launcher needs."""

from __future__ import annotations

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8600"

# Declare the client and actor, matching the CLI's provenance headers.
CLIENT_HEADER = "X-Agentic-Client"
ACTOR_HEADER = "X-Agentic-Actor"


class StackClient:
    def __init__(self, base_url: str | None = None, *, timeout: float = 10.0) -> None:
        self.base_url = (base_url or DEFAULT_API_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={CLIENT_HEADER: "cli", ACTOR_HEADER: "human"},
        )

    def close(self) -> None:
        self._client.close()

    def list_stack(self) -> list[dict]:
        return self._client.get("/api/stack").raise_for_status().json()

    def current(self) -> dict | None:
        return self._client.get("/api/stack/current").raise_for_status().json()

    def pop_stack(self) -> list[dict]:
        return self._client.post("/api/stack/pop").raise_for_status().json()
