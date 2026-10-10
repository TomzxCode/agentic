"""Application settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTIC_", env_file=".env", extra="ignore")

    # Storage
    data_dir: Path = Path.home() / ".agentic"
    database_url: str | None = None

    # Where git worktrees are created for problems.
    worktree_root: Path = Path.home() / ".agentic" / "worktrees"

    # Static frontend build output (frontend/dist). Served when it exists.
    static_dir: Path = Path(__file__).resolve().parents[2] / "static"

    # CORS origins for the Vite dev server.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Default harness used when a problem does not specify one.
    default_harness: str = "opencode"

    # Auto-approve ACP permission requests (single-user local tool). When false,
    # permission requests are surfaced to the UI and the run waits.
    auto_approve_permissions: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "agentic.db"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.db_path}"


settings = Settings()
