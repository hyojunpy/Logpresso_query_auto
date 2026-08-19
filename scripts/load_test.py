from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean
from time import perf_counter
import json
from urllib.request import Request, urlopen


def request(url: str, timeout: float, payload: bytes | None = None) -> tuple[bool, float]:
    started = perf_counter()
    try:
        target = Request(url, data=payload, headers={"Content-Type": "application/json"}) if payload else url
        with urlopen(target, timeout=timeout) as response:
            body = response.read()
            valid = response.status == 200
            if payload:
                valid = valid and json.loads(body).get("status") in {"generated", "needs_clarification", "unsupported"}
            return valid, (perf_counter() - started) * 1000
    except Exception:
        return False, (perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="Privacy-safe concurrent health load test")
    parser.add_argument("--url", default="http://ui:8501/_stcore/health")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--generate", action="store_true", help="Exercise the query generation API instead of health only")
    args = parser.parse_args()
    payload = None
    if args.generate:
        if args.url == "http://ui:8501/_stcore/health":
            args.url = "http://api:8000/api/v1/query/generate"
        payload = json.dumps({
            "request": "최근 24시간 firewall_logs에서 src_ip별 차단 건수를 집계해줘",
            "context": {"known_tables": ["firewall_logs"], "known_fields": ["src_ip", "action", "_time"]},
        }, ensure_ascii=False).encode("utf-8")
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = [future.result() for future in as_completed([
            pool.submit(request, args.url, args.timeout, payload) for _ in range(args.requests)
        ])]
    passed = sum(ok for ok, _ in results)
    durations = sorted(duration for _, duration in results)
    p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))]
    print(f"requests={len(results)} passed={passed} failed={len(results)-passed} avg_ms={mean(durations):.1f} p95_ms={p95:.1f}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
