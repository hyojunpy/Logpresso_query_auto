import unittest
from datetime import date, timedelta

from app.models.request import GenerateQueryRequest, RequestContext
from app.services.llm.mock_provider import MockProvider
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever
from tests.support import shared_index


def generator(llm=None) -> QueryGenerator:
    return QueryGenerator(Retriever(shared_index()), llm=llm)


class QueryGeneratorTest(unittest.TestCase):
    def test_generates_logger_query(self):
        response = generator().generate(
            GenerateQueryRequest(
                request=r"local\sample1, local\sample2 로그 수집기를 10초간 보여줘",
                context=RequestContext(known_fields=["message"]),
            )
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, r"logger window=10s local\sample1, local\sample2")
        self.assertIn("logger", response.validation.commands)

    def test_logger_query_needs_clarification(self):
        response = generator().generate(GenerateQueryRequest(request="로그 수집기 보여줘"))
        self.assertEqual(response.status, "needs_clarification")
        self.assertTrue(any("네임스페이스" in question for question in response.questions))
        self.assertTrue(any("기간" in question for question in response.questions))

    def test_generates_evtx_file_query(self):
        response = generator().generate(
            GenerateQueryRequest(request=r"D:\data\evtx\System.evtx 파일을 조회해줘")
        )
        self.assertEqual(response.status, "generated", response.questions)
        self.assertEqual(response.query, r"evtx-file D:\data\evtx\System.evtx")
        self.assertIn("evtx-file", response.validation.commands)

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
