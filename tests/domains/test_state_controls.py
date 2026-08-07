"""STATE-CONTROLS-01 계약 테스트.

두 축을 검증한다.

1. status selector 정본화: measurement/order/listing 대시보드의 inline status
   선택자에서 generic 완료(COMPLETED)·AS(AS/AS_RECEIVED/AS_COMPLETED)·삭제(DELETED)
   option 을 직접 선택 불가로 만든다. 이 전이는 canonical 컨트롤(STATE-AS / DELETE /
   COMPLETE)로만 수행한다. 현재 상태는 항상 보존한다.
2. orphan queue swipe 제거: dead ``/api/foms/queue/*`` route + mock/direct writer
   서비스 + 전역 swipe JS load + old queue macro 를 caller 0 확인 후 제거한다.

경계: 이 packet 은 선택자 option UI + dead swipe 정리만. DELETE/AS/overlay 백엔드
전이 semantics 는 불변(field_update / status SSOT 상수는 그대로).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"

TERMINAL = ("COMPLETED", "AS", "AS_RECEIVED", "AS_COMPLETED", "DELETED")

MEASUREMENT_DASHBOARDS = (
    "measurement/regional_dashboard.html",
    "measurement/self_measurement_dashboard.html",
    "measurement/metropolitan_dashboard.html",
)


# ---------------------------------------------------------------------------
# 1) orphan queue swipe route/service/JS/macro 제거 (caller 0)
# ---------------------------------------------------------------------------

REMOVED_ARTIFACTS = (
    "foms/api/foms_queue_actions.py",
    "foms/services/orders/mobile_queue_action.py",
    "static/js/foms/swipe-actions.js",
    "templates/partials/shared/erp_mobile_queue_card.html",
    "templates/orders/partials/dashboard_mobile_queue.html",
)


@pytest.mark.parametrize("rel", REMOVED_ARTIFACTS)
def test_orphan_swipe_artifact_removed(rel: str) -> None:
    assert not (ROOT / rel).exists(), f"orphan swipe artifact still present: {rel}"


def test_queue_swipe_blueprint_registration_removed() -> None:
    src = (ROOT / "foms/platform/blueprints.py").read_text(encoding="utf-8")
    assert "foms_queue_actions" not in src


def test_global_swipe_js_load_removed() -> None:
    bundle = (TEMPLATES / "partials/shared/foms_p2_surface_bundle.html").read_text(
        encoding="utf-8"
    )
    assert "swipe-actions.js" not in bundle


def test_no_template_loads_swipe_actions_js() -> None:
    offenders = [
        str(p.relative_to(ROOT))
        for p in TEMPLATES.rglob("*.html")
        if "swipe-actions.js" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"global swipe load still present: {offenders}"


def test_no_old_queue_card_macro_reference() -> None:
    """old macro(render_queue_card, v2 아님) import·include 가 0 이어야 한다."""
    pat = re.compile(r"erp_mobile_queue_card\.html|render_queue_card(?!_v2)")
    offenders = [
        str(p.relative_to(ROOT))
        for p in TEMPLATES.rglob("*.html")
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"old queue card macro still referenced: {offenders}"


def test_active_v2_card_has_no_swipe_ui() -> None:
    """active v2 카드가 dead swipe UI 를 부활시키지 않는다."""
    v2 = (TEMPLATES / "partials/shared/erp_mobile_queue_card_v2.html").read_text(
        encoding="utf-8"
    )
    assert "data-foms-swipe-card" not in v2
    assert "data-foms-swipe-action" not in v2


def test_queue_swipe_route_absent_from_url_map() -> None:
    """orphan caller 0 의 런타임 증명 — 앱 URL map 에 /api/foms/queue 라우트 없음."""
    import app

    rules = [r.rule for r in app.app.url_map.iter_rules()]
    assert not any(r.startswith("/api/foms/queue") for r in rules)


# ---------------------------------------------------------------------------
# 2) DELETE/AS/overlay 백엔드 semantics 불변 — UI 만 변경했음을 증명
# ---------------------------------------------------------------------------

def test_status_write_backend_endpoint_intact() -> None:
    """inline status write canonical 엔드포인트(field_update)는 그대로 존속."""
    import app

    rules = [r.rule for r in app.app.url_map.iter_rules()]
    assert "/api/update_order_field" in rules
    assert (ROOT / "foms/api/orders/field_update.py").exists()


def test_status_ssot_constants_still_know_terminal_codes() -> None:
    """백엔드 status SSOT 는 terminal 코드를 그대로 인지 — 제거는 선택자 UI 한정."""
    from foms.services.orders.status_constants import (
        BULK_ACTION_STATUS,
        LOGISTICS_BOARD_STATUS,
        STATUS,
    )

    for code in TERMINAL:
        assert code in STATUS, code
    # bulk 백엔드는 여전히 COMPLETED 검증을 통과시킨다(UI 노출만 제거).
    assert "COMPLETED" in BULK_ACTION_STATUS
    assert "COMPLETED" in LOGISTICS_BOARD_STATUS


# ---------------------------------------------------------------------------
# 3) status selector generic terminal option 0 (role+predicate canonical 전용)
# ---------------------------------------------------------------------------

def _render_macro(status_map: dict, current: str) -> str:
    import app

    tmpl = app.app.jinja_env.get_template("partials/shared/status_select_options.html")
    return str(tmpl.module.assignable_status_options(status_map, current))


def test_assignable_macro_omits_terminal_options() -> None:
    from foms.services.orders.status_constants import LOGISTICS_BOARD_STATUS

    html = _render_macro(LOGISTICS_BOARD_STATUS, "SCHEDULED")
    for code in TERMINAL:
        assert f'value="{code}"' not in html, f"terminal {code} offered as assignable"
    # 물류 중간 상태는 그대로 선택 가능해야 한다.
    assert 'value="SCHEDULED"' in html
    assert 'value="ON_HOLD"' in html


def test_assignable_macro_preserves_current_terminal_status() -> None:
    """현재가 terminal(예: 완료)이면 표시·submit 보존, 그 외 terminal 은 여전히 미노출."""
    from foms.services.orders.status_constants import LOGISTICS_BOARD_STATUS

    html = _render_macro(LOGISTICS_BOARD_STATUS, "COMPLETED")
    assert 'value="COMPLETED" selected' in html
    assert 'value="DELETED"' not in html
    assert 'value="AS_RECEIVED"' not in html


@pytest.mark.parametrize("rel", MEASUREMENT_DASHBOARDS)
def test_measurement_dashboard_compiles(rel: str) -> None:
    import app

    app.app.jinja_env.get_template(rel)  # TemplateSyntaxError 면 실패


# 지방 보드는 2026-08-07 개편에서 선택자를 전부 버리고 뱃지로 갔다(섹션=상태).
SELECTOR_DASHBOARDS = (
    "measurement/self_measurement_dashboard.html",
    "measurement/metropolitan_dashboard.html",
)


@pytest.mark.parametrize("rel", SELECTOR_DASHBOARDS)
def test_measurement_setters_use_canonical_macro(rel: str) -> None:
    src = (TEMPLATES / rel).read_text(encoding="utf-8")
    assert "assignable_status_options" in src
    # raw status-map setter loop(모든 status dump)이 남아있으면 안 된다.
    assert "LOGISTICS_BOARD_STATUS.items()" not in src
    assert "STATUS.items()" not in src


def test_regional_board_has_no_status_selector_macro() -> None:
    """지방 보드는 status 선택자 자체를 쓰지 않는다(뱃지 + canonical 버튼만)."""
    src = (TEMPLATES / "measurement/regional_dashboard.html").read_text(encoding="utf-8")
    assert "assignable_status_options" not in src
    assert "board_status_badge" in src


def test_orders_index_bulk_status_excludes_terminal() -> None:
    src = (TEMPLATES / "orders/index.html").read_text(encoding="utf-8")
    loops = re.findall(r"BULK_ACTION_STATUS\.items\(\)([^%]*)%\}", src)
    assert loops, "bulk status loop not found"
    for tail in loops:
        assert "if code not in" in tail, "bulk status loop missing terminal exclusion"


# ---------------------------------------------------------------------------
# 4) STATE-CONTROLS-02: canonical COMPLETE control — 선택자에서 제거한 COMPLETED
#    전이의 정식 진입점(대시보드 행 완료 버튼). 없으면 보드에서 완료 처리 불가 회귀.
# ---------------------------------------------------------------------------

def _render_complete_control(current: str) -> str:
    import app

    tmpl = app.app.jinja_env.get_template("partials/shared/status_select_options.html")
    return str(tmpl.module.complete_order_control(4552, current))


def test_complete_control_renders_for_active_status() -> None:
    html = _render_complete_control("MEASURE")
    assert "js-complete-order" in html
    assert 'data-order-id="4552"' in html


@pytest.mark.parametrize("code", TERMINAL)
def test_complete_control_hidden_for_terminal_status(code: str) -> None:
    """이미 terminal(완료·AS 계열·삭제)인 행에는 완료 버튼을 렌더하지 않는다."""
    assert _render_complete_control(code).strip() == ""


@pytest.mark.parametrize("rel", MEASUREMENT_DASHBOARDS)
def test_measurement_dashboards_wire_complete_control(rel: str) -> None:
    """3개 measurement 대시보드 모두 완료 버튼 매크로 + 배선 JS 를 로드한다.

    사용자 결정(2026-08-07): 완료 버튼은 '설치 예정' 계열 섹션 1곳에만 노출
    (지방=설치예정, 자가실측=설치예정, 수도권=설치 알림). 전 섹션 확산 금지.
    """
    src = (TEMPLATES / rel).read_text(encoding="utf-8")
    sites = src.count("complete_order_control(order.id")
    assert sites == 1, f"{rel}: complete control sites {sites} != 1 (설치예정 전용)"
    assert "complete-order-btn.js" in src, f"{rel}: complete control JS not loaded"


def test_regional_board_wires_as_complete_control() -> None:
    """지방 AS 섹션은 canonical AS 완료 컨트롤 1곳을 배선한다.

    status 직접 쓰기가 아니라 as_completed_date(complete_as_cycle 브리지)여야 AS
    대시보드 '완료' 탭 조건(status+as_completed_date 동시 충족)을 만족한다.
    """
    src = (TEMPLATES / "measurement/regional_dashboard.html").read_text(encoding="utf-8")
    assert src.count("as_complete_control(order.id") == 1
    macro = (TEMPLATES / "partials/shared/status_select_options.html").read_text(
        encoding="utf-8"
    )
    assert 'data-field="as_completed_date"' in macro
    assert 'data-value="AS_COMPLETED"' not in macro


def test_complete_control_js_exists() -> None:
    assert (ROOT / "static/js/measurement/complete-order-btn.js").exists()


# ---------------------------------------------------------------------------
# 5) 보드별 드롭다운 SSOT (2026-08-07 사용자 결정): 자가실측 3종·수도권 물류 4종.
#    화면 프로세스와 무관한 legacy 옵션(지방실측 등)·메인 파이프라인 유입 금지.
# ---------------------------------------------------------------------------

def test_board_status_maps_curated() -> None:
    from foms.services.orders import status_constants
    from foms.services.orders.status_constants import (
        LOGISTICS_BOARD_CODES,
        METRO_BOARD_STATUS,
        SELF_BOARD_STATUS,
    )

    assert set(SELF_BOARD_STATUS) == {"MEASURED", "SCHEDULED", "ON_HOLD"}
    assert set(METRO_BOARD_STATUS) == {
        "MEASURED", "SCHEDULED", "SHIPPED_PENDING", "ON_HOLD",
    }
    # 물류 상태의 부분집합이어야 field_update stage-override 가드를 그대로 탄다.
    assert set(SELF_BOARD_STATUS) <= LOGISTICS_BOARD_CODES
    assert set(METRO_BOARD_STATUS) <= LOGISTICS_BOARD_CODES
    # 지방 보드는 드롭다운이 없으므로 전용 맵도 없어야 한다(부활 방지).
    assert not hasattr(status_constants, "REGIONAL_BOARD_STATUS")


def test_dashboards_use_curated_board_maps() -> None:
    src_regional = (TEMPLATES / "measurement/regional_dashboard.html").read_text(
        encoding="utf-8"
    )
    src_self = (TEMPLATES / "measurement/self_measurement_dashboard.html").read_text(
        encoding="utf-8"
    )
    src_metro = (TEMPLATES / "measurement/metropolitan_dashboard.html").read_text(
        encoding="utf-8"
    )
    assert "assignable_status_options" not in src_regional
    assert "assignable_status_options(SELF_BOARD_STATUS" in src_self
    assert "assignable_status_options(LOGISTICS_BOARD_STATUS" not in src_self
    assert "assignable_status_options(METRO_BOARD_STATUS" in src_metro
    assert "assignable_status_options(STATUS," not in src_metro
