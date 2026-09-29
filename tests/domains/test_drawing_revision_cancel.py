"""Tests for the drawing revision-request cancel API (영업측 수정요청 취소).

전달취소(도면팀)의 대칭축인 수정요청 취소(영업측/관리자)를 검증한다.
- 정상 취소 시 drawing_status가 이전 상태(TRANSFERRED/CONFIRMED)로 복귀하고
  REQUEST_REVISION 이력이 빠지는 대신 REVISION_CANCELLED(원래 요청 전체·취소자·이유)가 붙는지.
- 취소는 아무 파일도 지우지 않는지(M2 — 예전에는 참고 파일을 커밋 전에 R2 에서 지웠다).
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
    assert actions == ["TRANSFER", "REVISION_CANCELLED"]


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


def test_cancel_revision_keeps_files_and_records_cancellation(client, monkeypatch):
    """취소는 아무 파일도 지우지 않고, REVISION_CANCELLED 에 원래 요청과 사진 key 가 남는다."""
    storage = _FakeStorage()
    monkeypatch.setattr(revision_api, "get_storage", lambda: storage, raising=False)

    sales = _make_user("rev_cancel_sales3", role="MANAGER", team="SALES", name="영업담당3")
    _login(client, sales)

    ref_key = "orders/rc3/drawing_gateway/revisions/ref1.jpg"
    original_key = "orders/rc3/original.pdf"
    request_entry = {
        "action": "REQUEST_REVISION", "at": "2026-09-29 02:00:00", "note": "손잡이 위치",
        "by_user_id": sales.id, "by_user_name": "영업담당3",
        "files": [{"key": ref_key, "filename": "ref1.jpg"}],
        "target_drawing_keys": [original_key],
        "review_check": {"checked": True, "checked_by_name": "도면팀"},
    }
    order = _make_returned_order(
        manager_name="영업담당3",
        current_files=[{"key": original_key, "filename": "original.pdf"}],
        history=[
            {"action": "TRANSFER", "mode": "APPEND", "files": [{"key": original_key, "filename": "original.pdf"}]},
            request_entry,
        ],
    )
    order_id = order.id

    for key, category in ((ref_key, "drawing_gateway"), (original_key, "drawing")):
        db_session.add(OrderAttachment(
            order_id=order_id, filename=key.rsplit("/", 1)[-1], file_type="file",
            category=category, storage_key=key,
        ))
    db_session.commit()

    # 지금 화면 두 곳처럼 본문·Content-Type 없이 POST 한다(415/400 이 나면 안 된다).
    res = client.post(f"/api/orders/{order_id}/cancel-revision-request")
    assert res.status_code == 200, res.get_data(as_text=True)

    assert storage.deleted_keys == [], "수정요청 취소가 스토리지 파일을 지웠다"
    remaining_keys = {
        row.storage_key
        for row in db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id)
    }
    assert remaining_keys == {ref_key, original_key}, "수정요청 취소가 첨부 행을 지웠다"

    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data
    assert sd["drawing_current_files"] == [{"key": original_key, "filename": "original.pdf"}]
    cancelled = [h for h in sd["drawing_transfer_history"] if h.get("action") == "REVISION_CANCELLED"]
    assert len(cancelled) == 1
    entry = cancelled[0]
    assert entry["request"] == request_entry  # 메모·대상·참고사진·반영 체크 전부 그대로
    assert entry["by_user_id"] == sales.id and entry["by_user_name"] == "영업담당3"
    assert entry["at"] and entry["reason"] == ""
    assert sd["drawing_transfer_history"][-1]["action"] == "REVISION_CANCELLED"


def test_cancel_revision_records_reason_from_body(client):
    """선택 본문 ``{reason}`` 이 이력에 남는다(200자까지)."""
    sales = _make_user("rev_cancel_reason", role="MANAGER", team="SALES", name="영업담당R")
    _login(client, sales)
    order = _make_returned_order(manager_name="영업담당R")
    order_id = order.id

    res = client.post(f"/api/orders/{order_id}/cancel-revision-request",
                      json={"reason": "  고객이 요청을 거둬들임  " + "가" * 300})
    assert res.status_code == 200, res.get_data(as_text=True)
    db_session.expire_all()
    entry = db_session.get(Order, order_id).structured_data["drawing_transfer_history"][-1]
    assert entry["action"] == "REVISION_CANCELLED"
    assert entry["reason"].startswith("고객이 요청을 거둬들임")
    assert len(entry["reason"]) == 200


def test_cancel_revision_with_non_json_body_still_succeeds(client):
    """Content-Type 이 JSON 이 아닌 본문이어도 취소는 된다(get_json(silent=True))."""
    sales = _make_user("rev_cancel_form", role="MANAGER", team="SALES", name="영업담당F")
    _login(client, sales)
    order = _make_returned_order(manager_name="영업담당F")
    res = client.post(f"/api/orders/{order.id}/cancel-revision-request", data="reason=abc",
                      content_type="application/x-www-form-urlencoded")
    assert res.status_code == 200, res.get_data(as_text=True)


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
