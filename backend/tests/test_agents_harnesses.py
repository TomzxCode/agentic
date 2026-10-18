"""Harness seeding, availability, and default-model resolution."""

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from agentic.agents import harnesses as harnesses_mod
from agentic.agents.harnesses import get_harness, harness_available, resolve_default_model, seed_harnesses
from agentic.config import settings
from agentic.models.agents import Harness

# Throwaway in-memory engines/sessions built by the pure-helper tests; tracked
# here so they are closed at test teardown instead of leaking pooled SQLite
# connections (ResourceWarning).
_fresh_engines: list = []
_fresh_sessions: list = []


def _fresh_session() -> Session:
    fresh_engine = create_engine("sqlite://")
    _fresh_engines.append(fresh_engine)
    SQLModel.metadata.create_all(fresh_engine)
    session = Session(fresh_engine)
    _fresh_sessions.append(session)
    return session


@pytest.fixture(autouse=True)
def _dispose_fresh_engines():
    yield
    while _fresh_sessions:
        _fresh_sessions.pop().close()
    while _fresh_engines:
        _fresh_engines.pop().dispose()


def test_resolve_default_model_reads_a_plain_key(tmp_path):
    config = tmp_path / "opencode.json"
    config.write_text('{"model": "zai-coding-plan/glm-5.3-flash"}')
    harness = Harness(name="h", command="h", default_model_source=f"{config}#model")
    assert resolve_default_model(harness) == "zai-coding-plan/glm-5.3-flash"


def test_resolve_default_model_reads_an_object_model_and_a_template(tmp_path):
    opencode = tmp_path / "opencode.json"
    opencode.write_text('{"model": {"providerID": "zai-coding-plan", "model": "glm-5.3-flash"}}')
    as_object = Harness(name="h", command="h", default_model_source=f"{opencode}#model")
    assert resolve_default_model(as_object) == "zai-coding-plan/glm-5.3-flash"

    pi = tmp_path / "settings.json"
    pi.write_text('{"defaultProvider": "opencode-go", "defaultModel": "deepseek-v4.1-flash"}')
    as_template = Harness(name="h", command="h", default_model_source=f"{pi}#{{defaultProvider}}/{{defaultModel}}")
    assert resolve_default_model(as_template) == "opencode-go/deepseek-v4.1-flash"


def test_resolve_default_model_is_none_when_the_source_cannot_answer(tmp_path):
    no_model = tmp_path / "settings.json"
    no_model.write_text('{"theme": "dark"}')
    cases = [
        # No source configured.
        Harness(name="h", command="h"),
        # The file is not there.
        Harness(name="h", command="h", default_model_source=f"{tmp_path / 'absent.json'}#model"),
        # The key is not there.
        Harness(name="h", command="h", default_model_source=f"{no_model}#model"),
        # One template placeholder is missing.
        Harness(name="h", command="h", default_model_source=f"{no_model}#{{defaultModel}}"),
        # Not a "<file>#<template>" source.
        Harness(name="h", command="h", default_model_source="model"),
    ]
    for harness in cases:
        assert resolve_default_model(harness) is None


def test_harness_available_reports_missing_and_present_commands():
    missing = Harness(id="m", name="m", command="definitely-not-a-real-command-xyz")
    available, detail = harness_available(missing)
    assert available is False and "not found on PATH" in detail

    shell = Harness(id="s", name="s", command="sh")
    available, detail = harness_available(shell)
    assert available is True and detail


def test_seed_harnesses_populates_presets_with_resume_commands_and_default(monkeypatch):
    monkeypatch.setattr(harnesses_mod, "_preferred_opencode_default", lambda: "opencode2")
    session = _fresh_session()
    seed_harnesses(session)
    harnesses = {h.id: h for h in session.exec(select(Harness)).all()}
    assert set(harnesses) == {"opencode", "opencode2", "pi"}
    assert harnesses["opencode"].resume_command == "opencode --session {session}"
    assert harnesses["opencode2"].resume_command == "opencode2 --session {session}"
    assert harnesses["pi"].resume_command == "pi --session {session}"
    assert harnesses["opencode2"].is_default is True
    assert harnesses["opencode"].is_default is False
    assert harnesses["pi"].is_default is False


def test_seed_harnesses_picks_opencode_v1_when_v2_is_absent(monkeypatch):
    monkeypatch.setattr(harnesses_mod, "_preferred_opencode_default", lambda: "opencode")
    session = _fresh_session()
    seed_harnesses(session)
    harnesses = {h.id: h for h in session.exec(select(Harness)).all()}
    assert harnesses["opencode"].is_default is True
    assert harnesses["opencode2"].is_default is False


def test_seed_harnesses_adds_missing_presets_without_overwriting_custom_edits(monkeypatch):
    monkeypatch.setattr(harnesses_mod, "_preferred_opencode_default", lambda: "opencode2")
    session = _fresh_session()
    session.add(Harness(id="opencode", name="Mine", command="my-opencode", is_default=True))
    session.commit()

    seed_harnesses(session)

    opencode = session.get(Harness, "opencode")
    assert opencode is not None and opencode.command == "my-opencode"
    assert session.get(Harness, "opencode2") is not None
    assert session.get(Harness, "pi") is not None


def test_seed_harnesses_moves_an_opencode_default_to_v2(monkeypatch):
    monkeypatch.setattr(harnesses_mod, "_preferred_opencode_default", lambda: "opencode2")
    session = _fresh_session()
    session.add(Harness(id="opencode", name="OpenCode", command="opencode", is_default=True))
    session.commit()

    seed_harnesses(session)

    v1 = session.get(Harness, "opencode")
    v2 = session.get(Harness, "opencode2")
    assert v1 is not None and v2 is not None
    assert v1.is_default is False
    assert v2.is_default is True


def test_seed_harnesses_keeps_a_default_outside_the_opencode_family(monkeypatch):
    monkeypatch.setattr(harnesses_mod, "_preferred_opencode_default", lambda: "opencode2")
    session = _fresh_session()
    session.add(Harness(id="pi", name="pi", command="pi-acp", is_default=True))
    session.commit()

    seed_harnesses(session)

    pi = session.get(Harness, "pi")
    v2 = session.get(Harness, "opencode2")
    assert pi is not None and v2 is not None
    assert pi.is_default is True
    assert v2.is_default is False


def test_seed_harnesses_does_not_override_a_default_chosen_later(monkeypatch):
    monkeypatch.setattr(harnesses_mod, "_preferred_opencode_default", lambda: "opencode2")
    session = _fresh_session()
    seed_harnesses(session)

    # The user switches the default to v1 after seeding.
    v1 = session.get(Harness, "opencode")
    v2 = session.get(Harness, "opencode2")
    assert v1 is not None and v2 is not None
    v1.is_default = True
    v2.is_default = False
    session.add(v1)
    session.add(v2)
    session.commit()

    seed_harnesses(session)

    v1 = session.get(Harness, "opencode")
    v2 = session.get(Harness, "opencode2")
    assert v1 is not None and v2 is not None
    assert v1.is_default is True
    assert v2.is_default is False


def test_seed_harnesses_backfills_resume_command_by_id_and_name():
    session = _fresh_session()
    session.add(Harness(id="opencode", name="OpenCode", command="opencode"))
    session.add(Harness(id="weird", name="PI", command="pi-acp"))
    session.add(Harness(id="zed", name="zed", command="zed"))
    session.commit()

    seed_harnesses(session)

    opencode = session.get(Harness, "opencode")
    weird = session.get(Harness, "weird")
    zed = session.get(Harness, "zed")
    assert opencode is not None and weird is not None and zed is not None

    assert opencode.resume_command == "opencode --session {session}"
    # Unknown ids fall back to the name lookup, case-insensitively.
    assert weird.resume_command == "pi --session {session}"
    # Nothing known matches, so the column is left as-is.
    assert zed.resume_command is None


def test_get_harness_prefers_explicit_id_then_default_flag():
    session = _fresh_session()
    session.add(Harness(id="a", name="a", command="a"))
    session.add(Harness(id="b", name="b", command="b", is_default=True))
    session.commit()

    assert get_harness(session, "a").id == "a"
    # An unknown id falls back to the harness flagged default.
    assert get_harness(session, "missing").id == "b"
    assert get_harness(session, None).id == "b"


def test_get_harness_uses_settings_default_name(monkeypatch):
    session = _fresh_session()
    session.add(Harness(id="p", name="pi", command="pi"))
    session.add(Harness(id="o", name="opencode", command="opencode"))
    session.commit()

    monkeypatch.setattr(settings, "default_harness", "pi")
    assert get_harness(session, None).id == "p"


def test_get_harness_falls_back_to_first_and_raises_when_empty():
    session = _fresh_session()
    session.add(Harness(id="only", name="only", command="only"))
    session.commit()
    assert get_harness(session, None).id == "only"

    empty = _fresh_session()
    with pytest.raises(RuntimeError):
        get_harness(empty, None)


def test_get_harness_resolves_the_default_then_falls_back(monkeypatch):
    monkeypatch.setattr(harnesses_mod, "_preferred_opencode_default", lambda: "opencode2")
    session = _fresh_session()
    seed_harnesses(session)

    assert get_harness(session, None).id == "opencode2"
    # An explicit choice wins over the default.
    assert get_harness(session, "opencode").id == "opencode"
