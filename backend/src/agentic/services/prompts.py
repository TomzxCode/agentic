"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import json
import re
from typing import Any

CONTEXT_INSTRUCTIONS = """You are maintaining the living context for a tracked task.

Given the task and its associated items below, produce a concise, current
context so someone can resume in under a minute. Respond with ONLY a JSON
object (no prose, no code fences) of this exact form:

{
  "summary": "2-5 sentence current state of the task: what it is, what has happened, what matters now",
  "next_steps": [
    {"text": "a concrete, actionable next step", "done": false}
  ]
}

Rules:
- summary: at most 3 sentences (roughly 60 words). Prioritize what matters now.
- next_steps: 2-5 concrete actions, most important first. Drop completed ones.
- Be specific: name files, branches, issues, people where relevant.
- If a repository group is listed, treat those repositories as potentially
  relevant: consult them for context and say which one matters.
- Do not invent facts that are not supported by the items.
- Keep the JSON compact; do not exceed it.
"""


SLACK_PLACEHOLDER_TITLE = "Slack thread"


SUMMARIZE_INSTRUCTIONS = """You are naming and summarizing a task captured from a Slack thread.

Given the Slack conversation below, respond with ONLY a JSON object (no prose,
no code fences) of this exact form:

{
  "title": "a short, specific task title (at most ~80 characters)",
  "summary": "2-4 sentences on what the discussion is about and where it stands"
}

Rules:
- title: imperative and specific; name the people, systems, or files involved.
- summary: what is being discussed, what has been decided, and what matters now.
- Do not invent facts that are not in the conversation.
"""


def build_summary_prompt(thread: str) -> str:
    """The prompt that asks an agent to name and summarize an imported thread."""
    body = (thread or "").strip()[:20_000]
    return "\n".join([SUMMARIZE_INSTRUCTIONS, "", "# Slack conversation", "", body])


def build_context_prompt(task: dict[str, Any], items: list[dict[str, Any]]) -> str:
    lines = [CONTEXT_INSTRUCTIONS, "", f"# Task: {task['title']}", ""]
    if task.get("description"):
        lines += ["## Description", task["description"], ""]
    lines.append(f"## Status\n{task.get('status')}  (priority {task.get('priority')})")
    if task.get("repositories"):
        lines += ["", "## Repositories"]
        lines += [f"- {path}" for path in task["repositories"]]
    group = task.get("group")
    if group:
        lines += ["", f"## Repository group: {group['name']}"]
        if group.get("description"):
            lines.append(group["description"])
        repositories = group.get("repositories") or []
        if repositories:
            lines.append("These repositories may contain information relevant to this task:")
            lines += [f"- {path}" for path in repositories]
    if task.get("worktrees"):
        lines += ["", "## Active worktrees"]
        lines += [f"- {w['branch']} at {w['path']}" for w in task["worktrees"]]
    lines += ["", f"## Associated items ({len(items)})"]
    for item in items:
        lines.append(f"\n### [{item['source']}] {item.get('title') or item.get('url')}")
        if item.get("url"):
            lines.append(f"URL: {item['url']}")
        content = (item.get("content") or "").strip()
        if content:
            lines.append(content[:4000])
    return "\n".join(lines)


def _iter_json_objects(text: str):
    """Yield every balanced ``{...}`` candidate, respecting strings/escapes."""
    i = 0
    length = len(text)
    while i < length:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escaped = False
        for j in range(i, length):
            char = text[j]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield text[i : j + 1]
                    i = j + 1
                    break
        else:
            return


def _repair_truncated_json(candidate: str) -> str | None:
    """Close brackets/strings left open by a truncated JSON payload."""
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in candidate:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]" and stack:
            stack.pop()
    if not stack and not in_string:
        return None
    repaired = candidate
    if in_string:
        repaired += '"'
    for opener in reversed(stack):
        repaired += "}" if opener == "{" else "]"
    return repaired


def _try_parse(candidate: str, required: str = "summary") -> dict[str, Any] | None:
    if not isinstance(candidate, str):
        return None
    for attempt in (candidate, _repair_truncated_json(candidate)):
        if not attempt:
            continue
        try:
            data = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and required in data:
            return data
    return None


def _json_candidates(text: str):
    """Yield slices of an agent reply that may hold a JSON object, best first."""
    for fenced in re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL):
        yield from _iter_json_objects(fenced)
    yield from _iter_json_objects(text)
    # Fallback for a payload truncated before its closing braces.
    first_brace = text.find("{")
    if first_brace != -1:
        yield text[first_brace:]


def _extract_json(text: str, required: str) -> dict[str, Any] | None:
    if not text:
        return None
    for candidate in _json_candidates(text):
        data = _try_parse(candidate, required)
        if data is not None:
            return data
    return None


def extract_context_json(text: str) -> dict[str, Any] | None:
    """Pull the first valid context JSON object out of an agent reply."""
    data = _extract_json(text, "summary")
    if data is None:
        return None
    steps = data.get("next_steps") or []
    data["next_steps"] = [
        {
            "text": str(s.get("text", s)) if isinstance(s, dict) else str(s),
            "done": bool(s.get("done")) if isinstance(s, dict) else False,
        }
        for s in steps
    ]
    return data


def extract_summary_json(text: str) -> dict[str, str] | None:
    """Pull the ``{title, summary}`` an agent produced for an imported thread.

    Either key is enough: a reply that only carries a summary still earns its
    summary, even though the title falls back to the placeholder.
    """
    data = _extract_json(text, "summary") or _extract_json(text, "title")
    if data is None:
        return None
    title = str(data.get("title") or "").strip()
    summary = str(data.get("summary") or "").strip()
    if not title and not summary:
        return None
    return {"title": title, "summary": summary}
