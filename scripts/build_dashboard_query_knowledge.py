from __future__ import annotations

import json
from pathlib import Path

from scripts.append_dashboard_query_examples import EXAMPLES


ALIASES = {
    "라이선스 만료일": ["라이선스 만료", "라이센스 만료일", "license expiry"],
    "일 로그 수집 현황": ["일로그수집현황", "하루 로그 수집 현황", "일일 로그 수집량"],
    "라이선스 종류": ["라이센스 종류", "라이선스 유형", "license type"],
    "수집 속도": ["로그 수집 속도", "초당 수집 속도", "수집속도"],
    "라이선스 사용 추이": ["라이센스 사용 추이", "라이선스 사용량 추이"],
    "최근 한 달 라이선스 초과 사용일": ["최근 1달 라이선스 초과 사용일", "라이선스 초과 사용일", "계약 용량 초과일"],
    "최근 7일 라이선스 사용량 상위 수집기": ["최근 7일 라이선스 사용량 TOP7", "라이선스 사용량 상위 수집기", "수집기 사용량 TOP7"],
    "전일 수집기별 수집량": ["전일자 수집기 별 수집량", "어제 수집기별 수집량", "전일 로그 수집량"],
}


def main() -> None:
    items = [
        {"title": title, "aliases": ALIASES.get(title, []), "description": description, "query": query}
        for title, description, query in EXAMPLES
    ]
    output = Path("app") / "resources" / "dashboard_query_examples.json"
    output.write_text(json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
