#!/usr/bin/env python3
"""RUM 일별 p50/p95 추세 리포트 + 회귀 판정 (P3 마지막 그물).

foms.services.rum_aggregate 가 Redis 에 쌓은 일별 고정버킷 히스토그램을 읽어
메트릭별 일자 표(p50/p95, 표본 수)를 출력하고, 최근 2일 p95 가 직전 5일 p95
중앙값 대비 +50% 이상이면 WARN 을 낸다.

의존: **REDIS_URL** (DB URL 아님). 운영 데이터는 Railway 내부 Redis 라서 로컬
직접 조회는 불가하다. 로컬 점검은 스테이징 REDIS 공개 프록시가 있을 때만:

    REDIS_URL="redis://<staging-proxy-host>:<port>" python tools/perf/rum_report.py

옵션:
    --days N     조회 일수(기본 7, 최소 7 권장: recent2+baseline5)
    --strict     회귀 감지 시 exit 1 (CI 게이트용). 기본은 exit 0(advisory).
    --json       JSON 출력.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foms.services.rum_aggregate import (  # noqa: E402
    ALLOWED_METRICS,
    build_rum_key,
    detect_regression,
    histogram_from_hash,
    percentile_from_histogram,
    recent_kst_dates,
)

RECENT_WINDOW: int = 2
BASELINE_WINDOW: int = 5


def _connect_redis() -> Any | None:
    """REDIS_URL 로 조회 전용 Redis 클라이언트 생성(실패 시 None)."""
    url = (os.environ.get("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        from redis import Redis

        client = Redis.from_url(
            url, decode_responses=True, socket_timeout=3, socket_connect_timeout=3
        )
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        print(f"[rum_report] Redis 연결 실패: {exc}", file=sys.stderr)
        return None


def _day_stats(client: Any, date_str: str, metric: str) -> dict[str, Any]:
    """하루치 히스토그램 → {samples, p50, p95}."""
    raw = client.hgetall(build_rum_key(date_str, metric))
    counts = histogram_from_hash(raw)
    return {
        "date": date_str,
        "samples": sum(counts),
        "p50": percentile_from_histogram(counts, 0.50),
        "p95": percentile_from_histogram(counts, 0.95),
    }


def collect(client: Any, days: int) -> dict[str, Any]:
    """메트릭별 최근 days 일 통계와 회귀 판정을 수집한다."""
    dates = recent_kst_dates(days)  # 최신 → 과거
    report: dict[str, Any] = {"days": days, "metrics": {}}
    for metric in sorted(ALLOWED_METRICS):
        daily = [_day_stats(client, d, metric) for d in dates]
        recent_p95 = [row["p95"] for row in daily[:RECENT_WINDOW]]
        baseline_p95 = [
            row["p95"] for row in daily[RECENT_WINDOW : RECENT_WINDOW + BASELINE_WINDOW]
        ]
        verdict = detect_regression(recent_p95, baseline_p95)
        report["metrics"][metric] = {
            "daily": daily,
            "regression": {
                "regressed": verdict.regressed,
                "recent_p95": verdict.recent_p95,
                "baseline_p95": verdict.baseline_p95,
                "ratio": verdict.ratio,
            },
        }
    return report


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:>7.0f}"


def print_report(report: dict[str, Any]) -> bool:
    """사람이 읽는 표 출력. 회귀 WARN 이 하나라도 있으면 True 반환."""
    any_regression = False
    for metric, block in report["metrics"].items():
        print(f"\n== {metric} (최근 {report['days']}일) ==")
        print(f"  {'date':<12} {'samples':>8} {'p50':>8} {'p95':>8}")
        for row in block["daily"]:
            print(
                f"  {row['date']:<12} {row['samples']:>8} "
                f"{_fmt(row['p50'])} {_fmt(row['p95'])}"
            )
        reg = block["regression"]
        if reg["regressed"] is None:
            print("  판정: 데이터 부족(skip)")
        elif reg["regressed"]:
            any_regression = True
            print(
                f"  판정: WARN 회귀 — recent p95 {reg['recent_p95']:.0f}ms "
                f"vs baseline 중앙값 {reg['baseline_p95']:.0f}ms "
                f"(x{reg['ratio']:.2f})"
            )
        else:
            ratio = reg["ratio"]
            ratio_s = f"x{ratio:.2f}" if ratio is not None else "-"
            print(f"  판정: OK ({ratio_s})")
    return any_regression


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RUM 일별 p95 추세 + 회귀 리포트")
    parser.add_argument("--days", type=int, default=7, help="조회 일수(기본 7)")
    parser.add_argument(
        "--strict", action="store_true", help="회귀 감지 시 exit 1(기본 exit 0)"
    )
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args(argv)

    days = max(RECENT_WINDOW + BASELINE_WINDOW, args.days)

    client = _connect_redis()
    if client is None:
        print(
            "[rum_report] REDIS_URL 미설정 또는 연결 불가 — 집계 조회 불가.\n"
            "  운영 데이터는 Railway 내부 Redis 이며 로컬 직접 조회 불가.\n"
            "  로컬은 스테이징 REDIS 공개 프록시가 있을 때만 REDIS_URL 로 실행.",
            file=sys.stderr,
        )
        return 0  # 조회 불가는 게이트 실패로 취급하지 않음(advisory).

    report = collect(client, days)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        any_regression = any(
            b["regression"]["regressed"] for b in report["metrics"].values()
        )
    else:
        any_regression = print_report(report)

    if any_regression and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
