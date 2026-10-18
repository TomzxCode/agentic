from sqlmodel import Session

from agentic.db import create_db_and_tables, engine
from agentic.links import build_session_links
from agentic.models.agents import Harness
from agentic.settings_store import update_settings


def _harness(id_: str, resume: str) -> Harness:
    return Harness(id=id_, name=id_, command=id_, resume_command=resume)


def test_no_links_without_session_or_config():
    create_db_and_tables()
    with Session(engine) as session:
        update_settings(session, {"openchamber_url": "", "terminal_url_template": ""})
        assert build_session_links(session, harness=_harness("h", "cmd {session}"), session_id=None, cwd=None) == []
        # A session but no configured targets still offers the resume command.
        links = build_session_links(
            session, harness=_harness("h", "opencode --session {session}"), session_id="ses_1", cwd="/w"
        )
        assert [link.id for link in links] == ["command"]
        assert links[0].command == "cd /w && opencode --session ses_1"


def test_openchamber_and_terminal_links():
    create_db_and_tables()
    with Session(engine) as session:
        update_settings(
            session,
            {
                "openchamber_url": "http://localhost:3001/",
                "openchamber_session_path": "/?session={session}",
                "terminal_url_template": "opencode://session/{session}?cwd={cwd}",
            },
        )
        links = build_session_links(
            session, harness=_harness("h", "opencode --session {session}"), session_id="ses_42", cwd="/work"
        )
        by_id = {link.id: link for link in links}
        assert by_id["openchamber"].url == "http://localhost:3001/?session=ses_42"
        assert by_id["terminal"].url == "opencode://session/ses_42?cwd=/work"
        assert by_id["command"].command == "cd /work && opencode --session ses_42"
        update_settings(session, {"openchamber_url": "", "terminal_url_template": ""})
