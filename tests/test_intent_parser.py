import unittest
import pytest
from datetime import date, timedelta

from app.models.request import GenerateQueryRequest, RequestContext
from app.services.intent_parser import IntentParser


pytestmark = pytest.mark.advanced_parser


class IntentParserTest(unittest.TestCase):
    def test_extracts_named_parser(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="ssh_logs 테이블에 openssh 파서를 적용해줘",
                context=RequestContext(known_tables=["ssh_logs"], known_fields=["line"]),
            )
        )
        self.assertEqual(intent.parser_name, "openssh")
        self.assertEqual(intent.missing_information, [])

    def test_extracts_json_parser_options(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="app_logs 테이블의 payload 필드 JSON 중첩을 펼쳐 파싱해줘",
                context=RequestContext(known_tables=["app_logs"], known_fields=["payload"]),
            )
        )
        self.assertEqual(intent.structured_parser, "parsejson")
        self.assertEqual(intent.structured_parser_field, "payload")
        self.assertTrue(intent.parser_flatten)
        self.assertNotIn("적용할 파서 이름", intent.missing_information)

    def test_extracts_tsv_parser_options(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="app_logs 테이블의 line 필드 TSV 문자열을 파싱해줘",
                context=RequestContext(known_tables=["app_logs"], known_fields=["line"]),
            )
        )
        self.assertEqual(intent.structured_parser, "parsecsv")
        self.assertEqual(intent.structured_parser_field, "line")
        self.assertTrue(intent.parser_tab)

    def test_parse_request_needs_parser_name(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="ssh_logs 테이블의 line을 파싱해줘",
                context=RequestContext(known_tables=["ssh_logs"], known_fields=["line"]),
            )
        )
        self.assertIn("적용할 파서 이름", intent.missing_information)

    def test_extracts_explode_array_field(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="app_logs 테이블의 tags 배열 필드를 행으로 확장해줘",
                context=RequestContext(known_tables=["app_logs"], known_fields=["tags", "message"]),
            )
        )
        self.assertEqual(intent.explode_fields, ["tags"])

    def test_explode_request_needs_known_field(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="app_logs 테이블의 tags 배열 필드를 행으로 확장해줘",
                context=RequestContext(known_tables=["app_logs"], known_fields=["message"]),
            )
        )
        self.assertEqual(intent.explode_fields, [])
        self.assertIn("행으로 확장할 배열 필드명", intent.missing_information)

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

    def test_extracts_stream_source_names_wildcard_and_window(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(request="sample1, audit_* 스트림을 10초간 보여줘")
        )
        self.assertEqual(intent.source_type, "stream")
        self.assertEqual(intent.query_type, "stream")
        self.assertEqual(intent.streams, ["sample1", "audit_*"])
        self.assertEqual(intent.stream_window, "10s")
        self.assertEqual(intent.missing_information, [])

    def test_stream_window_is_optional_but_name_is_required(self):
        intent = IntentParser().parse(GenerateQueryRequest(request="스트림을 보여줘"))
        self.assertIn("조회할 스트림 이름", intent.missing_information)
        self.assertNotIn("실시간 조회 기간", intent.missing_information)

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

    def test_extracts_documented_data_file_sources(self):
        cases = [
            (r"D:\data\events.csv 파일을 조회해줘", "csvfile"),
            ("events.tsv 파일을 조회해줘", "csvfile"),
            ("/var/log/events.json 파일을 조회해줘", "jsonfile"),
            ("app.txt 파일을 조회해줘", "textfile"),
        ]
        for request, command in cases:
            with self.subTest(request=request):
                intent = IntentParser().parse(GenerateQueryRequest(request=request))
                self.assertEqual(intent.source_type, "file")
                self.assertEqual(intent.file_command, command)
                self.assertEqual(intent.missing_information, [])

    def test_extracts_documented_forensic_file_sources(self):
        cases = [
            ("capture.pcap 파일을 조회해줘", "pcapfile"),
            ("report.xml 파일을 조회해줘", "xmlfile"),
            (r"C:\Windows\Prefetch\APP.PF 파일을 조회해줘", "prefetch-file"),
            ("Report.wer 파일을 조회해줘", "wer-file"),
        ]
        for request, command in cases:
            with self.subTest(request=request):
                intent = IntentParser().parse(GenerateQueryRequest(request=request))
                self.assertEqual(intent.source_type, "file")
                self.assertEqual(intent.file_command, command)
                self.assertEqual(intent.missing_information, [])

    def test_extracts_zip_path_and_member(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(request="/opt/logpresso/testdata.zip 안의 *.txt 파일을 조회해줘")
        )
        self.assertEqual(intent.file_command, "zipfile")
        self.assertEqual(intent.file_path, "/opt/logpresso/testdata.zip")
        self.assertEqual(intent.archive_member, "*.txt")
        self.assertEqual(intent.missing_information, [])

    def test_zip_source_needs_member_name(self):
        intent = IntentParser().parse(GenerateQueryRequest(request="/opt/logpresso/testdata.zip 파일을 조회해줘"))
        self.assertIn("ZIP 내부에서 조회할 파일 이름", intent.missing_information)

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

    def test_extracts_multiple_tables_and_node_paths(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="최근 1시간 동안 *:sys_cpu_logs와 node2:sys_mem_logs 테이블을 조회해줘",
                context=RequestContext(
                    known_tables=["*:sys_cpu_logs", "node2:sys_mem_logs"],
                    known_fields=["_time"],
                ),
            )
        )
        self.assertEqual(intent.tables, ["*:sys_cpu_logs", "node2:sys_mem_logs"])
        self.assertEqual(intent.time_range.duration, "1h")

    def test_extracts_source_record_order(self):
        cases = [("오래된 로그부터", "asc"), ("최신 로그부터", "desc")]
        for wording, expected in cases:
            with self.subTest(wording=wording):
                intent = IntentParser().parse(
                    GenerateQueryRequest(
                        request=f"firewall_logs에서 {wording} 보여줘",
                        context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
                    )
                )
                self.assertEqual(intent.source_order, expected)

    def test_missing_error_log_information(self):
        payload = GenerateQueryRequest(
            request="에러 로그 보여줘",
            context=RequestContext(known_tables=[], known_fields=[]),
        )
        intent = IntentParser().parse(payload)
        self.assertIn("조회할 로그프레소 테이블 이름", intent.missing_information)
        self.assertIn("필터에 사용할 필드명과 값", intent.missing_information)

    def test_explicit_error_field_overrides_default_field_priority(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="에러 로그 보여줘. 테이블은 firewall_logs, 에러 필드는 message, 기간은 최근 24시간",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["message", "level", "_time"],
                ),
            )
        )
        self.assertEqual(intent.filters[0].field, "message")
        self.assertEqual(intent.filters[0].value, "ERROR")

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

    def test_extracts_rename_request_with_euro_particle(self):
        payload = GenerateQueryRequest(
            request="firewall_logs의 src_ip를 할당ip으로 rename해줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(len(intent.renames), 1)
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

    def test_extracts_computed_field_without_particle_suffix(self):
        payload = GenerateQueryRequest(
            request="sys_cpu_logs에서 kernel + user를 total으로 계산해줘",
            context=RequestContext(known_tables=["sys_cpu_logs"], known_fields=["kernel", "user", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(len(intent.computed_fields), 1)
        self.assertEqual(intent.computed_fields[0].name, "total")

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

    def test_extracts_or_filters_across_different_fields(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="firewall_logs에서 action=deny 또는 level=error인 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "level"],
                ),
            )
        )
        self.assertEqual([item.field for item in intent.filters], ["action", "level"])
        self.assertEqual(intent.filters[0].conjunction, "and")
        self.assertEqual(intent.filters[1].conjunction, "or")

    def test_mixed_and_or_without_parentheses_needs_clarification(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="firewall_logs에서 action=deny 또는 level=error 그리고 host=web01인 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "level", "host"],
                ),
            )
        )
        self.assertIn("복합 필터 괄호 구조", intent.missing_information)

    def test_extracts_parenthesized_or_group_followed_by_and_filter(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="firewall_logs에서 (action=deny 또는 level=error) 그리고 host=web01인 로그 보여줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["action", "level", "host"],
                ),
            )
        )
        self.assertEqual([item.field for item in intent.filters], ["action", "level", "host"])
        self.assertEqual([item.conjunction for item in intent.filters], ["and", "or", "and"])
        self.assertNotIn("복합 필터 괄호 구조", intent.missing_information)

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

    def test_extracts_multiple_explicit_sort_fields_in_order(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="firewall_logs를 _time 내림차순 후 login_name 오름차순으로 정렬해줘",
                context=RequestContext(
                    known_tables=["firewall_logs"],
                    known_fields=["_time", "login_name", "message"],
                ),
            )
        )
        self.assertEqual(
            [(item.field, item.direction) for item in intent.sort],
            [("_time", "desc"), ("login_name", "asc")],
        )

    def test_extracts_top_n_sort_and_limit(self):
        payload = GenerateQueryRequest(
            request="firewall_logs에서 src_ip별 건수 TOP 10 보여줘",
            context=RequestContext(known_tables=["firewall_logs"], known_fields=["src_ip", "action", "_time"]),
        )
        intent = IntentParser().parse(payload)
        self.assertEqual(intent.sort[0].field, "count")
        self.assertEqual(intent.sort[0].direction, "desc")
        self.assertEqual(intent.limit, 10)

    def test_extracts_limit_offset_and_maximum(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="firewall_logs에서 10건을 건너뛰고 20건 보여줘",
                context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
            )
        )
        self.assertEqual(intent.offset, 10)
        self.assertEqual(intent.limit, 20)
        self.assertEqual(intent.missing_information, [])

    def test_offset_without_maximum_needs_clarification(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="firewall_logs에서 10건을 건너뛰고 보여줘",
                context=RequestContext(known_tables=["firewall_logs"], known_fields=["_time"]),
            )
        )
        self.assertEqual(intent.offset, 10)
        self.assertIsNone(intent.limit)
        self.assertIn("건너뛴 이후 출력 건수", intent.missing_information)

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

    def test_extracts_fulltext_and_or_expression(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request='최근 1시간 iis 테이블에서 "game"을 포함하면서 "MSIE" 또는 "Firefox"가 포함된 로그 fulltext 검색',
                context=RequestContext(known_tables=["iis"]),
            )
        )
        self.assertEqual(intent.source_type, "fulltext")
        self.assertEqual(intent.fulltext_expression, '"game" and ("MSIE" or "Firefox")')

    def test_extracts_fulltext_numeric_range(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="최근 1시간 iis 테이블에서 400~500 범위 숫자 fulltext 검색",
                context=RequestContext(known_tables=["iis"]),
            )
        )
        self.assertEqual(intent.fulltext_expression, "range(400, 500)")

    def test_extracts_fulltext_ip_range(self):
        intent = IntentParser().parse(
            GenerateQueryRequest(
                request="최근 1시간 전체 테이블에서 192.0.0.1~192.0.0.255 IP 범위 fulltext 검색"
            )
        )
        self.assertEqual(intent.fulltext_expression, 'iprange("192.0.0.1", "192.0.0.255")')

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
