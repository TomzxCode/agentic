"""Application settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTIC_", env_file=".env", extra="ignore")

    # Storage
    data_dir: Path = Path.home() / ".agentic"
    database_url: str | None = None

    # Agent-run queue (SAQ). Defaults to a SQLite queue next to the app database,
    # so a plain `uv sync` needs no external service. Override with a
    # redis://, postgres://, or sqlite:// URL to point the queue elsewhere.
    queue_url: str | None = None
    # How many agent runs a worker processes concurrently.
    worker_concurrency: int = 4
    # How often (seconds) a worker sweeps for stuck jobs (a dead worker's run).
    worker_sweep: int = 60
    # A run's job timeout in seconds (0 disables it). The heartbeat is how long a
    # job may go without a touch before a sweep considers it stuck and retries it.
    job_timeout: int = 0
    job_heartbeat: int = 120
    job_retries: int = 1

    # Where git worktrees are created for tasks.
    worktree_root: Path = Path.home() / ".agentic" / "worktrees"

    # Root the repository picker may browse. Defaults to the home directory;
    # set to "/" to allow browsing anywhere on the machine.
    fs_root: Path = Path.home()

    # Root of the user-global SDLC reviews store the review skills write to
    # ($HOME/.sdlc/{owner}/{repo}/pull-requests/{n}/). Read-only here.
    sdlc_dir: Path = Path.home() / ".sdlc"

    # Static frontend build output (frontend/dist). Served when it exists.
    static_dir: Path = Path(__file__).resolve().parents[2] / "static"

    # CORS origins for the Vite dev server.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Default harness used when a task does not specify one.
    default_harness: str = "opencode"

    # The GitHub login that counts as "you": a merged pull request is only
    # offered a change record when this account authored it. Empty auto-detects
    # the authenticated `gh` account (see ``detect_github_login``).
    github_login: str = ""

    # Session links. These are defaults; the Settings page can override them,
    # and overrides are stored in the database.
    # OpenChamber opens a session at "<base><path>" (default: /?session=<id>).
    openchamber_url: str = ""
    openchamber_session_path: str = "/?session={session}"
    # Optional URL template for opening a session in a terminal, e.g.
    # "opencode://session/{session}" or "http://localhost:7681/?cwd={cwd}".
    # Placeholders: {session} {cwd} {harness}.
    terminal_url_template: str = ""

    # Optional URL template for opening a worktree in an editor, e.g.
    # "vscode://file/{path}" or "zed://file/{path}". Placeholder: {path}.
    editor_url_template: str = ""

    # How often to re-fetch Slack threads (via slackx) and GitHub issues/PRs
    # (via ghx). Each is a tiered age policy: "1d=1h,7d=6h,30d=1d,*=7d"
    # refreshes hourly while an item is under a day old, every 6h under a week,
    # daily under 30 days, and weekly past that. Empty disables that source.
    slack_refresh_policy: str = ""
    github_refresh_policy: str = ""
    # How often (seconds) the API checks for due items. 0 disables the loop.
    item_refresh_tick: int = 300

    # Auto-approve ACP permission requests (single-user local tool). When false,
    # permission requests are surfaced to the UI and the run waits.
    auto_approve_permissions: bool = True

    # Scheduled shell tasks. How often (seconds) the API checks for due
    # scheduled tasks; 0 disables the scheduler. A task's command is killed
    # after scheduled_task_timeout seconds; 0 means no timeout.
    scheduled_task_tick: int = 30
    scheduled_task_timeout: int = 3600

    @property
    def db_path(self) -> Path:
        return self.data_dir / "agentic.db"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.db_path}"

    @property
    def queue_dsn(self) -> str:
        """The SAQ queue URL. An absolute SQLite path needs the four-slash form."""
        if self.queue_url:
            return self.queue_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:////{(self.data_dir / 'queue.db').as_posix().lstrip('/')}"

    @property
    def queue_path(self) -> Path:
        return self.data_dir / "queue.db"


settings = Settings()
