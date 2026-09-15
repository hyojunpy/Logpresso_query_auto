from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import json
import re


class DashboardQueryKnowledge:
    def __init__(self, payload: dict):
        self.payload = payload

    @classmethod
    @lru_cache(maxsize=1)
    def bundled(cls) -> "DashboardQueryKnowledge":
        resource = files("app.resources").joinpath("dashboard_query_examples.json")
        return cls(json.loads(resource.read_text(encoding="utf-8")))

    def match(self, request: str) -> dict | None:
        normalized = self._normalize(request)
        matches: list[tuple[int, dict]] = []
        for item in self.payload.get("items", []):
            for phrase in [item.get("title", ""), *item.get("aliases", [])]:
                candidate = self._normalize(str(phrase))
                if candidate and candidate in normalized:
                    matches.append((len(candidate), item))
        return max(matches, key=lambda value: value[0])[1] if matches else None

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9a-z가-힣]+", "", value.casefold())
