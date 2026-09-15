from __future__ import annotations

import re
from typing import Iterable


TOKEN_LABELS = {
    "account": "계정", "action": "동작", "admin": "관리자", "agent": "에이전트",
    "alert": "경보", "allow": "허용", "app": "애플리케이션", "application": "애플리케이션",
    "attack": "공격", "auth": "인증", "avg": "평균", "backup": "백업",
    "block": "차단", "bps": "초당 비트", "bytes": "바이트", "category": "분류",
    "cert": "인증서", "client": "클라이언트", "code": "코드", "command": "명령",
    "count": "건수", "country": "국가", "cpu": "CPU", "date": "날짜",
    "db": "데이터베이스", "department": "부서", "dept": "부서", "description": "설명",
    "detect": "탐지", "device": "장비", "direction": "방향", "disk": "디스크",
    "dns": "DNS", "domain": "도메인", "dst": "목적지", "duration": "지속 시간",
    "email": "이메일", "end": "종료", "error": "오류", "event": "이벤트",
    "file": "파일", "from": "발신", "group": "그룹", "hash": "해시",
    "host": "호스트", "hostname": "호스트명", "http": "HTTP", "id": "ID",
    "iface": "인터페이스", "in": "수신", "index": "인덱스", "ip": "IP",
    "level": "등급", "local": "로컬", "log": "로그", "mac": "MAC 주소",
    "mail": "메일", "max": "최대", "md5": "MD5", "mem": "메모리",
    "message": "메시지", "method": "방식", "min": "최소", "module": "모듈",
    "name": "이름", "nat": "NAT", "network": "네트워크", "object": "객체",
    "out": "송신", "packet": "패킷", "path": "경로", "payload": "페이로드",
    "pid": "프로세스 ID", "pkts": "패킷 수", "policy": "정책", "port": "포트",
    "pps": "초당 패킷", "process": "프로세스", "profile": "프로파일",
    "protocol": "프로토콜", "query": "쿼리", "reason": "사유", "remote": "원격",
    "request": "요청", "response": "응답", "result": "결과", "risk": "위험도",
    "role": "역할", "rule": "규칙", "rx": "수신", "sent": "송신",
    "server": "서버", "service": "서비스", "session": "세션", "severity": "심각도",
    "sid": "세션 ID", "signature": "시그니처", "size": "크기", "source": "출발지",
    "sql": "SQL", "src": "출발지", "start": "시작", "status": "상태",
    "subject": "제목", "success": "성공", "time": "시간", "timeout": "시간 초과",
    "to": "수신", "total": "전체", "traffic": "트래픽", "tx": "송신",
    "type": "유형", "uri": "URI", "url": "URL", "user": "사용자",
    "username": "사용자명", "uuid": "UUID", "value": "값", "ver": "버전",
    "version": "버전", "virtual": "가상", "vlan": "VLAN", "vpn": "VPN",
    "web": "웹", "zone": "영역", "flag": "구분값", "seq": "순번",
}

EXACT_LABELS = {
    "_time": "시각", "src_ip": "출발지 IP", "dst_ip": "목적지 IP",
    "src_port": "출발지 포트", "dst_port": "목적지 포트", "src_mac": "출발지 MAC 주소",
    "dst_mac": "목적지 MAC 주소", "event_time": "이벤트 시간", "start_time": "시작 시간",
    "end_time": "종료 시간", "log_type": "로그 유형", "packet_direction": "패킷 방향",
    "device_name": "장비명", "device_id": "장비 ID", "device_ip": "장비 IP",
    "host_ip": "호스트 IP", "user_name": "사용자명", "user_id": "사용자 ID",
    "session_id": "세션 ID", "event_id": "이벤트 ID", "event_type": "이벤트 유형",
    "event_count": "이벤트 건수", "file_name": "파일명", "file_size": "파일 크기",
    "dept_name": "부서명", "module_flag": "모듈 구분값", "ip_ver": "IP 버전",
    "src_country": "출발지 국가", "dst_country": "목적지 국가",
    "src_zone": "출발지 영역", "dst_zone": "목적지 영역",
    "src_iface": "출발지 인터페이스", "dst_iface": "목적지 인터페이스",
    "nat_src_ip": "NAT 출발지 IP", "nat_dst_ip": "NAT 목적지 IP",
    "nat_src_port": "NAT 출발지 포트", "nat_dst_port": "NAT 목적지 포트",
    "risk_score": "위험도 점수", "rule_id": "규칙 ID", "profile_id": "프로파일 ID",
}


def field_tokens(name: str) -> list[str]:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower().strip("_")
    return [token for token in re.split(r"[_\-.]+", normalized) if token]


def derived_display_name(name: str) -> str:
    if name in EXACT_LABELS:
        return EXACT_LABELS[name]
    tokens = field_tokens(name)
    if not tokens:
        return name
    labels = [TOKEN_LABELS.get(token, token.upper() if len(token) <= 4 else token) for token in tokens]
    return " ".join(labels)


def enrich_field_metadata(
    name: str,
    display_name: str = "",
    aliases: Iterable[str] = (),
    canonical_display: str = "",
    canonical_aliases: Iterable[str] = (),
) -> tuple[str, list[str]]:
    display = display_name.strip() or canonical_display.strip() or derived_display_name(name)
    values = {str(alias).strip() for alias in [*aliases, *canonical_aliases] if str(alias).strip()}
    values.update({display, re.sub(r"\s+", "", display)})
    spaced_name = " ".join(field_tokens(name))
    if spaced_name and spaced_name != name:
        values.add(spaced_name)
    values.discard(name)
    values = {value for value in values if len(value) >= 2}
    if not values:
        values.add(f"{display} 필드")
    return display, sorted(values, key=lambda value: (-len(value), value))


def enrich_payload(payload: dict) -> dict:
    fields = [
        field
        for product in payload.get("products", [])
        for schema in product.get("schemas", [])
        for field in schema.get("fields", [])
    ]
    canonical: dict[str, tuple[str, set[str]]] = {}
    for field in fields:
        name = str(field.get("name", ""))
        display, aliases = canonical.setdefault(name, ("", set()))
        if not display and field.get("display_name"):
            display = str(field["display_name"]).strip()
        aliases.update(str(alias) for alias in field.get("aliases", []) if alias)
        canonical[name] = (display, aliases)
    for field in fields:
        name = str(field.get("name", ""))
        display, aliases = canonical.get(name, ("", set()))
        field["display_name"], field["aliases"] = enrich_field_metadata(
            name,
            str(field.get("display_name", "")),
            field.get("aliases", []),
            display,
            aliases,
        )
    return payload
