"""AS 목록: 주문 식별자는 행 컨테이너에만 실린다 (payload 계약).

예전에는 행 안의 버튼·입력·셀마다 ``data-order-id`` 를 복제해 AS fragment 한 장에
1,271개가 실렸다(2026-08-13 실측, 행당 22개). 자손은 ``closest('[data-order-id]')``
로 컨테이너를 역참조하므로 중복 방출은 순수 낭비다. 이 테스트는 그 계약을 고정한다 —
행 안에 컨테이너 외 방출이 다시 생기면 red.

동시에 **컨테이너 자체는 반드시 남아야** 한다. 컨테이너가 사라지면 자손의 역참조가
전부 끊겨 미결 토글·날짜 저장·도면 체크가 조용히 죽는다(선택자 회귀는 화면에 안 보인다).
"""

from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

ROW_RE = re.compile(r'<tr id="as-row-(\d+)"[^>]*>(.*?)</tr>', re.S)

# 행 안에서 자기 data-order-id 를 유지해도 되는 루트. 쓰기 API 응답이 이 블록만 통째로
# 돌려주고 클라가 detached 상태에서 파싱·조회하므로, 자기 id 가 없으면 역참조가 끊긴다.
ALLOWED_ROOTS = ("as-tl-cell", "as-timeline", "as-rchart", "as-construction-worker-list")


def _login_as_admin(client):
    user = User(
        username="as_rowscope_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="AS Row Scope Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_as_order():
    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="행스코프 고객",
        phone="010-1111-2222",
        address="Seoul Gangnam",
        product="붙박이장",
        status="AS_RECEIVED",
        manager_name="Alice",
        as_received_date=today,
        is_erp_order=True,
        structured_data={
            # as_visit_date 는 컬럼이 아니라 structured_data 파생값이다(erp_display).
            "schedule": {"as_visit": {"date": today}},
            "shipment": {
                "as_content": "<div>내용</div>",
                "construction_workers": ["홍길동"],
            },
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_desktop_row_carries_order_id_only_on_tr(client, app):
    """데스크톱 표: ``<tr>`` 하나만 data-order-id 를 갖는다."""
    with app.app_context():
        _login_as_admin(client)
        order = _create_as_order()
        order_id = order.id

        resp = client.get("/erp/as", headers={"X-FOMS-ERP-SHELL": "1"})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        match = next((m for m in ROW_RE.finditer(html) if m.group(1) == str(order_id)), None)
        assert match is not None, "AS 행이 렌더되지 않았다"

        row_inner = match.group(2)
        offenders = [
            row_inner[max(0, hit.start() - 180):hit.start()].rsplit("<", 1)[-1]
            for hit in re.finditer(r"data-order-id", row_inner)
        ]
        unexpected = [tag for tag in offenders if not any(root in tag for root in ALLOWED_ROOTS)]
        assert not unexpected, (
            "행 자손에 data-order-id 가 다시 생겼다 — 자손은 closest('[data-order-id]') 로 "
            f"컨테이너를 역참조해야 한다: {unexpected}"
        )
        # 컨테이너 자체는 유지 계약(자손 역참조의 기반).
        assert f'<tr id="as-row-{order_id}" data-order-id="{order_id}">' in html


def test_row_scoped_controls_still_render(client, app):
    """역참조가 성립하려면 컨트롤들이 컨테이너 안에 남아 있어야 한다."""
    with app.app_context():
        _login_as_admin(client)
        order = _create_as_order()
        order_id = order.id

        resp = client.get("/erp/as", headers={"X-FOMS-ERP-SHELL": "1"})
        html = resp.get_data(as_text=True)
        match = next((m for m in ROW_RE.finditer(html) if m.group(1) == str(order_id)), None)
        assert match is not None
        row_inner = match.group(2)

        for needed in (
            "editable-date-as",
            "as-pending-btn",
            "as-photos-btn",
            "as-blueprint-checkbox",
            "erp-as-avail-chip",
            "erp-as-status-cell",
            "as-tl-cell",
        ):
            assert needed in row_inner, f"{needed} 가 행에서 사라졌다"
