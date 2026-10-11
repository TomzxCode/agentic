"""The backend CLI's describe/config output and uvicorn handoff."""

from agentic import server_cli


def test_info_prints_configuration(capsys):
    server_cli.info()
    out = capsys.readouterr().out
    assert "data dir:" in out
    assert "default harness:" in out
    assert "harnesses:" in out


def test_serve_delegates_to_uvicorn(monkeypatch):
    import uvicorn

    calls: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.update(args=args, kwargs=kwargs))

    server_cli.serve(host="0.0.0.0", port=9999, reload=True)

    assert calls["args"][0] == "agentic.main:app"
    assert calls["kwargs"]["host"] == "0.0.0.0"
    assert calls["kwargs"]["port"] == 9999
    assert calls["kwargs"]["reload"] is True
