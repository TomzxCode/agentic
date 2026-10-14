"""Build "open this session" links for agent runs.

Two configurable targets, both driven by ``settings_store``:

* OpenChamber: ``openchamber_url`` (base) + ``openchamber_session_path``
  (template, default ``/?session={session}``). Works for the web route
  (``http://host:port/?session=<id>``) and the native deep link
  (base ``openchamber://session`` + path ``/{session}``).
* Terminal: an optional ``terminal_url_template`` (e.g. ``warp://...`` or a web
  terminal), plus a copyable resume command from the harness's
  ``resume_command`` template.

Placeholders: ``{session}`` ``{cwd}`` ``{harness}``.
"""

from __future__ import annotations

from sqlmodel import Session

from .models import AgentRun, AgentSession, Harness
from .schemas import RunRead, SessionLink, SessionRead
from .settings_store import get_settings


def _fill(template: str, values: dict[str, str]) -> str:
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)
    return result


def _join(base: str, path: str) -> str:
    base = base.rstrip("/")
    if not path:
        return base
    return base + (path if path.startswith("/") else "/" + path)


def build_session_links(
    session: Session,
    *,
    harness: Harness | None,
    session_id: str | None,
    cwd: str | None,
) -> list[SessionLink]:
    if not session_id:
        return []

    config = get_settings(session)
    values = {
        "session": session_id,
        "cwd": cwd or "",
        "harness": harness.name if harness else "",
    }
    links: list[SessionLink] = []

    base = (config.get("openchamber_url") or "").strip()
    if base:
        path = config.get("openchamber_session_path") or "/?session={session}"
        links.append(SessionLink(id="openchamber", label="Open in OpenChamber", url=_fill(_join(base, path), values)))

    terminal_template = (config.get("terminal_url_template") or "").strip()
    if terminal_template:
        links.append(SessionLink(id="terminal", label="Open in terminal", url=_fill(terminal_template, values)))

    if harness and harness.resume_command:
        command = _fill(harness.resume_command, values)
        if cwd:
            command = f"cd {cwd} && {command}"
        links.append(SessionLink(id="command", label="Resume command", command=command))

    return links


def run_links(session: Session, run: AgentRun) -> list[SessionLink]:
    harness = session.get(Harness, run.harness_id) if run.harness_id else None
    return build_session_links(session, harness=harness, session_id=run.session_id, cwd=run.cwd)


def run_read(session: Session, run: AgentRun) -> RunRead:
    """Serialize a run with its session links attached."""
    data = RunRead.model_validate(run)
    data.links = run_links(session, run)
    return data


def session_read(session: Session, agent_session: AgentSession) -> SessionRead:
    """Serialize a recorded session with its session links attached."""
    data = SessionRead.model_validate(agent_session)
    harness = session.get(Harness, agent_session.harness_id) if agent_session.harness_id else None
    data.links = build_session_links(
        session, harness=harness, session_id=agent_session.session_id, cwd=agent_session.cwd
    )
    return data
