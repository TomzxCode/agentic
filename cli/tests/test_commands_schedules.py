"""Schedule commands."""

from agentic_cli.commands import schedules


def test_schedule_commands(text_format, fake_client):
    assert "s1" in schedules.schedule_list()
    assert "command: echo hi" in schedules.schedule_get("s1")
    assert "created" in schedules.schedule_create("N", "echo hi", "0 9 * * *")
    assert "UTC" in schedules.schedule_create("N", "echo hi", "0 9 * * *", timezone="UTC")
    assert "N" in schedules.schedule_update("s1", name="N", enable=True)
    assert "deleted s1" in schedules.schedule_delete("s1")
    assert "started run r1" in schedules.schedule_run("s1")
    runs = schedules.schedule_runs("s1")
    assert "succeeded" in runs and "hi" in runs
    all_runs = schedules.schedule_runs(limit=5)
    assert "Nightly" in all_runs and "succeeded" in all_runs
