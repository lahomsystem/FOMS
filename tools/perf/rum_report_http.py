#!/usr/bin/env python3
"""production RUM 리포트 HTTP 조회 — 로그인 → ``/api/foms/rum/report`` GET.

rum-daily 워크플로 전용. 운영 Redis 는 앱 내부에서만 접근되므로 admin 엔드포인트가
유일한 외부 조회로다. ``regressed=true`` 면 exit 1(job fail = GitHub 알림). GitHub
step summary($GITHUB_STEP_SUMMARY)에 메트릭별 p95·판정 표를 마크다운으로 append 한다.

크리덴셜은 env 로만 읽는다(argv 금지 — 셸 히스토리 유출 방지):
  FOMS_STAGING_USERNAME / FOMS_STAGING_PASSWORD (계정 재사용; ADMIN 이어야 200).

exit code:
  0 = 정상, 1 = 회귀 감지, 2 = 크리덴셜 부재, 3 = 조회/네트워크 실패.

의존: requests 만(앱/DB import 없음 — CI 설치 최소).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.harness.ept_b8_staging_session_from_login import fetch_session_cookie  # noqa: E402

DEFAULT_BASE = "https://lahom-production.up.railway.app"


def fetch_report(base: str, user: str, password: str, days: int) -> dict[str, Any]:
    """로그인 → report GET → data dict 반환(실패 시 예외)."""
    cookie, _ = fetch_session_cookie(base, user, password)
    session = requests.Session()
    session.headers["Cookie"] = cookie
    resp = session.get(
        base.rstrip("/") + "/api/foms/rum/report",
        params={"days": days},
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"report 실패: {body.get('error')}")
    return body["data"]


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.0f}"


def render_summary(report: dict[str, Any]) -> str:
    """GitHub step summary 용 마크다운 표(메트릭 | p95 | samples | ratio | 판정)."""
    verdict = "🔴 회귀 감지" if report.get("regressed") else "🟢 정상"
    lines = [
        f"## RUM 일일 리포트 (최근 {report['days']}일)",
        "",
        f"**판정: {verdict}**",
        "",
        "| metric | recent p95 (ms) | baseline p95 (ms) | recent n | baseline n | ratio | 판정 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for block in report["metrics"]:
        reg = block["regression"]
        ratio = reg["ratio"]
        ratio_s = "-" if ratio is None else f"x{ratio:.2f}"
        if reg["regressed"] is None:
            state = "skip"
        elif reg["regressed"] and reg.get("sample_shift"):
            state = "⚠️ 표본이동"
        elif reg["regressed"]:
            state = "WARN"
        else:
            state = "OK"
        lines.append(
            f"| {block['metric']} | {_fmt(reg['recent_p95'])} | "
            f"{_fmt(reg['baseline_p95'])} | "
            f"{reg.get('recent_samples', 0)} | {reg.get('baseline_samples', 0)} | "
            f"{ratio_s} | {state} |"
        )
    # 일별 표본(오탐 판독용) — 메트릭당 한 줄.
    lines.append("")
    lines.append("### 일별 samples (최신→과거)")
    for block in report["metrics"]:
        parts = [f"{row['date']}={row['samples']}" for row in block.get("daily", [])]
        lines.append(f"- {block['metric']}: " + ", ".join(parts))
    if report.get("warnings"):
        lines.append("")
        lines.append("### 경고")
        lines.extend(f"- {w}" for w in report["warnings"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="production RUM 리포트 조회(회귀 시 exit 1)."
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("FOMS_RUM_BASE_URL", DEFAULT_BASE).strip(),
        help="조회 origin(기본 production)",
    )
    parser.add_argument("--days", type=int, default=7, help="조회 일수(기본 7)")
    parser.add_argument(
        "--summary-file",
        default=os.environ.get("GITHUB_STEP_SUMMARY", ""),
        help="마크다운 표 append 대상(기본 $GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument("--json", action="store_true", help="원본 JSON 출력")
    args = parser.parse_args()

    user = os.environ.get("FOMS_STAGING_USERNAME", "").strip()
    password = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not password:
        print(
            "ERROR: FOMS_STAGING_USERNAME/FOMS_STAGING_PASSWORD 미설정(env only).",
            file=sys.stderr,
        )
        return 2

    try:
        report = fetch_report(args.base, user, password, args.days)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"ERROR: 리포트 조회 실패 — {exc}", file=sys.stderr)
        return 3

    summary = render_summary(report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(summary)

    if args.summary_file:
        try:
            with open(args.summary_file, "a", encoding="utf-8") as fh:
                fh.write(summary)
        except OSError as exc:  # step summary 기록 실패가 판정을 막지 않도록.
            print(f"[warn] step summary 기록 실패: {exc}", file=sys.stderr)

    return 1 if report.get("regressed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
