"""ERP 현장 스펙 피커 — 프런트 통합 배선 계약.

2026-08-04 자동 가격계산 제거 후 계약: 플래그(`flag_spec_picker`)가 off면 ERP 주문 폼은
기존과 100% 동일해야 하고(회귀 0), on이면 카탈로그 lazy-load + ▾ 피커 부착 +
저장 스냅샷(manual_override 고정) 수집만 배선된다. 가격엔진(WDC pricing-core)
연동·금액 자동기입·읽기전용 잠금은 존재해서는 안 된다(재도입 가드).
플래그도 함께 개명: env FOMS_ERP_SPEC_PICKER_ENABLED(구 FOMS_ERP_SPEC_CALC_ENABLED
fallback 유지) → 컨텍스트 flag_spec_picker → window.ERP_SPEC_PICKER_ENABLED.

DB 비의존 정적 계약 + context-processor 플래그(기본 on) 동작을 함께 검증한다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
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
    assert js.count("!window.ERP_SPEC_PICKER_ENABLED") >= 3
    # 항목 행 재강화 방지 가드
    assert "erpCalcEnhanced" in js


def test_spec_calc_lazy_loads_catalog_no_render_block() -> None:
    js = _read(SPEC_CALC_JS)
    # 카탈로그/프리셋/옵션은 기존 WDC 엔드포인트 재사용(사용 시점 lazy — 가드 G1/G2)
    assert "/api/wdcalculator/products" in js
    assert "/api/wdcalculator/spec-field-presets" in js
    assert "/api/wdcalculator/additional-options/categories" in js


def test_spec_calc_has_no_auto_pricing_engine() -> None:
    """자동 가격계산 제거(2026-08-04) 재도입 가드: 가격엔진·자동기입·잠금 흔적 금지."""
    js = _read(SPEC_CALC_JS)
    assert "pricing-core.js" not in js
    assert "wdcComputeCurrentEstimateMath" not in js
    assert "readOnly" not in js
    assert "수동 금액으로 전환" not in js
    assert "_recalc" not in js
    assert "erp-calc-price-meta" not in js
    # 저장 성공 후 자동 WDC 매칭도 함께 제거됨
    assert "syncEstimate" not in js
    assert "buildEstimateData" not in js


def test_spec_calc_composite_width_auto_sum() -> None:
    js = _read(SPEC_CALC_JS)
    # 복합 W 표기: 괄호 분해부 제거 후 숫자 토큰 합산(저장 스냅샷 width_mm 용)
    assert "_computeWidthMm" in js
    assert "replace(/\\([^)]*\\)/g" in js


def test_spec_calc_collect_is_always_manual_override() -> None:
    js = _read(SPEC_CALC_JS)
    # 금액은 항상 수동 입력 → 스냅샷 manual_override 고정 + computed=수동 금액
    assert "_manualPriceFromRow" in js
    assert "manual_override: true" in js
    assert "source: 'erp_spec_calc'" in js


@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_spec_calc_collect_snapshot_uses_manual_price(tmp_path: Path) -> None:
    """수동 금액 771000이 스냅샷 computed 전 필드에 그대로 실려야 한다."""
    runner = tmp_path / "erp_spec_calc_manual_collect.js"
    runner.write_text(
        f"""
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

global.window = {{ ERP_SPEC_PICKER_ENABLED: true }};
global.Event = function Event(name, opts) {{ this.name = name; this.opts = opts || {{}}; }};
global.document = {{
  readyState: "loading",
  addEventListener: function () {{}},
  querySelector: function () {{ return null; }},
  querySelectorAll: function () {{ return []; }},
  createElement: function () {{
    return {{
      setAttribute: function () {{}},
      addEventListener: function () {{}}
    }};
  }},
  getElementById: function (id) {{
    if (id === "erp-orderer-select") return {{ value: "라홈" }};
    return null;
  }},
  head: {{ appendChild: function () {{}} }}
}};

vm.runInThisContext(fs.readFileSync({json.dumps(str(SPEC_CALC_JS))}, "utf8"));

const priceInput = {{ value: "771,000원" }};
const row = {{
  __erpPricing: {{
    enabled: true,
    product_id: 14,
    option_rows: [{{ name: "옵션 > A", price: 10000, quantity: 1 }}]
  }},
  querySelector: function (selector) {{
    if (selector === '[data-erp="price"]') return priceInput;
    return null;
  }}
}};

const obj = {{ price: 771000 }};
window.ErpSpecCalc.collectPricing(row, obj);

assert.strictEqual(obj.pricing.manual_override, true);
assert.strictEqual(obj.pricing.product_id, 14);
assert.strictEqual(obj.pricing.computed.base_price, 771000);
assert.strictEqual(obj.pricing.computed.additional_price, 0);
assert.strictEqual(obj.pricing.computed.total_price, 771000);
assert.strictEqual(obj.pricing.computed.final_price, 771000);
assert.strictEqual(obj.pricing.option_rows.length, 1);

// 제품 미해석(레거시/직접입력) 항목은 pricing 미첨부
const bareRow = {{
  __erpPricing: {{ enabled: false, product_id: null, option_rows: [] }},
  querySelector: function () {{ return null; }}
}};
const bareObj = {{}};
window.ErpSpecCalc.collectPricing(bareRow, bareObj);
assert.strictEqual(bareObj.pricing, undefined);
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["node", str(runner)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


# ----- 코어 폼(erp-order-shared.js) 훅: 플래그 게이트, off=no-op -----
def test_shared_form_has_flag_gated_enhance_and_collect_hooks() -> None:
    js = _read(SHARED_JS)
    assert "window.ERP_SPEC_PICKER_ENABLED && window.ErpSpecCalc" in js
    assert "ErpSpecCalc.enhanceItemRow(row, item)" in js
    assert "ErpSpecCalc.collectPricing(row, obj)" in js
    # 저장 성공 후 자동 WDC 매칭 훅은 제거됨(재도입 가드)
    assert "syncEstimate" not in js


def test_spec_calc_runs_only_for_lahom_orderer() -> None:
    js = _read(SPEC_CALC_JS)
    shared_js = _read(SHARED_JS)

    assert "_isLahomOrderer" in js
    assert "document.getElementById('erp-orderer-direct')" in js
    assert "String(ordererName || '') === '라홈'" in js
    assert "if (!window.ERP_SPEC_PICKER_ENABLED || !_isLahomOrderer()) return;" in js
    assert "window.ErpSpecCalc.refreshForOrderer(document)" in shared_js


# ----- 모바일 UX persona -----
def test_spec_calc_css_exists_and_flag_gated_in_template() -> None:
    tpl = _read(ORDER_JS_TPL)
    assert "css/orders/erp-spec-calc.css" in tpl
    # 스타일시트도 플래그 게이트 블록 안에 있어야 함(off=미로드, 회귀 0)
    gated = tpl.split("{% if flag_spec_picker %}", 1)[1]
    assert "erp-spec-calc.css" in gated


def test_spec_calc_css_has_mobile_persona_rules() -> None:
    css = _read(SPEC_CALC_CSS)
    # 모바일 ▾ 트리거 터치 타깃(한 손 조작, 44px)
    assert ".erp-order-mobile-form .erp-calc-trigger" in css
    assert "height: 44px" in css
    # 모바일 컨텍스트로 스코프(데스크톱 회귀 방지)
    assert ".erp-order-mobile-form" in css
    # 자동계산 잠금(읽기전용) 스타일은 제거됨(재도입 가드)
    assert '[data-erp="price"][readonly]' not in css
    assert "erp-calc-unlock-link" not in css


def test_spec_calc_css_does_not_touch_legacy_selectors() -> None:
    """주입 클래스(.erp-calc-*)에만 적용 — 기존 폼 선택자 비침투."""
    css = _read(SPEC_CALC_CSS)
    for line in css.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("/*") or stripped.startswith("*"):
            continue
        if "{" in stripped:
            selector = stripped.split("{", 1)[0]
            assert "erp-calc" in selector, selector


# ----- 템플릿 배선: 플래그 글로벌 주입 + 조건부 defer 로드 -----
def test_order_js_template_injects_global_flag() -> None:
    tpl = _read(ORDER_JS_TPL)
    assert "window.ERP_SPEC_PICKER_ENABLED" in tpl
    assert "flag_spec_picker" in tpl


def test_order_js_template_lazy_includes_module_only_when_flag_on() -> None:
    tpl = _read(ORDER_JS_TPL)
    assert "{% if flag_spec_picker %}" in tpl
    assert "js/orders/erp-spec-calc.js" in tpl
    # 로컬 + defer (perf 계약 G1/G2)
    assert "erp-spec-calc.js') }}?v=" in tpl
    spec_line = next(line for line in tpl.splitlines() if "erp-spec-calc.js" in line)
    assert "defer" in spec_line
    assert "http://" not in spec_line and "https://" not in spec_line


# ----- 플래그 게이트(context processor): 기본 on, 명시적 off만 비활성 -----
def _flags_for_user(app, monkeypatch, env_value, legacy_env_value=None):
    monkeypatch.delenv("FOMS_ERP_SPEC_PICKER_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_ERP_SPEC_CALC_ENABLED", raising=False)
    if env_value is not None:
        monkeypatch.setenv("FOMS_ERP_SPEC_PICKER_ENABLED", env_value)
    if legacy_env_value is not None:
        monkeypatch.setenv("FOMS_ERP_SPEC_CALC_ENABLED", legacy_env_value)
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


def test_inject_foms_flags_spec_picker_on_by_default(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """기본 on — 환경변수 미설정 시 바로 사용 가능."""
    assert _flags_for_user(app, monkeypatch, None)["flag_spec_picker"] is True


def test_inject_foms_flags_spec_picker_explicit_disable(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FOMS_ERP_SPEC_PICKER_ENABLED=false 일 때만 비활성(긴급 킬스위치)."""
    assert _flags_for_user(app, monkeypatch, "false")["flag_spec_picker"] is False


def test_inject_foms_flags_spec_picker_legacy_env_fallback(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """구 FOMS_ERP_SPEC_CALC_ENABLED=false도 킬스위치로 유효(배포 env 호환)."""
    flags = _flags_for_user(app, monkeypatch, None, legacy_env_value="false")
    assert flags["flag_spec_picker"] is False
    # 신규 이름이 설정되면 구 이름보다 우선한다.
    flags = _flags_for_user(app, monkeypatch, "true", legacy_env_value="false")
    assert flags["flag_spec_picker"] is True
