"""스테이징 성능 게이트 v2 — 네트워크 없는 단위 테스트.

핵심 계약(v2 — 창 분산·tail 오염 면역):
  - budgets 파일 존재 + 스키마 v2 유효(9 경로 · ttfb_delta_min_ms · _global.schema==2).
  - 판정값 = min(warm path TTFB) − min(healthz TTFB). **min 만** 본다:
      · tail 오염(표본 절반이 3~5s)에도 min 불변 → PASS 유지(한국↔싱가포르 tail 내성).
      · 균일 +200ms 시프트(서버 회귀)는 min 도 오름 → FAIL(감지 유지).
  - healthz 델타 산식(음수는 0 바닥).
  - 바이트 판정 = median **wire(전송 압축) 바이트**(실사용 다운로드 비용). 반복 큰 마크업은
    압축돼 wire 가 안 늘어 오탐 없음(해압 바이트는 정보용). Content-Length 부재 시 해압 폴백
    (보수적) + wire_degraded 플래그만, FAIL 은 안 함.
  - --seed 마진: max(delta*1.3, delta+80ms).
  - 크리덴셜 부재 → exit 2(게이트 SKIP ≠ 실패).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.perf import staging_perf_gate as gate
from foms.services.common.erp_navigation_contract import ERP_PRIMARY_NAV_PATHS

GLOBAL_BUDGET = {"render_ms_max": 500, "etag_required": True, "conditional_304_required": True}


def _sample(
    ttfb_ms: int,
    bytes_: int = 1000,
    render_ms: float | None = 100.0,
    wire_bytes: int | None = None,
) -> dict:
    """표본 픽스처. wire_bytes 미지정 시 bytes_ 와 동일(압축=1:1 기본), wire_measured=True."""
    return {
        "ttfb_ms": ttfb_ms,
        "bytes": bytes_,
        "wire_bytes": bytes_ if wire_bytes is None else wire_bytes,
        "wire_measured": True,
        "render_ms": render_ms,
        "etag_present": True,
        "content_encoding": "br",
        "status": 200,
    }


def _budget(delta: int = 100, bytes_: int = 5000) -> dict:
    return {"ttfb_delta_min_ms": delta, "body_bytes_max": bytes_}


# ---------------------------------------------------------------------------
# budgets 파일 스키마 v2
# ---------------------------------------------------------------------------
def test_budgets_file_exists_and_valid_schema_v2():
    """perf_budgets.json 이 존재하고 v2 스키마(schema==2 · ttfb_delta_min_ms)를 만족한다."""
    budgets = json.loads(gate.BUDGETS_PATH.read_text(encoding="utf-8"))
    assert "_global" in budgets and "paths" in budgets

    g = budgets["_global"]
    assert g.get("schema") == 2, "v2 스키마 표기(_global.schema==2) 필수"
    assert isinstance(g["render_ms_max"], int)
    assert isinstance(g["etag_required"], bool)
    assert isinstance(g["conditional_304_required"], bool)

    expected = {gate.fragment_path(p) for p in ERP_PRIMARY_NAV_PATHS}
    assert set(budgets["paths"]) == expected, "budgets 경로가 nav 계약 9경로와 일치해야 한다"
    for path, b in budgets["paths"].items():
        assert isinstance(b["ttfb_delta_min_ms"], int) and b["ttfb_delta_min_ms"] > 0, path
        assert isinstance(b["body_bytes_max"], int) and b["body_bytes_max"] > 0, path
        # v1 판정 키는 완전히 제거되어야 한다(마이그레이션 회귀 방지).
        assert "ttfb_warm_median_ms" not in b, f"{path}: v1 키 잔존"


def test_fragment_paths_match_nav_contract():
    """게이트 경로 목록 = nav 계약 SSOT(9개, ?view=fragment)."""
    assert len(gate.FRAGMENT_PATHS) == len(ERP_PRIMARY_NAV_PATHS) == 9
    assert all(p.endswith("?view=fragment") for p in gate.FRAGMENT_PATHS)


# ---------------------------------------------------------------------------
# 판정: delta-min 기준 · tail 오염 면역
# ---------------------------------------------------------------------------
def test_delta_over_budget_fails():
    """delta(min − base) 가 예산 초과 → FAIL."""
    warm = [_sample(700), _sample(720), _sample(710), _sample(730)]  # min 700
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, _budget(delta=100), GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["delta_ttfb_ms"] == 320  # 700 - 380
    assert row["passed"] is False
    assert any("TTFB delta-min" in r for r in row["reasons"])


def test_delta_within_budget_passes():
    """delta 가 예산 이내 → PASS."""
    warm = [_sample(400), _sample(420), _sample(410), _sample(430)]  # min 400
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, _budget(delta=100), GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["delta_ttfb_ms"] == 20  # 400 - 380
    assert row["passed"] is True
    assert row["reasons"] == []


def test_tail_contamination_does_not_move_min_stays_pass():
    """tail 오염 내성 계약: warm 표본 절반이 3~5s 여도 min 불변 → PASS.

    실전 오탐(history [1107,237,287,269,3310,4888] median 697 오염)의 근본 해결:
    min 은 tail 이 절대 못 올리므로, 깨끗한 창과 오염된 창의 min·판정이 동일하다.
    """
    clean = [_sample(400), _sample(410), _sample(420), _sample(405), _sample(415), _sample(408)]
    tainted = [_sample(400), _sample(3310), _sample(410), _sample(4888), _sample(420), _sample(3000)]
    s_clean = gate.summarize_samples(clean)
    s_tainted = gate.summarize_samples(tainted)
    assert s_clean["min_ttfb_ms"] == s_tainted["min_ttfb_ms"] == 400  # min 완전 불변
    assert s_tainted["median_ttfb_ms"] > 400  # median 은 오염됨(리포트에만)
    row = gate.judge_path("/x", s_tainted, True, _budget(delta=100), GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["passed"] is True, "min 정상인데 tail 로 FAIL 나면 v2 tail 면역 계약 위반"


def test_uniform_server_shift_is_detected_fails():
    """균일 +200ms 서버 회귀(N+1 등): 전 표본이 오르면 min 도 올라 FAIL 로 감지 유지."""
    base_ttfb = 380
    clean = [_sample(400), _sample(410), _sample(420)]
    shifted = [_sample(600), _sample(610), _sample(620)]  # 전 표본 +200
    s_clean = gate.summarize_samples(clean)
    s_shifted = gate.summarize_samples(shifted)
    # 깨끗한 창은 통과, 시프트 창은 실패 — 같은 예산·같은 base 로.
    budget = _budget(delta=100)
    ok = gate.judge_path("/x", s_clean, True, budget, GLOBAL_BUDGET, base_ttfb_ms=base_ttfb)
    bad = gate.judge_path("/x", s_shifted, True, budget, GLOBAL_BUDGET, base_ttfb_ms=base_ttfb)
    assert ok["passed"] is True and ok["delta_ttfb_ms"] == 20
    assert bad["passed"] is False and bad["delta_ttfb_ms"] == 220


def test_healthz_delta_formula_and_negative_floor():
    """delta = min(path) − base; 음수(측정 노이즈)는 0 으로 바닥 처리."""
    warm = [_sample(500), _sample(520), _sample(510)]  # min 500
    summary = gate.summarize_samples(warm)
    assert gate.delta_ttfb_ms(summary, 300) == 200  # 500 - 300
    assert gate.delta_ttfb_ms(summary, 500) == 0
    assert gate.delta_ttfb_ms(summary, 700) == 0  # path 가 base 보다 빠른 노이즈 → 0 바닥


def test_bytes_over_budget_fails():
    """median wire bytes 가 예산 초과 → FAIL(bytes 는 delta 무관, 결정적)."""
    warm = [_sample(400, bytes_=9000), _sample(400, bytes_=9100), _sample(400, bytes_=9050), _sample(400, bytes_=9000)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, _budget(delta=100, bytes_=5000), GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["passed"] is False
    assert any("bytes" in r for r in row["reasons"])


# ---------------------------------------------------------------------------
# wire(전송 압축) 바이트 판정 — 재시드 두더지잡기 종결 계약
# ---------------------------------------------------------------------------
def test_wire_bytes_judged_not_decompressed_reseed_thrash_ended():
    """핵심 가치: 해압 90만 바이트여도 wire(압축) 5만이면 예산 이내 → PASS.

    반복 큰 태블릿 마크업(10~15:1 압축)은 해압 바이트만 부풀고 wire 는 거의 안 는다.
    판정 지표를 wire 로 옮기면 매 커밋 재시드 두더지잡기가 종결된다(해압 판정이면 FAIL).
    """
    warm = [_sample(400, bytes_=900000, wire_bytes=50000) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    assert summary["median_bytes"] == 900000  # 해압은 거대(정보용)
    assert summary["median_wire_bytes"] == 50000  # wire 는 작음(판정값)
    row = gate.judge_path(
        "/x", summary, True, _budget(delta=100, bytes_=137723), GLOBAL_BUDGET, base_ttfb_ms=380
    )
    assert row["passed"] is True, "wire 가 예산 이내면 해압 90만이어도 PASS 여야 한다"
    assert row["median_wire_bytes"] == 50000
    assert row["median_bytes"] == 900000  # 해압은 정보로 보존


def test_wire_bytes_over_budget_fails():
    """wire(압축) 바이트가 예산 초과 → FAIL(해압이 작아도 wire 로 판정)."""
    warm = [_sample(400, bytes_=6000, wire_bytes=9000) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    assert summary["median_wire_bytes"] == 9000
    row = gate.judge_path(
        "/x", summary, True, _budget(delta=100, bytes_=5000), GLOBAL_BUDGET, base_ttfb_ms=380
    )
    assert row["passed"] is False
    assert any("wire bytes" in r for r in row["reasons"])


def test_wire_fallback_flags_degraded_but_does_not_fail():
    """Content-Length 부재(wire_measured=False) → wire_degraded=True 이나 예산 이내면 PASS.

    폴백=해압값 사용이라 과대추정=보수적(오탐 안전측)이므로 신뢰도 저하 플래그만 남기고
    FAIL 시키지 않는다(reasons 미추가).
    """
    warm = [
        {
            "ttfb_ms": 400, "bytes": 3000, "wire_bytes": 3000, "wire_measured": False,
            "render_ms": 100.0, "etag_present": True, "content_encoding": "br", "status": 200,
        }
        for _ in range(4)
    ]
    summary = gate.summarize_samples(warm)
    assert summary["wire_measured_all"] is False
    row = gate.judge_path(
        "/x", summary, True, _budget(delta=100, bytes_=5000), GLOBAL_BUDGET, base_ttfb_ms=380
    )
    assert row["passed"] is True  # 폴백=보수적, 예산 이내면 통과
    assert row.get("wire_degraded") is True
    assert not any("wire" in r for r in row["reasons"])  # 폴백은 reasons 로 FAIL 시키지 않음


def test_summarize_wire_falls_back_to_bytes_for_old_samples():
    """구버전 표본(wire_bytes 키 없음) → median_wire_bytes 가 median_bytes 로 폴백."""
    warm = [
        {
            "ttfb_ms": 400, "bytes": 7000, "render_ms": 100.0,
            "etag_present": True, "content_encoding": "br", "status": 200,
        }
        for _ in range(4)
    ]
    summary = gate.summarize_samples(warm)
    assert summary["median_wire_bytes"] == summary["median_bytes"] == 7000
    assert summary["wire_measured_all"] is False  # wire_measured 키 부재 → 전부 폴백


def test_missing_etag_fails_when_required():
    """etag_required 인데 ETag 누락 → FAIL."""
    warm = [dict(_sample(400), etag_present=False) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, _budget(), GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["passed"] is False
    assert any("ETag" in r for r in row["reasons"])


def test_conditional_304_failure_fails():
    """conditional_304_required 인데 304 실패 → FAIL(하트비트 경제성 회귀)."""
    warm = [_sample(400) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, False, _budget(), GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["passed"] is False
    assert any("304" in r for r in row["reasons"])


def test_render_ms_over_budget_fails():
    """render 헤더가 전역 render_ms_max 초과 → FAIL(정밀 서버 회귀 채널)."""
    warm = [_sample(400, render_ms=600.0) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, _budget(), GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["passed"] is False
    assert any("render" in r for r in row["reasons"])


def test_render_ms_absent_is_not_judged():
    """render 헤더 부재(None)면 render 판정 스킵(오탐 금지)."""
    warm = [_sample(400, render_ms=None) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    assert summary["max_render_ms"] is None
    row = gate.judge_path("/x", summary, True, _budget(), GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["passed"] is True


def test_non_200_status_invalidates_measurement():
    """warm 표본에 non-200(302 세션만료/500) → 측정 무효 FAIL."""
    warm = [dict(_sample(400), status=302) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, _budget(), GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["passed"] is False
    assert any("non-200" in r for r in row["reasons"])


# ---------------------------------------------------------------------------
# --seed 마진: max(delta*1.3, delta+80)
# ---------------------------------------------------------------------------
def test_seed_budget_small_delta_uses_absolute_floor():
    """작은 델타(50ms): 상대 30%(65)보다 절대 하한(delta+80=130)이 커서 130."""
    warm = [_sample(250, bytes_=100000) for _ in range(4)]  # min 250
    summary = gate.summarize_samples(warm)
    b = gate.seed_budget(summary, base_ttfb_ms=200)  # delta 50
    assert b["ttfb_delta_min_ms"] == 130  # max(round(50*1.3)=65, 50+80=130)
    assert b["body_bytes_max"] == 130000


def test_seed_budget_large_delta_uses_relative_margin():
    """큰 델타(400ms): 상대 30%(520)가 절대 하한(delta+80=480)보다 커서 520."""
    warm = [_sample(700, bytes_=1000) for _ in range(4)]  # min 700
    summary = gate.summarize_samples(warm)
    b = gate.seed_budget(summary, base_ttfb_ms=300)  # delta 400
    assert b["ttfb_delta_min_ms"] == 520  # max(round(400*1.3)=520, 400+80=480)
    assert b["body_bytes_max"] == 1300


def test_seed_budget_custom_margin():
    warm = [_sample(400, bytes_=1000) for _ in range(4)]  # min 400
    summary = gate.summarize_samples(warm)
    b = gate.seed_budget(summary, base_ttfb_ms=200, margin=0.50, floor_ms=80)  # delta 200
    assert b["ttfb_delta_min_ms"] == 300  # max(round(200*1.5)=300, 200+80=280)
    assert b["body_bytes_max"] == 1500


# ---------------------------------------------------------------------------
# reconcile_seed_budget: 로컬 seed 는 CI 심판석 TTFB 보존, bytes 만 재시드
# ---------------------------------------------------------------------------
def test_reconcile_local_preserves_ci_ttfb_budget():
    """로컬(on_ci=False) + 이전 ttfb 존재 → ttfb 는 CI 값 보존, bytes 는 new, preserved=True."""
    new_budget = {"ttfb_delta_min_ms": 198, "body_bytes_max": 12000}
    old_budget = {"ttfb_delta_min_ms": 276, "body_bytes_max": 9000}
    merged, preserved = gate.reconcile_seed_budget(new_budget, old_budget, on_ci=False)
    assert preserved is True
    assert merged["ttfb_delta_min_ms"] == 276  # CI 심판석 값 보존(로컬 198 오염 차단)
    assert merged["body_bytes_max"] == 12000   # bytes 는 결정적 → 재시드


def test_reconcile_ci_updates_ttfb_budget():
    """CI(on_ci=True) + 이전 ttfb 존재 → ttfb 갱신(심판석 자격), preserved=False."""
    new_budget = {"ttfb_delta_min_ms": 198, "body_bytes_max": 12000}
    old_budget = {"ttfb_delta_min_ms": 276, "body_bytes_max": 9000}
    merged, preserved = gate.reconcile_seed_budget(new_budget, old_budget, on_ci=True)
    assert preserved is False
    assert merged["ttfb_delta_min_ms"] == 198  # CI 러너는 새 측정값을 그대로 반영
    assert merged["body_bytes_max"] == 12000


def test_reconcile_bootstrap_no_prev_ttfb_uses_new():
    """로컬 + 이전 ttfb 없음(최초 부트스트랩, old={}) → ttfb 는 new, preserved=False."""
    new_budget = {"ttfb_delta_min_ms": 198, "body_bytes_max": 12000}
    merged, preserved = gate.reconcile_seed_budget(new_budget, {}, on_ci=False)
    assert preserved is False
    assert merged["ttfb_delta_min_ms"] == 198  # 보존할 이전 값 없음 → 부트스트랩
    assert merged["body_bytes_max"] == 12000


def test_is_ci_detects_github_actions_and_ci_env(monkeypatch):
    """_is_ci(): GITHUB_ACTIONS/CI env 세팅 시 True, 해제 시 False."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    assert gate._is_ci() is False
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert gate._is_ci() is True
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("CI", "true")
    assert gate._is_ci() is True


# ---------------------------------------------------------------------------
# 크리덴셜 부재 → exit 2 (SKIP ≠ 실패)
# ---------------------------------------------------------------------------
def test_missing_credentials_exit_2(monkeypatch):
    """크리덴셜 env 부재 → main() exit 2(게이트 스킵, 실패와 구분)."""
    monkeypatch.delenv("FOMS_STAGING_USERNAME", raising=False)
    monkeypatch.delenv("FOMS_STAGING_PASSWORD", raising=False)
    monkeypatch.setattr("sys.argv", ["staging_perf_gate.py"])
    assert gate.main() == 2


def test_credentials_helper_none_when_blank(monkeypatch):
    monkeypatch.setenv("FOMS_STAGING_USERNAME", "")
    monkeypatch.setenv("FOMS_STAGING_PASSWORD", "")
    assert gate._credentials() is None
    monkeypatch.setenv("FOMS_STAGING_USERNAME", "u")
    monkeypatch.setenv("FOMS_STAGING_PASSWORD", "p")
    assert gate._credentials() == ("u", "p")
