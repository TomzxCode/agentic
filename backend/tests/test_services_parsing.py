"""Name slugs and URL parsing."""

from agentic.services import names, parsing


def test_slugify():
    assert names.slugify("Hello, World!") == "hello-world"
    assert names.slugify("") == "item"
    assert names.slugify("x" * 100) == "x" * 48


def test_parse_github_and_slack():
    github = parsing.parse_github("https://github.com/psf/requests/pull/12")
    assert github is not None
    assert github["kind"] == "pull_request"
    assert github["external_id"] == "psf/requests#12"
    assert parsing.parse_github("nope") is None

    slack = parsing.parse_slack("https://acme.slack.com/archives/C1/p1700000000000000")
    assert slack is not None
    assert slack["ts"] == "1700000000.000000"
    assert slack["external_id"] == "C1:1700000000000000"
    assert parsing.parse_slack("nope") is None


def test_worktree_path_slugifies_the_branch():
    path = names.worktree_path("task1", "agentic/Silly Goose")
    assert path.endswith("task1/agentic-silly-goose")
