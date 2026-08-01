"""STATE-DRAWING-01 도면 상태전이·transfer 조립 계약 (domain lane).

erp_orders_drawing / erp_orders_revision 핸들러의 canonical 규약을 SQLite domain 레인으로
고정한다(PG 원자성 대조는 tests/postgres/test_state_drawing.py):

* transfer 소스 = WIZ-TRANSFER helper 조립 → 도면 key 경로만 통과(실측/일반 첨부 유출 차단).
* explicit assignment 만 쓰기 허용 → 도면팀 소속(team-only write)은 거부.
* 재전달은 수정요청 체크리스트 완료 후에만 허용.
* 전달 취소 = 정확한 원상복원 + 회수 blob STORAGE_DELETE outbox enqueue(동기 R2 삭제 없음).
* 도면 변경 ack 는 idempotent(재요청 중복 0)이며 생산 ack 와 혼합되지 않는다.
"""
from __future__ import annotations

import copy

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from models import (
    DomainSideEffectOutbox,
    Notification,
    Order,
    OrderAttachment,
    OrderEvent,
    User,
)
from foms.api.drawing.erp_orders_drawing import perform_drawing_transfer


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


def _make_order(*, sd: dict) -> Order:
    order = Order(
        received_date="2026-07-01",
        customer_name="도면 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="DRAWING",
        manager_name="담당",
        is_erp_order=True,
        structured_data=sd,
        erp_stage_code="DRAWING",
    )
    db_session.add(order)
    db_session.commit()
    return order


def _base_sd(assignee_id: int | None) -> dict:
    assignments = {"drawing_assignee_user_ids": [assignee_id]} if assignee_id else {}
    return {
        "workflow": {"stage": "DRAWING"},
        "parties": {"customer": {"name": "홍"}, "manager": {"name": "영업 김"}},
        "assignments": assignments,
    }


# --- transfer 소스 조립: 도면 key 필터(leak 차단) -----------------------------


def test_transfer_filters_non_drawing_keys(app):
    """WIZ-TRANSFER helper 조립 → 도면 key 만 drawing_current_files 에 들어간다."""
    user = _make_user("sd_leak", team="DRAWING")
    order = _make_order(sd={**_base_sd(user.id)})
    oid = order.id
    drawing_key = f"orders/{oid}/drawing_wizard/exports/ok.png"
    measurement_key = f"orders/{oid}/measurement/leak.jpg"

    with app.test_request_context():
        payload, status = perform_drawing_transfer(
            db_session, order, oid, user, user.id,
            files=[
                {"key": drawing_key, "filename": "ok.png"},
                {"key": measurement_key, "filename": "leak.jpg"},
            ],
        )

    assert status == 200 and payload["success"] is True
    saved = db_session.get(Order, oid)
    keys = [f.get("key") for f in saved.structured_data.get("drawing_current_files", [])]
    assert drawing_key in keys
    assert measurement_key not in keys  # 실측 첨부 유출 차단


# --- explicit assignment: team-only write 거부 --------------------------------


def test_transfer_rejects_team_only_write(app):
    """도면팀 소속만으로는(지정 담당 아님) 전달 불가 — 지정 담당자만 허용."""
    assignee = _make_user("sd_assignee", team="DRAWING")
    intruder = _make_user("sd_intruder", team="DRAWING")
    order = _make_order(sd={**_base_sd(assignee.id)})
    oid = order.id
    key = f"orders/{oid}/drawing_wizard/exports/a.png"

    with app.test_request_context():
        payload, status = perform_drawing_transfer(
            db_session, order, oid, intruder, intruder.id,
            files=[{"key": key, "filename": "a.png"}],
        )
    assert status == 403 and payload["success"] is False

    with app.test_request_context():
        payload2, status2 = perform_drawing_transfer(
            db_session, order, oid, assignee, assignee.id,
            files=[{"key": key, "filename": "a.png"}],
        )
    assert status2 == 200 and payload2["success"] is True


# --- 재전달 전 수정요청 체크리스트 ---------------------------------------------


def test_retransfer_blocked_until_checklist(app):
    """RETURNED 에서 미체크 수정요청이 있으면 재전달 거부, 체크 후 허용."""
    user = _make_user("sd_chk", team="DRAWING")
    order = _make_order(sd={
        **_base_sd(user.id),
        "drawing_status": "RETURNED",
        "drawing_transfer_history": [{
            "action": "REQUEST_REVISION", "at": "2026-07-01 00:00:00",
            "by_user_id": 999, "review_check": {"checked": False},
        }],
    })
    oid = order.id
    key = f"orders/{oid}/drawing_wizard/exports/rev.png"

    with app.test_request_context():
        payload, status = perform_drawing_transfer(
            db_session, order, oid, user, user.id,
            files=[{"key": key, "filename": "rev.png"}],
        )
    assert status == 400 and payload["success"] is False

    sd = copy.deepcopy(order.structured_data)
    sd["drawing_transfer_history"][0]["review_check"] = {"checked": True}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()

    with app.test_request_context():
        payload2, status2 = perform_drawing_transfer(
            db_session, order, oid, user, user.id,
            files=[{"key": key, "filename": "rev.png"}],
        )
    assert status2 == 200 and payload2["success"] is True


# --- 전달 취소: 원상복원 + STORAGE_DELETE outbox ------------------------------


def test_cancel_transfer_restores_and_enqueues_storage_delete(app, client):
    """취소 시 정확 원상복원 + 회수 blob STORAGE_DELETE outbox(enqueue-only) + event/version."""
    admin = _make_user("sd_cancel_admin", role="ADMIN")
    _login(client, admin)

    old_file = {"key": "PLACEHOLDER_OLD", "filename": "old.png"}
    new_file = {"key": "PLACEHOLDER_NEW", "filename": "new.png"}
    order = _make_order(sd={
        "workflow": {"stage": "DRAWING"},
        "parties": {"customer": {"name": "홍"}, "manager": {"name": "영업 김"}},
        "drawing_status": "TRANSFERRED",
        "drawing_current_files": [old_file, new_file],
        "drawing_transfer_history": [{
            "action": "TRANSFER", "by_user_id": admin.id,
            "transferred_at": "2026-07-02 00:00:00",
            "files": [new_file], "previous_current_files": [old_file], "mode": "APPEND",
        }],
    })
    oid = order.id
    old_key = f"orders/{oid}/drawing_wizard/exports/old.png"
    new_key = f"orders/{oid}/drawing_wizard/exports/new.png"
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_current_files"][0]["key"] = old_key
    sd["drawing_current_files"][1]["key"] = new_key
    sd["drawing_transfer_history"][0]["files"][0]["key"] = new_key
    sd["drawing_transfer_history"][0]["previous_current_files"][0]["key"] = old_key
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.add(OrderAttachment(
        order_id=oid, filename="new.png", file_type="image",
        category="drawing", file_size=1, storage_key=new_key,
    ))
    db_session.commit()

    resp = client.post(f"/api/orders/{oid}/cancel-transfer")
    assert resp.status_code == 200 and resp.get_json()["success"] is True

    saved = db_session.get(Order, oid)
    assert saved.structured_data["drawing_status"] == "PENDING"
    restored = [f.get("key") for f in saved.structured_data["drawing_current_files"]]
    assert restored == [old_key]  # 정확 원상복원(새 파일만 회수, 기존 보존)
    assert saved.mutation_version == 2  # version bump

    # OrderAttachment DB row 는 tx 에서 제거됨.
    assert db_session.query(OrderAttachment).filter_by(storage_key=new_key).count() == 0

    # STORAGE_DELETE outbox 예약(회수 key), ORDER_EVENT source.
    rows = db_session.query(DomainSideEffectOutbox).filter_by(
        effect_type="STORAGE_DELETE").all()
    keys = {r.payload.get("object_key") for r in rows}
    assert new_key in keys
    assert old_key not in keys  # 보존 파일은 삭제 예약 금지
    assert all(r.order_event_id is not None for r in rows)

    ev = db_session.query(OrderEvent).filter_by(
        order_id=oid, event_type="DRAWING_TRANSFER_CANCELLED").all()
    assert len(ev) == 1


# --- 도면 변경 ack: idempotency + 생산 미혼합 --------------------------------


def test_ack_order_change_idempotent_and_not_production(app, client):
    """도면 변경 ack 는 재요청 중복 0(idempotent)이며 생산 ack 를 만들지 않는다."""
    admin = _make_user("sd_ack_admin", role="ADMIN")
    _login(client, admin)
    order = _make_order(sd={
        "workflow": {"stage": "DRAWING"},
        "parties": {"customer": {"name": "홍"}},
        "drawing": {"order_change_pending": True},
        "drawing_transfer_history": [{
            "action": "ERP_ORDER_CHANGED", "at": "2026-07-03 00:00:00",
            "by_user_id": 5, "acked": False, "note": "변경",
        }],
    })
    oid = order.id

    r1 = client.post(f"/api/orders/{oid}/drawing/ack-order-change")
    assert r1.status_code == 200 and r1.get_json()["acked"] is True
    r2 = client.post(f"/api/orders/{oid}/drawing/ack-order-change")
    assert r2.status_code == 200 and r2.get_json()["acked"] is False  # 재요청 no-op

    saved = db_session.get(Order, oid)
    hist = saved.structured_data["drawing_transfer_history"]
    acked = [h for h in hist if h.get("action") == "ERP_ORDER_CHANGED" and h.get("acked")]
    assert len(acked) == 1  # 정확히 한 번만 acked

    prod = db_session.query(Notification).filter(
        Notification.order_id == oid,
        Notification.notification_type == "PRODUCTION_ORDER_CHANGED",
    ).all()
    assert prod == []  # 생산 ACK 미혼합
