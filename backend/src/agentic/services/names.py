"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import random
import re
import secrets

from ..config import settings
from . import shell


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "item"


_ADJECTIVES = (
    "brisk",
    "calm",
    "clever",
    "curious",
    "dapper",
    "eager",
    "fuzzy",
    "gentle",
    "jolly",
    "lucky",
    "mellow",
    "nimble",
    "plucky",
    "quirky",
    "rusty",
    "silly",
    "snappy",
    "spry",
    "witty",
    "zesty",
)


_NOUNS = (
    "badger",
    "beetle",
    "bison",
    "crane",
    "dolphin",
    "falcon",
    "ferret",
    "gecko",
    "goose",
    "heron",
    "lemur",
    "llama",
    "marmot",
    "moose",
    "otter",
    "panda",
    "pelican",
    "puffin",
    "raven",
    "walrus",
)


def random_name() -> str:
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}"


def random_branch_name(repo_path: str, prefix: str = "agentic/") -> str:
    """A short memorable branch name that does not already exist in the repo."""
    for _ in range(10):
        candidate = f"{prefix}{random_name()}"
        if shell._git(["rev-parse", "--verify", candidate], cwd=repo_path, timeout=15).returncode != 0:
            return candidate
    return f"{prefix}{random_name()}-{secrets.token_hex(3)}"


def worktree_path(task_id: str, branch: str) -> str:
    return str(settings.worktree_root / task_id / slugify(branch))
