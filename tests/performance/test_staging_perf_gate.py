"""스테이징 성능 게이트 — 네트워크 없는 단위 테스트.

핵심 계약:
  - budgets 파일 존재 + 스키마 유효(9 경로 · 전역 예산).
  - 판정 함수는 **median 만** 본다: median 초과→FAIL, p95 폭주해도 median 정상→PASS
    (한국↔싱가포르 tail 내성 — 게이트 상습 오탐 방지의 심장).
  - --seed 마진 계산(실측 + 30%).
  - 크리덴셜 부재 → exit 2(게이트 SKIP ≠ 실패).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.perf import staging_perf_gate as gate
from foms.services.common.erp_navigation_contract import ERP_PRIMARY_NAV_PATHS

GLOBAL_BUDGET = {"render_ms_max": 500, "etag_required": True, "conditional_304_required": True}


def _sample(ttfb_ms: int, bytes_: int = 1000, render_ms: float | None = 100.0) -> dict:
    return {
        "ttfb_ms": ttfb_ms,
        "bytes": bytes_,
        "render_ms": render_ms,
        "etag_present": True,
        "content_encoding": "br",
    }


# ---------------------------------------------------------------------------
# budgets 파일 스키마
# ---------------------------------------------------------------------------
def test_budgets_file_exists_and_valid_schema():
    """perf_budgets.json 이 존재하고 9 경로 + 전역 예산 스키마를 만족한다."""
    budgets = json.loads(gate.BUDGETS_PATH.read_text(encoding="utf-8"))
    assert "_global" in budgets and "paths" in budgets

    g = budgets["_global"]
    assert isinstance(g["render_ms_max"], int)
    assert isinstance(g["etag_required"], bool)
    assert isinstance(g["conditional_304_required"], bool)

    expected = {gate.fragment_path(p) for p in ERP_PRIMARY_NAV_PATHS}
    assert set(budgets["paths"]) == expected, "budgets 경로가 nav 계약 9경로와 일치해야 한다"
    for path, b in budgets["paths"].items():
        assert isinstance(b["ttfb_warm_median_ms"], int) and b["ttfb_warm_median_ms"] > 0, path
        assert isinstance(b["body_bytes_max"], int) and b["body_bytes_max"] > 0, path


def test_fragment_paths_match_nav_contract():
    """게이트 경로 목록 = nav 계약 SSOT(9개, ?view=fragment)."""
    assert len(gate.FRAGMENT_PATHS) == len(ERP_PRIMARY_NAV_PATHS) == 9
    assert all(p.endswith("?view=fragment") for p in gate.FRAGMENT_PATHS)


# ---------------------------------------------------------------------------
# 판정: median 기준 · tail 내성
# ---------------------------------------------------------------------------
def test_median_over_budget_fails():
    """warm median TTFB 가 예산 초과 → FAIL."""
    warm = [_sample(700), _sample(720), _sample(710), _sample(730)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, {"ttfb_warm_median_ms": 600, "body_bytes_max": 5000}, GLOBAL_BUDGET)
    assert row["passed"] is False
    assert any("TTFB median" in r for r in row["reasons"])


def test_median_within_budget_passes():
    """warm median TTFB 가 예산 이내 → PASS."""
    warm = [_sample(400), _sample(420), _sample(410), _sample(430)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, {"ttfb_warm_median_ms": 600, "body_bytes_max": 5000}, GLOBAL_BUDGET)
    assert row["passed"] is True
    assert row["reasons"] == []


def test_p95_spike_does_not_fail_when_median_ok():
    """tail 내성 계약: p95/max 가 폭주(9000ms)해도 median 이 정상이면 PASS.

    한국↔싱가포르 네트워크 tail 이 정상 존재하므로 tail 은 절대 판정에 들지 않는다.
    """
    warm = [_sample(400), _sample(420), _sample(410), _sample(9000)]  # 마지막이 tail 스파이크
    summary = gate.summarize_samples(warm)
    assert summary["max_ttfb_ms"] == 9000
    assert summary["p95_ttfb_ms"] >= 420
    assert summary["median_ttfb_ms"] <= 600  # median 은 tail 에 안 흔들림
    row = gate.judge_path("/x", summary, True, {"ttfb_warm_median_ms": 600, "body_bytes_max": 5000}, GLOBAL_BUDGET)
    assert row["passed"] is True, "median 정상인데 p95 tail 로 FAIL 나면 tail 내성 계약 위반"


def test_bytes_over_budget_fails():
    """median bytes 가 예산 초과 → FAIL."""
    warm = [_sample(400, bytes_=9000), _sample(400, bytes_=9100), _sample(400, bytes_=9050), _sample(400, bytes_=9000)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, {"ttfb_warm_median_ms": 600, "body_bytes_max": 5000}, GLOBAL_BUDGET)
    assert row["passed"] is False
    assert any("bytes" in r for r in row["reasons"])


def test_missing_etag_fails_when_required():
    """etag_required 인데 ETag 누락 → FAIL."""
    warm = [dict(_sample(400), etag_present=False) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, {"ttfb_warm_median_ms": 600, "body_bytes_max": 5000}, GLOBAL_BUDGET)
    assert row["passed"] is False
    assert any("ETag" in r for r in row["reasons"])


def test_conditional_304_failure_fails():
    """conditional_304_required 인데 304 실패 → FAIL(하트비트 경제성 회귀)."""
    warm = [_sample(400) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, False, {"ttfb_warm_median_ms": 600, "body_bytes_max": 5000}, GLOBAL_BUDGET)
    assert row["passed"] is False
    assert any("304" in r for r in row["reasons"])


def test_render_ms_over_budget_fails():
    """render 헤더가 전역 render_ms_max 초과 → FAIL."""
    warm = [_sample(400, render_ms=600.0) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    row = gate.judge_path("/x", summary, True, {"ttfb_warm_median_ms": 600, "body_bytes_max": 5000}, GLOBAL_BUDGET)
    assert row["passed"] is False
    assert any("render" in r for r in row["reasons"])


def test_render_ms_absent_is_not_judged():
    """render 헤더 부재(None)면 render 판정 스킵(오탐 금지)."""
    warm = [_sample(400, render_ms=None) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    assert summary["max_render_ms"] is None
    row = gate.judge_path("/x", summary, True, {"ttfb_warm_median_ms": 600, "body_bytes_max": 5000}, GLOBAL_BUDGET)
    assert row["passed"] is True


# ---------------------------------------------------------------------------
# --seed 마진
# ---------------------------------------------------------------------------
def test_seed_budget_applies_30pct_margin():
    """seed 예산 = 실측 median * 1.30(반올림)."""
    warm = [_sample(500, bytes_=100000) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    b = gate.seed_budget(summary, margin=0.30)
    assert b["ttfb_warm_median_ms"] == 650
    assert b["body_bytes_max"] == 130000


def test_seed_budget_custom_margin():
    warm = [_sample(200, bytes_=1000) for _ in range(4)]
    summary = gate.summarize_samples(warm)
    b = gate.seed_budget(summary, margin=0.50)
    assert b["ttfb_warm_median_ms"] == 300
    assert b["body_bytes_max"] == 1500


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
