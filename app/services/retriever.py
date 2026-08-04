from app.models.document import SearchResult
from app.services.indexer import DocumentIndex


class Retriever:
    def __init__(self, index: DocumentIndex):
        self.index = index

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        return self.index.search(query, limit)

    def search_entry(self, entry_name: str, query: str = "", limit: int = 3) -> list[SearchResult]:
        results = self.index.search(f"{entry_name} {query}".strip(), limit=30)
        exact = [item for item in results if item.entry_name == entry_name]
        exact.sort(key=lambda item: self._entry_priority(entry_name, item), reverse=True)
        return exact[:limit]

    def get_entry(self, entry_name: str) -> dict[str, object]:
        results = self.index.search(entry_name, limit=20)
        matched = [item for item in results if item.entry_name == entry_name]
        return {"entry_name": entry_name, "results": matched or results[:5]}

    def command_exists(self, command: str) -> bool:
        names = self.index.command_names()
        fallback = {"table", "fulltext", "search", "stats", "rollup", "timechart", "sort", "limit", "set", "setq"}
        return command in names or command in fallback

    def options_for_command(self, command: str) -> set[str]:
        options = self.index.options_for_entry(command)
        fallback = {
            "table": {"duration", "from", "to", "limit", "offset", "order"},
            "fulltext": {"duration", "from", "to", "limit", "offset", "order", "tt"},
            "timechart": {"span", "offset", "parallel"},
            "rollup": {"label", "parallel"},
            "stream": {"forward", "window"},
            "sort": {"limit"},
        }
        known = fallback.get(command, set())
        if known and (not options or len(options) > max(len(known) * 3, 12)):
            return known
        return options or known

    def function_exists(self, function: str) -> bool:
        functions = self.index.functions_for_entry()
        fallback = {"count", "sum", "avg", "min", "max", "first", "last", "ago", "now", "str", "dateadd"}
        return function in functions if functions else function in fallback

    def _entry_priority(self, entry_name: str, result: SearchResult) -> tuple[int, int, float]:
        excerpt = result.excerpt.strip().lower()
        starts_like_command = excerpt.startswith(f"{entry_name} ") or excerpt.startswith(f"{entry_name}[")
        section = result.section or ""
        content_type_score = {"syntax": 3, "description": 2, "example": 1}.get(result.content_type, 0)
        section_score = 2 if "문법" in section else (1 if "설명" in section else 0)
        return (1 if starts_like_command else 0, int(result.score * 1000), content_type_score + section_score)
