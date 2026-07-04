#!/usr/bin/env python3
"""P1 — 스테이징 성능 게이트 봇 (배포 후 검증 / production 승격 전 필수).

취지: "커밋→푸쉬→사용자가 느려짐 발견→분석→패치" 악순환에서 발견 주체를
사용자 → 봇으로 옮긴다. 배포된 스테이징(lahom-dev)에 로그인 → 9개 primary
fragment 경로를 반복 측정 → 커밋된 예산(``perf_budgets.json``)과 비교해 초과 시
exit 1 로 승격을 차단한다.

판정 철학 (절대 준수):
  - pass/fail 은 **warm 중앙값(median) TTFB** 와 **바이트(해압 후)** 만으로 한다.
  - p95/최댓값은 **판정에 절대 넣지 않는다**. 한국↔싱가포르 네트워크 tail(2~9s)이
    정상적으로 존재하므로, tail 을 게이트에 넣으면 상습 오탐 → 신뢰 상실 → 게이트가
    꺼진다. p95 는 리포트에 정보로만 싣는다.

exit code:
  0 = PASS, 1 = FAIL(예산 초과), 2 = 크리덴셜 부재/로그인 실패(게이트 SKIP ≠ 실패).

크리덴셜은 환경변수로만 읽는다(argv 금지 — 셸 히스토리 유출 방지):
  FOMS_STAGING_USERNAME / FOMS_STAGING_PASSWORD, base 는 --base(기본 lahom-dev).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# SSOT: 9 primary 경로는 foms.services.common.erp_navigation_contract 에서 읽는다.
# (static/js/runtime/erp-shell.js PRIMARY_NAV_PATHS 와 동일 잠금판; 서버 계약과 byte-match)
from foms.services.common.erp_navigation_contract import ERP_PRIMARY_NAV_PATHS
from tools.harness.ept_b8_staging_session_from_login import fetch_session_cookie

DEFAULT_BASE = "https://lahom-dev.up.railway.app"
BUDGETS_PATH = ROOT / "tools" / "perf" / "perf_budgets.json"
EVIDENCE_DIR = ROOT / "docs" / "harness" / "evidence"
KST = timezone(timedelta(hours=9))

ROUNDS = 7  # 판정: 첫 회 웜업 버림 → warm 표본 6 (tail 1-2발 뭉침에도 median 방어)
# 시드는 예산의 SSOT라 median 이 tail 에 오염되면 예산이 상습적으로 헐거워진다.
# 표본을 늘려 median 이 tail(2~9s) 스파이크에 흔들리지 않게 한다(시드는 드물어 비용 무방).
SEED_ROUNDS = 13  # 첫 회 버림 → warm 표본 12(median 이 최대 5개 tail 오염에도 견딤)
SLEEP_S = 0.3
SEED_MARGIN = 0.30  # 실측 + 30% 여유

# fragment GET 공통 헤더 (shell 요청 계약).
FRAGMENT_HEADERS = {
    "X-FOMS-ERP-SHELL": "1",
    "Accept": "text/html",
    # 실브라우저 경로(Flask-Compress 재평가 + suffix etag)를 재현하려 압축 협상 유지.
    "Accept-Encoding": "gzip, br",
}


def fragment_path(primary_path: str) -> str:
    """primary 경로 → shell fragment GET 경로(``?view=fragment``)."""
    return f"{primary_path.rstrip('/')}?view=fragment"


FRAGMENT_PATHS: tuple[str, ...] = tuple(fragment_path(p) for p in ERP_PRIMARY_NAV_PATHS)


# ---------------------------------------------------------------------------
# 순수 판정 로직 (네트워크 없이 단위 테스트 가능) — tail 내성 계약의 심장
# ---------------------------------------------------------------------------
def percentile(values: list[float], pct: float) -> float:
    """정렬 표본의 근사 백분위수(pct 0~100). 정보용(판정 미사용)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * len(ordered))) - 1))
    return float(ordered[idx])


def summarize_samples(warm_samples: list[dict[str, Any]]) -> dict[str, Any]:
    """warm 표본(첫 회 제외 후) → median/p95 TTFB·median bytes·render/etag 요약.

    Args:
        warm_samples: 각 원소는 ``ttfb_ms``·``bytes``·``render_ms``(None 가능)·
            ``etag_present``(bool)·``content_encoding``(str|None) 키를 갖는다.

    Returns:
        판정·리포트에 쓰는 요약 dict. median 만 판정에, p95 는 정보로만.
    """
    ttfbs = [float(s["ttfb_ms"]) for s in warm_samples]
    byts = [int(s["bytes"]) for s in warm_samples]
    renders = [float(s["render_ms"]) for s in warm_samples if s.get("render_ms") is not None]
    return {
        "median_ttfb_ms": int(statistics.median(ttfbs)) if ttfbs else 0,
        "p95_ttfb_ms": int(percentile(ttfbs, 95)) if ttfbs else 0,
        "max_ttfb_ms": int(max(ttfbs)) if ttfbs else 0,
        "median_bytes": int(statistics.median(byts)) if byts else 0,
        "max_render_ms": int(max(renders)) if renders else None,
        "etag_present_all": bool(warm_samples) and all(s.get("etag_present") for s in warm_samples),
        "content_encoding": next((s.get("content_encoding") for s in warm_samples), None),
        "warm_count": len(warm_samples),
        # 판정 자격 검사용(judge_path) — warm 표본 전부 200 이어야 유효 측정.
        # status 미기록 표본(구버전/단위테스트 픽스처)은 자격 검사에서 제외(관용).
        "statuses": [int(s["status"]) for s in warm_samples if s.get("status") is not None],
    }


def judge_path(
    path: str,
    summary: dict[str, Any],
    cond_304_ok: bool,
    budget: dict[str, Any],
    global_budget: dict[str, Any],
) -> dict[str, Any]:
    """단일 경로 판정 — **median TTFB·bytes 만** 예산과 비교(p95 는 정보용).

    Args:
        summary: ``summarize_samples`` 결과.
        cond_304_ok: 조건부 If-None-Match 가 304 로 접혔는지.
        budget: 경로별 예산 ``{ttfb_warm_median_ms, body_bytes_max}``.
        global_budget: 전역 예산(render_ms_max·etag_required·conditional_304_required).

    Returns:
        판정 row(``passed`` bool + ``reasons`` 목록 + 측정/예산 값).
    """
    reasons: list[str] = []
    # 1:1 리뷰 MAJOR: status 미검사 시 302(세션만료)/500 이 bytes·ttfb 만으로
    # false-PASS 될 수 있다 — warm 표본 전부 200 이어야 판정 자격.
    bad = [s for s in (summary.get("statuses") or []) if s != 200]
    if bad:
        reasons.append(f"non-200 응답 {bad} (세션만료/서버오류 — 측정 무효)")
    ttfb_budget = budget.get("ttfb_warm_median_ms")
    bytes_budget = budget.get("body_bytes_max")

    if ttfb_budget is not None and summary["median_ttfb_ms"] > ttfb_budget:
        reasons.append(f"TTFB median {summary['median_ttfb_ms']}ms > budget {ttfb_budget}ms")
    if bytes_budget is not None and summary["median_bytes"] > bytes_budget:
        reasons.append(f"bytes {summary['median_bytes']} > budget {bytes_budget}")

    render_max = global_budget.get("render_ms_max")
    if render_max is not None and summary["max_render_ms"] is not None:
        if summary["max_render_ms"] > render_max:
            reasons.append(f"render {summary['max_render_ms']}ms > budget {render_max}ms")
    if global_budget.get("etag_required") and not summary["etag_present_all"]:
        reasons.append("ETag 누락(revalidation 계약 위반)")
    if global_budget.get("conditional_304_required") and not cond_304_ok:
        reasons.append("조건부 304 실패(하트비트 경제성 회귀)")

    return {
        "path": path,
        "median_ttfb_ms": summary["median_ttfb_ms"],
        "budget_ttfb_ms": ttfb_budget,
        "p95_ttfb_ms": summary["p95_ttfb_ms"],
        "median_bytes": summary["median_bytes"],
        "budget_bytes": bytes_budget,
        "cond_304": cond_304_ok,
        "passed": not reasons,
        "reasons": reasons,
    }


def seed_budget(summary: dict[str, Any], margin: float = SEED_MARGIN) -> dict[str, int]:
    """실측 요약 → 경로별 예산(median + margin). ``--seed`` 모드에서만 사용."""
    return {
        "ttfb_warm_median_ms": int(round(summary["median_ttfb_ms"] * (1 + margin))),
        "body_bytes_max": int(round(summary["median_bytes"] * (1 + margin))),
    }


# ---------------------------------------------------------------------------
# 측정 (네트워크) — 재시도 포함
# ---------------------------------------------------------------------------
def _get_with_retry(session: requests.Session, url: str, headers: dict[str, str]) -> requests.Response:
    """fragment GET — 네트워크 예외/5xx 1회 재시도."""
    for attempt in range(2):
        try:
            resp = session.get(url, headers=headers, timeout=120)
            if resp.status_code >= 500 and attempt == 0:
                time.sleep(0.5)
                continue
            return resp
        except requests.RequestException:
            if attempt == 0:
                time.sleep(0.5)
                continue
            raise
    return resp  # pragma: no cover


def measure_path(session: requests.Session, base: str, path: str, rounds: int = ROUNDS) -> dict[str, Any]:
    """한 경로를 rounds 회 측정(첫 회 웜업 버림) + 조건부 304 계약 확인."""
    url = base.rstrip("/") + path
    samples: list[dict[str, Any]] = []
    for i in range(rounds):
        t0 = time.perf_counter()
        resp = _get_with_retry(session, url, FRAGMENT_HEADERS)
        t_headers = time.perf_counter()
        body = resp.content  # requests 자동 해압 → len 은 해압 후 바이트(wire 아님)
        t_total = time.perf_counter()
        render = resp.headers.get("X-FOMS-EPT-B7-RENDER-MS")
        samples.append({
            "round": i + 1,
            "status": resp.status_code,
            "ttfb_ms": round((t_headers - t0) * 1000),
            "total_ms": round((t_total - t0) * 1000),
            "bytes": len(body),
            "render_ms": float(render) if render not in (None, "") else None,
            "content_encoding": resp.headers.get("Content-Encoding"),
            "etag_present": bool(resp.headers.get("ETag")),
        })
        time.sleep(SLEEP_S)
    warm = samples[1:] if len(samples) > 1 else samples
    cond_304_ok = _check_conditional_304(session, url)
    return {"path": path, "samples": samples, "warm": warm, "cond_304_ok": cond_304_ok}


def _check_conditional_304(session: requests.Session, url: str) -> bool:
    """1회 ETag 에코(If-None-Match) → 304 여부(하트비트 경제성 회귀 감시)."""
    warm_resp = _get_with_retry(session, url, FRAGMENT_HEADERS)
    etag = warm_resp.headers.get("ETag")
    if not etag:
        return False
    headers = dict(FRAGMENT_HEADERS)
    headers["If-None-Match"] = etag
    cond = _get_with_retry(session, url, headers)
    return cond.status_code == 304


# ---------------------------------------------------------------------------
# 오케스트레이션
# ---------------------------------------------------------------------------
def run_gate(base: str, user: str, password: str, budgets: dict[str, Any]) -> dict[str, Any]:
    """로그인 → 9경로 측정 → 판정. 측정+판정 결과 dict 반환(exit code 는 caller)."""
    cookie, _ = fetch_session_cookie(base, user, password)
    session = requests.Session()
    session.headers["Cookie"] = cookie
    global_budget = budgets.get("_global", {})
    path_budgets = budgets.get("paths", {})

    rows: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    for path in FRAGMENT_PATHS:
        measured = measure_path(session, base, path)
        raw.append(measured)
        summary = summarize_samples(measured["warm"])
        row = judge_path(path, summary, measured["cond_304_ok"], path_budgets.get(path, {}), global_budget)
        # tail-cluster 오탐 방어: TTFB "만" 위반이면 1회 재측정 후 재판정.
        # (한국↔SG tail 이 4표본 창에 뭉치면 median 도 오염 — 진짜 회귀는 재측정에서도
        # 재현되고, tail 뭉침은 연속 재현이 드물다. bytes/ETag/304 위반은 결정적이라 재측정 없음.)
        ttfb_only = row["reasons"] and all("TTFB" in r for r in row["reasons"])
        if not row["passed"] and ttfb_only:
            time.sleep(2.0)
            remeasured = measure_path(session, base, path)
            resummary = summarize_samples(remeasured["warm"])
            if resummary["median_ttfb_ms"] < summary["median_ttfb_ms"]:
                raw.append(remeasured)
                summary = resummary
                row = judge_path(path, summary, remeasured["cond_304_ok"], path_budgets.get(path, {}), global_budget)
                row["retried"] = True
        row["_summary"] = summary
        rows.append(row)

    ok = all(r["passed"] for r in rows)
    return {"base": base, "ok": ok, "rows": rows, "raw": raw}


def run_seed(base: str, user: str, password: str, prev: dict[str, Any]) -> dict[str, Any]:
    """--seed: 현 측정값 + 30% 마진으로 budgets 갱신(전역 예산은 보존/기본값)."""
    cookie, _ = fetch_session_cookie(base, user, password)
    session = requests.Session()
    session.headers["Cookie"] = cookie
    paths: dict[str, Any] = {}
    prev_paths = prev.get("paths", {})
    loosened: list[str] = []
    for path in FRAGMENT_PATHS:
        measured = measure_path(session, base, path, rounds=SEED_ROUNDS)
        summary = summarize_samples(measured["warm"])
        new_budget = seed_budget(summary)
        old_budget = prev_paths.get(path) or {}
        for k in ("ttfb_warm_median_ms", "body_bytes_max"):
            if old_budget.get(k) is not None and new_budget[k] > old_budget[k]:
                loosened.append(f"{path} {k}: {old_budget[k]} -> {new_budget[k]}")
        paths[path] = new_budget
    if loosened:
        # 예산 완화(느려짐 수용)는 실수로 일어나면 게이트 무력화 — 명시 확인 강제.
        print("[perf-gate][WARN] --seed 가 기존 예산을 완화합니다(의도된 성능 변화인지 diff 리뷰 필수):")
        for line in loosened:
            print(f"  - {line}")
    return {
        "_comment": (
            "스테이징 성능 게이트 예산(SSOT: tools/perf/staging_perf_gate.py). "
            "ttfb_warm_median_ms=warm 중앙값 상한(ms), body_bytes_max=응답 바이트 상한(해압 후, wire 아님). "
            "--seed 는 의도된 성능 변화 때만 실행하고 diff 를 리뷰한다."
        ),
        "_global": prev.get("_global", {
            "render_ms_max": 500,
            "etag_required": True,
            "conditional_304_required": True,
        }),
        "paths": paths,
    }


def load_budgets(path: Path = BUDGETS_PATH) -> dict[str, Any]:
    """budgets 파일 로드(없으면 빈 스키마)."""
    if not path.exists():
        return {"_global": {}, "paths": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_budgets(budgets: dict[str, Any], path: Path = BUDGETS_PATH) -> None:
    """budgets 파일 저장(정렬된 JSON, UTF-8)."""
    path.write_text(json.dumps(budgets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def archive_result(result: dict[str, Any], keep: int = 20) -> Path:
    """판정 결과를 evidence 로 아카이브(최근 ``keep`` 개만 유지 — 무한 누적 방지)."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(KST).strftime("%Y-%m-%dT%H%M%S")
    fp = EVIDENCE_DIR / f"perf-gate-{ts}.json"
    fp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    old = sorted(EVIDENCE_DIR.glob("perf-gate-*.json"))[:-keep]
    for stale in old:
        try:
            stale.unlink()
        except OSError:
            pass
    return fp


def render_table(rows: list[dict[str, Any]]) -> str:
    """판정 표(경로|median|budget|바이트|budget|304|판정) 텍스트."""
    header = f"{'PATH':<40} {'medTTFB':>8} {'budget':>7} {'p95':>6} {'bytes':>8} {'budget':>8} {'304':>4} {'RESULT':>6}"
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r['path']:<40} {r['median_ttfb_ms']:>8} {str(r['budget_ttfb_ms']):>7} "
            f"{r['p95_ttfb_ms']:>6} {r['median_bytes']:>8} {str(r['budget_bytes']):>8} "
            f"{('OK' if r['cond_304'] else 'NO'):>4} {('PASS' if r['passed'] else 'FAIL'):>6}"
        )
        for reason in r["reasons"]:
            lines.append(f"    ↳ {reason}")
    return "\n".join(lines)


def _credentials() -> tuple[str, str] | None:
    """env 크리덴셜 읽기(없으면 None)."""
    user = os.environ.get("FOMS_STAGING_USERNAME", "").strip()
    pw = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not pw:
        return None
    return user, pw


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass  # Win 콘솔 cp949에서 표 문자('↳') 출력 크래시 방지 — perf_scan.py 동일 관례.
    parser = argparse.ArgumentParser(description="FOMS 스테이징 성능 게이트 봇.")
    parser.add_argument("--base", default=DEFAULT_BASE, help="스테이징 origin")
    parser.add_argument("--seed", action="store_true", help="현 측정값+30%% 마진으로 budgets 갱신")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    creds = _credentials()
    if creds is None:
        print(
            "SKIP: FOMS_STAGING_USERNAME/FOMS_STAGING_PASSWORD 미설정 → 게이트 스킵(실패 아님, exit 2).",
            file=sys.stderr,
        )
        return 2
    user, pw = creds

    try:
        if args.seed:
            budgets = run_seed(args.base, user, pw, load_budgets())
            save_budgets(budgets)
            print(f"[SEED] budgets 갱신: {BUDGETS_PATH}")
            if args.json:
                print(json.dumps(budgets, ensure_ascii=False, indent=2))
            else:
                for path, b in budgets["paths"].items():
                    print(f"  {path:<40} ttfb<={b['ttfb_warm_median_ms']}ms bytes<={b['body_bytes_max']}")
            return 0

        result = run_gate(args.base, user, pw, load_budgets())
    except (RuntimeError, requests.RequestException) as exc:
        print(f"SKIP: 로그인/네트워크 실패 → {exc}", file=sys.stderr)
        return 2

    fp = archive_result(result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_table(result["rows"]))
        print(f"\nevidence: {fp}")
        print("RESULT: " + ("PASS" if result["ok"] else "FAIL"))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
