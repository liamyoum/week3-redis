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
    # 발표나 README 표에 바로 쓰기 좋도록 결과를 하나의 구조로 묶는다.
    label: str
    requests: int
    total_ms: float
    average_ms: float
    hit_ratio: float | None = None


def request_json(url: str) -> object:
    # 외부 라이브러리 의존성을 늘리지 않기 위해
    # 표준 라이브러리 HTTP 클라이언트만 사용해서 JSON 응답을 가져온다.
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def time_requests(url: str, repeats: int) -> list[float]:
    durations: list[float] = []
    for _ in range(repeats):
        # 각 요청의 시작/종료 시간을 재서 엔드투엔드 지연 시간을 ms 단위로 기록한다.
        # 이후 uncached와 cached의 평균 응답 시간을 비교하는 데 사용한다.
        started = time.perf_counter()
        request_json(url)
        durations.append((time.perf_counter() - started) * 1000)
    return durations


def summarize(
    label: str,
    durations: list[float],
    hit_ratio: float | None = None,
) -> BenchmarkResult:
    # 여러 요청의 개별 지연 시간을 합계/평균 중심 결과로 요약한다.
    return BenchmarkResult(
        label=label,
        requests=len(durations),
        total_ms=sum(durations),
        average_ms=statistics.fmean(durations),
        hit_ratio=hit_ratio,
    )


def render_markdown(results: list[BenchmarkResult]) -> str:
    # README와 발표 자료에 바로 붙여넣기 쉬운 markdown 표 형태로 결과를 만든다.
    # 벤치 스크립트를 돌린 뒤 결과 정리에 드는 수작업을 줄이기 위한 함수다.
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
    # base URL과 path를 안전하게 합쳐 benchmark 대상 URL을 만든다.
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def parse_args() -> argparse.Namespace:
    # 실행 환경에 맞게 대상 서버, 요청 횟수, item_id, 결과 파일 경로를 조정할 수 있다.
    parser = argparse.ArgumentParser(
        description="Benchmark uncached vs cached local demo endpoints.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument(
        "--scenario",
        choices=["storefront", "demo"],
        default="storefront",
    )
    parser.add_argument("--item-id", default=f"bench-{int(time.time())}")
    parser.add_argument("--product-id", default="sunset-lamp")
    parser.add_argument(
        "--report-path",
        default="",
        help="Optional markdown file path for saving the benchmark table.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.scenario == "demo":
        upstream_url = build_url(args.base_url, f"/demo/upstream/{args.item_id}")
        cached_url = build_url(args.base_url, f"/demo/cached/{args.item_id}")
        uncached_label = "Uncached upstream"
        cached_label = "Cached demo"
    else:
        upstream_url = build_url(args.base_url, f"/store/products/{args.product_id}/direct")
        cached_url = build_url(args.base_url, f"/store/products/{args.product_id}/cached")
        uncached_label = "Storefront direct"
        cached_label = "Storefront cached"

    try:
        # 같은 item_id를 반복 호출해서 첫 요청 miss 이후 cached endpoint에서
        # hit가 누적되는 상황을 의도적으로 만든다.
        uncached = time_requests(upstream_url, args.requests)
        cached = time_requests(cached_url, args.requests)
    except urllib.error.URLError as exc:
        print(f"Benchmark failed: {exc}")
        return 1

    # 새로운 item_id 기준으로는 첫 cached 요청만 miss이고
    # 나머지는 hit라고 가정해 단순 hit ratio를 계산한다.
    cached_hit_ratio = 0.0 if args.requests == 0 else max(args.requests - 1, 0) / args.requests
    results = [
        summarize(uncached_label, uncached),
        summarize(cached_label, cached, hit_ratio=cached_hit_ratio),
    ]
    table = render_markdown(results)
    print(table)
    print()
    # 이 벤치는 같은 item_id를 반복 호출한다는 전제를 함께 출력해
    # 결과 해석 시 오해가 없도록 한다.
    print(
        "Assumption: the first cached request is a miss and the remaining "
        "requests are hits for the same item_id."
    )

    if args.report_path:
        report_path = Path(args.report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        # 선택적으로 markdown 파일까지 저장해 발표 자료나 README에 바로 활용할 수 있다.
        report_path.write_text(table + "\n", encoding="utf-8")
        print(f"Saved report to {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
