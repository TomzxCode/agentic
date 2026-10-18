"""Fixtures shared by the CLI command test modules."""

import pytest
from _helpers import FakeClient

from agentic_cli import cli, runtime


@pytest.fixture
def text_format():
    previous = runtime.CONTEXT["format"]
    runtime.CONTEXT["format"] = "text"
    yield
    runtime.CONTEXT["format"] = previous


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(cli.runtime, "_client", FakeClient)
    return FakeClient()
