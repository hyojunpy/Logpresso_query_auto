from ui.quick_test_catalog import QUICK_TEST_REQUESTS, build_quick_test_preset, quick_test_count
from app.models.request import GenerateQueryRequest, RequestContext
from app.services.llm.mock_provider import MockProvider
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever
from tests.support import shared_index


def test_quick_test_catalog_contains_all_grouped_composite_examples():
    assert quick_test_count() == 70
    assert len(QUICK_TEST_REQUESTS) == 12


def test_quick_test_preset_infers_schema_and_realtime_sources():
    request = QUICK_TEST_REQUESTS["실시간 Logger·Stream"][2]
    preset = build_quick_test_preset(request)

    assert preset["tables"] == ["asset_info"]
    assert preset["streams"] == ["security_stream"]
    assert {"severity", "src_ip", "ip_address", "event_type"}.issubset(preset["fields"])


def test_every_quick_test_generates_a_query():
    outcomes = []
    generator = QueryGenerator(Retriever(shared_index()), llm=MockProvider())
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
            outcomes.append((category, request, response.status, response.query))
    failures = [item for item in outcomes if item[2] != "generated" or not item[3]]
    assert failures == []
    assert len(outcomes) == 63
