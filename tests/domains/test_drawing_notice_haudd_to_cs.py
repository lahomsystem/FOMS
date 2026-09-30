"""하우드 담당 주문의 도면 전달·전달취소 알림은 CS 팀(라홈팀/하우드팀)이 받는다.

없는 HAUDD 팀으로 보내면 수신자가 0명이 된다.
"""

from __future__ import annotations

from db import db_session
from models import Notification
from tests.domains.test_drawing_collab_fixes import (
    _login,
    _make_order,
    _make_user,
    _state_user_ids,
    _transferred_order,
)


def test_cancel_transfer_routes_cs_for_haudd_manager(client):
    """하우드 건도 CS 팀(라홈팀/하우드팀)이 받는다 — 없는 HAUDD 팀으로 보내면 수신자 0명."""
    admin = _make_user("ct_admin3", role="ADMIN")
    cs = _make_user("ct_cs3", role="STAFF", team="CS", name="씨에스")
    sales = _make_user("ct_sales3", role="STAFF", team="SALES", name="영업하")
    cs_id, sales_id = cs.id, sales.id
    _login(client, admin)
    order = _transferred_order("하우드 김성일")
    oid = order.id
    res = client.post(f"/api/orders/{oid}/cancel-transfer")
    assert res.status_code == 200
    n = (
        db_session.query(Notification)
        .filter(Notification.order_id == oid, Notification.notification_type == "DRAWING_TRANSFER_CANCELLED")
        .one()
    )
    assert n.target_team == "CS"
    assert n.target_manager_name is None
    recipients = _state_user_ids(n.id)
    assert cs_id in recipients
    assert sales_id not in recipients


def test_transfer_routes_cs_for_haudd_manager(client):
    admin = _make_user("tr_admin_h", role="ADMIN")
    cs = _make_user("tr_cs_h", role="STAFF", team="CS", name="씨에스하")
    sales = _make_user("tr_sales_h", role="STAFF", team="SALES", name="영업하우")
    cs_id, sales_id = cs.id, sales.id
    _login(client, admin)
    order = _make_order(
        manager_name="하우드 김성일",
        sd={
            "parties": {"customer": {"name": "홍길동"}, "manager": {"name": "하우드 김성일"}},
            "workflow": {"stage": "DRAWING"},
            "assignments": {"drawing_assignee_user_ids": [admin.id]},
        },
    )
    oid = order.id

    res = client.post(
        f"/api/orders/{oid}/transfer-drawing",
        json={"note": "", "mode": "APPEND",
              "files": [{"key": f"orders/{oid}/drawing_gateway/revisions/a.png", "filename": "a.png"}]},
    )
    assert res.status_code == 200, res.get_json()
    assert "[CS팀]" in res.get_json()["message"]

    n = (
        db_session.query(Notification)
        .filter(Notification.order_id == oid, Notification.notification_type == "DRAWING_TRANSFERRED")
        .one()
    )
    assert n.target_team == "CS"
    recipients = _state_user_ids(n.id)
    assert cs_id in recipients
    assert sales_id not in recipients
