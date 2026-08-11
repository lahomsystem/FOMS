"""주문 변경 원장 계약 (ORDER-DIFF-01).

1안(``security_logs.detail['changes']``)으로는 "실측일이 바뀐 주문 전부" 같은 **필드 기준
질의**가 인덱스를 타지 못했다. 이 원장이 그 질문을 받는 자리이므로, 여기서 고정하는 것은
(a) 저장이 원장을 상한 없이 채우는가, (b) 헤더↔항목이 이어지는가, (c) 필드 필터가 실제로
좁히는가, (d) 원장 쓰기가 실패해도 저장이 살아남는가 네 가지다.
"""

import copy

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders import order_field_change_writer
from foms.services.orders.order_field_change_writer import path_template_of
from foms.services.orders.structured_diff import MAX_CHANGES
from models import Order, OrderFieldChange, SecurityLog, User


def _login_as_admin(client, username="ledger-admin"):
    """원장을 남길 ADMIN 세션."""
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Ledger Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_order(items=None) -> Order:
    """감사 대상 ERP 주문 1건."""
    order = Order(
        received_date="2026-08-11",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "RECEIVED"},
            "shipment": {},
            "schedule": {"measurement": {"date": "2026-08-12"}},
            "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
            "items": items if items is not None else [{"product_name": "붙박이장", "price": "500000"}],
            "site": {"address_full": "서울 테헤란로 123", "address_main": "서울 테헤란로 123",
                     "address_detail": ""},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _save(client, order_id: int, mutate):
    """구조화 전체 저장 1회(문서를 mutate 로 바꿔서 보낸다)."""
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    mutate(sd)
    response = client.put(f"/api/orders/{order_id}/structured",
                          json={"structured_data": sd, "structured_schema_version": 1})
    assert response.status_code == 200, response.get_data(as_text=True)[:200]
    db_session.expire_all()
    return response


def _ledger(order_id: int):
    """해당 주문의 원장 행(오래된 순)."""
    return (
        db_session.query(OrderFieldChange)
        .filter(OrderFieldChange.order_id == order_id)
        .order_by(OrderFieldChange.id)
        .all()
    )


def test_path_template_strips_item_index():
    """품목 번호를 지운 질의 키가 만들어진다 — 번호와 무관하게 "단가 변경"을 물을 수 있어야 한다."""
    assert path_template_of("items.2.price") == "items.*.price"
    assert path_template_of("items.10") == "items.*"
    assert path_template_of("schedule.measurement.date") == "schedule.measurement.date"


def test_save_writes_ledger_rows_linked_to_header(client):
    """저장이 원장을 채우고, change_set 으로 헤더(security_logs)와 이어진다."""
    _login_as_admin(client)
    order = _create_order()
    order_id = order.id

    def mutate(sd):
        sd["schedule"]["measurement"]["date"] = "2026-08-14"
        sd["items"][0]["price"] = "620000"

    _save(client, order_id, mutate)

    rows = _ledger(order_id)
    by_path = {row.path: row for row in rows}
    assert "schedule.measurement.date" in by_path
    assert "items.0.price" in by_path

    date_row = by_path["schedule.measurement.date"]
    assert (date_row.before_value, date_row.after_value, date_row.op) == ("2026-08-12", "2026-08-14", "set")

    price_row = by_path["items.0.price"]
    assert price_row.path_template == "items.*.price"
    assert price_row.item_index == 0
    assert price_row.item_name == "붙박이장"

    header = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ORDER_STRUCTURED_SAVED", SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id.desc())
        .first()
    )
    assert header.detail["change_set"]
    assert {row.change_set_id for row in rows} == {header.detail["change_set"]}
    assert header.detail["change_count"] == len(rows)


def test_ledger_keeps_everything_when_detail_is_capped(client):
    """화면 detail 은 상한이 있어도 원장은 전량이다(상한은 표를 읽기 위한 것이지 기록 축소가 아니다)."""
    _login_as_admin(client, username="ledger-cap")
    order = _create_order(items=[{"product_name": f"품목{i}"} for i in range(MAX_CHANGES + 6)])
    order_id = order.id

    def mutate(sd):
        for index, item in enumerate(sd["items"]):
            item["product_name"] = f"변경{index}"

    _save(client, order_id, mutate)

    header = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ORDER_STRUCTURED_SAVED", SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id.desc())
        .first()
    )
    rows = _ledger(order_id)
    name_rows = [row for row in rows if row.path_template == "items.*.product_name"]

    assert len(header.detail["changes"]) == MAX_CHANGES
    assert header.detail["truncated"] == header.detail["change_count"] - MAX_CHANGES
    assert len(name_rows) == MAX_CHANGES + 6  # 원장에는 전부


def test_changed_field_filter_narrows_audit_screen(client):
    """변경 필드 필터가 해당 저장만 남긴다(무관한 저장은 목록에서 빠진다)."""
    _login_as_admin(client, username="ledger-filter")
    target_id = _create_order().id
    other_id = _create_order().id

    _save(client, target_id, lambda sd: sd["schedule"]["measurement"].__setitem__("date", "2026-08-15"))
    _save(client, other_id, lambda sd: sd["parties"]["customer"].__setitem__("name", "김철수"))

    page = client.get("/security_logs", query_string={"changed_field": "schedule.measurement.date"})
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    assert f"#{target_id}" in body
    assert f"주문 #{other_id}" not in body


def test_changed_field_filter_with_no_match_returns_empty(client):
    """조건에 맞는 변경이 없으면 빈 목록이다 — 필터를 조용히 무시하면 거짓 목록이 된다."""
    _login_as_admin(client, username="ledger-empty")
    order = _create_order()
    _save(client, order.id, lambda sd: sd["schedule"]["measurement"].__setitem__("date", "2026-08-16"))

    page = client.get("/security_logs", query_string={"changed_field": "totals.shipping_price",
                                                     "changed_value": "존재하지-않는-값"})

    assert page.status_code == 200
    assert "로그 정보가 없습니다" in page.get_data(as_text=True)


def test_ledger_failure_does_not_break_save(client, monkeypatch):
    """원장 기록이 실패해도 주문 저장은 성공한다(fail-open) — 단 조용히 넘어가지는 않는다."""
    _login_as_admin(client, username="ledger-failopen")
    order = _create_order()
    order_id = order.id

    def _boom(*args, **kwargs):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(order_field_change_writer, "build_change_rows", _boom)

    _save(client, order_id, lambda sd: sd["schedule"]["measurement"].__setitem__("date", "2026-08-17"))

    assert _ledger(order_id) == []
    header = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ORDER_STRUCTURED_SAVED", SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id.desc())
        .first()
    )
    # 헤더(사람용 요약 + 화면 detail)는 원장과 독립적으로 남아야 한다.
    assert header is not None
    assert header.detail["change_count"] >= 1
