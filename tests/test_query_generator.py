import unittest
from datetime import date, timedelta
from unittest.mock import patch

from app.core.config import settings
from app.models.request import Catalog, CatalogField, CatalogTable, GenerateQueryRequest, RequestContext
from app.services.llm.mock_provider import MockProvider
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever
from tests.support import shared_index


def generator(llm=None) -> QueryGenerator:
    return QueryGenerator(Retriever(shared_index()), llm=llm)


class QueryGeneratorTest(unittest.TestCase):
    def test_generates_realtime_stream_query_with_filter(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="sample_stream 스트림에서 최근 10초 동안 error 로그 보여줘",
                context=RequestContext(known_fields=["level"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'stream window=10s sample_stream\n| search level == "error"')

    def test_generates_stream_query_from_context_name(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_stream 최근 1분 동안 error 로그 보여줘",
                context=RequestContext(known_streams=["firewall_stream"], known_fields=["level"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'stream window=1m firewall_stream\n| search level == "error"')

    def test_generates_realtime_logger_query_with_filter(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="local\\sample_logger 로거에서 최근 10초 동안 error 로그 보여줘",
                context=RequestContext(known_loggers=["local\\sample_logger"], known_fields=["level"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'logger window=10s local\\sample_logger\n| search level == "error"')

    def test_generates_logger_query_from_context_name(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logger 로거에서 최근 1분 동안 로그 보여줘",
                context=RequestContext(known_loggers=["firewall_logger"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "logger window=1m firewall_logger")

    def test_generates_realtime_stream_aggregation_sorted_and_limited(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="sample_stream 스트림에서 최근 1분 동안 host별 error 건수 top 10 보여줘",
                context=RequestContext(known_fields=["level", "host"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            'stream window=1m sample_stream\n| search level == "error"\n| stats count by host\n| sort -count\n| limit 10',
        )

    def test_realtime_source_needs_duration(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="sample_stream 스트림 로그 보여줘",
                context=RequestContext(known_fields=["level"]),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(response.questions)
    def test_generates_left_join_with_distinct_source_keys_and_renames(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs의 src_ip를 출발지 ip로 바꾸고 firewall_djt의 dst_ip를 도착지 ip로 바꾼 후에 얘네를 left 조인 해줘. src_ip를 기준으로 left 조인 할거야",
                context=RequestContext(
                    known_tables=["firewall_logs", "firewall_djt"],
                    known_fields=["src_ip", "dst_ip"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            "table firewall_logs\n"
            "| rename src_ip as 출발지_ip\n"
            "| eval _join_key = 출발지_ip\n"
            "| join type=left _join_key [\n"
            "    table firewall_djt\n"
            "    | rename dst_ip as 도착지_ip\n"
            "    | eval _join_key = 도착지_ip\n"
            "]",
        )
        self.assertIn("join", response.validation.commands)

    def test_generates_explicit_korean_possessive_join_without_sidebar_schema(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs의 src_ip와 firewall_djt의 dst_ip를 src_ip를 기준으로 left join 해줘",
                context=RequestContext(),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            "table firewall_logs\n"
            "| eval _join_key = src_ip\n"
            "| join type=left _join_key [\n"
            "    table firewall_djt\n"
            "    | eval _join_key = dst_ip\n"
            "]",
        )

    def test_generates_join_from_table_and_db_wording_with_shared_rename(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall 테이블의 src_ip와 insa db의 ip를 할당 ip로 바꾸고 left join 할거야",
                context=RequestContext(),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            "table firewall\n"
            "| rename src_ip as 할당_ip\n"
            "| eval _join_key = 할당_ip\n"
            "| join type=left _join_key [\n"
            "    table insa\n"
            "    | rename ip as 할당_ip\n"
            "    | eval _join_key = 할당_ip\n"
            "]",
        )

    def test_generates_full_join_when_requested(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs의 src_ip와 firewall_djt의 dst_ip를 기준으로 full join 해줘",
                context=RequestContext(
                    known_tables=["firewall_logs", "firewall_djt"],
                    known_fields=["src_ip", "dst_ip"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertIn("| join type=full _join_key [", response.query)

    def test_generates_firewall_deny_aggregation_from_natural_language_aliases(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 24시간 firewall_logs에서 출발지 IP별 차단 건수를 많은 순으로 20개 보여줘",
                context=RequestContext(),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            'table duration=24h firewall_logs\n'
            '| search action == "deny"\n'
            "| stats count by src_ip\n"
            "| sort -count\n"
            "| limit 20",
        )
        self.assertTrue(any("Natural-language field aliases inferred" in item for item in response.intent.assumptions))

    def test_understands_declared_tables_same_join_key_and_firewall_left_join(self):
        response = generator().generate(
            GenerateQueryRequest(
                request=(
                    "인사 DB 테이블의 ip 컬럼이랑 방화벽 테이블의 ip 컬럼 레프트 조인해서 방화벽 로그에 따라 볼수 있게 작성해줘\n"
                    "추가 조건: 테이블은 insa, firewall 조인키는 둘다 ip"
                ),
                context=RequestContext(),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            "table firewall\n"
            "| eval _join_key = ip\n"
            "| join type=left _join_key [\n"
            "    table insa\n"
            "    | eval _join_key = ip\n"
            "]",
        )

    def test_generates_experimental_eval_for_join_match_indicator(self):
        response = generator().generate(
            GenerateQueryRequest(
                request=(
                    "인사와 방화벽을 IP로 left join해줘\n"
                    "추가 조건: 테이블은 insa, firewall / 조인키는 둘 다 ip\n"
                    "추가 조건: firewall의 log에서 insa에 있는 ip가 포함된 경우는 새로운 칼럼에서 모아서 볼 수 있게 만들어줘"
                ),
                context=RequestContext(),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertIn("table firewall", response.query)
        self.assertIn("table insa", response.query)
        self.assertIn("rename ip as insa_ip", response.query)
        self.assertIn('eval insa_ip_match = if(isnull(insa_ip), "unmatched", "matched")', response.query)
        self.assertTrue(any(issue.code == "unknown_function" for issue in response.validation.warnings))

    def test_generates_left_streamjoin_with_table_subquery(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="sample_stream 스트림에서 최근 10초 동안 src_ip와 firewall_djt의 dst_ip를 기준으로 left streamjoin 해줘",
                context=RequestContext(
                    known_tables=["firewall_djt"],
                    known_fields=["src_ip", "dst_ip"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertIn("stream window=10s sample_stream", response.query)
        self.assertIn("| streamjoin type=left _join_key [", response.query)

    def test_join_keeps_time_filter_and_limit_conditions(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 24시간 firewall_logs의 src_ip와 firewall_djt의 dst_ip를 기준으로 left join 하고 action이 deny인 것만 10개 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs", "firewall_djt"],
                    known_fields=["src_ip", "dst_ip", "action"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertIn("table duration=24h firewall_logs", response.query)
        self.assertIn('| search action == "deny"', response.query)
        self.assertTrue(response.query.endswith("| limit 10"))

    def test_join_applies_explicit_pre_join_filter_to_left_source(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs의 src_ip와 firewall_djt의 dst_ip를 src_ip를 기준으로 left join 하고 조인 전에 action == deny인 것만 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs", "firewall_djt"],
                    known_fields=["src_ip", "dst_ip", "action"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertLess(response.query.index('| search action == "deny"'), response.query.index("| eval _join_key = src_ip"))

    def test_join_applies_right_table_qualified_filter_in_subquery(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs의 src_ip와 firewall_djt의 dst_ip를 src_ip를 기준으로 left join 하고 firewall_djt.dst_port == 443인 것만 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs", "firewall_djt"],
                    known_fields=["src_ip", "dst_ip", "dst_port"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertIn("    | search dst_port == 443", response.query)
        self.assertLess(response.query.index("    | search dst_port == 443"), response.query.index("    | eval _join_key = dst_ip"))

    def test_generates_stream_forward_with_confirmation_preview(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 1시간 firewall_logs에서 100건을 sample_stream 스트림으로 전달해줘",
                context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertTrue(response.query.endswith("| stream forward=t sample_stream"))
        self.assertEqual(response.execution_preview.status, "requires_confirmation")
        self.assertFalse(response.execution_preview.is_read_only)
    def test_references_only_generated_commands_when_possible(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 24시간 동안 firewall_logs에서 출발지 IP별 차단 건수를 집계해서 많은 순으로 20개 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated")
        command_set = set(response.validation.commands)
        referenced = {ref.entry_name for ref in response.references}
        self.assertTrue(referenced)
        self.assertTrue(referenced.issubset(command_set), referenced)
        self.assertNotIn("set", referenced)
        self.assertNotIn("eval", referenced)

    def test_needs_clarification_for_ambiguous_error_logs(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="에러 로그 보여줘",
                context=RequestContext(),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("테이블" in question for question in response.questions))
        self.assertTrue(any("필드명" in question for question in response.questions))

    def test_generates_timechart_for_span_request(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="araqne_query_logs에서 root 사용자의 실행 건수를 10분 단위로 보여줘",
                context=RequestContext(
                    known_tables=["araqne_query_logs"],
                    known_fields=["login_name", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertIn("| timechart span=10m count", response.query)

    def test_uses_valid_llm_query(self):
        response = generator(
            MockProvider(
                generation_response={
                    "status": "generated",
                    "query": 'table duration=24h firewall_logs\n| search action == "deny"',
                }
            )
        ).generate(
            GenerateQueryRequest(
                request="최근 24시간 firewall_logs 차단 로그",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated")
        self.assertIn('| search action == "deny"', response.query)
        self.assertTrue(response.debug["llm_used"])

    def test_llm_resolves_missing_intent_when_real_provider_is_enabled(self):
        instance = generator(
            MockProvider(
                generation_response={
                    "status": "generated",
                    "table": "custom_logs",
                    "duration": "24h",
                    "filter_field": "severity",
                    "filter_value": "error",
                    "group_by": "account",
                    "limit": 20,
                    "sort_desc": True,
                    "assumptions": ["severity and account were inferred from the request wording."],
                }
            )
        )
        with patch.object(settings, "llm_provider", "openai"):
            response = instance.generate(
                GenerateQueryRequest(
                    request="최근 24시간 custom_logs에서 client_group별 오류 건수 20개를 보여줘",
                    context=RequestContext(
                        known_tables=["custom_logs"],
                        request_catalog=Catalog(
                            source="fixture",
                            tables=[
                                CatalogTable(
                                    table_name="custom_logs",
                                    fields=[
                                        CatalogField(field_name="severity", field_type="string"),
                                        CatalogField(field_name="account", field_type="string"),
                                    ],
                                )
                            ],
                        ),
                    ),
                )
            )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertTrue(response.debug["llm_intent_fallback"])
        self.assertIn("stats count by account", response.query)
        self.assertTrue(any("inferred from the request" in item for item in response.assumptions))

    def test_generates_account_error_aggregation_from_common_aliases(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 24시간 app_logs에서 계정별 오류 건수 20개를 보여줘",
                context=RequestContext(),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            'table duration=24h app_logs\n'
            '| search severity == "error"\n'
            "| stats count by account_id\n"
            "| limit 20",
        )

    def test_repairs_invalid_llm_query(self):
        response = generator(
            MockProvider(
                generation_response={"status": "generated", "query": "unknown firewall_logs"},
                repair_response={"status": "generated", "query": "table firewall_logs"},
            )
        ).generate(
            GenerateQueryRequest(
                request="firewall_logs 보여줘",
                context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
            )
        )
        self.assertEqual(response.status, "generated")
        self.assertEqual(response.query, "table firewall_logs")
        self.assertEqual(response.debug["repair_attempts"], 1)

    def test_falls_back_to_template_when_llm_remains_invalid(self):
        response = generator(
            MockProvider(generation_response={"status": "generated", "query": "unknown firewall_logs"})
        ).generate(
            GenerateQueryRequest(
                request="firewall_logs 보여줘",
                context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
            )
        )
        self.assertEqual(response.status, "generated")
        self.assertEqual(response.query, "table firewall_logs")
        self.assertTrue(response.debug["template_fallback"])

    def test_falls_back_to_template_when_repair_remains_invalid(self):
        response = generator(
            MockProvider(
                generation_response={"status": "generated", "query": "unknown firewall_logs"},
                repair_response={"status": "generated", "query": "still_unknown firewall_logs"},
            )
        ).generate(
            GenerateQueryRequest(
                request="firewall_logs 보여줘",
                context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
            )
        )
        self.assertEqual(response.status, "generated")
        self.assertEqual(response.query, "table firewall_logs")
        self.assertEqual(response.debug["repair_attempts"], 2)
        self.assertTrue(response.debug["template_fallback"])

    def test_returns_unsupported_when_invalid_llm_and_template_cannot_be_built(self):
        instance = generator(
            MockProvider(generation_response={"status": "generated", "query": "unknown firewall_logs"})
        )
        original_template_query = instance._template_query
        instance._template_query = lambda intent: (_ for _ in ()).throw(ValueError("template unavailable"))
        try:
            response = instance.generate(
                GenerateQueryRequest(
                    request="firewall_logs 보여줘",
                    context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
                )
            )
        finally:
            instance._template_query = original_template_query
        self.assertEqual(response.status, "unsupported")
        self.assertIsNone(response.query)
        self.assertFalse(response.validation.valid)
        self.assertFalse(response.debug["template_fallback"])

    def test_generates_rename_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs의 src_ip를 할당ip로 rename해줘",
                context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "_time"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| rename src_ip as 할당ip")
        self.assertIn("rename", response.validation.commands)
        self.assertTrue(any(ref.entry_name == "rename" for ref in response.references))

    def test_rename_with_euro_ending_korean_particle_keeps_field_name(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs의 src_ip를 할당ip으로 rename해줘",
                context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "_time"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| rename src_ip as 할당ip")

    def test_rename_needs_clarification_when_source_field_unknown(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs의 unknown_ip를 할당ip로 rename해줘",
                context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "_time"]),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("원본 필드명" in question for question in response.questions))

    def test_generates_fields_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 src_ip, action만 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| fields src_ip, action")
        self.assertIn("fields", response.validation.commands)
        self.assertTrue(any(ref.entry_name == "fields" for ref in response.references))

    def test_fields_need_clarification_when_unknown(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 ip주소 필드만 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("출력할 필드명" in question for question in response.questions))

    def test_generates_eval_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="sys_cpu_logs에서 kernel + user를 total로 계산해줘",
                context=RequestContext(
                    known_tables=["sys_cpu_logs"],
                    known_fields=["kernel", "user", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table sys_cpu_logs\n| eval total = kernel + user")
        self.assertIn("eval", response.validation.commands)
        self.assertTrue(any(ref.entry_name == "eval" for ref in response.references))

    def test_eval_needs_clarification_when_source_field_unknown(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="sys_cpu_logs에서 kernel + idle를 total로 계산해줘",
                context=RequestContext(
                    known_tables=["sys_cpu_logs"],
                    known_fields=["kernel", "user", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("계산할 표현식" in question for question in response.questions))

    def test_generates_numeric_comparison_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 1시간 동안 sys_cpu_logs에서 kernel + user가 80 이상인 데이터만 보여줘",
                context=RequestContext(
                    known_tables=["sys_cpu_logs"],
                    known_fields=["kernel", "user", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table duration=1h sys_cpu_logs\n| search kernel + user >= 80")
        self.assertIn("search", response.validation.commands)

    def test_generates_yesterday_absolute_time_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="어제 firewall_logs에서 action이 deny인 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "_time"],
                ),
            )
        )
        today = date.today()
        yesterday = today - timedelta(days=1)
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            f'table from={yesterday.isoformat()} to={today.isoformat()} firewall_logs\n| search action == "deny"',
        )

    def test_generates_explicit_absolute_time_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="2026-08-01부터 2026-08-03까지 firewall_logs 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table from=2026-08-01 to=2026-08-04 firewall_logs")

    def test_generates_relative_datetime_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="어제 9시부터 오늘 3시까지 firewall_logs에서 action이 deny인 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "_time"],
                ),
            )
        )
        today = date.today()
        yesterday = today - timedelta(days=1)
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            f'table from={yesterday.isoformat()} 09:00:00 to={today.isoformat()} 03:00:00 firewall_logs\n| search action == "deny"',
        )

    def test_generates_explicit_datetime_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="2026-08-01 10:30부터 2026-08-01 12:00까지 firewall_logs 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table from=2026-08-01 10:30:00 to=2026-08-01 12:00:00 firewall_logs")

    def test_generates_korean_meridiem_datetime_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="어제 밤 11시부터 오늘 새벽 2시까지 firewall_logs에서 action이 deny인 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "_time"],
                ),
            )
        )
        today = date.today()
        yesterday = today - timedelta(days=1)
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            f'table from={yesterday.isoformat()} 23:00:00 to={today.isoformat()} 02:00:00 firewall_logs\n| search action == "deny"',
        )

    def test_generates_noon_midnight_datetime_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="오늘 자정부터 오늘 정오까지 firewall_logs 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["_time"],
                ),
            )
        )
        today = date.today()
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            f"table from={today.isoformat()} 00:00:00 to={today.isoformat()} 12:00:00 firewall_logs",
        )

    def test_generates_string_equality_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 action이 deny인 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'table firewall_logs\n| search action == "deny"')
        self.assertIn("search", response.validation.commands)

    def test_generates_string_inequality_query_with_numeric_value(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="web_logs에서 status가 200이 아닌 로그 보여줘",
                context=RequestContext(
                    known_tables=["web_logs"],
                    known_fields=["status", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table web_logs\n| search status != 200")
        self.assertIn("search", response.validation.commands)

    def test_generates_combined_filter_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="sys_cpu_logs에서 kernel + user가 80 이상이고 host가 web01인 데이터 보여줘",
                context=RequestContext(
                    known_tables=["sys_cpu_logs"],
                    known_fields=["kernel", "user", "host", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            'table sys_cpu_logs\n| search kernel + user >= 80\n| search host == "web01"',
        )

    def test_generates_or_filter_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 action이 deny 또는 allow인 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'table firewall_logs\n| search action == "deny" or action == "allow"')

    def test_generates_contains_filter_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="app_logs에서 message에 timeout 포함된 로그 보여줘",
                context=RequestContext(
                    known_tables=["app_logs"],
                    known_fields=["message", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'table app_logs\n| search message == "*timeout*"')

    def test_generates_average_stats_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="metrics_logs에서 host별 bytes 평균을 보여줘",
                context=RequestContext(
                    known_tables=["metrics_logs"],
                    known_fields=["host", "bytes", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table metrics_logs\n| stats avg(bytes) as avg_bytes by host")
        self.assertIn("stats", response.validation.commands)

    def test_generates_sum_and_count_stats_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 src_ip별 bytes 합계와 건수를 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "bytes", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| stats sum(bytes) as sum_bytes, count by src_ip")

    def test_metric_aggregation_needs_clarification_when_field_unknown(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="metrics_logs에서 평균을 보여줘",
                context=RequestContext(
                    known_tables=["metrics_logs"],
                    known_fields=["host", "bytes", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("집계할 필드명" in question for question in response.questions))

    def test_generates_metric_stats_sorted_by_alias(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="metrics_logs에서 host별 bytes 평균을 높은 순으로 10개 보여줘",
                context=RequestContext(
                    known_tables=["metrics_logs"],
                    known_fields=["host", "bytes", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            "table metrics_logs\n| stats avg(bytes) as avg_bytes by host\n| sort -avg_bytes\n| limit 10",
        )

    def test_generates_top_n_count_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 src_ip별 건수 TOP 10 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| stats count by src_ip\n| sort -count\n| limit 10")

    def test_generates_bottom_n_count_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 src_ip별 건수 하위 5개 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| stats count by src_ip\n| sort count\n| limit 5")

    def test_generates_most_common_field_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 가장 많이 나온 src_ip 10개 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| stats count by src_ip\n| sort -count\n| limit 10")

    def test_generates_ratio_rollup_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="web_logs에서 status별 비율 보여줘",
                context=RequestContext(
                    known_tables=["web_logs"],
                    known_fields=["status", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table web_logs\n| rollup count by status")
        self.assertIn("rollup", response.validation.commands)

    def test_ratio_needs_group_field(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="web_logs에서 비율 보여줘",
                context=RequestContext(
                    known_tables=["web_logs"],
                    known_fields=["status", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("그룹 기준" in question for question in response.questions))

    def test_generates_unique_values_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 src_ip 고유값 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| stats count by src_ip")

    def test_generates_unique_count_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 src_ip 고유 개수 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| stats count by src_ip\n| stats count as unique_src_ip")

    def test_generates_first_sample_log_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 src_ip별 첫 번째 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "line", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| stats first(line) as first_line by src_ip")
        self.assertIn("first", response.validation.functions)

    def test_generates_last_sample_log_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="app_logs에서 host별 최신 로그 보여줘",
                context=RequestContext(
                    known_tables=["app_logs"],
                    known_fields=["host", "message", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table app_logs\n| stats last(message) as last_message by host")
        self.assertIn("last", response.validation.functions)

    def test_sample_log_needs_output_field_when_unknown(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 src_ip별 첫 번째 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("대표 로그" in question for question in response.questions))

    def test_generates_fulltext_all_tables_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 24시간 동안 전체 테이블에서 1.2.3.4 포함 로그 검색",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'fulltext duration=24h "1.2.3.4"')
        self.assertIn("fulltext", response.validation.commands)

    def test_generates_fulltext_specific_table_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 1시간 동안 app_logs 테이블에서 timeout 포함 로그 fulltext 검색",
                context=RequestContext(
                    known_tables=["app_logs"],
                    known_fields=["_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'fulltext duration=1h "timeout" from app_logs')

    def test_uses_explicit_table_and_field_without_sidebar_hints(self):
        response = generator().generate(
            GenerateQueryRequest(request="custom_logs 테이블에서 severity == critical 로그 보여줘")
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'table custom_logs\n| search severity == "critical"')
        self.assertTrue(any(issue.code == "catalog_unavailable" for issue in response.schema_validation.warnings))

    def test_uses_explicit_field_for_rename_without_sidebar_hints(self):
        response = generator().generate(
            GenerateQueryRequest(request="custom_logs 테이블에서 client_ip를 source_ip로 rename해줘")
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table custom_logs\n| rename client_ip as source_ip")

    def test_generates_explicit_numeric_range_without_sidebar_hints(self):
        response = generator().generate(
            GenerateQueryRequest(request="custom_logs 테이블에서 bytes가 100 이상 1000 이하인 로그 보여줘")
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table custom_logs\n| search bytes >= 100\n| search bytes <= 1000")

    def test_generates_explicit_grouped_sum_without_sidebar_hints(self):
        response = generator().generate(
            GenerateQueryRequest(request="custom_logs 테이블에서 user_id별 bytes 합계 top 10 보여줘")
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            "table custom_logs\n| stats sum(bytes) as sum_bytes by user_id\n| sort -sum_bytes\n| limit 10",
        )

    def test_generates_explicit_contains_filter_without_sidebar_hints(self):
        response = generator().generate(
            GenerateQueryRequest(request="custom_logs 테이블에서 message contains timeout 로그 보여줘")
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, 'table custom_logs\n| search message == "*timeout*"')

    def test_generates_boolean_fulltext_expression(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 1시간 iis에서 game을 포함하면서 MSIE 또는 Firefox 문자열을 포함한 로그 fulltext 검색",
                context=RequestContext(known_tables=["iis"], known_fields=["_time"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            'fulltext duration=1h "game" and ("MSIE" or "Firefox") from iis',
        )

    def test_generates_fulltext_aggregation_sorted_and_limited(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 1시간 app_logs에서 timeout fulltext 검색 후 host별 건수 top 10 보여줘",
                context=RequestContext(known_tables=["app_logs"], known_fields=["host", "_time"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            'fulltext duration=1h "timeout" from app_logs\n| stats count by host\n| sort -count\n| limit 10',
        )

    def test_fulltext_search_needs_expression(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 24시간 동안 전체 테이블에서 로그 검색",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("전체 텍스트" in question for question in response.questions))

    def test_fulltext_all_tables_needs_time_range(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="1.2.3.4 fulltext 검색",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("조회 기간" in question for question in response.questions))

    def test_generates_parameterized_time_range_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 7일간 YOUR_TABLE을 동적으로 조회하는 매개변수 예제를 만들어줘",
                context=RequestContext(
                    known_tables=[],
                    known_fields=["_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            'set from=ago("7d")\n| set to=str(now())\n| table from=$("from") to=$("to") YOUR_TABLE',
        )
        self.assertEqual(response.validation.commands, ["set", "set", "table"])
        self.assertEqual(response.validation.functions, ["ago", "now", "str"])

    def test_parameterized_time_range_needs_duration(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="YOUR_TABLE을 동적으로 조회하는 매개변수 예제를 만들어줘",
                context=RequestContext(
                    known_tables=[],
                    known_fields=["_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("조회 기간" in question for question in response.questions))

    def test_unique_values_need_group_field(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 고유값 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("그룹 기준" in question for question in response.questions))

    def test_generates_metric_timechart_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 6시간 동안 metrics_logs에서 bytes 합계를 30분 단위로 보여줘",
                context=RequestContext(
                    known_tables=["metrics_logs"],
                    known_fields=["bytes", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table duration=6h metrics_logs\n| timechart span=30m sum(bytes) as sum_bytes")

    def test_generates_post_filter_for_metric_aggregation(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="metrics_logs에서 host별 bytes 평균이 100 이상인 것만 보여줘",
                context=RequestContext(
                    known_tables=["metrics_logs"],
                    known_fields=["host", "bytes", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(
            response.query,
            "table metrics_logs\n| stats avg(bytes) as avg_bytes by host\n| search avg_bytes >= 100",
        )

    def test_generates_post_filter_for_count_aggregation(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 src_ip별 건수가 10 이상인 것만 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["src_ip", "action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, "table firewall_logs\n| stats count by src_ip\n| search count >= 10")

    def test_string_filter_needs_clarification_when_field_unknown(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="firewall_logs에서 result가 deny인 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("필드명" in question for question in response.questions))

    def test_numeric_comparison_needs_clarification_when_field_unknown(self):
        response = generator().generate(
            GenerateQueryRequest(
                request="최근 1시간 동안 sys_cpu_logs에서 kernel + idle가 80 이상인 데이터만 보여줘",
                context=RequestContext(
                    known_tables=["sys_cpu_logs"],
                    known_fields=["kernel", "user", "_time"],
                ),
            )
        )
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("비교 조건" in question for question in response.questions))


if __name__ == "__main__":
    unittest.main()
