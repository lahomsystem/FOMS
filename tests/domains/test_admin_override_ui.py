"""관리자 강제 진행(ADMIN-OVERRIDE-01) 화면·타임라인 계약.

여기서 고정하는 것은 세 가지다.
1. 강제 변경 모달의 AS 3종·삭제 목표는 관리자에게만 보인다(매니저는 음성 대조군).
2. 공통 재시도 JS 가 권한 축만 다시 보내고, 시트가 없으면 무음으로 넘어가지 않는다.
3. ``ADMIN_OVERRIDE_USED`` 는 타임라인에 한글로 보이되 **단계 이벤트는 아니다**
   (단계 집합에 넣으면 밟지도 않은 유령 단계 행이 생긴다).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import render_template

from foms.services import order_event_display, order_timeline_v3

REPO_ROOT = Path(__file__).resolve().parents[2]
MODAL_TEMPLATE = "orders/partials/erp_stage_override_modal.html"
SHEET_TEMPLATE = REPO_ROOT / "templates" / "partials" / "shared" / "foms_reason_sheet.html"
MODAL_PATH = REPO_ROOT / "templates" / "orders" / "partials" / "erp_stage_override_modal.html"
ADMIN_OVERRIDE_JS = REPO_ROOT / "static" / "js" / "foms" / "foms-admin-override.js"
REASON_SHEET_JS = REPO_ROOT / "static" / "js" / "foms" / "foms-reason-sheet.js"
STAGE_OVERRIDE_JS = REPO_ROOT / "static" / "js" / "orders" / "erp-stage-override.js"

# 재시도를 배선한 화면은 시트 include 와 두 스크립트가 반드시 세트여야 한다.
RETRY_WIRED_TEMPLATES = [
    "templates/orders/dashboard.html",
    "templates/orders/partials/erp_order_js.html",
    "templates/construction/partials/mobile_queue.html",
    "templates/production/partials/mobile_queue.html",
    "templates/partials/v3/persona_home_construction.html",
    "templates/partials/v3/persona_home_production.html",
    "templates/measurement/metropolitan_dashboard.html",
    "templates/measurement/regional_dashboard.html",
    "templates/measurement/self_measurement_dashboard.html",
    "templates/construction/partials/scripts.html",
    "templates/orders/partials/order_detail_mobile_v2.html",
    "templates/production/partials/tablet_kanban_body.html",
    "templates/shipment/layout.html",
]

# 출고는 파샬(templates/shipment/partials/dashboard_scripts.html)이 아니라 **셸**
# (templates/shipment/layout.html)에 한 번만 싣는다 — 그 파샬은 <script src> 2개 상한이
# perf_scan fragment-multi-script veto 로 고정돼 있다
# (tests/domains/test_shipment_change_alert_render.py). 파샬은 무변경이어야 한다.

# 거부 응답을 공통 재시도 컨트롤러로 넘기는 호출부. 한 곳이라도 빠지면 그 화면의
# 관리자는 거부 문구만 보고 끝난다(서버는 뚫을 수 있는데 화면에 길이 없다).
RETRY_CALLER_SCRIPTS = [
    "static/js/measurement/complete-order-btn.js",
    "static/js/measurement/drawing-transfer-btn.js",
    "static/js/foms/erp-quest-approve.js",
    "static/js/construction/dashboard.js",
    "static/js/foms/tablet-domain-sheets.js",
    "static/js/foms/tablet-production-kanban.js",
    "static/js/orders/erp-order-shared.js",
    "static/js/orders/dashboard/erp-dashboard-quest.js",
    "static/js/orders/erp-stage-override.js",
]

#: 재시도를 배선한 JS 가 템플릿에 실릴 때 붙어야 하는 자산 핀.
RETRY_ASSET_PIN = "20260921a"

ADMIN_ONLY_OPTIONS = [
    '<option value="AS_RECEIVED">',
    '<option value="AS">',
    '<option value="AS_COMPLETED">',
    '<option value="DELETED">',
]


def _render_modal(app, role: str) -> str:
    """주어진 역할로 강제 변경 모달만 렌더한다."""
    user = SimpleNamespace(id=1, role=role, name="테스트", team="CS")
    with app.test_request_context("/"):
        return render_template(MODAL_TEMPLATE, current_user=user)


def test_모달은_관리자에게_AS_3종과_삭제_목표를_보여_준다(app):
    html = _render_modal(app, "ADMIN")
    for option in ADMIN_ONLY_OPTIONS:
        assert option in html
    assert "AS·삭제(관리자 전용)" in html
    assert '<optgroup label="본공정">' in html


def test_모달은_매니저에게_AS_삭제_목표를_보여_주지_않는다(app):
    """음성 대조군 — 매니저 화면은 한 글자도 바뀌지 않는다."""
    html = _render_modal(app, "MANAGER")
    assert '<option value="AS_RECEIVED">' not in html
    assert '<option value="AS_COMPLETED">' not in html
    assert '<option value="DELETED">' not in html
    assert "AS·삭제(관리자 전용)" not in html
    # 본공정 8단계와 모달 가시성은 그대로다.
    assert '<option value="COMPLETED">' in html
    assert 'data-can-stage-override="1"' in html


def test_모달에_AS_포함_체크박스와_경고_문구가_있다(app):
    html = _render_modal(app, "ADMIN")
    assert 'id="erp-stage-override-include-as"' in html
    assert "AS 접수·완료 상태인 주문도 함께 바꾸기" in html
    assert "본공정 단계는 그대로 두고 AS 건만 엽니다." in html
    assert "휴지통으로 보냅니다. 복구할 수 있습니다." in html


def test_모달과_시트_템플릿에_인라인_style_이_없다():
    for path in (MODAL_PATH, SHEET_TEMPLATE):
        body = path.read_text(encoding="utf-8")
        assert ' style="' not in body, f"{path} 에 인라인 style 이 들어갔다"


def test_공통_재시도_JS_가_권한_축만_다시_보낸다():
    body = ADMIN_OVERRIDE_JS.read_text(encoding="utf-8")
    # 뚫는 축은 본문 두 키뿐이다.
    assert "admin_override" in body
    assert "override_reason" in body
    # 본문이 바뀌므로 멱등 키를 새로 만든다(같은 키면 서버가 409 를 낸다).
    assert "Idempotency-Key" in body
    assert "newIdempotencyKey" in body
    # fetch 는 try/catch + data.success 검증.
    assert "data.success" in body
    assert "try" in body and "catch" in body
    # jQuery 금지.
    assert "jQuery" not in body
    assert "$(" not in body
    # 시트가 없으면 무음으로 넘어가지 않는다.
    assert "no-sheet" in body
    # 정합 축은 재시도 목록에 없다 — 사유를 적어도 다시 보내지 않는다.
    retryable = body.split("var RETRYABLE_CODES")[1].split("]")[0]
    for forbidden in ("ALREADY_STARTED", "ADMIN_ONLY", "REASON_REQUIRED"):
        assert forbidden not in retryable
    for allowed in ("USE_CS_COMPLETE", "INVALID_STAGE", "EVIDENCE_MISSING", "OVERRIDE_BLOCK"):
        assert allowed in retryable


def test_재시도_배선_페이지는_시트와_두_스크립트를_세트로_갖는다():
    for rel in RETRY_WIRED_TEMPLATES:
        body = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "partials/shared/foms_reason_sheet.html" in body, rel
        assert "js/foms/foms-reason-sheet.js" in body, rel
        assert "js/foms/foms-admin-override.js" in body, rel


@pytest.mark.parametrize("rel", RETRY_WIRED_TEMPLATES)
def test_재시도_배선_페이지의_자산_핀이_올라가_있다(rel):
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "js/foms/foms-admin-override.js') }}?v=20260921a" in body


@pytest.mark.parametrize("rel", RETRY_CALLER_SCRIPTS)
def test_거부_처리_분기가_공통_재시도를_부른다(rel):
    """게이트 거부를 받는 화면 JS 가 FomsAdminOverride.retry 를 실제로 부른다."""
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "FomsAdminOverride" in body, rel
    assert ".retry(" in body, rel
    # 컨트롤러가 없는 화면에서도 무음으로 죽지 않는다(원래 오류를 그대로 띄운다).
    assert "typeof ctl.retry" in body or "typeof ctl.retry !==" in body, rel


def test_관리자_판정용_전역_role_이_모든_레이아웃에_있다():
    """canOverride() 는 window.MY_ROLE 만 본다 — 공용 레이아웃이 그것을 심는다."""
    body = (REPO_ROOT / "templates" / "partials" / "shared" / "layout_scripts.html").read_text(
        encoding="utf-8"
    )
    assert "window.MY_ROLE = window.MY_ROLE ||" in body


def test_타임라인이_관리자_강제_진행을_한글로_보여_준다():
    assert (
        order_event_display.translate_event_type_to_korean("ADMIN_OVERRIDE_USED")
        == "관리자 강제 진행"
    )
    payload = {
        "gate": "USE_CS_COMPLETE",
        "gates": ["USE_CS_COMPLETE", "QUEST_INCOMPLETE"],
        "route": "erp_orders_cs.api_cs_complete",
        "axis": "MAIN",
        "from": "CONSTRUCTION",
        "to": "COMPLETED",
        "reason": "고객 요청으로 잔여 절차 생략",
        "actor": {"id": 12, "name": "김관리", "role": "ADMIN"},
        "bulk": False,
    }
    text = order_event_display.generate_change_description(
        "ADMIN_OVERRIDE_USED", "", "", "", payload
    )
    assert "관리자가 검사를 건너뛰고 진행했습니다" in text
    assert "완료 경로" in text
    assert "필수 승인" in text
    assert "고객 요청으로 잔여 절차 생략" in text


def test_게이트가_하나면_gate_키만으로도_한글이_나온다():
    text = order_event_display.generate_change_description(
        "ADMIN_OVERRIDE_USED", "", "", "", {"gate": "HOLD_ACTIVE", "reason": "긴급"}
    )
    assert "보류" in text
    assert "긴급" in text


def test_모르는_게이트_코드는_지우지_않고_그대로_보여_준다():
    text = order_event_display.generate_change_description(
        "ADMIN_OVERRIDE_USED", "", "", "", {"gates": ["NEW_GATE_X"], "reason": "r"}
    )
    assert "NEW_GATE_X" in text


def test_관리자_강제_진행은_단계_이벤트가_아니다():
    """음성 대조군 — 단계 집합에 들어가면 유령 단계 행이 생긴다."""
    assert "ADMIN_OVERRIDE_USED" not in order_event_display._STAGE_EVENT_TYPES
    assert "ADMIN_OVERRIDE_USED" not in order_timeline_v3._STAGE_EVENT_TYPES
    # 대조군: 진짜 단계 이벤트는 두 집합에 모두 있다.
    assert "STAGE_OVERRIDE" in order_event_display._STAGE_EVENT_TYPES
    assert "STAGE_OVERRIDE" in order_timeline_v3._STAGE_EVENT_TYPES

def test_재시도를_배선한_JS_는_전부_새_핀으로_실린다():
    """바뀐 JS 의 자산 핀을 안 올리면 브라우저 캐시가 옛 파일을 살려 재시도가 안 뜬다.

    호출부 JS 는 화면마다 다른 템플릿이 싣는다 — 한 줄이라도 옛 핀이면 그 화면의
    관리자는 거부 문구만 보고 끝난다.
    """
    import re as _re

    missed = []
    for rel in RETRY_CALLER_SCRIPTS:
        # basename 으로 찾으면 다른 dashboard.js 까지 걸린다 — static/ 뒤 전체 경로로 짚는다.
        name = rel[len("static/"):]
        for tpl in (REPO_ROOT / "templates").rglob("*.html"):
            for line in tpl.read_text(encoding="utf-8").splitlines():
                if name not in line or "?v=" not in line:
                    continue
                # 계약은 "재시도 배선 이후의 핀" 이다 — 같은 값이 아니라 **그보다 낡지 않은**
                # 값. 리터럴 동일성으로 재면 그 뒤 정당한 범프(2026-09-21 AS 접수 머무름,
                # erp-order-shared.js 20260921b)마다 무관한 커밋이 빨개진다. 날짜+접미 핀은
                # 사전순이 시간순이다.
                found = _re.search(r"\?v=([0-9]{8}[a-z]?)", line)
                if not found or found.group(1) < RETRY_ASSET_PIN:
                    missed.append(f"{tpl.relative_to(REPO_ROOT).as_posix()}: {line.strip()}")
    assert not missed, "재시도 배선 JS 인데 핀이 안 올라간 곳: " + "; ".join(missed)


def test_출고_파샬은_스크립트_2개_상한을_그대로_지킨다():
    """음성 대조군 — 배선은 셸에만 올린다. 파샬을 건드리면 perf_scan veto 가 난다."""
    body = (REPO_ROOT / "templates" / "shipment" / "partials"
            / "dashboard_scripts.html").read_text(encoding="utf-8")
    assert body.count("<script src=") == 2
    assert "foms-admin-override.js" not in body
    assert "foms_reason_sheet.html" not in body


def test_강제_변경_모달은_관리자일_때만_완료_목표에_뚫기를_싣는다():
    """완료 목표는 CS 게이트를 지나므로 ADMIN 요청만 권한 축을 함께 켠다.

    매니저는 현행 그대로 409 다 — 그래서 MANAGER 까지 포함하는 ``canOverride()`` 가 아니라
    ADMIN 만 보는 판정을 쓴다.
    """
    body = STAGE_OVERRIDE_JS.read_text(encoding="utf-8")
    assert "adminTargetKind(to) || (to === 'COMPLETED' && isAdminRole())" in body
    assert "body.admin_override = true;" in body
    assert "body.override_reason = reason;" in body
    # 음성 대조군: 매니저까지 포함하는 판정으로 뚫기를 싣지 않는다.
    assert "canOverride() && to === " not in body


def test_강제_변경_화면의_409_는_코드로_갈린다():
    """REV 충돌만 '다른 탭' 문구다 — 게이트 코드는 서버 문구를 그대로 띄운다."""
    body = STAGE_OVERRIDE_JS.read_text(encoding="utf-8")
    assert "REV_CONFLICT_CODES" in body
    assert "'REVISION_CONFLICT'" in body
    assert "'IDEMPOTENCY_KEY_CONFLICT'" in body
    assert "isRevConflictCode(failCode)" in body
    # 코드를 보지 않고 409 를 통째로 '다른 탭' 으로 덮던 분기는 사라졌다.
    assert "if (res.status === 409) {" not in body


def test_빈_사유는_시트가_막는다():
    """``requireDetail`` 이 켜지면 빈 제출로 닫히지 않는다 — 취소와 빈 사유가 갈린다."""
    sheet = REASON_SHEET_JS.read_text(encoding="utf-8")
    assert "state.requireDetail && !detail" in sheet
    assert "사유를 입력하세요." in sheet
    # 기존 호출부는 기본값 false 라 동작이 바뀌지 않는다.
    assert "options.requireDetail === true" in sheet
    # 공통 재시도 컨트롤러는 이 옵션을 켠다.
    assert "requireDetail: true" in ADMIN_OVERRIDE_JS.read_text(encoding="utf-8")
