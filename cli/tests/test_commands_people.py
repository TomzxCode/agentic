"""People commands."""

from agentic_cli.commands import people


def test_people_commands(text_format, fake_client, capsys):
    assert "Ada" in people.person_list()
    text = people.person_get("p1")
    assert "aliases: ada, ada@example.com" in text and "tasks: t1" in text
    assert "created p2" in people.person_create(name="Ada")
    assert "updated p1" in people.person_update("p1", aliases=["ada"])
    assert "deleted p1" in people.person_delete("p1")
    assert "linked p1 to task t1" in people.person_link("p1", task="t1")
    assert "linked p1 to item i1" in people.person_link("p1", item="i1")
    assert "linked p1 as a requester of task t1" in people.person_link("p1", requested_by="t1")
    assert "unlinked p1 from task t1" in people.person_unlink("p1", task="t1")
    assert "unlinked p1 as a requester of task t1" in people.person_unlink("p1", requested_by="t1")
    assert "merged p1 into p2  Grace" in people.person_merge("p1", into="p2")
    assert people.person_link("p1") == 1
    assert "provide --task, --item, or --requested-by" in capsys.readouterr().err
