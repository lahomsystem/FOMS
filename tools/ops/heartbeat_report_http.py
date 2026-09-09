#!/usr/bin/env python3
"""production 워커 하트비트 HTTP 조회 — 로그인 → ``/api/foms/ops/worker-heartbeats`` GET.

``worker-heartbeat-daily`` 워크플로 전용. 운영 DB DSN 은 GitHub 에 두지 않기로 했으므로
(등록된 비밀은 스테이징 로그인 2개뿐) admin 엔드포인트가 **유일한 외부 조회로**다.
:mod:`tools.ops.drift_report_http` 와 같은 모양이다.

**왜 매일 도는가**: :mod:`tools.ops.check_sidefx_readiness` 는 사람이 명령을 쳐야 판정한다.
2026-02 워커 offline·2026-08-31 SIDEFX 미배포는 두 번 다 사용자가 화면에서 먼저 발견했다.
재는 도구가 있어도 재는 사람이 없으면 없는 것과 같다.

**판정**: 엔드포인트의 `ready`(하트비트 유무·신선도·scan lag·큐 적체·DEAD 네 축)가 거짓이면
실패(exit 1). 옛 배포라 그 키가 없으면 `not_ready` 만으로 물러서고 그 사실을 요약에 적는다.
기준선 래칫이 아니라 절대 0 인 이유는,
하트비트가 낡았다는 것은 누적 부채가 아니라 **지금 루프가 멎었다는 뜻**이기 때문이다.
예산은 서버가 정한다 — 루프가 신고한 tick 간격 x 3 과 등록부 값 중 큰 쪽이라, 간격을 env 로
바꿔도 살아 있는 루프를 죽었다고 하지 않는다.

등록부에 없는 kind(`unknown_kinds`)도 실패로 본다 — 판정할 수 없는 신호를 초록으로 넘기면
"아무도 안 읽는" 상태로 되돌아간다.

크리덴셜은 env 로만 읽는다(argv 금지 — 셸 히스토리 유출 방지):
  FOMS_STAGING_USERNAME / FOMS_STAGING_PASSWORD (계정 재사용; ADMIN 이어야 200).

exit code:
  0 = 전부 신선,
  1 = not-ready 있음 또는 판정 불가 kind 있음,
  2 = 크리덴셜 부재,
  3 = 조회/네트워크 실패(거짓 초록 대신 시끄럽게 실패한다).

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
REPORT_PATH = "/api/foms/ops/worker-heartbeats"
#: 하트비트 표는 행이 열 개 남짓이라 조회가 가볍다. 그래도 서버가 죽기 전에 클라이언트가
#: 먼저 포기해 원인을 흐리는 일이 없게 gunicorn --timeout 120 보다 넉넉히 잡는다.
REQUEST_TIMEOUT = 150


def fetch_report(base: str, user: str, password: str) -> dict[str, Any]:
    """로그인 → 하트비트 조회 GET → ``data`` dict 반환(실패 시 예외).

    Args:
        base: 조회 origin.
        user: 로그인 아이디(ADMIN).
        password: 비밀번호.

    Returns:
        엔드포인트 응답의 ``data`` (kinds/not_ready/not_ready_count/unknown_kinds/elapsed_ms).

    Raises:
        requests.RequestException: 네트워크·HTTP 오류.
        RuntimeError: ``success`` 가 False 인 응답.
    """
    cookie, _ = fetch_session_cookie(base, user, password)
    session = requests.Session()
    session.headers["Cookie"] = cookie
    resp = session.get(base.rstrip("/") + REPORT_PATH, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"worker-heartbeats 실패: {body.get('error')}")
    return body["data"]


def render_summary(report: dict[str, Any]) -> str:
    """GitHub step summary 용 마크다운 표.

    Args:
        report: :func:`fetch_report` 결과.

    Returns:
        마크다운 문자열(표 + 판정 줄). 고객 정보는 원래 응답에 없다.
    """
    lines = ["", "## 워커 루프 하트비트", "",
             "| worker_kind | 나이(초) | 신고 간격 | 예산(초) | 필수 | 판정 |",
             "|---|---:|---:|---:|:--:|---|"]
    for kind, row in sorted(report.get("kinds", {}).items()):
        age = "-" if row["age_seconds"] is None else str(row["age_seconds"])
        interval = "-" if row.get("interval_seconds") is None else str(row["interval_seconds"])
        mark = "OK" if row["ready"] else f"**{row['reason'].upper()}**"
        lines.append(f"| `{kind}` | {age} | {interval} | {row['limit_seconds']} | "
                     f"{'Y' if row['required'] else '-'} | {mark} |")
    unknown = report.get("unknown_kinds") or []
    if unknown:
        lines += ["", f"판정 불가 kind: {', '.join('`%s`' % k for k in unknown)} "
                      "(등록부 `WORKER_KIND_SPECS` 에 없다)"]

    # 큐 축. 하트비트가 전부 신선해도 여기서 not-ready 가 날 수 있다 — 소비 프로세스는
    # 살아 있는데 잡이 밀리거나 DEAD 로 쌓이는 상태가 실재한다(운영 DEAD 1,344건).
    if "dead_count" in report or "oldest_pending_lag" in report:
        pending = report.get("oldest_pending_lag")
        lines += ["", f"큐: 가장 오래 밀린 잡 {'-' if pending is None else str(pending) + '초'} · "
                       f"DEAD {report.get('dead_count', 0)}건"]

    failures = report.get("failures") or []
    if failures:
        lines += ["", "실패 축:"]
        for fail in failures:
            kind = fail.get("kind")
            lines.append(f"- `{fail.get('check')}`" + (f" ({kind})" if kind else "")
                         + f" — 실측 {fail.get('detail')}"
                         + (f", 한도 {fail['limit']}" if 'limit' in fail else ''))

    # 판정값은 엔드포인트의 ``ready`` 다(네 축 전부). 옛 배포는 그 키가 없으므로
    # 하트비트 축만으로 물러서되, 그 사실을 요약에 적는다(조용한 반쪽 판정 금지).
    legacy = "ready" not in report
    ok = (not report.get("not_ready") and not unknown) if legacy else (
        bool(report.get("ready")) and not unknown)
    verdict = "전부 신선" if ok else "문제 있음"
    lines += ["", f"판정: **{verdict}** · 조회 {report.get('elapsed_ms', 0)}ms"]
    if legacy:
        lines += ["", "주의: 이 응답에는 큐 축이 없다(운영 미승격) — 하트비트 축만 판정했다."]
    lines += [""]
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    """CLI 인자 정의(크리덴셜 인자는 없다 — env only)."""
    parser = argparse.ArgumentParser(
        description="production 워커 하트비트 조회(멎은 루프가 있으면 exit 1)."
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("FOMS_HEARTBEAT_BASE_URL", DEFAULT_BASE).strip(),
        help=f"조회 origin (기본 {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--summary-file",
        default=os.environ.get("GITHUB_STEP_SUMMARY", ""),
        help="마크다운 표 append 대상(기본 $GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument("--json", action="store_true", help="기계 판독용 JSON 출력")
    return parser


def _append_summary(path: str, summary: str) -> None:
    """step summary 파일에 append(기록 실패는 경고만 — 판정을 막지 않는다)."""
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(summary)
    except OSError as exc:
        print(f"[warn] step summary 기록 실패: {exc}", file=sys.stderr)


def main() -> int:
    """엔트리포인트. 상단 docstring 의 exit code 규약을 그대로 돌려준다."""
    args = _build_parser().parse_args()

    user = os.environ.get("FOMS_STAGING_USERNAME", "").strip()
    password = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not password:
        print("ERROR: FOMS_STAGING_USERNAME/FOMS_STAGING_PASSWORD 미설정(env only).",
              file=sys.stderr)
        return 2

    try:
        report = fetch_report(args.base, user, password)
        summary = render_summary(report)
    except (requests.RequestException, RuntimeError, ValueError, TypeError, KeyError) as exc:
        print(f"ERROR: 하트비트 조회 실패 — {exc}", file=sys.stderr)
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else summary)
    _append_summary(args.summary_file, summary)

    unknown = report.get("unknown_kinds") or []
    not_ready = report.get("not_ready") or []
    if unknown:
        print(f"ERROR: 판정 불가 kind — {', '.join(unknown)} (등록부에 없다).", file=sys.stderr)
    for kind in not_ready:
        row = report["kinds"][kind]
        print(f"ERROR: {kind} 하트비트 {row['reason']} — 나이 {row['age_seconds']}초 "
              f"(예산 {row['limit_seconds']}초).", file=sys.stderr)
    for fail in report.get("failures") or []:
        if fail.get("check") in ("heartbeat_present", "heartbeat_fresh"):
            continue  # 위에서 kind 별로 이미 말했다
        print(f"ERROR: {fail.get('check')} — 실측 {fail.get('detail')}"
              + (f", 한도 {fail['limit']}" if 'limit' in fail else ''), file=sys.stderr)

    # ``ready`` 가 정본이다. 없으면(운영 미승격) 하트비트 축만으로 물러선다.
    if "ready" in report:
        return 0 if (report["ready"] and not unknown) else 1
    return 1 if (not_ready or unknown) else 0


if __name__ == "__main__":
    raise SystemExit(main())
