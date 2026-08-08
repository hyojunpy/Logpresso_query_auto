from __future__ import annotations

from difflib import unified_diff


def append_version(versions: list[str], query: str, max_items: int = 10) -> list[str]:
    if not query.strip() or (versions and versions[-1] == query):
        return versions
    return [*versions, query][-max_items:]


def query_diff(previous: str, current: str) -> str:
    return "\n".join(unified_diff(previous.splitlines(), current.splitlines(), fromfile="previous", tofile="current", lineterm=""))
