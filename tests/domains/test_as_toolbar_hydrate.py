"""D1b 계약: AS 리치 툴바를 행별 렌더(400개)에서 fragment당 <template> 1개 + focus clone-hydrate로 전환.

성능 목적(payload 비만 제거)이므로 계약의 의도는 두 가지다.
1) 서버 렌더 마크업: 툴바는 fragment당 정확히 1개(<template>)만 존재하고, 행별로는 0개여야 한다.
2) 클라이언트 hydrate: focusin 위임(1회 등록·window 가드) + editor.dataset.toolbarHydrated 멱등으로
   원본과 동일한 삽입 위치(.as-rich-editor의 first child)에 clone 삽입한다.
툴바 명령 집합(굵게/빨강/파랑/서식초기화/영업·전달)은 template 안에 보존되어야 한다(UX 무변경).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

_ROOT = Path(__file__).resolve().parents[2]


def _login_as_admin(client):
    user = User(
        username="as_toolbar_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="AS Toolbar Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_as_order(name):
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name=name,
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status="AS_RECEIVED",
        manager_name="Alice",
        as_received_date=today,
        is_erp_order=True,
        structured_data={"shipment": {"as_content": "", "as_content_2": ""}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_toolbar_rendered_once_as_template_not_per_row(client, monkeypatch):
    """서버 렌더: 툴바 원본은 fragment당 <template> 1개, 행별 툴바는 0개.

    에디터(.as-rich-editor)는 여러 행에 걸쳐 다수 존재하지만
    실제 툴바 div(class="as-rich-toolbar")는 template 안 1개뿐이어야 한다(payload dedup).
    """
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    for i in range(3):
        _create_as_order(f"툴바 AS {i}")

    resp = client.get(
        "/erp/as?tab=incomplete&view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # 여러 행 → 에디터는 다수(PC 2 + 모바일 2 = 행당 4)
    assert body.count("as-rich-editor") >= 4
    # template 원본은 정확히 1개
    assert body.count('id="as-rich-toolbar-template"') == 1
    # 실제 툴바 div는 template 안 1개뿐(행별 렌더 0)
    assert body.count('class="as-rich-toolbar"') == 1
    # 명령 버튼 집합은 template 안에 보존(UX 무변경)
    assert body.count('data-rich-command="bold"') == 1
    assert body.count('data-rich-command="foreColor"') == 2  # red + blue
    assert body.count('data-rich-command="clear-format"') == 1
    assert body.count("as-sales-delivery-btn") == 1
    # 주문별 영업/전달 상태는 에디터에 data 속성으로만 실린다(툴바 아님)
    assert "data-sales-delivery=" in body


def test_as_toolbar_hydrate_source_contract():
    """클라이언트 hydrate 계약: 위임 focusin(1회 등록·window 가드) + 멱등 dataset 가드."""
    js = (_ROOT / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")
    # template에서 clone하는 hydrate 함수
    assert "hydrateAsRichToolbar" in js
    assert "as-rich-toolbar-template" in js
    # 멱등: 이미 hydrate된 에디터는 재삽입 금지
    assert "toolbarHydrated" in js
    # 삽입 위치 계약: .as-rich-editor의 first child(원본 마크업과 동일)
    assert "editor.insertBefore(toolbar, editor.firstChild)" in js
    # document 위임 focusin + 1회 등록 window 가드
    assert "window.__FOMS_AS_TOOLBAR_BOUND" in js
    assert "'focusin'" in js
    # 주문별 영업/전달 상태 주입(툴바 dedup 후에도 per-order 상태 보존)
    assert "salesDelivery" in js


def test_as_toolbar_macro_has_no_per_row_render():
    """매크로 소스 계약: content-tabs는 더 이상 행별 툴바를 렌더하지 않는다."""
    macros = (_ROOT / "templates/cs/partials/as_card_macros.html").read_text(encoding="utf-8")
    # 행별 툴바 렌더 매크로 호출 제거
    assert "render_as_rich_toolbar(" not in macros
    # template 매크로 존재
    assert "render_as_rich_toolbar_template" in macros
    assert 'id="as-rich-toolbar-template"' in macros
    # tabbed-editor가 주문별 영업/전달 상태를 실어 hydrate 시 주입 가능
    assert 'data-sales-delivery="' in macros
