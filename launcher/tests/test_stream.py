"""Parsing the stack stream the tray follows."""

from agentic_launcher.client import sse_entries


def test_reads_a_snapshot_split_over_several_data_lines():
    lines = [
        "event: message",
        'data: [{"id": "a",',
        'data:  "task": {"title": "one"}}]',
        "",
    ]
    assert list(sse_entries(lines)) == [[{"id": "a", "task": {"title": "one"}}]]


def test_skips_pings_comments_and_non_list_payloads():
    lines = [
        ": ping - keep-alive",
        "",
        "event: message",
        'data: {"not": "a list"}',
        "",
        "event: message",
        "data: []",
        "",
    ]
    assert list(sse_entries(lines)) == [[]]


def test_reads_a_final_block_without_its_blank_line():
    assert list(sse_entries(["data: [1, 2]"])) == [[1, 2]]
