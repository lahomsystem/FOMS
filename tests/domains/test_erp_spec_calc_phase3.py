"""Phase 3: ERP 현장 스펙 즉시견적 — 프런트 통합 배선 계약.

플래그(`flag_spec_calc`)가 off면 ERP 주문 폼은 기존과 100% 동일해야 하고(회귀 0),
on이면 엔진/카탈로그 lazy-load + 드롭다운 부착 + 라이브 계산 모듈이 배선돼야 한다.

DB 비의존 정적 계약 + context-processor 플래그(기본 on) 동작을 함께 검증한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from foms.services.context_processors import inject_foms_flags
from models import User

ROOT = Path(__file__).resolve().parents[2]

SPEC_CALC_JS = ROOT / "static/js/orders/erp-spec-calc.js"
SPEC_CALC_CSS = ROOT / "static/css/orders/erp-spec-calc.css"
SHARED_JS = ROOT / "static/js/orders/erp-order-shared.js"
ORDER_JS_TPL = ROOT / "templates/orders/partials/erp_order_js.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ----- 모듈 자체 계약 -----
def test_spec_calc_module_exists_and_exposes_public_api() -> None:
    js = _read(SPEC_CALC_JS)
    assert "window.ErpSpecCalc" in js
    assert "enhanceItemRow" in js
    assert "collectPricing" in js


def test_spec_calc_module_is_flag_gated_and_idempotent() -> None:
    js = _read(SPEC_CALC_JS)
    # 단일 바인딩 가드(G4)
    assert "window.__erpSpecCalcBound" in js
    # 공개 메서드는 플래그 off면 즉시 반환(무영향)
    assert js.count("if (!window.ERP_SPEC_CALC_ENABLED) return;") >= 2
    # 항목 행 재강화 방지 가드
    assert "erpCalcEnhanced" in js


def test_spec_calc_lazy_loads_engine_and_catalog_no_render_block() -> None:
    js = _read(SPEC_CALC_JS)
    # 가격 엔진은 사용 시점 lazy 로드(전역/렌더 차단 금지 — 가드 G1/G2)
    assert "/static/js/wdcalculator/pricing-core.js" in js
    assert "wdcComputeCurrentEstimateMath" in js
    # 카탈로그/프리셋/옵션은 기존 WDC 엔드포인트 재사용
    assert "/api/wdcalculator/products" in js
    assert "/api/wdcalculator/spec-field-presets" in js
    assert "/api/wdcalculator/additional-options/categories" in js


def test_spec_calc_escapes_user_text_for_xss() -> None:
    js = _read(SPEC_CALC_JS)
    # 동적 option 라벨 주입 시 textContent 기반 escape 사용
    assert "_escape" in js
    assert "textContent" in js


def test_spec_calc_composite_width_auto_sum() -> None:
    js = _read(SPEC_CALC_JS)
    # 복합 W 표기: 괄호 분해부 제거 후 숫자 토큰 합산(원문 보존은 입력칸 유지)
    assert "_computeWidthMm" in js
    assert "replace(/\\([^)]*\\)/g" in js


def test_spec_calc_price_lock_with_manual_override() -> None:
    js = _read(SPEC_CALC_JS)
    # 기본 읽기전용 + 수동전환 토글
    assert "manual_override" in js
    assert "readOnly" in js
    assert "수동 금액으로 전환" in js


# ----- 코어 폼(erp-order-shared.js) 훅: 플래그 게이트, off=no-op -----
def test_shared_form_has_flag_gated_enhance_and_collect_hooks() -> None:
    js = _read(SHARED_JS)
    assert "window.ERP_SPEC_CALC_ENABLED && window.ErpSpecCalc" in js
    assert "ErpSpecCalc.enhanceItemRow(row, item)" in js
    assert "ErpSpecCalc.collectPricing(row, obj)" in js


# ----- Phase 4: 저장 dual-write/자동매칭 -----
def test_spec_calc_module_builds_estimate_data_and_syncs() -> None:
    js = _read(SPEC_CALC_JS)
    assert "buildEstimateData" in js
    assert "syncEstimate" in js
    # WDC 표준 estimate_data 키(견적서 렌더 호환)
    assert "totalBasePrice" in js
    assert "estimates" in js
    # 자동매칭 엔드포인트 호출
    assert "/wdc-estimate-sync" in js
    # estimate_id 라운드트립(meta 반영 → 다음 저장은 upsert)
    assert "wdc_estimate_id" in js


def test_shared_form_calls_sync_after_save_success() -> None:
    js = _read(SHARED_JS)
    assert "ErpSpecCalc.syncEstimate(targetId, structured_data)" in js
    # fail-open: try/catch로 감싸 저장 결과에 영향 없음
    assert "estimate sync 실패" in js


# ----- Phase 5: 모바일 UX persona 마감 -----
def test_spec_calc_css_exists_and_flag_gated_in_template() -> None:
    tpl = _read(ORDER_JS_TPL)
    assert "css/orders/erp-spec-calc.css" in tpl
    # 스타일시트도 플래그 게이트 블록 안에 있어야 함(off=미로드, 회귀 0)
    gated = tpl.split("{% if flag_spec_calc %}", 1)[1]
    assert "erp-spec-calc.css" in gated


def test_spec_calc_css_has_mobile_persona_rules() -> None:
    css = _read(SPEC_CALC_CSS)
    # 48px 터치 타깃(한 손 조작)
    assert "min-height: 48px" in css
    # 모바일 컨텍스트로 스코프(데스크톱 회귀 방지)
    assert ".erp-order-mobile-form" in css
    # 자동계산 잠금 금액 즉시 피드백(읽기전용 시각 구분)
    assert '[data-erp="price"][readonly]' in css


def test_spec_calc_css_does_not_touch_legacy_selectors() -> None:
    """주입 클래스(.erp-calc-*)와 readonly 상태에만 적용 — 기존 폼 선택자 비침투."""
    css = _read(SPEC_CALC_CSS)
    for line in css.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("/*") or stripped.startswith("*"):
            continue
        if "{" in stripped:
            selector = stripped.split("{", 1)[0]
            assert ("erp-calc" in selector) or ("[readonly]" in selector), selector


# ----- 템플릿 배선: 플래그 글로벌 주입 + 조건부 defer 로드 -----
def test_order_js_template_injects_global_flag() -> None:
    tpl = _read(ORDER_JS_TPL)
    assert "window.ERP_SPEC_CALC_ENABLED" in tpl
    assert "flag_spec_calc" in tpl


def test_order_js_template_lazy_includes_module_only_when_flag_on() -> None:
    tpl = _read(ORDER_JS_TPL)
    assert "{% if flag_spec_calc %}" in tpl
    assert "js/orders/erp-spec-calc.js" in tpl
    # 로컬 + defer (perf 계약 G1/G2)
    assert "erp-spec-calc.js') }}?v=" in tpl
    spec_line = next(line for line in tpl.splitlines() if "erp-spec-calc.js" in line)
    assert "defer" in spec_line
    assert "http://" not in spec_line and "https://" not in spec_line


# ----- 플래그 게이트(context processor): 기본 on, 명시적 off만 비활성 -----
def _flags_for_user(app, monkeypatch, env_value):
    if env_value is None:
        monkeypatch.delenv("FOMS_ERP_SPEC_CALC_ENABLED", raising=False)
    else:
        monkeypatch.setenv("FOMS_ERP_SPEC_CALC_ENABLED", env_value)
    user = User(
        username="spec_calc_ctx",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="SpecCalc Ctx",
        is_active=True,
    )
    user.id = 55
    with app.test_request_context("/erp/dashboard"):
        from flask import g

        g.current_user = user
        return inject_foms_flags()


def test_inject_foms_flags_spec_calc_on_by_default(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """기본 on — 환경변수 미설정 시 바로 사용 가능."""
    assert _flags_for_user(app, monkeypatch, None)["flag_spec_calc"] is True


def test_inject_foms_flags_spec_calc_explicit_disable(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FOMS_ERP_SPEC_CALC_ENABLED=false 일 때만 비활성(긴급 킬스위치)."""
    assert _flags_for_user(app, monkeypatch, "false")["flag_spec_calc"] is False
