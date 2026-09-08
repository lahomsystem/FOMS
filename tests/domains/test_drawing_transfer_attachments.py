"""도면 전달 → 주문 '도면' 탭 첨부 정본 등록 계약.

운영 실측(2026-09-09): 도면 마법사로 만든 도면을 전달하고 수령확정까지 해도 주문의 '도면'
탭이 비어 있었다. 그 탭의 정본은 ``OrderAttachment(category='drawing')`` 행인데
(:mod:`foms.api.files.order_routes`), 도면 경로 어디에도 그 행을 **만드는** 코드가 없었다.
전달은 이미 있는 행의 category 만 바꾸는 UPDATE 였고, 마법사 산출물
(``orders/<id>/drawing_wizard/exports/``)은 행 자체가 없어(저장/전달 분리 ``dc81a5658``)
대상 0건으로 조용히 지나갔다.

전달은 도면이 그 정본에 등록되는 유일한 시점이므로, 여기서 행이 생기는지 고정한다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.drawing.erp_orders_drawing import perform_drawing_transfer
from models import Order, OrderAttachment, User


def _make_user(username: str, *, team: str = "DRAWING", role: str = "ADMIN") -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        name=username,
        role=role,
        team=team,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_order(assignee_id: int) -> Order:
    order = Order(
        received_date="2026-09-09",
        customer_name="도면 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="DRAWING",
        manager_name="담당",
        is_erp_order=True,
        erp_stage_code="DRAWING",
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "parties": {"customer": {"name": "홍"}, "manager": {"name": "영업 김"}},
            "assignments": {"drawing_assignee_user_ids": [assignee_id]},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _drawing_attachments(order_id: int) -> list[OrderAttachment]:
    return (
        db_session.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order_id, OrderAttachment.category == "drawing")
        .all()
    )


def test_transfer_creates_drawing_attachment_for_wizard_export(app):
    """첨부 행이 없던 마법사 도면도 전달 시 '도면' 탭 정본에 등록된다."""
    user = _make_user("dws_att_new")
    order = _make_order(user.id)
    oid = order.id
    key = f"orders/{oid}/drawing_wizard/exports/도면1.png"

    with app.test_request_context():
        payload, status = perform_drawing_transfer(
            db_session, order, oid, user, user.id,
            files=[{"key": key, "filename": "도면1.png"}],
        )

    assert status == 200 and payload["success"] is True
    rows = _drawing_attachments(oid)
    assert [r.storage_key for r in rows] == [key], "전달한 도면이 첨부 정본에 없다"
    assert rows[0].filename == "도면1.png"
    assert rows[0].file_type == "image"
    assert rows[0].user_id == user.id


def test_transfer_does_not_duplicate_existing_attachment_row(app):
    """이미 행이 있는 key 는 category 갱신만 — 중복 행을 만들지 않는다."""
    user = _make_user("dws_att_dup")
    order = _make_order(user.id)
    oid = order.id
    key = f"orders/{oid}/drawing_gateway/기존.png"
    db_session.add(OrderAttachment(
        order_id=oid, filename="기존.png", file_type="image",
        category="measurement", storage_key=key, file_size=123, user_id=user.id,
    ))
    db_session.commit()

    with app.test_request_context():
        payload, status = perform_drawing_transfer(
            db_session, order, oid, user, user.id,
            files=[{"key": key, "filename": "기존.png"}],
        )

    assert status == 200 and payload["success"] is True
    db_session.expire_all()
    rows = _drawing_attachments(oid)
    assert len(rows) == 1, "같은 key 로 첨부 행이 중복 생성됐다"
    assert rows[0].file_size == 123, "기존 행이 새 행으로 대체됐다"


def test_transfer_does_not_create_rows_for_non_drawing_keys(app):
    """실측 등 도면 아닌 key 는 애초에 전달 대상이 아니므로 첨부 행도 안 생긴다."""
    user = _make_user("dws_att_leak")
    order = _make_order(user.id)
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
    keys = {r.storage_key for r in _drawing_attachments(oid)}
    assert drawing_key in keys
    assert measurement_key not in keys
