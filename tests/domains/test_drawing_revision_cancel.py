"""Tests for the drawing revision-request cancel API (영업측 수정요청 취소).

전달취소(도면팀)의 대칭축인 수정요청 취소(영업측/관리자)를 검증한다.
- 정상 취소 시 drawing_status가 이전 상태(TRANSFERRED/CONFIRMED)로 복귀하고
  REQUEST_REVISION 이력이 제거되는지.
- 이번 요청에서 올린 참고 파일만 삭제되고 도면 원본은 보존되는지.
- 팀 상호배타 게이트(도면팀 403) 및 상태 전제조건(RETURNED 아니면 400).
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
from db import db_session
from models import Order, OrderAttachment, User


class _FakeStorage:
    """delete_file 호출 키를 수집하는 테스트용 스토리지."""

    def __init__(self):
        self.deleted_keys: list[str] = []

    def delete_file(self, key):
        self.deleted_keys.append(key)
        return True


def _make_user(username, *, role, team, name):
    user = User(
        username=username,
        password=generate_password_hash("pass"),
        role=role,
        team=team,
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_returned_order(*, manager_name="영업담당", history=None, current_files=None):
    structured_data = {
        "parties": {"customer": {"name": "고객"}, "manager": {"name": manager_name}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "RETURNED",
        "assignments": {"sales_assignee_user_ids": []},
        "drawing_current_files": current_files if current_files is not None else [],
        "drawing_transfer_history": history if history is not None else [
            {"action": "TRANSFER", "mode": "APPEND", "files": []},
            {"action": "REQUEST_REVISION", "files": []},
        ],
    }
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="DRAWING",
        manager_name=manager_name,
        is_erp_order=True,
        structured_data=structured_data,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_cancel_revision_by_sales_restores_transferred(client):
    """영업 담당(주문 매니저 일치)이 수정요청을 취소하면 TRANSFERRED로 복귀."""
    sales = _make_user("rev_cancel_sales1", role="MANAGER", team="SALES", name="영업담당")
    _login(client, sales)
    order = _make_returned_order(manager_name="영업담당")
    order_id = order.id

    res = client.post(f"/api/orders/{order_id}/cancel-revision-request")
    assert res.status_code == 200
    assert res.get_json()["success"] is True

    order = db_session.get(Order, order_id)
    assert order.structured_data["drawing_status"] == "TRANSFERRED"
    actions = [h.get("action") for h in order.structured_data["drawing_transfer_history"]]
    assert "REQUEST_REVISION" not in actions
    assert actions == ["TRANSFER"]


def test_cancel_revision_restores_confirmed_when_prior_confirm(client):
    """직전 상태가 CONFIRM_RECEIPT였다면 취소 시 CONFIRMED로 복귀."""
    sales = _make_user("rev_cancel_sales2", role="MANAGER", team="SALES", name="영업담당2")
    _login(client, sales)
    order = _make_returned_order(
        manager_name="영업담당2",
        history=[
            {"action": "TRANSFER", "mode": "APPEND", "files": []},
            {"action": "CONFIRM_RECEIPT", "files": []},
            {"action": "REQUEST_REVISION", "files": []},
        ],
    )
    order_id = order.id

    res = client.post(f"/api/orders/{order_id}/cancel-revision-request")
    assert res.status_code == 200

    order = db_session.get(Order, order_id)
    assert order.structured_data["drawing_status"] == "CONFIRMED"
    actions = [h.get("action") for h in order.structured_data["drawing_transfer_history"]]
    assert "REQUEST_REVISION" not in actions


def test_cancel_revision_by_admin_allowed(client):
    """관리자(ADMIN)는 매니저가 아니어도 취소 가능."""
    admin = _make_user("rev_cancel_admin", role="ADMIN", team="SALES", name="관리자")
    _login(client, admin)
    order = _make_returned_order(manager_name="다른담당")
    order_id = order.id

    res = client.post(f"/api/orders/{order_id}/cancel-revision-request")
    assert res.status_code == 200
    order = db_session.get(Order, order_id)
    assert order.structured_data["drawing_status"] == "TRANSFERRED"


def test_cancel_revision_deletes_reference_files_only(client, monkeypatch):
    """이번 요청에서 올린 참고 파일만 삭제하고 도면 원본은 보존한다."""
    storage = _FakeStorage()
    monkeypatch.setattr(revision_api, "get_storage", lambda: storage)

    sales = _make_user("rev_cancel_sales3", role="MANAGER", team="SALES", name="영업담당3")
    _login(client, sales)

    ref_key = "orders/rc3/ref1.jpg"
    original_key = "orders/rc3/original.pdf"
    order = _make_returned_order(
        manager_name="영업담당3",
        current_files=[{"key": original_key, "filename": "original.pdf"}],
        history=[
            {"action": "TRANSFER", "mode": "APPEND", "files": [{"key": original_key, "filename": "original.pdf"}]},
            {"action": "REQUEST_REVISION", "files": [{"key": ref_key, "filename": "ref1.jpg"}]},
        ],
    )
    order_id = order.id

    ref_att = OrderAttachment(
        order_id=order_id,
        filename="ref1.jpg",
        file_type="file",
        category="drawing_gateway",
        storage_key=ref_key,
        thumbnail_key="orders/rc3/thumb_ref1.png",
    )
    original_att = OrderAttachment(
        order_id=order_id,
        filename="original.pdf",
        file_type="file",
        category="drawing",
        storage_key=original_key,
    )
    db_session.add(ref_att)
    db_session.add(original_att)
    db_session.commit()

    res = client.post(f"/api/orders/{order_id}/cancel-revision-request")
    assert res.status_code == 200

    # 참고 파일만 스토리지에서 삭제, 도면 원본 키는 삭제되지 않음.
    assert ref_key in storage.deleted_keys
    assert "orders/rc3/thumb_ref1.png" in storage.deleted_keys
    assert original_key not in storage.deleted_keys

    remaining = (
        db_session.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order_id)
        .all()
    )
    remaining_keys = {row.storage_key for row in remaining}
    assert ref_key not in remaining_keys
    assert original_key in remaining_keys

    # 도면 원본(drawing_current_files)은 손대지 않는다.
    order = db_session.get(Order, order_id)
    assert order.structured_data["drawing_current_files"] == [
        {"key": original_key, "filename": "original.pdf"}
    ]


def test_cancel_revision_forbidden_for_drawing_team(client):
    """도면팀 계정(비관리자)은 수정요청 취소 불가(403). 팀 상호배타 게이트."""
    drawer = _make_user("rev_cancel_drawing", role="MANAGER", team="DRAWING", name="도면담당")
    _login(client, drawer)
    order = _make_returned_order(manager_name="도면담당")  # 이름 일치여도 도면팀은 차단
    order_id = order.id

    res = client.post(f"/api/orders/{order_id}/cancel-revision-request")
    assert res.status_code == 403
    assert res.get_json()["success"] is False

    order = db_session.get(Order, order_id)
    assert order.structured_data["drawing_status"] == "RETURNED"


def test_cancel_revision_rejects_non_returned_status(client):
    """RETURNED가 아닌 상태에서는 취소 불가(400)."""
    sales = _make_user("rev_cancel_sales4", role="MANAGER", team="SALES", name="영업담당4")
    _login(client, sales)
    order = _make_returned_order(manager_name="영업담당4")
    order.structured_data = {**order.structured_data, "drawing_status": "TRANSFERRED"}
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(order, "structured_data")
    db_session.commit()
    order_id = order.id

    res = client.post(f"/api/orders/{order_id}/cancel-revision-request")
    assert res.status_code == 400
    assert res.get_json()["success"] is False
