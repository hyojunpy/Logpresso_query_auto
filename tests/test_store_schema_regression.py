import re

from app.models.request import GenerateQueryRequest, RequestContext
from app.services.llm.mock_provider import MockProvider
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever
from app.services.store_schema_knowledge import StoreSchemaKnowledge
from tests.support import shared_index


def test_all_154_detailed_store_schemas_generate_grouped_queries():
    knowledge = StoreSchemaKnowledge.bundled()
    generator = QueryGenerator(Retriever(shared_index()), llm=MockProvider())
    detailed = [
        (product, schema)
        for product in knowledge.payload["products"]
        for schema in product["schemas"]
        if schema["fields"]
    ]
    assert len(detailed) == 154
    failures = []
    for product, schema in detailed:
        field = next((
            item["name"] for item in schema["fields"]
            if item["name"] != "_time" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item["name"])
        ), None)
        if not field:
            failures.append(f"{product['name']} / {schema['name']}: no safe field")
            continue
        response = generator.generate(GenerateQueryRequest(
            request=f"최근 24시간 {field}별 건수를 보여줘",
            context=RequestContext(
                known_tables=["store_events"],
                store_product=product["name"],
                store_schema=schema["name"],
            ),
        ))
        if response.status != "generated" or "stats count by" not in (response.query or ""):
            failures.append(f"{product['name']} / {schema['name']} / {field}: {response.status} {response.questions}")
    assert failures == []
