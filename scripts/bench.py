from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class BenchmarkResult:
    label: str
    requests: int
    total_ms: float
    average_ms: float
    hit_ratio: float | None = None


def request_json(url: str) -> object:
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def time_requests(url: str, repeats: int) -> list[float]:
    durations: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        request_json(url)
        durations.append((time.perf_counter() - started) * 1000)
    return durations


def summarize(label: str, durations: list[float], hit_ratio: float | None = None) -> BenchmarkResult:
    return BenchmarkResult(
        label=label,
        requests=len(durations),
        total_ms=sum(durations),
        average_ms=statistics.fmean(durations),
        hit_ratio=hit_ratio,
    )


def render_markdown(results: list[BenchmarkResult]) -> str:
    lines = [
        "| Scenario | Requests | Total (ms) | Avg (ms) | Hit Ratio |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        hit_ratio = "-" if result.hit_ratio is None else f"{result.hit_ratio:.2%}"
        lines.append(
            f"| {result.label} | {result.requests} | {result.total_ms:.2f} | "
            f"{result.average_ms:.2f} | {hit_ratio} |"
        )
    return "\n".join(lines)


def build_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark uncached vs cached local demo endpoints.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--item-id", default=f"bench-{int(time.time())}")
    parser.add_argument(
        "--report-path",
        default="",
        help="Optional markdown file path for saving the benchmark table.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    upstream_url = build_url(args.base_url, f"/demo/upstream/{args.item_id}")
    cached_url = build_url(args.base_url, f"/demo/cached/{args.item_id}")

    try:
        uncached = time_requests(upstream_url, args.requests)
        cached = time_requests(cached_url, args.requests)
    except urllib.error.URLError as exc:
        print(f"Benchmark failed: {exc}")
        return 1

    cached_hit_ratio = 0.0 if args.requests == 0 else max(args.requests - 1, 0) / args.requests
    results = [
        summarize("Uncached upstream", uncached),
        summarize("Cached demo", cached, hit_ratio=cached_hit_ratio),
    ]
    table = render_markdown(results)
    print(table)
    print()
    print(
        "Assumption: the first cached request is a miss and the remaining "
        "requests are hits for the same item_id."
    )

    if args.report_path:
        report_path = Path(args.report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(table + "\n", encoding="utf-8")
        print(f"Saved report to {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
