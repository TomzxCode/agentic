"""FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from .agents import seed_harnesses
from .config import settings
from .db import create_db_and_tables, engine
from .routers import agents, fs, groups, items, problems, repositories, worktrees
from .routers import settings as settings_router

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    with Session(engine) as session:
        seed_harnesses(session)
    log.info("agentic ready", data_dir=str(settings.data_dir))
    yield


app = FastAPI(title="Agentic", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (repositories, groups, items, problems, worktrees, agents, settings_router, fs):
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentic"}


def _mount_frontend() -> None:
    static_dir = settings.static_dir
    if not (static_dir / "index.html").exists():
        log.info("frontend build not found; API only", static_dir=str(static_dir))
        return
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
    if (static_dir / "icons").is_dir():
        app.mount("/icons", StaticFiles(directory=static_dir / "icons"), name="icons")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (static_dir / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(static_dir.resolve())):
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")


_mount_frontend()
