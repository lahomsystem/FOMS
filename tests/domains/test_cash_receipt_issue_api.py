"""현금영수증 발행 API 계약 (POST /api/orders/<id>/cash-receipt/issue).

- 발행: settlement.cash_receipt = {issued: True, at, by, note} 기록, {success, data} 반환.
- 재발행 차단(멱등 경계): 이미 발행된 건은 409.
- 권한: 시공팀(CONSTRUCTION) 403.
- 완료·AS 상태가 아니면 400.
- 파생 상태(cash_receipt_state) 'issued' 반영.
- OrderEvent CASH_RECEIPT_ISSUED 기록 + deepcopy+flag_modified 저장.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from foms.web.cs.completion_dashboard import _cash_receipt_issued, _cash_receipt_state
from models import Order, OrderEvent, User


def _make_user(username: str, *, role: str = "STAFF", team: str | None = None) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(status: str = "COMPLETED", *, cash_receipt_text: str = "현금영수증 010-1111-2222") -> Order:
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="영수증 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Bob",
        is_erp_order=True,
        structured_data={"payment": {"cash_receipt": cash_receipt_text}},
        erp_stage_code="완료",
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_issue_records_cash_receipt(client):
    user = _make_user("cr_admin", role="ADMIN")
    user_name = user.name
    _login(client, user)
    order_id = _make_order().id

    resp = client.post(
        f"/api/orders/{order_id}/cash-receipt/issue",
        json={"note": "지류 발행"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    cr = data["data"]["cash_receipt"]
    assert cr["issued"] is True
    assert cr["note"] == "지류 발행"
    assert cr["at"]
    assert cr["by"] == user_name

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["settlement"]["cash_receipt"]["issued"] is True


def test_reissue_returns_409(client):
    user = _make_user("cr_admin2", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id

    first = client.post(f"/api/orders/{order_id}/cash-receipt/issue", json={})
    assert first.status_code == 200
    second = client.post(f"/api/orders/{order_id}/cash-receipt/issue", json={})
    assert second.status_code == 409
    assert second.get_json()["success"] is False


def test_construction_team_forbidden(client):
    user = _make_user("cr_construction", role="STAFF", team="CONSTRUCTION")
    _login(client, user)
    order_id = _make_order().id
    resp = client.post(f"/api/orders/{order_id}/cash-receipt/issue", json={})
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


def test_non_target_status_returns_400(client):
    user = _make_user("cr_admin3", role="ADMIN")
    _login(client, user)
    order_id = _make_order(status="PRODUCTION").id
    resp = client.post(f"/api/orders/{order_id}/cash-receipt/issue", json={})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_missing_order_returns_404(client):
    user = _make_user("cr_admin4", role="ADMIN")
    _login(client, user)
    resp = client.post("/api/orders/999999/cash-receipt/issue", json={})
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


def test_order_event_recorded(client):
    user = _make_user("cr_admin5", role="ADMIN")
    user_id = user.id
    _login(client, user)
    order_id = _make_order().id

    client.post(f"/api/orders/{order_id}/cash-receipt/issue", json={"note": "메모"})
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "CASH_RECEIPT_ISSUED")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["note"] == "메모"
    assert events[0].created_by_user_id == user_id


def test_cash_receipt_state_derivation():
    """파생 헬퍼: issued > requested > none 우선순위."""
    assert _cash_receipt_state("요청텍스트", True) == "issued"
    assert _cash_receipt_state("요청텍스트", False) == "requested"
    assert _cash_receipt_state("", False) == "none"
    assert _cash_receipt_issued({"cash_receipt": {"issued": True}}) is True
    assert _cash_receipt_issued({"cash_receipt": {"issued": False}}) is False
    assert _cash_receipt_issued({}) is False
    assert _cash_receipt_issued(None) is False
