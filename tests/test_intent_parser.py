import unittest
from datetime import date, timedelta

from app.models.request import GenerateQueryRequest, RequestContext
from app.services.intent_parser import IntentParser


class IntentParserTest(unittest.TestCase):
    def test_extracts_logger_source(self):
        payload = GenerateQueryRequest(
            request=r"local\sample1, local\sample2 로그 수집기를 10초간 보여줘",
            context=RequestContext(known_fields=["message"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.source_type, "logger")
        self.assertEqual(intent.query_type, "realtime")
        self.assertEqual(intent.loggers, [r"local\sample1", r"local\sample2"])
        self.assertEqual(intent.logger_window, "10s")
        self.assertEqual(intent.tables, [])
        self.assertEqual(intent.missing_information, [])

    def test_logger_needs_namespace_name_and_window(self):
        intent = IntentParser().parse(GenerateQueryRequest(request="로그 수집기 보여줘"))
        self.assertEqual(intent.source_type, "logger")
        self.assertIn("조회할 로그 수집기 이름", intent.missing_information)
        self.assertIn("실시간 조회 기간", intent.missing_information)

    def test_extracts_evtx_file_source(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(request=r"D:\data\evtx\System.evtx 파일을 조회해줘")
        )
        self.assertEqual(intent.source_type, "file")
        self.assertEqual(intent.file_command, "evtx-file")
        self.assertEqual(intent.file_path, r"D:\data\evtx\System.evtx")
        self.assertEqual(intent.tables, [])

    def test_file_source_needs_path(self):
        intent = IntentParser().parse(GenerateQueryRequest(request="파일을 조회해줘"))
        self.assertEqual(intent.source_type, "file")
        self.assertIn("조회할 파일 경로", intent.missing_information)

    def test_file_path_with_spaces_needs_clarification(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(request=r'"D:\event logs\System.evtx" 파일을 조회해줘')
        )
        self.assertIn("공백 없는 파일 경로", intent.missing_information)

    def test_extracts_firewall_count_request(self):
        payload = GenerateQueryRequest(
            request="최근 24시간 동안 firewall_logs에서 출발지 IP별 차단 건수를 집계해서 많은 순으로 20개 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.tables, ["firewall_logs"])
        self.assertEqual(intent.time_range.duration, "24h")
        self.assertEqual(intent.group_by, ["src_ip"])
        self.assertEqual(intent.limit, 20)

    def test_missing_error_log_information(self):
        payload = GenerateQueryRequest(
            request="에러 로그 보여줘",
            context=RequestContext(known_tables=[], known_fields=[]),
        )
        intent = IntentParser().parse(payload)
        self.assertIn("조회할 로그프레소 테이블 이름", intent.missing_information)
        self.assertIn("필터에 사용할 필드명과 값", intent.missing_information)

    def test_does_not_invent_unknown_field(self):
        payload = GenerateQueryRequest(
            request="최근 1시간 동안 app_logs에서 에러 로그 보여줘",
            context=RequestContext(known_tables=["app_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.filters, [])
        self.assertIn("필터에 사용할 필드명과 값", intent.missing_information)

    def test_timechart_span_request(self):
        payload = GenerateQueryRequest(
            request="araqne_query_logs에서 root 사용자의 실행 건수를 10분 단위로 보여줘",
            context=RequestContext(known_tables=["araqne_query_logs"], known_fields=["login_name", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.tables, ["araqne_query_logs"])
        self.assertEqual(intent.filters[0].field, "login_name")
        self.assertEqual(intent.aggregations[0].function, "count")

    def test_extracts_rename_request(self):
        payload = GenerateQueryRequest(
            request="firewall_logs의 src_ip를 할당ip로 rename해줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.tables, ["firewall_logs"])
        self.assertEqual(len(intent.renames), 1)
        self.assertEqual(intent.renames[0].field, "src_ip")
        self.assertEqual(intent.renames[0].new_name, "할당ip")

    def test_rename_needs_field_names_when_unknown(self):
        payload = GenerateQueryRequest(
            request="firewall_logs의 unknown_ip를 할당ip로 rename해줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.renames, [])
        self.assertIn("변경할 원본 필드명과 새 필드명", intent.missing_information)

    def test_extracts_selected_fields(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip, action만 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.tables, ["firewall_logs"])
        self.assertEqual(intent.selected_fields, ["src_ip", "action"])

    def test_selected_fields_need_clarification_when_unknown(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 ip주소 필드만 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.selected_fields, [])
        self.assertIn("출력할 필드명", intent.missing_information)

    def test_extracts_computed_field(self):
        payload = GenerateQueryRequest(
            request="sys_cpu_logs에서 kernel + user를 total로 계산해줘",
            context=RequestContext(known_tables=["sys_cpu_logs"], known_fields=["kernel", "user", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.tables, ["sys_cpu_logs"])
        self.assertEqual(len(intent.computed_fields), 1)
        self.assertEqual(intent.computed_fields[0].name, "total")
        self.assertEqual(intent.computed_fields[0].expression, "kernel + user")

    def test_computed_field_needs_clarification_when_source_field_unknown(self):
        payload = GenerateQueryRequest(
            request="sys_cpu_logs에서 kernel + idle를 total로 계산해줘",
            context=RequestContext(known_tables=["sys_cpu_logs"], known_fields=["kernel", "user", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.computed_fields, [])
        self.assertIn("계산할 표현식과 새 필드명", intent.missing_information)

    def test_extracts_numeric_comparison_filter(self):
        payload = GenerateQueryRequest(
            request="최근 1시간 동안 sys_cpu_logs에서 kernel + user가 80 이상인 데이터만 보여줘",
            context=RequestContext(known_tables=["sys_cpu_logs"], known_fields=["kernel", "user", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.time_range.duration, "1h")
        self.assertEqual(intent.selected_fields, [])
        self.assertEqual(len(intent.filters), 1)
        self.assertEqual(intent.filters[0].field, "kernel + user")
        self.assertEqual(intent.filters[0].operator, ">=")
        self.assertEqual(intent.filters[0].value, "80")
        self.assertEqual(intent.filters[0].value_type, "number")

    def test_extracts_yesterday_absolute_time_range(self):
        payload = GenerateQueryRequest(
            request="어제 firewall_logs에서 action이 deny인 로그 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        today = date.today()
        self.assertEqual(intent.time_range.mode, "absolute")
        self.assertEqual(intent.time_range.from_, (today - timedelta(days=1)).isoformat())
        self.assertEqual(intent.time_range.to, today.isoformat())

    def test_extracts_explicit_date_range_inclusive_until(self):
        payload = GenerateQueryRequest(
            request="2026-08-01부터 2026-08-03까지 firewall_logs 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.time_range.mode, "absolute")
        self.assertEqual(intent.time_range.from_, "2026-08-01")
        self.assertEqual(intent.time_range.to, "2026-08-04")

    def test_extracts_previous_week_absolute_time_range(self):
        payload = GenerateQueryRequest(
            request="지난주 firewall_logs 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        self.assertEqual(intent.time_range.mode, "absolute")
        self.assertEqual(intent.time_range.from_, (this_monday - timedelta(days=7)).isoformat())
        self.assertEqual(intent.time_range.to, this_monday.isoformat())

    def test_extracts_relative_datetime_range(self):
        payload = GenerateQueryRequest(
            request="어제 9시부터 오늘 3시까지 firewall_logs 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        today = date.today()
        self.assertEqual(intent.time_range.mode, "absolute")
        self.assertEqual(intent.time_range.from_, f"{(today - timedelta(days=1)).isoformat()} 09:00:00")
        self.assertEqual(intent.time_range.to, f"{today.isoformat()} 03:00:00")

    def test_extracts_explicit_datetime_range(self):
        payload = GenerateQueryRequest(
            request="2026-08-01 10:30부터 2026-08-01 12:00까지 firewall_logs 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.time_range.mode, "absolute")
        self.assertEqual(intent.time_range.from_, "2026-08-01 10:30:00")
        self.assertEqual(intent.time_range.to, "2026-08-01 12:00:00")

    def test_extracts_korean_meridiem_datetime_range(self):
        payload = GenerateQueryRequest(
            request="어제 밤 11시부터 오늘 새벽 2시까지 firewall_logs 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        today = date.today()
        self.assertEqual(intent.time_range.mode, "absolute")
        self.assertEqual(intent.time_range.from_, f"{(today - timedelta(days=1)).isoformat()} 23:00:00")
        self.assertEqual(intent.time_range.to, f"{today.isoformat()} 02:00:00")

    def test_extracts_noon_and_midnight_datetime_range(self):
        payload = GenerateQueryRequest(
            request="오늘 자정부터 오늘 정오까지 firewall_logs 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        today = date.today()
        self.assertEqual(intent.time_range.mode, "absolute")
        self.assertEqual(intent.time_range.from_, f"{today.isoformat()} 00:00:00")
        self.assertEqual(intent.time_range.to, f"{today.isoformat()} 12:00:00")

    def test_extracts_explicit_pm_datetime_range(self):
        payload = GenerateQueryRequest(
            request="2026-08-01 오후 3시부터 오후 5시까지 firewall_logs 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.time_range.mode, "absolute")
        self.assertEqual(intent.time_range.from_, "2026-08-01 15:00:00")
        self.assertEqual(intent.time_range.to, "2026-08-01 17:00:00")

    def test_extracts_string_equality_filter(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 action이 deny인 로그 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(len(intent.filters), 1)
        self.assertEqual(intent.filters[0].field, "action")
        self.assertEqual(intent.filters[0].operator, "==")
        self.assertEqual(intent.filters[0].value, "deny")
        self.assertEqual(intent.filters[0].value_type, "string")

    def test_extracts_string_inequality_with_numeric_value(self):
        payload = GenerateQueryRequest(
            request="web_logs에서 status가 200이 아닌 로그 보여줘",
            context=RequestContext(known_tables=["web_logs"], known_fields=["status", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(len(intent.filters), 1)
        self.assertEqual(intent.filters[0].field, "status")
        self.assertEqual(intent.filters[0].operator, "!=")
        self.assertEqual(intent.filters[0].value, "200")
        self.assertEqual(intent.filters[0].value_type, "number")

    def test_combines_numeric_and_string_filters(self):
        payload = GenerateQueryRequest(
            request="sys_cpu_logs에서 kernel + user가 80 이상이고 host가 web01인 데이터 보여줘",
            context=RequestContext(known_tables=["sys_cpu_logs"], known_fields=["kernel", "user", "host", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(len(intent.filters), 2)
        self.assertEqual(intent.filters[0].field, "kernel + user")
        self.assertEqual(intent.filters[0].operator, ">=")
        self.assertEqual(intent.filters[1].field, "host")
        self.assertEqual(intent.filters[1].operator, "==")
        self.assertEqual(intent.filters[1].value, "web01")

    def test_extracts_or_filter_values(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 action이 deny 또는 allow인 로그 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(len(intent.filters), 2)
        self.assertEqual(intent.filters[0].field, "action")
        self.assertEqual(intent.filters[0].value, "deny")
        self.assertEqual(intent.filters[0].conjunction, "and")
        self.assertEqual(intent.filters[1].field, "action")
        self.assertEqual(intent.filters[1].value, "allow")
        self.assertEqual(intent.filters[1].conjunction, "or")

    def test_extracts_contains_filter(self):
        payload = GenerateQueryRequest(
            request="app_logs에서 message에 timeout 포함된 로그 보여줘",
            context=RequestContext(known_tables=["app_logs"], known_fields=["message", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(len(intent.filters), 1)
        self.assertEqual(intent.filters[0].field, "message")
        self.assertEqual(intent.filters[0].operator, "==")
        self.assertEqual(intent.filters[0].value, "*timeout*")

    def test_extracts_average_aggregation_by_field(self):
        payload = GenerateQueryRequest(
            request="metrics_logs에서 host별 bytes 평균을 보여줘",
            context=RequestContext(known_tables=["metrics_logs"], known_fields=["host", "bytes", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.group_by, ["host"])
        self.assertEqual(len(intent.aggregations), 1)
        self.assertEqual(intent.aggregations[0].function, "avg")
        self.assertEqual(intent.aggregations[0].field, "bytes")
        self.assertEqual(intent.aggregations[0].alias, "avg_bytes")

    def test_extracts_sum_and_count_aggregation(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip별 bytes 합계와 건수를 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "bytes", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.group_by, ["src_ip"])
        self.assertEqual([(item.function, item.field) for item in intent.aggregations], [("sum", "bytes"), ("count", None)])

    def test_metric_aggregation_needs_clarification_when_field_unknown(self):
        payload = GenerateQueryRequest(
            request="metrics_logs에서 평균을 보여줘",
            context=RequestContext(known_tables=["metrics_logs"], known_fields=["host", "bytes", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.aggregations, [])
        self.assertIn("집계할 필드명", intent.missing_information)

    def test_sorts_by_metric_aggregation_alias(self):
        payload = GenerateQueryRequest(
            request="metrics_logs에서 host별 bytes 평균을 높은 순으로 10개 보여줘",
            context=RequestContext(known_tables=["metrics_logs"], known_fields=["host", "bytes", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.sort[0].field, "avg_bytes")
        self.assertEqual(intent.sort[0].direction, "desc")
        self.assertEqual(intent.limit, 10)

    def test_sorts_by_metric_aggregation_alias_ascending(self):
        payload = GenerateQueryRequest(
            request="metrics_logs에서 host별 bytes 평균을 낮은 순으로 보여줘",
            context=RequestContext(known_tables=["metrics_logs"], known_fields=["host", "bytes", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.sort[0].field, "avg_bytes")
        self.assertEqual(intent.sort[0].direction, "asc")

    def test_extracts_top_n_sort_and_limit(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip별 건수 TOP 10 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.sort[0].field, "count")
        self.assertEqual(intent.sort[0].direction, "desc")
        self.assertEqual(intent.limit, 10)

    def test_extracts_bottom_n_sort_and_limit(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip별 건수 하위 5개 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.sort[0].field, "count")
        self.assertEqual(intent.sort[0].direction, "asc")
        self.assertEqual(intent.limit, 5)

    def test_extracts_most_common_sort_phrase(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 가장 많이 나온 src_ip 10개 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.group_by, ["src_ip"])
        self.assertEqual(intent.aggregations[0].function, "count")
        self.assertEqual(intent.sort[0].field, "count")
        self.assertEqual(intent.sort[0].direction, "desc")
        self.assertEqual(intent.limit, 10)

    def test_extracts_ratio_rollup_request(self):
        payload = GenerateQueryRequest(
            request="web_logs에서 status별 비율 보여줘",
            context=RequestContext(known_tables=["web_logs"], known_fields=["status", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.group_by, ["status"])
        self.assertEqual(intent.aggregations[0].function, "count")
        self.assertEqual(intent.aggregation_command, "rollup")

    def test_ratio_needs_group_field(self):
        payload = GenerateQueryRequest(
            request="web_logs에서 비율 보여줘",
            context=RequestContext(known_tables=["web_logs"], known_fields=["status", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertIn("그룹 기준 필드명", intent.missing_information)

    def test_extracts_unique_values_request(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip 고유값 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.selected_fields, [])
        self.assertEqual(intent.group_by, ["src_ip"])
        self.assertEqual(intent.aggregations[0].function, "count")
        self.assertEqual(intent.final_aggregations, [])

    def test_extracts_unique_count_request(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip 고유 개수 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.group_by, ["src_ip"])
        self.assertEqual(intent.aggregations[0].function, "count")
        self.assertEqual(intent.final_aggregations[0].function, "count")
        self.assertEqual(intent.final_aggregations[0].alias, "unique_src_ip")

    def test_extracts_first_sample_log_by_field(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip별 첫 번째 로그 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "line", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.selected_fields, [])
        self.assertEqual(intent.group_by, ["src_ip"])
        self.assertEqual(intent.aggregations[0].function, "first")
        self.assertEqual(intent.aggregations[0].field, "line")
        self.assertEqual(intent.aggregations[0].alias, "first_line")

    def test_extracts_last_sample_log_by_field(self):
        payload = GenerateQueryRequest(
            request="app_logs에서 host별 최신 로그 보여줘",
            context=RequestContext(known_tables=["app_logs"], known_fields=["host", "message", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.group_by, ["host"])
        self.assertEqual(intent.aggregations[0].function, "last")
        self.assertEqual(intent.aggregations[0].field, "message")
        self.assertEqual(intent.aggregations[0].alias, "last_message")

    def test_sample_log_needs_output_field_when_unknown(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip별 첫 번째 로그 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.aggregations, [])
        self.assertIn("대표 로그로 출력할 필드명", intent.missing_information)

    def test_extracts_fulltext_search_all_tables(self):
        payload = GenerateQueryRequest(
            request="최근 24시간 동안 전체 테이블에서 1.2.3.4 포함 로그 검색",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.source_type, "fulltext")
        self.assertEqual(intent.tables, [])
        self.assertEqual(intent.fulltext_expression, "1.2.3.4")
        self.assertEqual(intent.time_range.duration, "24h")

    def test_fulltext_search_needs_expression(self):
        payload = GenerateQueryRequest(
            request="최근 24시간 동안 전체 테이블에서 로그 검색",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.source_type, "fulltext")
        self.assertIn("전체 텍스트 검색어", intent.missing_information)

    def test_fulltext_all_tables_needs_time_range(self):
        payload = GenerateQueryRequest(
            request="1.2.3.4 fulltext 검색",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.source_type, "fulltext")
        self.assertEqual(intent.tables, [])
        self.assertEqual(intent.fulltext_expression, "1.2.3.4")
        self.assertIn("조회 기간", intent.missing_information)
        self.assertEqual(intent.missing_information.count("조회 기간"), 1)

    def test_extracts_parameterized_time_range_request(self):
        payload = GenerateQueryRequest(
            request="최근 7일간 YOUR_TABLE을 동적으로 조회하는 매개변수 예제를 만들어줘",
            context=RequestContext(known_tables=[], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.tables, ["YOUR_TABLE"])
        self.assertEqual(intent.time_range.duration, "7d")
        self.assertTrue(intent.use_parameterized_time_range)

    def test_parameterized_time_range_needs_duration(self):
        payload = GenerateQueryRequest(
            request="YOUR_TABLE을 동적으로 조회하는 매개변수 예제를 만들어줘",
            context=RequestContext(known_tables=[], known_fields=["_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertTrue(intent.use_parameterized_time_range)
        self.assertIn("매개변수로 지정할 조회 기간", intent.missing_information)

    def test_unique_values_need_group_field(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 고유값 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertIn("그룹 기준 필드명", intent.missing_information)

    def test_extracts_post_filter_for_metric_aggregation(self):
        payload = GenerateQueryRequest(
            request="metrics_logs에서 host별 bytes 평균이 100 이상인 것만 보여줘",
            context=RequestContext(known_tables=["metrics_logs"], known_fields=["host", "bytes", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.filters, [])
        self.assertEqual(len(intent.post_filters), 1)
        self.assertEqual(intent.post_filters[0].field, "avg_bytes")
        self.assertEqual(intent.post_filters[0].operator, ">=")
        self.assertEqual(intent.post_filters[0].value, "100")

    def test_extracts_post_filter_for_count_aggregation(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip별 건수가 10 이상인 것만 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.filters, [])
        self.assertEqual(intent.aggregations[0].function, "count")
        self.assertEqual(intent.post_filters[0].field, "count")
        self.assertEqual(intent.post_filters[0].operator, ">=")
        self.assertEqual(intent.post_filters[0].value, "10")

    def test_string_filter_needs_clarification_when_field_unknown(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 result가 deny인 로그 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.filters, [])
        self.assertIn("필터에 사용할 필드명과 값", intent.missing_information)

    def test_numeric_comparison_needs_clarification_when_field_unknown(self):
        payload = GenerateQueryRequest(
            request="최근 1시간 동안 sys_cpu_logs에서 kernel + idle가 80 이상인 데이터만 보여줘",
            context=RequestContext(known_tables=["sys_cpu_logs"], known_fields=["kernel", "user", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.filters, [])
        self.assertIn("비교 조건에 사용할 필드명과 값", intent.missing_information)


if __name__ == "__main__":
    unittest.main()
