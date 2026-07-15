#!/usr/bin/env python3
"""P1 — 스테이징 성능 게이트 봇 (배포 후 검증 / production 승격 전 필수).

취지: "커밋→푸쉬→사용자가 느려짐 발견→분석→패치" 악순환에서 발견 주체를
사용자 → 봇으로 옮긴다. 배포된 스테이징(lahom-dev)에 로그인 → 9개 primary
fragment 경로와 실측 날짜칩 hot path 를 반복 측정 → 커밋된 예산
(``perf_budgets.json``)과 비교해 초과 시 exit 1 로 승격을 차단한다.

판정 철학 v2 (절대 준수 — 창 분산·tail 오염 면역):
  - 경로 TTFB 대표값은 warm 표본 **최솟값(min)**. tail(2~9s)은 값을 올리기만 하므로
    min 은 tail 오염에 완전 면역이고, 균일 서버 회귀(N+1 추가 등)는 전 표본을 올려
    min 도 상승 → 감지가 유지된다. (median/p95 는 리포트 정보로만 보존; 판정 미사용.)
  - 매 런 시작 시 무인증 ``GET {base}/healthz`` 를 반복 측정한 **min = 그 창의 네트워크
    베이스 RTT**. 판정값 = ``ttfb_min(path) − ttfb_min(healthz)`` = **서버+페이로드 델타**로,
    시간대별 베이스 RTT 분산(창 분산)을 상쇄해 빠른 창에 시드한 예산이 정상 창을
    오탐하던 실전 결함을 근본 제거한다.
  - p95/최댓값은 **판정에 절대 넣지 않는다**(정보용). 정밀 서버 회귀는 render_ms·바이트·
    쿼리 계약이 잡는다.
  - render_ms 도 **min 으로 판정**(TTFB 와 동일 tail 면역). 진짜 render 회귀(N+1·무거운
    루프)는 전 표본을 올려 min 도 오르지만, CI CPU 경합·GC 로 인한 단일 슬로우 샘플은
    max 만 올리고 min 은 불변 → 노이즈 면역. max_render_ms 는 정보용으로만 보존.
  - 바이트 판정은 **전송(wire, 압축) 바이트** = 실사용 다운로드 비용. 응답은 br/gzip 으로
    압축 전송되므로 반복 큰 마크업(10~15:1 압축)은 wire 가 거의 안 늘어 오탐하지 않고, 진짜
    무거운 추가만 잡는다. 해압(decompressed) 바이트는 정보용으로만 보존한다.

exit code:
  0 = PASS, 1 = FAIL(예산 초과), 2 = 크리덴셜 부재/로그인 실패(게이트 SKIP ≠ 실패).
  --advisory: 예산 초과여도 exit 0(job fail 대신 경고 어노테이션만) — deploy 푸시용 비블로킹 조기 신호.

크리덴셜은 환경변수로만 읽는다(argv 금지 — 셸 히스토리 유출 방지):
  FOMS_STAGING_USERNAME / FOMS_STAGING_PASSWORD, base 는 --base(기본 lahom-dev).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
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

# SSOT: 9 primary 경로는 foms/services/common/erp_navigation_contract.py 에서 읽는다.
# (static/js/runtime/erp-shell.js PRIMARY_NAV_PATHS 와 동일 잠금판; 서버 계약과 byte-match)
# 주의: `from foms...` 패키지 import 는 foms/__init__ 연쇄가 folium 등 앱 전체 의존성을
# 끌어와 CI(최소 설치: requests 만)에서 ModuleNotFoundError 로 죽는다(첫 자동 런 실증).
# 모듈 파일을 직접 로드해 패키지 init 을 우회한다 — SSOT 파일은 동일.
import importlib.util as _ilu

def _load_module_file(name: str, rel_path: str):
    """패키지 __init__ 연쇄 없이 단일 모듈 파일 로드(CI 최소 의존 유지)."""
    spec = _ilu.spec_from_file_location(name, ROOT / rel_path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

ERP_PRIMARY_NAV_PATHS = _load_module_file(
    "erp_navigation_contract", "foms/services/common/erp_navigation_contract.py"
).ERP_PRIMARY_NAV_PATHS
fetch_session_cookie = _load_module_file(
    "ept_b8_staging_session_from_login", "tools/harness/ept_b8_staging_session_from_login.py"
).fetch_session_cookie

DEFAULT_BASE = "https://lahom-dev.up.railway.app"
BUDGETS_PATH = ROOT / "tools" / "perf" / "perf_budgets.json"
EVIDENCE_DIR = ROOT / "docs" / "harness" / "evidence"
KST = timezone(timedelta(hours=9))

ROUNDS = 7  # 판정: 첫 회 웜업 버림 → warm 표본 6 (min 은 tail 오염 면역이라 표본 6이면 충분)
# 시드는 예산의 SSOT. min 은 표본이 많을수록 그 창의 진짜 바닥(서버 최상)에 수렴한다.
SEED_ROUNDS = 13  # 첫 회 버림 → warm 표본 12(min 이 창의 최상 서버 시간에 안정 수렴)
HEALTHZ_ROUNDS = 7  # 무인증 /healthz 반복 → min = 그 창의 네트워크 베이스 RTT(델타 차감용)
SLEEP_S = 0.3
SEED_MARGIN = 0.30  # 델타 실측 + 30% 여유(상대)
SEED_DELTA_FLOOR_MS = 80  # 델타는 값이 작아(수십~수백ms) 상대 30%가 빡빡 → 절대 하한 마진

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
MEASUREMENT_DATE_CHIP_BUDGET_KEY = "/erp/measurement?date=*&view=fragment"
MEASUREMENT_DATE_CHIP_DISCOVERY_PATH = "/erp/measurement?view=fragment"
MEASUREMENT_DATE_CHIP_MAX_PATHS = 3
_MEASUREMENT_DATE_HREF_RE = re.compile(
    r"""href=['"][^'"]*/erp/measurement\?[^'"]*\bdate=(\d{4}-\d{2}-\d{2})[^'"]*['"]""",
    re.I,
)


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
    """warm 표본(첫 회 제외 후) → min/median/p95 TTFB·median wire/해압 bytes·render/etag 요약.

    Args:
        warm_samples: 각 원소는 ``ttfb_ms``·``bytes``(해압 후)·``wire_bytes``(전송 압축
            바이트; 부재 시 ``bytes`` 폴백)·``wire_measured``(bool; Content-Length 로 실측
            했는지)·``render_ms``(None 가능)·``etag_present``(bool)·``content_encoding``
            (str|None) 키를 갖는다.

    Returns:
        판정·리포트에 쓰는 요약 dict. **min TTFB 만 TTFB 판정에**(healthz 델타 차감 후),
        바이트 판정은 ``median_wire_bytes``(전송 압축 바이트)로. render 는 ``min_render_ms``
        로 판정(TTFB 와 동일 tail/노이즈 면역), ``max_render_ms`` 는 정보용. median/p95
        TTFB·해압 median_bytes 는 정보로만. ``wire_measured_all`` 이 False 면 일부/전부
        폴백(보수적).
    """
    ttfbs = [float(s["ttfb_ms"]) for s in warm_samples]
    byts = [int(s["bytes"]) for s in warm_samples]
    wires = [int(s.get("wire_bytes", s["bytes"])) for s in warm_samples]
    renders = [float(s["render_ms"]) for s in warm_samples if s.get("render_ms") is not None]
    return {
        "min_ttfb_ms": int(min(ttfbs)) if ttfbs else 0,
        "median_ttfb_ms": int(statistics.median(ttfbs)) if ttfbs else 0,
        "p95_ttfb_ms": int(percentile(ttfbs, 95)) if ttfbs else 0,
        "max_ttfb_ms": int(max(ttfbs)) if ttfbs else 0,
        "median_bytes": int(statistics.median(byts)) if byts else 0,
        "median_wire_bytes": int(statistics.median(wires)) if wires else 0,
        "wire_measured_all": bool(warm_samples) and all(s.get("wire_measured", False) for s in warm_samples),
        "min_render_ms": int(min(renders)) if renders else None,
        "max_render_ms": int(max(renders)) if renders else None,
        "etag_present_all": bool(warm_samples) and all(s.get("etag_present") for s in warm_samples),
        "content_encoding": next((s.get("content_encoding") for s in warm_samples), None),
        "warm_count": len(warm_samples),
        # 판정 자격 검사용(judge_path) — warm 표본 전부 200 이어야 유효 측정.
        # status 미기록 표본(구버전/단위테스트 픽스처)은 자격 검사에서 제외(관용).
        "statuses": [int(s["status"]) for s in warm_samples if s.get("status") is not None],
    }


def delta_ttfb_ms(summary: dict[str, Any], base_ttfb_ms: int) -> int:
    """판정값 = ``ttfb_min(path) − ttfb_min(healthz)`` = 창 무관 서버+페이로드 델타.

    tail 은 min 을 못 올리므로 tail 오염 면역이고, healthz 차감이 그 창의 네트워크
    베이스 RTT(창 분산)를 상쇄한다. 음수(측정 노이즈로 path 가 base 보다 빠른 경우)는
    0 으로 바닥 처리(예산은 항상 양수 델타 기준으로 시드/판정).
    """
    return max(0, int(summary["min_ttfb_ms"]) - int(base_ttfb_ms))


def judge_path(
    path: str,
    summary: dict[str, Any],
    cond_304_ok: bool,
    budget: dict[str, Any],
    global_budget: dict[str, Any],
    base_ttfb_ms: int,
) -> dict[str, Any]:
    """단일 경로 판정 — **delta-min TTFB·wire bytes 만** 예산과 비교(median/p95·해압은 정보용).

    Args:
        summary: ``summarize_samples`` 결과.
        cond_304_ok: 조건부 If-None-Match 가 304 로 접혔는지.
        budget: 경로별 예산 ``{ttfb_delta_min_ms, body_bytes_max}``.
        global_budget: 전역 예산(render_ms_max·etag_required·conditional_304_required).
        base_ttfb_ms: 이 런의 healthz min TTFB(네트워크 베이스, 델타 차감 기준).

    Returns:
        판정 row(``passed`` bool + ``reasons`` 목록 + 측정/예산 값).
    """
    reasons: list[str] = []
    # 1:1 리뷰 MAJOR: status 미검사 시 302(세션만료)/500 이 bytes·ttfb 만으로
    # false-PASS 될 수 있다 — warm 표본 전부 200 이어야 판정 자격.
    bad = [s for s in (summary.get("statuses") or []) if s != 200]
    if bad:
        reasons.append(f"non-200 응답 {bad} (세션만료/서버오류 — 측정 무효)")
    delta_budget = budget.get("ttfb_delta_min_ms")
    p95_delta_budget = budget.get("p95_ttfb_delta_ms")
    bytes_budget = budget.get("body_bytes_max")
    delta = delta_ttfb_ms(summary, base_ttfb_ms)
    p95_delta = max(0, int(summary["p95_ttfb_ms"]) - int(base_ttfb_ms))

    if delta_budget is not None and delta > delta_budget:
        reasons.append(
            f"TTFB delta-min {delta}ms > budget {delta_budget}ms "
            f"(min {summary['min_ttfb_ms']}ms − healthz base {base_ttfb_ms}ms; 서버+페이로드 회귀)"
        )
    if p95_delta_budget is not None and p95_delta > p95_delta_budget:
        reasons.append(
            f"TTFB delta-p95 {p95_delta}ms > budget {p95_delta_budget}ms "
            f"(p95 {summary['p95_ttfb_ms']}ms − healthz base {base_ttfb_ms}ms; 날짜 이동 tail 회귀)"
        )
    if bytes_budget is not None and summary["median_wire_bytes"] > bytes_budget:
        reasons.append(
            f"wire bytes {summary['median_wire_bytes']} > budget {bytes_budget} "
            f"(전송 압축 바이트; 해압 {summary['median_bytes']})"
        )

    render_max = global_budget.get("render_ms_max")
    if render_max is not None and summary["min_render_ms"] is not None:
        if summary["min_render_ms"] > render_max:
            reasons.append(
                f"render min {summary['min_render_ms']}ms > budget {render_max}ms "
                f"(max {summary['max_render_ms']}ms; min 은 CI 노이즈 면역 — 균일 회귀만 잡음)"
            )
    if global_budget.get("etag_required") and not summary["etag_present_all"]:
        reasons.append("ETag 누락(revalidation 계약 위반)")
    if global_budget.get("conditional_304_required") and not cond_304_ok:
        reasons.append("조건부 304 실패(하트비트 경제성 회귀)")

    row = {
        "path": path,
        "delta_ttfb_ms": delta,
        "budget_delta_ttfb_ms": delta_budget,
        "p95_ttfb_delta_ms": p95_delta,
        "budget_p95_ttfb_delta_ms": p95_delta_budget,
        "min_ttfb_ms": summary["min_ttfb_ms"],
        "base_ttfb_ms": base_ttfb_ms,
        "median_ttfb_ms": summary["median_ttfb_ms"],  # 정보용
        "p95_ttfb_ms": summary["p95_ttfb_ms"],  # 정보용
        "median_wire_bytes": summary["median_wire_bytes"],  # 판정값(전송 압축 바이트)
        "median_bytes": summary["median_bytes"],  # 정보용(해압 후 바이트)
        "budget_bytes": bytes_budget,
        "min_render_ms": summary["min_render_ms"],  # render 판정값(노이즈 면역)
        "max_render_ms": summary["max_render_ms"],  # 정보용(단일 슬로우 샘플 노출)
        "cond_304": cond_304_ok,
        "passed": not reasons,
        "reasons": reasons,
    }
    # Content-Length 부재로 폴백된 경우: 폴백=해압값이라 과대추정=보수적(오탐 안전측)이므로
    # FAIL 시키지 않고 경고성 플래그로만 표시(reasons 미추가).
    if not summary["wire_measured_all"]:
        row["wire_degraded"] = True
    return row


def seed_budget(
    summary: dict[str, Any],
    base_ttfb_ms: int,
    margin: float = SEED_MARGIN,
    floor_ms: int = SEED_DELTA_FLOOR_MS,
) -> dict[str, int]:
    """실측 요약 → 경로별 예산. ``--seed`` 모드에서만 사용.

    델타 예산 = ``max(delta*(1+margin), delta+floor_ms)``. 델타는 값이 작아(수십~수백ms)
    상대 마진만으로는 빡빡하므로 절대 하한 마진(floor_ms)을 함께 적용한다.
    bytes 는 결정적이라 median wire(전송 압축 바이트)×(1+margin).
    """
    delta = delta_ttfb_ms(summary, base_ttfb_ms)
    delta_budget = max(int(round(delta * (1 + margin))), delta + floor_ms)
    return {
        "ttfb_delta_min_ms": delta_budget,
        "body_bytes_max": int(round(summary["median_wire_bytes"] * (1 + margin))),
    }


def reconcile_seed_budget(
    new_budget: dict[str, int], old_budget: dict[str, Any], on_ci: bool
) -> tuple[dict[str, int], bool]:
    """로컬 seed 는 CI 심판석 TTFB 예산을 보존하고 bytes 만 재시드한다.

    TTFB 예산(ttfb_delta_min_ms)의 관측 기준은 CI 러너다. 로컬 머신에서 --seed 를
    돌리면 로컬 네트워크/CPU 측정값이 CI 심판석 예산을 오염(엄격화/완화)시켜 CI 가
    오탐/누락한다(실증: b10dd728 history 276→198 오염). on_ci=False 이고 이전 예산에
    ttfb 값이 있으면 그 값을 보존한다(bytes 는 결정적이라 항상 재시드). on_ci=True(심판석)
    이거나 이전 ttfb 예산이 없으면(최초 부트스트랩) 새 측정값을 그대로 쓴다.

    Returns:
        (병합된 예산, ttfb_보존_여부).
    """
    merged = dict(new_budget)
    preserved = False
    if not on_ci and old_budget.get("ttfb_delta_min_ms") is not None:
        merged["ttfb_delta_min_ms"] = old_budget["ttfb_delta_min_ms"]
        preserved = True
    return merged, preserved


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
        # 실사용 다운로드 비용 = 전송(wire, 압축) 바이트. requests 는 본문을 해압해도
        # 수신 원본 헤더 Content-Length(=압축 wire 크기)를 유지한다. 청크 응답 등으로
        # 부재하면 해압 len 폴백(과대추정=보수적) + 플래그로 신뢰도 저하만 표시.
        cl = resp.headers.get("Content-Length")
        wire_bytes = int(cl) if (cl is not None and cl.isdigit()) else len(body)
        wire_measured = bool(cl is not None and cl.isdigit())
        render = resp.headers.get("X-FOMS-EPT-B7-RENDER-MS")
        samples.append({
            "round": i + 1,
            "status": resp.status_code,
            "ttfb_ms": round((t_headers - t0) * 1000),
            "total_ms": round((t_total - t0) * 1000),
            "bytes": len(body),
            "wire_bytes": wire_bytes,
            "wire_measured": wire_measured,
            "render_ms": float(render) if render not in (None, "") else None,
            "content_encoding": resp.headers.get("Content-Encoding"),
            "etag_present": bool(resp.headers.get("ETag")),
        })
        time.sleep(SLEEP_S)
    warm = samples[1:] if len(samples) > 1 else samples
    cond_304_ok = _check_conditional_304(session, url)
    return {"path": path, "samples": samples, "warm": warm, "cond_304_ok": cond_304_ok}


def measure_healthz_base(session: requests.Session, base: str, rounds: int = HEALTHZ_ROUNDS) -> int:
    """무인증 ``GET {base}/healthz`` 를 rounds 회 → min TTFB = 그 창의 네트워크 베이스 RTT.

    healthz 는 DB·세션·인증을 건드리지 않는 순수 liveness(무거운 서버 작업 0)라, 그
    min 은 "이 창에서 왕복만으로 드는 최소 시간"에 수렴한다. 경로 min 에서 이 값을 빼면
    시간대별 베이스 RTT 변동(창 분산)이 상쇄돼 서버+페이로드 순수 델타가 남는다.
    """
    url = base.rstrip("/") + "/healthz"
    ttfbs: list[float] = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        resp = _get_with_retry(session, url, {"Accept": "application/json"})
        _ = resp.content  # 본문 소비(측정 방법을 경로 측정과 동일하게 맞춤)
        ttfbs.append((time.perf_counter() - t0) * 1000)
        time.sleep(SLEEP_S)
    return int(min(ttfbs)) if ttfbs else 0


def measurement_date_fragment_path(date_str: str) -> str:
    """날짜칩 클릭 경로를 shell fragment 측정 경로로 정규화."""
    return f"/erp/measurement?date={date_str}&view=fragment"


def discover_measurement_date_chip_paths(
    session: requests.Session,
    base: str,
    *,
    max_paths: int = MEASUREMENT_DATE_CHIP_MAX_PATHS,
) -> tuple[str, ...]:
    """실측 대시보드에서 실제 날짜칩 링크를 찾아 날짜 이동 hot path 로 측정한다."""
    url = base.rstrip("/") + MEASUREMENT_DATE_CHIP_DISCOVERY_PATH
    resp = _get_with_retry(session, url, FRAGMENT_HEADERS)
    if resp.status_code != 200:
        return ()
    text = html.unescape(resp.text or "")
    paths: list[str] = []
    seen: set[str] = set()
    for match in _MEASUREMENT_DATE_HREF_RE.finditer(text):
        date_str = match.group(1)
        if date_str in seen:
            continue
        seen.add(date_str)
        paths.append(measurement_date_fragment_path(date_str))
        if len(paths) >= max_paths:
            break
    return tuple(paths)


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
    # 창 무관 판정의 핵심: 런 시작 시 그 창의 네트워크 베이스 RTT 를 확정한다.
    base_ttfb_ms = measure_healthz_base(session, base)

    rows: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    path_plan: list[tuple[str, dict[str, Any]]] = [
        (path, path_budgets.get(path, {})) for path in FRAGMENT_PATHS
    ]
    for path in discover_measurement_date_chip_paths(session, base):
        path_plan.append((path, path_budgets.get(MEASUREMENT_DATE_CHIP_BUDGET_KEY, {})))

    for path, budget in path_plan:
        measured = measure_path(session, base, path)
        raw.append(measured)
        summary = summarize_samples(measured["warm"])
        row = judge_path(path, summary, measured["cond_304_ok"], budget, global_budget, base_ttfb_ms)
        # 재측정 방어(v2 에선 발동 확률 낮음): delta "만" 위반이면 1회 재측정 후 재판정.
        # min 은 tail 면역이라 이제 tail 뭉침으로는 거의 안 뚫리지만, 순간적 서버 hiccup
        # (경로 min 이 그 창에서만 높음)을 걸러낸다. bytes/ETag/304 위반은 결정적이라 재측정 없음.
        ttfb_only = row["reasons"] and all("TTFB" in r for r in row["reasons"])
        if not row["passed"] and ttfb_only:
            time.sleep(2.0)
            remeasured = measure_path(session, base, path)
            resummary = summarize_samples(remeasured["warm"])
            if (
                resummary["min_ttfb_ms"] < summary["min_ttfb_ms"]
                or resummary["p95_ttfb_ms"] < summary["p95_ttfb_ms"]
            ):
                raw.append(remeasured)
                summary = resummary
                row = judge_path(path, summary, remeasured["cond_304_ok"], budget, global_budget, base_ttfb_ms)
                row["retried"] = True
        row["_summary"] = summary
        rows.append(row)

    ok = all(r["passed"] for r in rows)
    return {"base": base, "ok": ok, "base_ttfb_ms": base_ttfb_ms, "rows": rows, "raw": raw}


def run_seed(base: str, user: str, password: str, prev: dict[str, Any]) -> dict[str, Any]:
    """--seed: 델타 실측 + 마진으로 budgets 갱신(v2 스키마, 전역 예산은 보존/기본값)."""
    cookie, _ = fetch_session_cookie(base, user, password)
    session = requests.Session()
    session.headers["Cookie"] = cookie
    base_ttfb_ms = measure_healthz_base(session, base, rounds=SEED_ROUNDS)
    paths: dict[str, Any] = {}
    prev_paths = prev.get("paths", {})
    loosened: list[str] = []
    preserved_paths: list[str] = []
    on_ci = _is_ci()
    for path in FRAGMENT_PATHS:
        measured = measure_path(session, base, path, rounds=SEED_ROUNDS)
        summary = summarize_samples(measured["warm"])
        new_budget = seed_budget(summary, base_ttfb_ms)
        old_budget = prev_paths.get(path) or {}
        new_budget, preserved = reconcile_seed_budget(new_budget, old_budget, on_ci)
        if preserved:
            preserved_paths.append(path)
        for k in ("ttfb_delta_min_ms", "body_bytes_max"):
            if old_budget.get(k) is not None and new_budget[k] > old_budget[k]:
                loosened.append(f"{path} {k}: {old_budget[k]} -> {new_budget[k]}")
        paths[path] = new_budget
    if loosened:
        # 예산 완화(느려짐 수용)는 실수로 일어나면 게이트 무력화 — 명시 확인 강제.
        print("[perf-gate][WARN] --seed 가 기존 예산을 완화합니다(의도된 성능 변화인지 diff 리뷰 필수):")
        for line in loosened:
            print(f"  - {line}")
    if preserved_paths:
        print("[perf-gate][NOTE] 로컬 --seed: TTFB 예산은 CI 심판석 값 보존(bytes 만 재시드). "
              "ttfb 갱신은 CI(GITHUB_ACTIONS=true)에서만 반영:")
        for p in preserved_paths:
            print(f"  - {p}")
    for path, old_budget in prev_paths.items():
        if path not in paths:
            paths[path] = old_budget
    prev_global = prev.get("_global") or {}
    return {
        "_comment": (
            "스테이징 성능 게이트 예산 v2(SSOT: tools/perf/staging_perf_gate.py). "
            "판정값 ttfb_delta_min_ms = min(warm path TTFB) − min(healthz TTFB): "
            "min 은 tail(2~9s) 오염 면역, healthz 델타는 시간대별 베이스 RTT(창 분산)를 상쇄한다. "
            "body_bytes_max = 전송(wire, 압축) 바이트 상한(실사용 다운로드 비용; 해압은 정보용, 결정적 min 성격). "
            "정밀 서버 회귀는 render_ms_max·bytes·쿼리 계약이 잡는다. "
            "--seed 는 의도된 성능 변화 때만 실행하고 diff 를 리뷰한다."
        ),
        "_global": {
            "schema": 2,
            "render_ms_max": prev_global.get("render_ms_max", 500),
            "etag_required": prev_global.get("etag_required", True),
            "conditional_304_required": prev_global.get("conditional_304_required", True),
        },
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


def render_table(rows: list[dict[str, Any]], base_ttfb_ms: int | None = None) -> str:
    """판정 표(경로|dTTFB|budget|min|medTTFB|p95|wire|budget|raw|304|판정) 텍스트.

    dTTFB(delta-min) = min(path) − healthz base 가 판정값. medTTFB·p95 는 정보용.
    wire = median 전송(압축) 바이트 = 바이트 판정값. raw = median 해압 바이트(정보용).
    """
    header = (
        f"{'PATH':<40} {'dTTFB':>6} {'budget':>7} {'min':>6} "
        f"{'medTTFB':>8} {'p95':>6} {'wire':>8} {'budget':>8} {'raw':>8} {'304':>4} {'RESULT':>6}"
    )
    lines: list[str] = []
    if base_ttfb_ms is not None:
        lines.append(
            f"healthz base(min TTFB): {base_ttfb_ms}ms  "
            f"|  판정값 dTTFB = min(path) − base (창 무관 서버+페이로드 델타)"
        )
        lines.append(
            "바이트 판정값 = wire(전송 압축 바이트) = 실사용 다운로드 비용. raw = 해압 바이트(정보용)."
        )
        lines.append("")
    lines.extend([header, "-" * len(header)])
    for r in rows:
        lines.append(
            f"{r['path']:<40} {r['delta_ttfb_ms']:>6} {str(r['budget_delta_ttfb_ms']):>7} "
            f"{r['min_ttfb_ms']:>6} {r['median_ttfb_ms']:>8} {r['p95_ttfb_ms']:>6} "
            f"{r['median_wire_bytes']:>8} {str(r['budget_bytes']):>8} {r['median_bytes']:>8} "
            f"{('OK' if r['cond_304'] else 'NO'):>4} {('PASS' if r['passed'] else 'FAIL'):>6}"
        )
        if r.get("wire_degraded"):
            lines.append("    ↳ wire 측정 폴백(Content-Length 부재 — 해압값 사용, 보수적)")
        for reason in r["reasons"]:
            lines.append(f"    ↳ {reason}")
    return "\n".join(lines)


def _is_ci() -> bool:
    """GitHub Actions/CI 러너 여부 — TTFB 예산 시드의 심판석 자격 판별."""
    return os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"


def gate_exit_code(ok: bool, advisory: bool) -> int:
    """판정 결과 → exit code. advisory 면 예산 초과(ok=False)여도 0(비블로킹 조기 신호),
    아니면 초과 시 1(블로킹). 크리덴셜/네트워크 실패(exit 2)는 caller 가 별도 처리."""
    if ok:
        return 0
    return 0 if advisory else 1


def emit_advisory_annotations(result: dict[str, Any]) -> None:
    """예산 초과를 job fail 대신 GitHub 경고 어노테이션 + step summary 로 방출(비블로킹).

    초과 경로마다 ``::warning::perf-gate ADVISORY: <path> <reasons>`` 를 stdout 에 찍고,
    $GITHUB_STEP_SUMMARY 파일이 있으면 초과 경로 markdown 표를 append 한다(없으면 스킵).
    """
    failed = [r for r in result.get("rows", []) if not r["passed"]]
    for row in failed:
        reason = "; ".join(row["reasons"])
        print(f"::warning::perf-gate ADVISORY: {row['path']} {reason}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = [
        "",
        "### perf-gate ADVISORY (비블로킹 조기 신호 — 예산 초과는 별도 커밋으로 재시드/근본수정)",
        "",
        "| path | reason |",
        "| --- | --- |",
    ]
    for row in failed:
        lines.append(f"| {row['path']} | {'; '.join(row['reasons'])} |")
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


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
    parser.add_argument("--advisory", action="store_true", help="예산 초과를 job fail 대신 경고로 — 비블로킹 조기 신호")
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
                    print(f"  {path:<40} dTTFB<={b['ttfb_delta_min_ms']}ms bytes<={b['body_bytes_max']}")
            return 0

        result = run_gate(args.base, user, pw, load_budgets())
    except (RuntimeError, requests.RequestException) as exc:
        print(f"SKIP: 로그인/네트워크 실패 → {exc}", file=sys.stderr)
        return 2

    fp = archive_result(result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_table(result["rows"], result.get("base_ttfb_ms")))
        print(f"\nevidence: {fp}")
        print("RESULT: " + ("PASS" if result["ok"] else "FAIL"))
    if not result["ok"] and args.advisory:
        emit_advisory_annotations(result)
    return gate_exit_code(result["ok"], args.advisory)


if __name__ == "__main__":
    raise SystemExit(main())
