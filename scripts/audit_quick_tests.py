from __future__ import annotations

from collections import Counter

from app.core.config import settings
from app.models.request import GenerateQueryRequest, RequestContext
from app.services.indexer import DocumentIndex
from app.services.llm.mock_provider import MockProvider
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever
from ui.quick_test_catalog import QUICK_TEST_REQUESTS, build_quick_test_preset


def main() -> None:
    generator = QueryGenerator(Retriever(DocumentIndex(settings.db_path)), llm=MockProvider())
    counts: Counter[str] = Counter()
    rows: list[tuple[str, str, str, str]] = []

    for category, requests in QUICK_TEST_REQUESTS.items():
        for request in requests:
            preset = build_quick_test_preset(request)
            context = RequestContext(
                known_tables=preset["tables"],
                known_fields=preset["fields"],
                known_streams=preset["streams"],
                known_loggers=preset["loggers"],
            )
            response = generator.generate(GenerateQueryRequest(request=request, context=context))
            counts[response.status] += 1
            detail = response.query or " / ".join(response.questions) or ""
            rows.append((category, response.status, request, detail.replace("\n", " ")))

    print("SUMMARY " + " ".join(f"{name}={count}" for name, count in sorted(counts.items())))
    for category, status, request, detail in rows:
        print(f"{status}\t{category}\t{request}\t{detail}")


if __name__ == "__main__":
    main()
