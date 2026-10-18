"""Change and metrics commands."""

from agentic_cli.commands import changes, metrics


def test_change_and_metrics_commands(text_format, fake_client):
    assert "c1" in changes.change_list()
    text = changes.change_get("c1")
    assert "accepted" in text and "intervention [correction]" in text
    assert "created change c2" in changes.change_create("t1", title="C", change_class="bugfix")
    assert "verified: c1" in changes.change_verify("c1")
    assert "accepted: c1" in changes.change_accept("c1")
    assert "rejected: c1" in changes.change_reject("c1")
    assert "reverted: c1" in changes.change_revert("c1")
    assert "intervened (correction) on c1" in changes.change_intervene("c1", kind="correction", note="n")
    assert "deleted c1" in changes.change_delete("c1")
    assert "Autonomy rate" in metrics.metrics_show()
    assert "autonomy_rate" in metrics.baseline_list()
    assert "baseline = 20.0%" in metrics.baseline_set("autonomy_rate", 0.2)
    assert "deleted baseline yield" in metrics.baseline_delete("yield")
