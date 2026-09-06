#!/usr/bin/env python3
"""production 드리프트 감사 HTTP 조회 — 로그인 → ``/api/foms/ops/drift-audit`` GET.

drift-audit-daily 워크플로 전용. 운영 DB DSN 은 GitHub 에 두지 않기로 했으므로(등록된
비밀은 스테이징 로그인 2개뿐) admin 엔드포인트가 **유일한 외부 조회로**다. GitHub step
summary($GITHUB_STEP_SUMMARY)에 감사별 건수·기준선 대비·표본 표를 마크다운으로 append 한다.

**판정은 기준선 래칫이다.** 절대 0건이 아니라 ``drift_baseline.json`` 대비 **순증**만
실패로 본다. 2026-09-07 운영 실측이 ERP flat 1,750건이라 절대 0건 기준으로 두면 게이트가
첫날부터 매일 빨간불이고, 매일 오는 빨간불은 곧 아무도 안 본다 — 관측 배선이 죽는 흔한
방식이다. 기준선을 얼려 두면 내일부터 쓸모 있는 신호가 되고, 줄어드는 숫자가 사본 규약을
기계로 바꾸는 작업(검토 보고서 ④ 이번 분기)의 진척 척도가 된다.

AS 축은 예외로 ``must_stay_zero`` 다 — 운영 659건 검사에서 이미 0이라 1건이라도 늘면 실패다.

크리덴셜은 env 로만 읽는다(argv 금지 — 셸 히스토리 유출 방지):
  FOMS_STAGING_USERNAME / FOMS_STAGING_PASSWORD (계정 재사용; ADMIN 이어야 200).

exit code:
  0 = 기준선 이하(순증 없음),
  1 = 순증(또는 응답이 ``truncated`` 라 판정을 신뢰할 수 없음),
  2 = 크리덴셜 부재,
  3 = 조회/네트워크 실패(요청 타임아웃 포함 — 거짓 초록 대신 시끄럽게 실패한다).

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
REPORT_PATH = "/api/foms/ops/drift-audit"
#: 기준선 래칫 정본. 이 파일과 나란히 산다(워크플로는 requests 만 설치하므로 json 만 읽는다).
BASELINE_PATH = Path(__file__).resolve().parent / "drift_baseline.json"
# 전 주문 스캔이라 응답이 길다. gunicorn --timeout 120 보다 넉넉히 잡아, 서버가 죽기 전에
# 클라이언트가 먼저 포기해 원인을 흐리는 일을 막는다.
REQUEST_TIMEOUT = 180


def fetch_report(base: str, user: str, password: str) -> dict[str, Any]:
    """로그인 → drift-audit GET → ``data`` dict 반환(실패 시 예외).

    Args:
        base: 조회 origin.
        user: 로그인 아이디(ADMIN).
        password: 비밀번호.

    Returns:
        엔드포인트 응답의 ``data`` (as_axis/erp_flat/drift_total/truncated/elapsed_ms).

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
        raise RuntimeError(f"drift-audit 실패: {body.get('error')}")
    return body["data"]


def _sample_lines(report: dict[str, Any]) -> list[str]:
    """드리프트 표본을 사람이 읽는 목록으로(주문 id·컬럼명·사유만)."""
    lines: list[str] = []
    as_samples = report["as_axis"].get("samples") or []
    if as_samples:
        lines.append("")
        lines.append("### AS 축 불일치 표본")
        for s in as_samples:
            lines.append(
                f"- #{s['order_id']} 컬럼={s['column']} 유도={s['derived']} status={s['status']}"
            )
    flat_samples = report["erp_flat"].get("samples") or []
    if flat_samples:
        lines.append("")
        lines.append("### ERP flat 드리프트 표본")
        for s in flat_samples:
            reason = f" 사유={s['reason']}" if s.get("reason") else ""
            lines.append(
                f"- #{s['order_id']} {s['classification']}"
                f" 컬럼={','.join(s['drift_columns']) or '-'}{reason}"
            )
    return lines


def load_baseline(path: Path | None = None) -> dict[str, Any]:
    """기준선 JSON 을 읽는다.

    Args:
        path: 기준선 파일 경로(기본 :data:`BASELINE_PATH`).

    Returns:
        기준선 dict.

    Raises:
        RuntimeError: 파일이 없거나 스키마가 다를 때. **기본값으로 폴백하지 않는다** —
            기준선이 사라졌는데 조용히 "0건 기준" 으로 돌면 게이트가 매일 빨간불이 되고,
            반대로 무한대로 폴백하면 게이트가 죽는다. 어느 쪽도 조용히 하면 안 된다.
    """
    target = path or BASELINE_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"기준선을 읽지 못했다({target}): {exc}") from exc
    if data.get("schema") != "drift-ratchet/1":
        raise RuntimeError(f"기준선 스키마가 다르다: {data.get('schema')!r}")
    return data


def compare_to_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """감사별 현재값을 기준선과 견준다(순증만 회귀).

    Args:
        report: :func:`fetch_report` 가 돌려준 ``data``.
        baseline: :func:`load_baseline` 결과.

    Returns:
        ``{'rows': [{key, label, current, baseline, delta, regressed}], 'regressed': bool}``.
        AS 축은 ``must_stay_zero`` 라 1건이라도 있으면 회귀다.
    """
    rows: list[dict[str, Any]] = []
    for key, label in (("as_axis", "AS 축 투영(as_axis_status)"), ("erp_flat", "ERP flat 컬럼")):
        current = int(report[key]["drift"])
        base_entry = baseline.get(key, {})
        base = int(base_entry.get("drift", 0))
        if base_entry.get("must_stay_zero"):
            regressed = current > 0
        else:
            regressed = current > base
        rows.append({
            "key": key, "label": label, "current": current, "baseline": base,
            "delta": current - base, "regressed": regressed,
        })
    return {
        "rows": rows,
        "regressed": any(r["regressed"] for r in rows),
        "measured_at": baseline.get("measured_at", "미상"),
    }


def render_summary(report: dict[str, Any], comparison: dict[str, Any]) -> str:
    """GitHub step summary 용 마크다운(감사 | 검사수 | 드리프트 | 기준선 | 증감 + 표본).

    Args:
        report: :func:`fetch_report` 가 돌려준 ``data``.
        comparison: :func:`compare_to_baseline` 결과.

    Returns:
        append 할 마크다운 문자열(마지막 개행 포함).
    """
    total = report["drift_total"]
    regressed = comparison["regressed"]
    verdict = "🔴 기준선 대비 순증" if regressed else "🟢 순증 없음"
    if report.get("truncated"):
        verdict = "🔴 응답 절단 — 판정 신뢰 불가"
    as_axis, flat = report["as_axis"], report["erp_flat"]
    by_key = {row["key"]: row for row in comparison["rows"]}

    def _delta(key: str) -> str:
        row = by_key[key]
        mark = "🔴 " if row["regressed"] else ""
        sign = "+" if row["delta"] > 0 else ""
        return f"{mark}{sign}{row['delta']}"

    lines = [
        "## 드리프트 감사 일일 리포트",
        "",
        f"**판정: {verdict}** (총 {total}건 / 소요 {report.get('elapsed_ms', 0)}ms / "
        f"절단 {report.get('truncated')})",
        "",
        "| 감사 | 검사 대상 | 드리프트 | 기준선 | 증감 | 상세 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
        f"| AS 축 투영(as_axis_status) | {as_axis['checked']} | {as_axis['drift']} | "
        f"{by_key['as_axis']['baseline']} | {_delta('as_axis')} | "
        f"투영 누락 {as_axis['missing_projection']} · legacy 전용 {as_axis['legacy_only']} |",
        f"| ERP flat 컬럼 | {flat['total']} | {flat['drift']} | "
        f"{by_key['erp_flat']['baseline']} | {_delta('erp_flat')} | "
        f"SAFE {flat['safe']} · AMBIGUOUS {flat['ambiguous']} · CLEAN {flat['clean']} |",
        "",
        f"기준선 정본 `tools/ops/drift_baseline.json` "
        f"(측정 {comparison.get('measured_at', '미상')}). "
        "숫자를 줄인 뒤에는 기준선도 같이 낮춘다 — 올리는 방향은 래칫을 푸는 것이라 사유가 필요하다.",
    ]
    reasons = flat.get("ambiguous_reasons") or {}
    if reasons:
        lines.append("")
        lines.append("AMBIGUOUS 사유: " + ", ".join(f"{k}={v}" for k, v in reasons.items()))
    lines.extend(_sample_lines(report))
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    """CLI 인자 정의(크리덴셜 인자는 없다 — env only)."""
    parser = argparse.ArgumentParser(
        description="production 드리프트 감사 2종 조회(드리프트 있으면 exit 1)."
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("FOMS_DRIFT_BASE_URL", DEFAULT_BASE).strip(),
        help="조회 origin(기본 production)",
    )
    parser.add_argument(
        "--summary-file",
        default=os.environ.get("GITHUB_STEP_SUMMARY", ""),
        help="마크다운 표 append 대상(기본 $GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument("--json", action="store_true", help="원본 JSON 출력")
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
        print(
            "ERROR: FOMS_STAGING_USERNAME/FOMS_STAGING_PASSWORD 미설정(env only).",
            file=sys.stderr,
        )
        return 2

    try:
        report = fetch_report(args.base, user, password)
        baseline = load_baseline()
        comparison = compare_to_baseline(report, baseline)
        summary = render_summary(report, comparison)
        truncated = bool(report.get("truncated"))
    except (requests.RequestException, RuntimeError, ValueError, TypeError, KeyError) as exc:
        print(f"ERROR: 드리프트 감사 조회 실패 — {exc}", file=sys.stderr)
        return 3

    payload = {"report": report, "comparison": comparison}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else summary)
    _append_summary(args.summary_file, summary)

    if truncated:
        print("ERROR: 응답이 절단됐다 — 판정을 신뢰할 수 없다.", file=sys.stderr)
        return 1
    if comparison["regressed"]:
        for row in comparison["rows"]:
            if row["regressed"]:
                print(
                    f"ERROR: {row['label']} 드리프트가 기준선을 넘었다 — "
                    f"{row['baseline']} → {row['current']} (+{row['delta']}).",
                    file=sys.stderr,
                )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
