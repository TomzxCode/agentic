"""Operation audit-log commands."""

from agentic_cli.commands import operations


def test_operation_list_command(text_format, fake_client):
    text = operations.operation_list()
    assert "POST" in text and "/api/tasks" in text and "cli" in text and "agent" in text
