from agentic import server_cli


def test_backend_cli_owns_serve_and_info():
    assert "serve" in server_cli.app
    assert "info" in server_cli.app
    # The user client (agentic-cli) must not carry the server command.
    assert "task" not in server_cli.app
