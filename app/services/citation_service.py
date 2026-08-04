from app.models.document import SearchResult
from app.models.response import QueryReference
from app.services.retriever import Retriever


def references_from_results(results: list[SearchResult], reason: str) -> list[QueryReference]:
    refs: list[QueryReference] = []
    seen: set[tuple[str | None, str | None]] = set()
    for result in results:
        key = (result.entry_name, result.section)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            QueryReference(
                entry_name=result.entry_name,
                section=result.section,
                reason=reason,
                excerpt=result.excerpt[:220],
                options=result.options,
                functions=result.functions,
            )
        )
    return refs


def references_for_commands(
    retriever: Retriever,
    commands: list[str],
    query: str,
    reason: str,
    per_command: int = 2,
) -> list[QueryReference]:
    refs: list[QueryReference] = []
    seen: set[tuple[str | None, str | None]] = set()
    for command in commands:
        for result in retriever.search_entry(command, query=query, limit=per_command):
            key = (result.entry_name, result.section)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                QueryReference(
                    entry_name=result.entry_name,
                    section=result.section,
                    reason=reason,
                    excerpt=result.excerpt[:220],
                    options=result.options,
                    functions=result.functions,
                )
            )
    return refs


def references_for_query_parts(
    retriever: Retriever,
    query: str,
    reason: str,
    per_command: int = 2,
) -> list[QueryReference]:
    refs: list[QueryReference] = []
    seen: set[tuple[str | None, str | None]] = set()
    for line in query.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("|"):
            stripped = stripped[1:].strip()
        command = stripped.split()[0].lower()
        for result in retriever.search_entry(command, query=stripped, limit=per_command):
            key = (result.entry_name, result.section)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                QueryReference(
                    entry_name=result.entry_name,
                    section=result.section,
                    reason=reason,
                    excerpt=result.excerpt[:220],
                    options=result.options,
                    functions=result.functions,
                )
            )
    return refs
