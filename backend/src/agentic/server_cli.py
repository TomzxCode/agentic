"""Backend CLI: run and inspect the Agentic server.

Separate from the user-facing ``agentic`` client, which talks to a running API.
This command owns the process: it starts the server and reports its config.

    agentic-server                 # start the server (default)
    agentic-server serve --reload
    agentic-server worker          # process queued agent runs
    agentic-server info
"""

from __future__ import annotations

from cyclopts import App
from sqlmodel import Session, select

from .agents.harnesses import get_harness, harness_available, seed_harnesses
from .config import settings
from .db import create_db_and_tables, engine
from .models.agents import Harness


def serve(host: str = "127.0.0.1", port: int = 8600, reload: bool = False) -> None:
    """Run the Agentic API server (and serve the built SPA if present)."""
    import uvicorn

    uvicorn.run("agentic.main:app", host=host, port=port, reload=reload)


def worker(concurrency: int | None = None) -> None:
    """Run a background worker that processes queued agent runs.

    Separate from the API so long agent turns survive an API restart. Point it at
    the same queue with AGENTIC_QUEUE_URL (defaults to a SQLite queue in the data
    directory, so no external service is needed).
    """
    import asyncio

    from .jobs import run_worker
    from .log_setup import configure_logging

    configure_logging()
    asyncio.run(run_worker(concurrency=concurrency))


def info() -> None:
    """Print backend configuration, database location, and harness availability."""
    create_db_and_tables()
    with Session(engine) as session:
        seed_harnesses(session)
        harnesses = session.exec(select(Harness)).all()
        default = get_harness(session, None)

    static = settings.static_dir
    built = static.is_dir() and (static / "index.html").exists()
    print(f"data dir:     {settings.data_dir}")
    print(f"database:     {settings.db_path}")
    print(f"queue:        {settings.queue_dsn}")
    print(f"worktrees:    {settings.worktree_root}")
    print(f"static dir:   {static} (built: {built})")
    print(f"default harness: {default.id}")
    print("harnesses:")
    for harness in harnesses:
        available, detail = harness_available(harness)
        mark = "ok " if available else "   "
        star = "*" if harness.id == default.id else " "
        print(f" {star}{mark} {harness.id:<10} {detail or harness.command}")


app = App(name="agentic-server", help="Run and inspect the Agentic backend.")
app.command(serve, name="serve")
app.command(worker, name="worker")
app.command(info, name="info")
app.default(serve)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
