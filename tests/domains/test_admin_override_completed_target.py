"""강제 단계 변경의 ``COMPLETED`` 목표 음성 대조군 (ADMIN-OVERRIDE-01).

``test_state_form.py:395-414`` 는 빈 사유 대조군을 MEASURE(메인)와 AS_RECEIVED(AS) 두
목표로만 본다 — ``COMPLETED`` 목표는 확장 응답 조립기
(``foms/api/orders/stage_override_admin.py``)를 따로 타는데 거기에 사유 검사가 없어서
대조군이 통째로 비어 있었다. 아래 다섯 갈래가 그 구멍을 닫는다.

여기서 보는 것은 전부 **정합 축**이다 — 빈 사유와 동일 단계는 관리자도 못 뚫는다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _login(client, username: str, role: str = "ADMIN") -> User:
    """사용자를 만들고 세션에 로그인시킨다."""
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team="CS", name=f"{username}-이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_order(status: str) -> int:
    """해당 단계에 올라와 있는 ERP 주문 1건의 id."""
    order = Order(
        received_date="2026-09-01", customer_name="강제-고객", phone="010-5555-6666",
        address="Seoul", product="붙박이장", status=status, manager_name="Mgr",
        is_erp_order=True, structured_data={"workflow": {"stage": status}},
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _event_types(order_id: int) -> list:
    """주문에 쌓인 이벤트 종류 목록."""
    db_session.expire_all()
    return [
        e.event_type
        for e in db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).all()
    ]


@pytest.mark.parametrize("role", ["ADMIN", "MANAGER"])
def test_완료_목표는_사유가_비면_단건도_400_이다(client, role):
    """음성 — 뚫기 여부와 무관하게 빈 사유는 메인 경로와 같은 400·같은 문구다."""
    _login(client, f"ovc_blank_single_{role.lower()}", role=role)
    order_id = _make_order("CS")

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "COMPLETED", "reason": "   ", "confirm": True},
    )

    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "사유를 입력하세요."
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "CS"
    assert "ADMIN_OVERRIDE_USED" not in _event_types(order_id)


@pytest.mark.parametrize("role", ["ADMIN", "MANAGER"])
def test_완료_목표는_사유가_비면_일괄도_400_이다(client, role):
    """음성 — 일괄도 같은 자리에서 같은 문구로 끊긴다."""
    _login(client, f"ovc_blank_bulk_{role.lower()}", role=role)
    order_id = _make_order("CS")

    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [order_id],
            "to_stage": "COMPLETED",
            "reason": "",
            "confirm": True,
        },
    )

    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "사유를 입력하세요."
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "CS"
    assert "ADMIN_OVERRIDE_USED" not in _event_types(order_id)


def test_이미_완료된_주문은_뚫기로도_같은_단계로_못_간다(client):
    """음성(정합 축) — 동일 단계는 권한 문제가 아니다. 이벤트도 0행이다."""
    _login(client, "ovc_same_completed", role="ADMIN")
    order_id = _make_order("COMPLETED")

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "COMPLETED",
            "reason": "그래도 한 번 더 완료",
            "confirm": True,
            "admin_override": True,
            "override_reason": "그래도 한 번 더 완료",
        },
    )

    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "현재와 동일한 단계로는 변경할 수 없습니다."
    assert _event_types(order_id).count("ADMIN_OVERRIDE_USED") == 0
