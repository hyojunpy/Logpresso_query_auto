from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean
from time import perf_counter
from urllib.request import urlopen


def request(url: str, timeout: float) -> tuple[bool, float]:
    started = perf_counter()
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.status == 200, (perf_counter() - started) * 1000
    except Exception:
        return False, (perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="Privacy-safe concurrent health load test")
    parser.add_argument("--url", default="http://ui:8501/_stcore/health")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = [future.result() for future in as_completed([
            pool.submit(request, args.url, args.timeout) for _ in range(args.requests)
        ])]
    passed = sum(ok for ok, _ in results)
    durations = sorted(duration for _, duration in results)
    p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))]
    print(f"requests={len(results)} passed={passed} failed={len(results)-passed} avg_ms={mean(durations):.1f} p95_ms={p95:.1f}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
