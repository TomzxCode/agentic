"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SettingsRead(BaseModel):
    effective: dict[str, str]
    overrides: dict[str, str]
    defaults: dict[str, str]


class SettingsUpdate(BaseModel):
    github_login: str | None = None
    openchamber_url: str | None = None
    openchamber_session_path: str | None = None
    terminal_url_template: str | None = None
    editor_url_template: str | None = None
    # Base URLs of the ghx and slackx web UIs, used to link items into them.
    ghx_url: str | None = None
    slackx_url: str | None = None
    # How the server runs the ghx and slackx helper CLIs: "cli" spawns the
    # binary per call, "rpc" sends the same command lines to the tool's own
    # JSON-RPC server (`ghx rpc serve`, `slackx rpc serve`). The URL is the
    # server's base (the endpoint is <url>/rpc); a token is only needed when a
    # server is bound beyond loopback.
    ghx_backend: str | None = None
    ghx_rpc_url: str | None = None
    ghx_rpc_token: str | None = None
    slackx_backend: str | None = None
    slackx_rpc_url: str | None = None
    slackx_rpc_token: str | None = None
    slack_refresh_policy: str | None = None
    slack_user_id: str | None = None
    slack_bot_token: str | None = None
    slack_events_user_id: str | None = None
    slack_events_channel: str | None = None
    slack_notify_user_id: str | None = None
    github_refresh_policy: str | None = None
    # The review scan's cadence ("1h", "30m"; empty disables it) and what a
    # repository with no policy of its own does (include or exclude).
    review_scan_interval: str | None = None
    review_scan_default: str | None = None
    # A JSON list of user-defined agent prompts (kind, label, template).
    agent_prompts: str | None = None


class RefreshTierRead(BaseModel):
    """One band of a refresh policy: an age bound and its refresh interval."""

    max_age_seconds: float
    interval_seconds: float | None = None


class RefreshPolicyPreview(BaseModel):
    """A refresh policy parsed for display, or the error that stopped it."""

    valid: bool = True
    error: str | None = None
    enabled: bool = False
    tiers: list[RefreshTierRead] = []
    fallback_seconds: float | None = None


class RefreshPolicyPreviewRequest(BaseModel):
    value: str = ""


class RefreshDueItem(BaseModel):
    """One item the refresh runner considered."""

    item_id: str
    source: str
    title: str
    refreshed: bool = False
    error: str | None = None


class RefreshDueReport(BaseModel):
    """The outcome of a run over the items the refresh policy says are due."""

    checked: int = 0
    due: int = 0
    refreshed: int = 0
    failed: int = 0
    items: list[RefreshDueItem] = []


class RefreshSourceStatus(BaseModel):
    """When a source was last refreshed, how it went, and what triggered it."""

    last_run_at: datetime | None = None
    refreshed: int = 0
    failed: int = 0
    error: str | None = None
    origin: str | None = None
    # Items refreshed across the runs of the last 24 hours, from the stored history.
    refreshed_24h: int = 0


class RefreshStatusRead(BaseModel):
    """Per-source background refresh status, keyed by source."""

    sources: dict[str, RefreshSourceStatus] = {}


class DependencyRead(BaseModel):
    """One external command the app may run and what probing it found."""

    id: str
    name: str
    command: str
    # "runtime" (the server's own interpreter), "tool" (a helper CLI), or
    # "harness" (an ACP agent command).
    category: str = "tool"
    required: bool = False
    purpose: str = ""
    present: bool = False
    path: str | None = None
    version: str | None = None
    error: str | None = None


class GhxHitRateRead(BaseModel):
    """How often one ghx retrieval was served from the local cache."""

    # A whole percentage; None when ghx recorded no retrieval of this kind.
    percent: int | None = None
    # The retrievals the percentage is computed over.
    retrievals: int = 0


class CachedRepositoryRead(BaseModel):
    """One repository in ghx's local cache."""

    repository: str
    issues: int = 0
    pull_requests: int = 0
    # For example "14d"; None when ghx has no cache metadata for the repository.
    cached_age: str | None = None
    status: str = ""
    # The cache hit rate per retrieval operation, as ghx reports it.
    issue_list: GhxHitRateRead = GhxHitRateRead()
    issue_view: GhxHitRateRead = GhxHitRateRead()
    pr_list: GhxHitRateRead = GhxHitRateRead()
    pr_view: GhxHitRateRead = GhxHitRateRead()


class GhxCacheRead(BaseModel):
    """The repositories ghx has cached, or why the listing failed."""

    available: bool = False
    error: str | None = None
    repositories: list[CachedRepositoryRead] = []


class SlackxCacheRead(BaseModel):
    """The counts and last-updated times in slackx's cache database."""

    available: bool = False
    error: str | None = None
    # Which Slack workspace's cache this is, and the database file it lives in.
    workspace: str | None = None
    db_path: str | None = None
    channel_count: int = 0
    user_count: int = 0
    thread_count: int = 0
    message_count: int = 0
    read_marker_count: int = 0
    channels_updated_at: datetime | None = None
    users_updated_at: datetime | None = None
    threads_updated_at: datetime | None = None


class DiagnosticsRead(BaseModel):
    """The result of probing every dependency the Diagnostics section lists."""

    dependencies: list[DependencyRead] = []
    ghx_cache: GhxCacheRead = GhxCacheRead()
    slackx_cache: SlackxCacheRead = SlackxCacheRead()
    checked_at: datetime
