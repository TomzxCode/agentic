"""The link command guard when nothing is given to link."""

from agentic_cli.commands import links


def test_link_add_requires_something_to_link(capsys):
    assert links.link_add("t1") == 1
    assert "provide --item-id" in capsys.readouterr().err
