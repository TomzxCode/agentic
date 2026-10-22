"""Agentic user CLI.

A thin, scriptable client over the Agentic HTTP API, meant to be driven by
people and by agents. This is the user-facing client; the backend (running the
server) lives in ``agentic.server_cli``.

Commands return data; use ``--format json`` (or pipe the output, which selects
json automatically) for machine-readable results.
"""

from __future__ import annotations

import time as time
from typing import Annotated, Any, Literal

from cyclopts import App, Parameter
from rich.console import Console

from . import render as render
from . import runtime as runtime
from .client import DEFAULT_API_URL
from .commands import (
    changes,
    events,
    harnesses,
    health,
    items,
    links,
    metrics,
    operations,
    people,
    repositories,
    runs,
    schedules,
    settings,
    stack,
    tags,
    tasks,
)
from .runtime import CONTEXT

# --- app ------------------------------------------------------------------
# Plain console: no Rich markup (so `[open]` stays literal) and no wrapping
# (so json output stays valid when piped).
_CONSOLE = Console(markup=False, highlight=False, soft_wrap=True)

app = App(
    name="agentic",
    help="Drive the Agentic app (tasks, items, agents) from the command line.",
    console=_CONSOLE,
)
app.meta.console = _CONSOLE


@app.meta.default
def _launcher(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    api_url: str = DEFAULT_API_URL,
    format: Literal["auto", "json", "text"] = "auto",
    timeout: float = 60.0,
) -> Any:
    """Agentic CLI.

    Parameters
    ----------
    api_url
        Base URL of the Agentic API (default: $AGENTIC_API_URL or 127.0.0.1:8600).
    format
        Output format. `auto` uses json when stdout is not a terminal.
    timeout
        Per-request timeout in seconds.
    """
    CONTEXT.update(api_url=api_url, format=format, timeout=timeout)
    # Nested dispatch returns the command's value; return it so the meta app
    # prints it (and turns int results into exit codes).
    return app(tokens)


_COMMAND_MODULES = (
    health,
    tasks,
    tags,
    people,
    changes,
    events,
    metrics,
    items,
    links,
    repositories,
    runs,
    harnesses,
    settings,
    stack,
    schedules,
    operations,
)

for _module in _COMMAND_MODULES:
    _module.register(app)


def main() -> None:
    app.meta()


if __name__ == "__main__":
    main()
