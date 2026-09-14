from __future__ import annotations

from typing import Any


QUICK_TEST_REQUESTS: dict[str, list[str]] = {
    "기본 조회·필터": [
        "최근 1시간 app_logs에서 level이 error인 로그를 최신순으로 100개 보여줘",
        "최근 24시간 web_logs에서 status가 400 이상인 요청을 최신순으로 200개 보여줘",
        "최근 6시간 app_logs에서 message에 timeout 또는 connection refused가 포함된 로그를 보여줘",
        "최근 24시간 audit_logs에서 admin 사용자의 로그인 실패 기록을 보여줘",
        "최근 1시간 firewall_logs에서 목적지 포트가 22 또는 3389인 로그를 보여줘",
        "최근 24시간 firewall_logs에서 action이 deny인 로그를 최신순으로 500개 보여줘",
        "최근 1시간 web_logs에서 response_time이 1000 이상이고 status가 500 이상인 요청을 보여줘",
        "최근 24시간 app_logs에서 warning 로그를 최신순으로 정렬하고 100건을 건너뛴 뒤 50건 보여줘",
    ],
    "집계·순위": [
        "최근 24시간 app_logs에서 error 로그를 service별로 집계해서 많은 순으로 10개 보여줘",
        "최근 24시간 firewall_logs에서 deny 로그를 src_ip별로 집계해서 많은 순으로 20개 보여줘",
        "최근 7일 network_logs에서 user_id별 bytes 합계를 많은 순으로 10개 보여줘",
        "최근 24시간 web_logs에서 service별 요청 건수와 평균 및 최대 response_time을 보여줘",
        "최근 24시간 app_logs에서 error가 10건 이상인 service를 많은 순으로 보여줘",
        "최근 1시간 firewall_logs에서 dst_ip와 dst_port별 접근 건수를 많은 순으로 20개 보여줘",
        "최근 7일 audit_logs에서 user별 고유 src_ip 개수를 많은 순으로 20개 보여줘",
        "최근 24시간 app_logs에서 service와 result별 건수를 많은 순으로 100개 보여줘",
        "최근 24시간 firewall_logs에서 접근이 가장 적은 dst_port 20개를 보여줘",
        "최근 24시간 network_logs에서 host별 bytes_in과 bytes_out 합계를 보여줘",
    ],
    "시간 추이": [
        "최근 24시간 app_logs의 error 발생 건수를 1시간 간격으로 보여줘",
        "최근 1시간 web_logs의 service별 요청 건수를 5분 간격으로 보여줘",
        "최근 6시간 web_logs의 평균 response_time을 10분 간격으로 보여줘",
        "최근 24시간 firewall_logs의 deny 건수를 1시간 간격으로 보여줘",
        "최근 24시간 web_logs의 service별 5xx 오류 건수를 1시간 간격으로 보여줘",
        "최근 7일 audit_logs의 user별 로그인 실패 건수를 1시간 간격으로 보여줘",
    ],
    "Fulltext": [
        "최근 1시간 web_logs에서 game을 포함하면서 MSIE 또는 Firefox를 포함한 로그를 fulltext 검색해줘",
        "최근 24시간 app_logs와 firewall_logs에서 ransomware 또는 malware를 fulltext 검색해줘",
        "최근 1시간 app_logs에서 timeout을 fulltext 검색하고 host별 건수를 많은 순으로 10개 보여줘",
        "최근 24시간 audit_logs에서 login failed를 fulltext 검색하고 user별로 3건 이상인 결과를 보여줘",
        "최근 24시간 firewall_logs에서 10.0.0.1과 deny를 모두 포함한 로그를 fulltext 검색해줘",
    ],
    "계산·후처리": [
        "최근 24시간 network_logs에서 bytes_in과 bytes_out을 더해 MB로 환산하고 host별 사용량 상위 10개를 보여줘",
        "최근 24시간 web_logs에서 response_time이 1000 이상이면 slow로 분류하고 service별로 집계해줘",
        "최근 1시간 sys_cpu_logs에서 kernel과 user를 더한 total_cpu의 host별 평균과 최대값을 보여줘",
        "최근 24시간 audit_logs에서 result가 failed이면 1로 계산하고 user별 실패 건수를 보여줘",
    ],
    "Join": [
        "최근 24시간 firewall_logs의 src_ip와 asset_info의 ip_address를 기준으로 left join하고 deny 로그를 보여줘",
        "최근 24시간 audit_logs의 user와 user_info의 user_id를 기준으로 left join하고 로그인 실패를 보여줘",
        "최근 24시간 firewall_logs의 src_ip와 asset_info의 ip_address를 기준으로 leftonly join해서 미등록 IP를 보여줘",
        "최근 7일 firewall_logs의 src_ip와 asset_info의 ip_address를 기준으로 inner join해서 등록 IP만 보여줘",
        "최근 24시간 login_logs의 user_id와 file_access_logs의 user_id를 기준으로 left join해줘",
        "최근 24시간 firewall_logs의 src_ip와 asset_info의 ip_address를 기준으로 full join해줘",
    ],
    "실시간 Logger·Stream": [
        "application_logger logger에서 최근 1분 동안 error 로그를 service별로 집계해서 많은 순으로 10개 보여줘",
        "firewall_stream 스트림에서 최근 30초 동안 deny 로그를 src_ip별로 집계해서 많은 순으로 10개 보여줘",
        "security_stream 스트림에서 최근 1분 동안 severity가 7 이상인 이벤트를 asset_info 테이블과 src_ip와 ip_address 기준으로 left streamjoin하고 event_type별 건수를 많은 순으로 20개 보여줘",
        "security_stream 스트림에서 최근 1분 동안 severity가 8 이상인 이벤트 100개를 high_risk_stream으로 전달해줘",
    ],
    "구조화 데이터": [
        "최근 1시간 app_logs의 message를 JSON으로 파싱하고 error_code별 오류 건수를 보여줘",
        "최근 24시간 import_logs의 message를 CSV로 파싱하고 user_id별 bytes 합계를 보여줘",
        "최근 1시간 event_logs의 message를 JSON으로 파싱하고 events 배열을 행으로 펼쳐 event_type별로 집계해줘",
        "최근 1시간 raw_web_logs의 message를 JSON으로 파싱하고 status가 500 이상인 요청을 보여줘",
    ],
    "보안 분석": [
        "최근 24시간 audit_logs에서 3개 이상의 user가 사용한 src_ip를 로그인 건수와 함께 보여줘",
        "최근 1시간 audit_logs에서 로그인 실패가 10건 이상인 src_ip를 보여줘",
        "최근 24시간 audit_logs에서 admin 사용자가 내부 대역이 아닌 src_ip로 접근한 기록을 보여줘",
        "최근 24시간 firewall_logs에서 deny가 10건 이상인 src_ip를 asset_info와 leftonly join해서 보여줘",
        "최근 24시간 login_logs의 user_id와 file_access_logs의 user_id를 기준으로 inner join해서 로그인 후 파일 접근을 보여줘",
        "최근 24시간 app_logs에서 error 여부를 계산하고 host별 오류 건수와 전체 건수를 보여줘",
    ],
    "운영 모니터링": [
        "최근 1시간 web_logs에서 5xx 여부를 계산하고 service별 오류 건수와 평균 response_time을 보여줘",
        "최근 24시간 web_logs에서 response_time이 1000 이상인 uri의 건수와 평균 및 최대 시간을 보여줘",
        "최근 1시간 app_logs에서 warning 또는 error 로그를 host와 level별로 집계해줘",
        "최근 24시간 network_logs에서 host별 전체 사용량을 계산하고 asset_info와 host와 hostname 기준으로 left join해줘",
        "최근 24시간 db_logs에서 duration_ms가 1000 이상인 쿼리를 database별로 집계해줘",
    ],
    "Logpresso Store 스키마": [
        "최근 24시간 secui_events에서 블루맥스 NGF 웹 필터의 출발지 IP별 건수를 많은 순으로 10개 보여줘",
        "최근 24시간 secui_events에서 WAPPLES 침입탐지의 출발지 IP별 위험도 점수 평균을 보여줘",
        "최근 24시간 secui_events에서 QueryPie DAC SQL 감사의 사용자별 실행 시간 평균을 보여줘",
        "최근 24시간 secui_events에서 FortiGate Webfilter의 출발지 IP별 건수를 보여줘",
        "최근 1시간 secui_events에서 AhnLab TrusGuard IPS의 출발지 IP별 건수를 보여줘",
        "최근 24시간 secui_events에서 Genian EDR DNS 로그의 도메인별 건수를 보여줘",
        "최근 24시간 secui_events에서 Cisco Meraki IPS의 출발지 IP별 건수를 보여줘",
    ],
    "긴 복합 파이프라인": [
        "최근 24시간 firewall_logs에서 deny 로그를 src_ip별로 집계하고 10건 이상인 결과를 asset_info의 ip_address와 left join해줘",
        "최근 24시간 web_logs에서 5xx 오류를 service별로 집계하고 10건 이상이며 평균 response_time이 1000 이상인 결과를 보여줘",
        "최근 24시간 audit_logs에서 로그인 실패를 user별로 집계하고 5건 이상인 결과를 user_info와 left join해줘",
        "최근 5분 raw_security_logs의 message를 JSON으로 파싱하고 events를 펼쳐 severity가 8 이상인 결과를 high_risk_stream으로 전달해줘",
        "최근 24시간 app_logs, firewall_logs, web_logs에서 malware 또는 ransomware를 fulltext 검색하고 src_ip별로 3건 이상인 결과를 보여줘",
    ],
}


SAMPLE_TABLE_FIELDS: dict[str, list[str]] = {
    "app_logs": ["_time", "host", "service", "level", "message", "result", "error_code"],
    "web_logs": ["_time", "client_ip", "service", "method", "uri", "status", "response_time", "user_agent"],
    "firewall_logs": ["_time", "src_ip", "src_port", "dst_ip", "dst_port", "protocol", "action"],
    "audit_logs": ["_time", "user", "src_ip", "action", "result"],
    "network_logs": ["_time", "host", "user_id", "bytes", "bytes_in", "bytes_out"],
    "sys_cpu_logs": ["_time", "host", "kernel", "user", "total_cpu"],
    "asset_info": ["ip_address", "hostname", "department"],
    "user_info": ["user_id", "user_name", "department"],
    "login_logs": ["_time", "user_id", "src_ip", "result"],
    "file_access_logs": ["_time", "user_id", "file_path", "action"],
    "import_logs": ["_time", "message", "user_id", "bytes"],
    "event_logs": ["_time", "message", "events", "event_type"],
    "raw_web_logs": ["_time", "message", "service", "method", "uri", "status", "response_time"],
    "raw_security_logs": ["_time", "message", "events", "event_type", "src_ip", "dst_ip", "severity"],
    "db_logs": ["_time", "database", "duration_ms", "query"],
    "secui_events": [
        "_time", "hostname", "log_type", "src_ip", "src_port", "dst_ip", "dst_port", "action",
        "domain", "tunnel_id", "tx_bytes", "rx_bytes", "cpu_usage", "total_bytes", "user", "result",
    ],
    "insa": ["ip", "name", "department"],
}

SAMPLE_STREAM_FIELDS = {
    "firewall_stream": ["_time", "src_ip", "dst_ip", "action"],
    "security_stream": ["_time", "src_ip", "dst_ip", "severity", "event_type"],
    "high_risk_stream": ["_time", "src_ip", "dst_ip", "severity", "event_type"],
}

SAMPLE_LOGGER_FIELDS = {
    "application_logger": ["_time", "host", "service", "level", "message"],
}


def build_quick_test_preset(request: str) -> dict[str, Any]:
    tables = [name for name in SAMPLE_TABLE_FIELDS if name in request]
    streams = [name for name in SAMPLE_STREAM_FIELDS if name in request]
    loggers = [name for name in SAMPLE_LOGGER_FIELDS if name in request]
    fields: list[str] = []
    for source in tables:
        fields.extend(SAMPLE_TABLE_FIELDS[source])
    for source in streams:
        fields.extend(SAMPLE_STREAM_FIELDS[source])
    for source in loggers:
        fields.extend(SAMPLE_LOGGER_FIELDS[source])
    return {
        "request": request,
        "tables": tables,
        "streams": streams,
        "loggers": loggers,
        "fields": list(dict.fromkeys(fields)),
        "table_fields": {name: SAMPLE_TABLE_FIELDS[name] for name in tables},
        "stream_fields": {name: SAMPLE_STREAM_FIELDS[name] for name in streams},
        "logger_fields": {name: SAMPLE_LOGGER_FIELDS[name] for name in loggers},
    }


def quick_test_count() -> int:
    return sum(len(requests) for requests in QUICK_TEST_REQUESTS.values())
