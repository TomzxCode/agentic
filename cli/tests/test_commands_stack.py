"""Focus stack commands."""

from agentic_cli.commands import stack


def test_stack_commands(text_format, fake_client, capsys):
    assert "* 0  T  x2  1m 30s" in stack.stack_list()
    assert "* 0  T  x2  1m 30s" in stack.stack_current()
    assert "Old" in stack.stack_history()
    assert "T" in stack.stack_push(title="T")
    assert "existing" in stack.stack_push(task_id="t1")
    assert stack.stack_push() == 1
    assert "provide --title or --task-id" in capsys.readouterr().err
    assert stack.stack_pop() == "(none)"
    assert "* 0" in stack.stack_promote("s1")
    assert "* 0" in stack.stack_reorder("s1", 0)
    assert "T" in stack.stack_edit("s1", title="T")
    assert "removed s1" in stack.stack_remove("s1")
