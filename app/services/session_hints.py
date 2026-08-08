from __future__ import annotations


def merge_hints(existing: list[str], additions: list[str]) -> list[str]:
    """Keep a stable, non-empty session-only hint list."""
    return list(dict.fromkeys(item.strip() for item in [*existing, *additions] if item and item.strip()))


def remove_hint(items: list[str], value: str) -> list[str]:
    return [item for item in items if item != value]
