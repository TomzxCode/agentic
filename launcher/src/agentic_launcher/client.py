"""HTTP client for the parts of the Agentic API the launcher needs."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Generator, Iterable, Iterator

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8600"

# Declare the client and actor, matching the CLI's provenance headers.
CLIENT_HEADER = "X-Agentic-Client"
ACTOR_HEADER = "X-Agentic-Actor"


def _decode(data: list[str]) -> list[dict] | None:
    if not data:
        return None
    try:
        value = json.loads("\n".join(data))
    except ValueError:
        return None
    return value if isinstance(value, list) else None


def sse_entries(lines: Iterable[str]) -> Iterator[list[dict]]:
    """Yield the stack snapshots carried by a server-sent event line stream.

    A block is the ``data:`` lines up to the next blank line; comments (the
    server's pings) and any non-list payload are skipped.
    """
    data: list[str] = []
    for line in lines:
        if line == "":
            entries = _decode(data)
            data = []
            if entries is not None:
                yield entries
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    entries = _decode(data)
    if entries is not None:
        yield entries


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

    @contextlib.contextmanager
    def stream_stack(self) -> Generator[httpx.Response, None, None]:
        """Hold the stack stream open; the server pings every 15 seconds."""
        timeout = httpx.Timeout(10.0, read=60.0)
        with self._client.stream("GET", "/api/stack/stream", timeout=timeout) as response:
            response.raise_for_status()
            yield response
