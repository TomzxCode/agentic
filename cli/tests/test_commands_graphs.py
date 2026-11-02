"""Execution graph commands: schedule trigger nodes they add to a definition."""

from agentic_cli.commands import graphs


def test_add_schedule_node_builds_a_trigger_node():
    definition = graphs._add_schedule_node(None, "0 9 * * *", "Europe/Paris")
    nodes = definition["nodes"]
    assert len(nodes) == 1
    node = nodes[0]
    assert node["kind"] == "trigger"
    assert node["triggerType"] == "schedule"
    assert node["schedule"] == "0 9 * * *"
    assert node["timezone"] == "Europe/Paris"
    assert node["enabled"] is True
    assert node["outputs"] == []
    assert node["id"]


def test_add_schedule_node_keeps_the_definition_and_titles_unique():
    definition = {
        "nodes": [
            {"id": "a", "kind": "run", "title": "Schedule", "position": {"x": 10, "y": 300}},
            {"id": "b", "kind": "run", "title": "Other", "position": {"x": 10, "y": 100}},
        ],
        "edges": [{"id": "e1", "source": "a", "target": "b"}],
    }
    built = graphs._add_schedule_node(definition, "* * * * *", None, enabled=False)
    assert [node["title"] for node in built["nodes"]] == ["Schedule", "Other", "Schedule 2"]
    added = built["nodes"][-1]
    assert added["enabled"] is False
    # The new node sits below everything already on the canvas.
    assert added["position"]["y"] > 300
    assert built["edges"] == definition["edges"]


def test_replace_schedules_swaps_every_schedule_node():
    definition = {
        "nodes": [
            {"id": "s1", "kind": "trigger", "triggerType": "schedule", "title": "Morning", "schedule": "0 9 * * *"},
            {"id": "e1", "kind": "trigger", "triggerType": "event", "title": "Hook", "outputs": []},
            {"id": "a", "kind": "run", "title": "Step", "position": {"x": 0, "y": 0}},
        ],
        "edges": [],
    }
    replaced = graphs._replace_schedules(definition, "*/15 * * * *", "UTC")
    schedules = [node for node in replaced["nodes"] if node.get("triggerType") == "schedule"]
    assert len(schedules) == 1 and schedules[0]["schedule"] == "*/15 * * * *"
    # The event trigger and the agent run are untouched.
    assert [node["id"] for node in replaced["nodes"] if node.get("triggerType") != "schedule"] == ["e1", "a"]

    cleared = graphs._replace_schedules(definition, "", None)
    assert not [node for node in cleared["nodes"] if node.get("triggerType") == "schedule"]


def test_set_schedules_enabled_flips_only_schedules():
    definition = {
        "nodes": [
            {"id": "s1", "kind": "trigger", "triggerType": "schedule", "title": "S", "enabled": True},
            {"id": "e1", "kind": "trigger", "triggerType": "event", "title": "Hook"},
        ],
        "edges": [],
    }
    off = graphs._set_schedules_enabled(definition, False)
    assert off["nodes"][0]["enabled"] is False
    assert "enabled" not in off["nodes"][1]
