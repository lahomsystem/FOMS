"""STATE-CONTROLS-04 — 도면 전달 버튼 마크업·배선 계약(T8~T12).

매크로 출력·템플릿 배선·라우트 렌더·API 왕복·이름 축 분리. CTA 판정 계약은
tests/domains/test_measurement_drawing_transfer_cta.py 에 있다.
"""


from __future__ import annotations

import copy
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.orders.state_axes import read_main_stage
from models import Order, User
from tests.domains.drawing_transfer_helpers import (
    _make_user,
    _login,
    _measure_assignee_quest,
    _create_order,
    _set_stage,
    _cta,
    STATIC,
    SELF_TEMPLATE,
    REGIONAL_TEMPLATE,
    TRANSFER_JS,
    CTA_SERVICE,
    ASSET_PIN,
)

#: ADMIN-OVERRIDE-01 에서 바뀐 JS 의 자산 핀. CSS(``ASSET_PIN``)는 안 바뀌었으니 그대로 둔다.
ADMIN_OVERRIDE_JS_PIN = "20260921a"

# --------------------------------------------------------------------------- #
# T8 매크로 출력 문자열.
# --------------------------------------------------------------------------- #
def _render_transfer_control(cta) -> str:
    import app as app_module

    tmpl = app_module.app.jinja_env.get_template("partials/shared/status_select_options.html")
    return str(tmpl.module.drawing_transfer_control(4552, cta))


def _cta_dict(**overrides) -> dict:
    base = {
        "visible": True,
        "enabled": True,
        "label": "도면 전달",
        "confirm": "실측을 완료하고 도면 단계로 넘길까요?",
        "blocked_reason": "",
    }
    base.update(overrides)
    return base


def test_macro_renders_nothing_without_cta() -> None:
    assert _render_transfer_control(None).strip() == ""


def test_macro_renders_nothing_when_hidden() -> None:
    hidden = _cta_dict(visible=False, enabled=False, label="", confirm="")
    assert _render_transfer_control(hidden).strip() == ""


def test_macro_renders_enabled_button() -> None:
    html = _render_transfer_control(_cta_dict())

    assert "js-drawing-transfer" in html
    assert "btn btn-sm btn-outline-primary" in html
    assert 'data-order-id="4552"' in html
    assert "data-confirm=" in html
    assert "도면 전달" in html
    assert "disabled" not in html
    assert "<div" not in html, "버튼 하나뿐 — 새 div 래퍼는 버킷 정규식을 깬다"


def test_macro_button_is_visually_distinct_from_drawing_file_viewer() -> None:
    """같은 행의 도면 **파일** 뷰어 버튼과 눈으로 갈려야 한다(오클릭 = stage 전이).

    뷰어는 ``btn-outline-info`` + ``fa-drafting-compass`` 다. 이 버튼은 둘 다 쓰지 않는다.
    """
    html = _render_transfer_control(_cta_dict())

    assert "btn-outline-info" not in html, "도면 파일 뷰어와 같은 톤이다"
    assert "fa-drafting-compass" not in html, "도면 파일 뷰어와 같은 아이콘이다"
    assert "fa-arrow-right" in html, "단계 이동을 뜻하는 아이콘이어야 한다"

    # 색은 CSS 가 못박는다(인라인 스타일 금지).
    css = (STATIC / "css/measurement/complete-order-btn.css").read_text(encoding="utf-8")
    assert ".js-drawing-transfer.btn" in css
    assert "#3949ab" in css, "전용 색이 CSS 에 없다"
    assert "style=" not in html, "인라인 스타일 금지"


def test_transfer_button_margin_matches_status_stack_gap() -> None:
    """.foms-board-status-stack 은 gap 4px 를 준다 — 그 안에서는 margin-top 을 겹치지 않는다."""
    css = (STATIC / "css/measurement/complete-order-btn.css").read_text(encoding="utf-8")

    block = re.search(
        r"\.foms-board-status-stack \.js-drawing-transfer\.btn\s*\{[^}]*\}", css
    )
    assert block, "스택 안 margin 상쇄 규칙이 없다"
    assert re.search(r"margin-top:\s*0", block.group(0)), block.group(0)


def test_macro_renders_disabled_button_with_reason() -> None:
    html = _render_transfer_control(_cta_dict(enabled=False, blocked_reason="권한 없음"))

    assert "disabled" in html
    assert 'title="권한 없음"' in html
    assert "js-drawing-transfer" in html


def test_macro_escapes_confirm_attribute() -> None:
    """confirm 에 큰따옴표가 들어가도 속성이 깨지거나 스크립트가 새지 않는다."""
    html = _render_transfer_control(_cta_dict(confirm='"><script>alert(1)</script>'))

    assert "<script>" not in html
    assert "&#34;" in html or "&quot;" in html


# --------------------------------------------------------------------------- #
# T9 템플릿 배선.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "path,expected_sites",
    [(SELF_TEMPLATE, 2), (REGIONAL_TEMPLATE, 3)],
)
def test_templates_wire_drawing_transfer_control(path: Path, expected_sites: int) -> None:
    src = path.read_text(encoding="utf-8")

    sites = src.count("drawing_transfer_control(order.id")
    assert sites == expected_sites, f"{path.name}: 호출 {sites} != {expected_sites}"

    import_lines = [
        line
        for line in src.splitlines()
        if "status_select_options.html' import" in line
    ]
    assert import_lines, f"{path.name}: 공용 매크로 import 줄이 없다"
    assert any("drawing_transfer_control" in line for line in import_lines), (
        f"{path.name}: import 줄에 drawing_transfer_control 이 없다"
    )


@pytest.mark.parametrize("path", [SELF_TEMPLATE, REGIONAL_TEMPLATE])
def test_templates_pin_transfer_assets(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()

    js_lines = [line for line in lines if "drawing-transfer-btn.js" in line]
    assert len(js_lines) == 1, f"{path.name}: 새 JS script 태그 {len(js_lines)}개"
    # ADMIN-OVERRIDE-01 에서 이 JS 에 관리자 강제 진행 재시도를 배선했으므로 핀이 올랐다.
    assert ADMIN_OVERRIDE_JS_PIN in js_lines[0], (
        f"{path.name}: 새 JS 핀이 {ADMIN_OVERRIDE_JS_PIN} 가 아니다")

    css_lines = [line for line in lines if "complete-order-btn.css" in line]
    assert len(css_lines) == 1, f"{path.name}: CSS 링크 {len(css_lines)}개"
    assert ASSET_PIN in css_lines[0], f"{path.name}: CSS 핀이 {ASSET_PIN} 가 아니다"

    # complete-order-btn.js 도 ADMIN-OVERRIDE-01 재시도 배선으로 바뀌어 핀이 올랐다.
    assert f"complete-order-btn.js') }}}}?v={ADMIN_OVERRIDE_JS_PIN}" in src


@pytest.mark.parametrize("path", [SELF_TEMPLATE, REGIONAL_TEMPLATE])
def test_complete_order_control_site_count_unchanged(path: Path) -> None:
    """STATE-CONTROLS-02 회귀 가드 — 완료 버튼은 여전히 1곳뿐이다."""
    src = path.read_text(encoding="utf-8")
    assert src.count("complete_order_control(order.id") == 1


def test_regional_template_has_no_status_select() -> None:
    """지방 보드 행에는 status 드롭다운이 없다(2026-08-07 개편 계약)."""
    src = REGIONAL_TEMPLATE.read_text(encoding="utf-8")
    for match in re.finditer(r"<select[^>]*>", src):
        assert 'data-field="status"' not in match.group(0), match.group(0)


# --------------------------------------------------------------------------- #
# T10 라우트 end-to-end 렌더.
# --------------------------------------------------------------------------- #
def _button_for(html: str, order_id: int) -> bool:
    """해당 주문 id 를 단 도면 전달 버튼이 렌더됐는지."""
    for match in re.finditer(r"<button[^>]*js-drawing-transfer[^>]*>", html):
        if f'data-order-id="{order_id}"' in match.group(0):
            return True
    return False


def test_self_dashboard_renders_transfer_button(client) -> None:
    user = _make_user(role="STAFF", team="SALES", username="self-board-staff")
    _login(client, user)
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",           # pending 버킷
        is_self_measurement=True,
    )

    resp = client.get("/self_measurement_dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert _button_for(body, order.id), "자가실측 pending 행에 도면 전달 버튼이 없다"

    order_id = order.id
    _set_stage(order_id, "PRODUCTION")
    body2 = client.get("/self_measurement_dashboard").get_data(as_text=True)
    assert not _button_for(body2, order_id), "PRODUCTION 인데 버튼이 남아 있다"


def test_regional_dashboard_renders_transfer_button(client) -> None:
    user = _make_user(role="STAFF", team="SALES", username="regional-board-staff")
    _login(client, user)
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",           # 진행 중 버킷(상차일 없음)
        is_regional=True,
        measurement_completed=True,
    )

    resp = client.get("/regional_dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert _button_for(body, order.id), "지방 진행 중 행에 도면 전달 버튼이 없다"

    order_id = order.id
    _set_stage(order_id, "PRODUCTION")
    body2 = client.get("/regional_dashboard").get_data(as_text=True)
    assert not _button_for(body2, order_id), "PRODUCTION 인데 버튼이 남아 있다"


def test_shipping_alert_card_div_depth_unchanged(client) -> None:
    """버튼 때문에 상차 예정 알림 카드의 div 층이 늘면 버킷 테스트가 깨진다.

    test_regional_dashboard_buckets.py:90-95 와 **같은 정규식**으로 카드를 잘라
    order id 가 여전히 잡히는지로 확인한다.
    """
    from datetime import timedelta

    from foms.services.erp_display import get_today_kst

    user = _make_user(role="STAFF", team="SALES", username="regional-alert-staff")
    _login(client, user)
    future = (get_today_kst() + timedelta(days=3)).strftime("%Y-%m-%d")
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",
        is_regional=True,
        measurement_completed=True,
        shipping_scheduled_date=future,
    )

    body = client.get("/regional_dashboard").get_data(as_text=True)
    match = re.search(
        r'<div class="card shadow shipping-alert-card".*?</div>\s*</div>\s*</div>',
        body,
        re.S,
    )
    assert match, "상차 예정 알림 카드를 정규식으로 잘라내지 못했다"
    assert str(order.id) in set(re.findall(r'data-order-id="(\d+)"', match.group(0)))


# --------------------------------------------------------------------------- #
# T11 API 왕복 — 화면 판정 = 서버 판정.
# --------------------------------------------------------------------------- #
def test_disabled_user_is_rejected_and_enabled_user_transitions(client) -> None:
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",
        is_self_measurement=True,
    )
    order_id = order.id

    denied_user = _make_user(role="STAFF", team="PRODUCTION", username="transfer-denied")
    allowed_user = _make_user(role="STAFF", team="SALES", username="transfer-allowed")

    assert _cta(order, denied_user)["enabled"] is False
    assert _cta(order, allowed_user)["enabled"] is True

    # (b) 화면이 비활성으로 그린 사용자는 서버가 실제로 거부한다.
    _login(client, denied_user)
    denied = client.post(f"/api/orders/{order.id}/quest/approve", json={})
    assert denied.status_code == 403, denied.get_data(as_text=True)

    db_session.expire_all()
    assert read_main_stage(db_session.query(Order).filter(Order.id == order_id).one()) == "MEASURE"

    # (a) 활성으로 그린 사용자는 실제로 도면 단계로 넘어간다.
    _login(client, allowed_user)
    ok = client.post(f"/api/orders/{order.id}/quest/approve", json={})
    assert ok.status_code == 200, ok.get_data(as_text=True)
    data = ok.get_json()
    assert data["success"] is True
    assert data["auto_transitioned"] is True

    db_session.expire_all()
    moved = db_session.query(Order).filter(Order.id == order_id).one()
    assert read_main_stage(moved) == "DRAWING"

    # 전이 뒤에는 버튼이 사라진다(DRAWING 은 command-required).
    assert _cta(moved, allowed_user)["visible"] is False


# --------------------------------------------------------------------------- #
# T12 이름 축 분리 — drawing_status 축을 건드리지 않는다.
# --------------------------------------------------------------------------- #
def _js_code_only(src: str) -> str:
    """주석을 걷어낸 JS 본문. 축 구분을 설명하는 주석까지 금칙어로 잡지 않기 위해서다."""
    without_blocks = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    kept = [
        line
        for line in without_blocks.splitlines()
        if not line.strip().startswith("//")
    ]
    return "\n".join(re.sub(r"//.*$", "", line) for line in kept)


def _python_code_only(src: str) -> str:
    """주석과 docstring 을 걷어낸 파이썬 본문(문자열 리터럴은 남긴다)."""
    import io
    import tokenize

    pieces: list[str] = []
    prev_type = tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and prev_type in (
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.NEWLINE,
            tokenize.NL,
            tokenize.ENCODING,
        ):
            # 논리 행 첫 토큰인 문자열 = docstring.
            prev_type = tok.type
            continue
        if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            pieces.append(tok.string)
        prev_type = tok.type
    return "\n".join(pieces)


def test_transfer_js_calls_quest_approve_only() -> None:
    src = TRANSFER_JS.read_text(encoding="utf-8")
    code = _js_code_only(src)

    assert "'/api/orders/' + orderId + '/quest/approve'" in src
    assert "__FOMS_DRAWING_TRANSFER_BTN_BOUND" in src
    assert "drawing_status" not in code, "도면 파일 전달(drawing_status) 축과 섞였다"
    assert "emergency_override" not in code
    assert "override_reason" not in code
    assert "jQuery" not in code
    assert "$(" not in code


def test_transfer_js_guards_non_json_response() -> None:
    """세션 만료 시 role_required 는 로그인 페이지로 redirect 한다 — HTML 을 json() 하면
    사용자에게 "Unexpected token '<'" 가 뜬다. 파싱을 감싸고 한글 문장으로 바꾼다."""
    code = _js_code_only(TRANSFER_JS.read_text(encoding="utf-8"))

    assert "res.json()" in code
    assert re.search(r"try\s*\{\s*data\s*=\s*await\s+res\.json\(\)", code), (
        "res.json() 이 try 로 감싸여 있지 않다"
    )
    assert "res.redirected" in code
    assert "로그인이 만료되었습니다" in code
    assert "HTTP " in code, "상태코드를 사람이 볼 수 있게 남겨야 한다"


def test_cta_service_does_not_touch_drawing_status_axis() -> None:
    code = _python_code_only(CTA_SERVICE.read_text(encoding="utf-8"))

    assert "drawing_status" not in code
    assert "erp_orders_drawing" not in code


# --------------------------------------------------------------------------- #
# T13 실측완료 표시 — 전이가 체크리스트 축도 함께 켠다 (2026-09-22).
#
# 버튼 확인문이 "실측을 완료하고 도면 단계로 넘길까요?" 라고 약속하므로 단계만 옮기면
# 문구와 동작이 어긋난다. 체크박스 경로와 **같은 원장 path** 를 남겨야 한 축으로 읽힌다.
# --------------------------------------------------------------------------- #
def _measurement_ledger(order_id: int):
    from models import OrderFieldChange

    db_session.expire_all()
    return (
        db_session.query(OrderFieldChange)
        .filter(
            OrderFieldChange.order_id == order_id,
            OrderFieldChange.path == "measurement_completed",
        )
        .order_by(OrderFieldChange.id)
        .all()
    )


def _approve(client, order_id: int):
    return client.post(f"/api/orders/{order_id}/quest/approve", json={})


def test_transfer_marks_measurement_completed_on_self_order(client) -> None:
    """자가실측 주문: 도면 전달 한 번으로 단계 이동 + 실측완료 표시가 함께 켜진다."""
    user = _make_user(role="STAFF", team="SALES", username="transfer-marks-self")
    _login(client, user)
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",
        is_self_measurement=True,
        measurement_completed=False,
    )
    order_id = order.id

    assert _approve(client, order_id).status_code == 200

    db_session.expire_all()
    moved = db_session.query(Order).filter(Order.id == order_id).one()
    assert read_main_stage(moved) == "DRAWING"
    assert moved.measurement_completed is True, "단계만 옮기고 실측완료 표시를 안 켰다"

    rows = _measurement_ledger(order_id)
    assert [(r.before_value, r.after_value) for r in rows] == [("False", "True")], (
        "체크박스 경로와 같은 평면 path 로 원장 1행이 남아야 한다"
    )


def test_transfer_marks_measurement_completed_on_regional_order(client) -> None:
    """지방 주문도 같다 — 체크리스트 API 가 허용하는 두 종류 모두 대상이다."""
    user = _make_user(role="STAFF", team="SALES", username="transfer-marks-regional")
    _login(client, user)
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",
        is_regional=True,
        measurement_completed=False,
    )
    order_id = order.id

    assert _approve(client, order_id).status_code == 200

    db_session.expire_all()
    assert db_session.query(Order).filter(Order.id == order_id).one().measurement_completed is True


def test_transfer_leaves_plain_erp_order_flag_untouched(client) -> None:
    """음성 대조군 — 지방도 자가실측도 아닌 주문은 단계만 옮기고 컬럼을 안 건드린다.

    체크박스가 없는 화면에 값만 생기면 두 축이 또 갈라진다. 허용 경계는 체크리스트 API
    (``foms/api/orders/regional.py`` 의 ``_order_or_404``)와 같아야 한다.
    """
    user = _make_user(role="STAFF", team="SALES", username="transfer-marks-plain")
    _login(client, user)
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",
        measurement_completed=False,
    )
    order_id = order.id

    assert _approve(client, order_id).status_code == 200

    db_session.expire_all()
    moved = db_session.query(Order).filter(Order.id == order_id).one()
    assert read_main_stage(moved) == "DRAWING", "전이 자체는 그대로 일어나야 한다"
    assert not moved.measurement_completed, "체크박스 없는 주문에 값이 생겼다"
    assert _measurement_ledger(order_id) == []


def test_transfer_does_not_duplicate_ledger_when_already_checked(client) -> None:
    """이미 체크되어 있던 건은 원장 행을 만들지 않는다(무변경 억제)."""
    user = _make_user(role="STAFF", team="SALES", username="transfer-marks-idem")
    _login(client, user)
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",
        is_regional=True,
        measurement_completed=True,
    )
    order_id = order.id

    assert _approve(client, order_id).status_code == 200

    db_session.expire_all()
    assert db_session.query(Order).filter(Order.id == order_id).one().measurement_completed is True
    assert _measurement_ledger(order_id) == [], "값이 그대로인데 원장 행이 생겼다"
