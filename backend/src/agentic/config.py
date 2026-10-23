"""Application settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
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

    # Root of the markdown notes tree that holds the colleague-decisions reports
    # the extract-colleague-decisions skill writes (decisions/YYYY/MM/DD.md).
    # Read-only here. The skill's own NOTES_DIR name is accepted too.
    notes_dir: Path = Field(
        default=Path.home() / "notes",
        validation_alias=AliasChoices("AGENTIC_NOTES_DIR", "NOTES_DIR"),
    )

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

    # Slack: the credentials a poke uses to start a DM with a reviewer. They are
    # read under the same names slackx uses, so one configuration serves both;
    # the AGENTIC_ spellings are accepted too. An xoxc- web token also needs its
    # xoxd- cookie. Empty disables poking.
    slack_token: str = Field(default="", validation_alias=AliasChoices("AGENTIC_SLACK_TOKEN", "SLACK_TOKEN"))
    slack_cookie: str = Field(default="", validation_alias=AliasChoices("AGENTIC_SLACK_COOKIE", "SLACK_COOKIE"))
    # A bot token (xoxb-) used to post notifications as a bot rather than as
    # you. Empty falls back to SLACK_TOKEN.
    slack_bot_token: str = Field(
        default="", validation_alias=AliasChoices("AGENTIC_SLACK_BOT_TOKEN", "SLACK_BOT_TOKEN")
    )
    slack_bot_cookie: str = Field(
        default="", validation_alias=AliasChoices("AGENTIC_SLACK_BOT_COOKIE", "SLACK_BOT_COOKIE")
    )
    slack_api_base_url: str = Field(
        default="https://slack.com/api",
        validation_alias=AliasChoices("AGENTIC_SLACK_API_BASE_URL", "SLACK_API_BASE_URL"),
    )

    # The Slack user or channel that receives events sent through Slack. Empty
    # disables sending unless a recipient is given on the call.
    slack_user_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AGENTIC_SLACK_USER_ID", "SLACK_USER_ID", "AGENTIC_SLACK_EVENTS_USER_ID", "SLACK_EVENTS_USER_ID"
        ),
    )
    slack_events_user_id: str = Field(
        default="", validation_alias=AliasChoices("AGENTIC_SLACK_EVENTS_USER_ID", "SLACK_EVENTS_USER_ID")
    )
    slack_events_channel: str = Field(
        default="", validation_alias=AliasChoices("AGENTIC_SLACK_EVENTS_CHANNEL", "SLACK_EVENTS_CHANNEL")
    )
    slack_notify_user_id: str = Field(
        default="", validation_alias=AliasChoices("AGENTIC_SLACK_NOTIFY_USER_ID", "SLACK_NOTIFY_USER_ID")
    )

    # How the server runs the ghx and slackx helper CLIs: "cli" spawns the
    # binary per call, "rpc" sends the same command lines to the tool's own
    # JSON-RPC server instead (`ghx rpc serve`, `slackx rpc serve`), so one warm
    # process serves every read. The URL is the server's base URL; the
    # JSON-RPC endpoint lives at <url>/rpc. A token is only needed when a
    # server is bound beyond loopback.
    ghx_backend: Literal["cli", "rpc", "serve", "managed", "managed-serve", "managed_serve"] = "cli"
    ghx_rpc_url: str = "http://127.0.0.1:8090"
    ghx_rpc_token: str = ""
    slackx_backend: Literal["cli", "rpc", "serve", "managed", "managed-serve", "managed_serve"] = "cli"
    slackx_rpc_url: str = "http://127.0.0.1:8280"
    slackx_rpc_token: str = ""

    # Base URLs of the tools' own web UIs (`ghx serve`, `slackx serve`). When
    # set, GitHub and Slack items link into those UIs, so an item opens in the
    # local copy instead of the hosted one.
    ghx_url: str = ""
    slackx_url: str = ""

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

    # Keep an ACP session open for the default harness from API startup, so the
    # task view can list the harness's model choices without spawning it. Runs
    # are unaffected (the worker spawns its own session per run). False starts
    # nothing; the model list then comes from a short-lived session on request.
    warm_harness_session: bool = True

    # Start ghx and slackx as managed processes in serve mode alongside the
    # backend server, so their lifecycle is tied to it (they start when it
    # starts and stop when it stops). Enabled automatically when either tool's
    # backend is set to a managed serve mode; this flag forces it on for both.
    managed_tools: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "AGENTIC_MANAGED_TOOLS",
            "AGENTIC_MANAGE_TOOLS",
            "AGENTIC_MANAGED_TOOL_SERVERS",
            "AGENTIC_START_TOOL_SERVERS",
            "AGENTIC_TOOL_SERVERS_MANAGED",
            "AGENTIC_MANAGE_TOOL_SERVERS",
        ),
    )

    # Scheduled shell tasks. How often (seconds) the API checks for due
    # scheduled tasks; 0 disables the scheduler. A task's command is killed
    # after scheduled_task_timeout seconds; 0 means no timeout.
    scheduled_task_tick: int = 30
    scheduled_task_timeout: int = 3600

    # The review scan: a background pass that asks GitHub which pull requests
    # await the user's review, stored for the review queue. ``review_scan_interval``
    # is the cadence ("1h", "30m"; empty disables it); ``review_scan_tick`` is how
    # often (seconds) the API checks whether it is due, so a change to the
    # interval takes effect without a restart. ``review_scan_default`` decides
    # what a repository with no opinion of its own does: "include" every
    # repository, or "exclude" all but the ones marked include. The searches run
    # through `gh` (ghx has no search qualifiers), so ``gh`` must be installed.
    review_scan_interval: str = "1h"
    review_scan_tick: int = 300
    review_scan_default: str = "include"
    review_scan_limit: int = 100
    # Comma-separated logins left out of the scan, e.g. a dependency-bump bot.
    review_scan_exclude_authors: str = "dependabot[bot]"
    # The review SLO: how long a pull request may await the user's review before
    # the inbox flags it. A duration such as "1d" or "8h"; empty disables it.
    # The wait is measured from when the scan first saw the pull request waiting.
    review_slo: str = ""

    # Where application logs are written. Empty uses <data_dir>/logs/agentic.log.
    # Set to a path to override, or to "none"/"off" to disable file logging.
    log_file: str = Field(default="", validation_alias=AliasChoices("AGENTIC_LOG_FILE"))

    @property
    def log_path(self) -> Path | None:
        value = (self.log_file or "").strip().lower()
        if value in {"none", "off", "false", "0", ""}:
            # empty means default, not disabled; handle empty separately
            if value == "":
                return self.data_dir / "agentic.log"
            return None
        return Path(self.log_file)

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
