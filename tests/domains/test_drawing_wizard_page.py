"""도면 마법사 페이지 라우트 계약 테스트 (200 + config JSON 파싱 + 미로그인 redirect)."""

import json
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_admin(client, username="wizard-page-admin"):
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="DRAWING",
        name="도면관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _erp_order():
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="서으뜸",
        phone="010-1111-2222",
        address="대구",
        product="붙박이장",
        status="DRAWING",
        manager_name="하우드 김성일",
        is_erp_order=True,
        structured_data={"parties": {"customer": {"name": "서으뜸"}}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_wizard_page_renders_with_parseable_config(client):
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.get(f"/erp/drawing-workbench/{order_id}/wizard")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="dws-root"' in body
    assert f"도면 마법사 — 주문 #{order_id}" in body

    marker = '<script id="drawing-wizard-config" type="application/json">'
    start = body.index(marker) + len(marker)
    end = body.index("</script>", start)
    config = json.loads(body[start:end])
    assert config["order_id"] == order_id
    assert config["can_save"] is True


def test_wizard_page_has_exit_button(client):
    """앱바 좌측 '나가기' 버튼(#dws-btn-exit)이 렌더된다 — 도면 작업실 복귀 진입점."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.get(f"/erp/drawing-workbench/{order_id}/wizard")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="dws-btn-exit"' in body
    # 나가기 라벨/접근성 텍스트 존재
    assert "나가기" in body


def test_wizard_page_missing_order_redirects_to_dashboard(client):
    _login_admin(client)

    resp = client.get("/erp/drawing-workbench/99999/wizard")

    assert resp.status_code == 302
    assert "/erp/drawing-workbench" in resp.headers["Location"]


def test_wizard_page_requires_login(client):
    order = _erp_order()
    order_id = order.id

    resp = client.get(f"/erp/drawing-workbench/{order_id}/wizard")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_workbench_detail_shows_wizard_entry_button(client):
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.get(f"/erp/drawing-workbench/{order_id}")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert f"/drawing-workbench/{order_id}/wizard" in body


def test_wizard_image_toolbar_exposes_trim_button(client):
    """이미지 미니툴바에 '여백 자르기' 버튼 — 이미 올려둔(여백 포함) 그림을 사람이 직접
    정리하는 진입로. 신규 라우트 없이 기존 asset 업로드 파이프라인을 다시 태운다."""
    _login_admin(client)
    order = _erp_order()

    resp = client.get(f"/erp/drawing-workbench/{order.id}/wizard")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="dws-mt-trim"' in body
    assert "여백 자르기" in body
    # 내용이 바뀐 wizard.js 는 SW staticCacheFirst 스테일 봉합 핀을 함께 올린다.
    assert "js/drawing/wizard.js') }}?v=20260908b" not in body


def test_wizard_alt_drag_duplicates_in_place():
    """포토샵처럼 Alt+드래그 = 제자리 복제. 단일(노드)·다중(transformer) 두 드래그 경로가
    모두 dragstart 의 altKey 로 startAltDuplicate 를 부르고, 한 제스처 한 번만(altDupArmed)."""
    from pathlib import Path

    js = Path("static/js/drawing/wizard.js").read_text(encoding="utf-8")
    assert "function startAltDuplicate(ids)" in js
    assert js.count("e.evt.altKey") >= 2
    assert js.count("startAltDuplicate(") >= 4  # 정의 1 + 단일 1 + 다중 노드 1 + transformer 1
    assert js.count("altDupArmed = false;") >= 3  # 선언 1 + 노드·transformer dragend 해제
    # Alt 누른 채 객체 위 = 복사 커서(앵커 제외), CSS 는 wizard.css 에만(인라인 금지).
    assert "function syncAltCopyCursor(altDown)" in js
    css = Path("static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")
    assert ".dws-anno.dws-alt-copy canvas { cursor: copy; }" in css
