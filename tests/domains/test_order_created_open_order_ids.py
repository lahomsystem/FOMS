"""생성 기록 — ``ORDER_CREATED`` payload 의 ``open_order_ids`` (설계서 2026-11-20 6.2 · M17).

주문을 만드는 모든 길이 그 순간 같은 고객의 진행 중 주문 번호를 남긴다. 4~8주 뒤 "진행 중 주문이 있는데도 새로
만든 주문" 수를 여기서 센다. 길은 둘로 모인다: ``create_order``(마법사 · 옛 폼 · 복사 · 협력사 · 채널톡 · 네이버)와
PC 주문 폼의 초안 승격.

완료 기준: PC 승격 · 마법사 · 옛 폼 · ``create_order`` 직접 호출 모두 기록 · 자기 자신과 남의 초안 줄은 안 셈 ·
걸린 주문이 없으면 빈 목록 · 찾기가 실패해도 주문은 만들어지고 열쇠만 빠짐 · SQL 오류는 찾기의 저장점만 되돌림 ·
찾기가 만드는 중인 줄을 flush 하지 않음.
"""

from __future__ import annotations

import json

from sqlalchemy import event, text

from db import db_session
from foms.services.orders import open_order_lookup
from foms.services.orders.order_create import create_order
from models import Order, OrderEvent
from tests.domains.test_erp_draft_order_events import _autosave, _create_draft, _erp_sd, _events, _login, _make_user
from tests.domains.test_erp_order_draft_wizard import _login as _wizard_login
from tests.domains.test_erp_order_draft_wizard import wizard_enabled  # noqa: F401 — fixture

_CREATED = "ORDER_CREATED"
PC_PHONE = "010-2222-3333"  # _erp_sd 의 고객 전화


def _open_order(phone: str, *, stage: str = "PRODUCTION", status: str | None = None, name: str = "먼저 있던 고객") -> int:
    """같은 고객의 주문 한 줄(전화 숫자 칸까지 채운 ERP 주문)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    order = Order(
        received_date="2026-11-01", customer_name=name, phone=phone, address="합성시 가상구 다른로 1",
        product="합성 붙박이장", status=status or stage, is_erp_order=True, erp_stage_code=stage,
        erp_phone_digits=digits,
        structured_data={"workflow": {"stage": stage}, "parties": {"customer": {"name": name, "phone": phone}}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def test_pc_draft_promotion_records_in_progress_orders(client):
    _login(client, _make_user("c7_pc_promote", role="ADMIN"))
    existing_id = _open_order(PC_PHONE)
    _open_order(PC_PHONE, stage="COMPLETED")  # 대조군: 완료 주문
    _open_order(PC_PHONE, stage="RECEIVED", status="DRAFT")  # 대조군: 남이 쓰다 만 초안 줄
    order_id = _create_draft(client, "c7-pc-promote")
    assert _autosave(client, "c7-pc-promote").status_code == 200  # 자동 저장이 자기 초안 줄의 전화 숫자 칸을 채운다

    resp = client.put(f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd()})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    created = _events(order_id, _CREATED)
    assert len(created) == 1
    assert created[0].payload == {"via": "erp_draft", "status": "RECEIVED", "open_order_ids": [existing_id]}


def test_pc_draft_promotion_records_empty_list_when_no_other_order(client):
    _login(client, _make_user("c7_pc_alone", role="ADMIN"))
    _open_order("010-7777-0001")  # 대조군: 다른 고객
    order_id = _create_draft(client, "c7-pc-alone")

    resp = client.put(f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd()})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _events(order_id, _CREATED)[0].payload["open_order_ids"] == []


def test_wizard_submit_records_in_progress_orders(client, app, wizard_enabled):  # noqa: F811
    _wizard_login(client, app, "c7_wizard_user")
    phone = "010-9999-8888"
    existing_id = _open_order(phone, stage="CONSTRUCTION")
    key = "new.c7-wizard"
    payload = {"schema_version": 1, "step": 4, "data": {
        "customer_name": "마법사 고객", "phone": phone, "address": "경기도 성남시", "received_date": "2026-11-20",
        "items": [{"product_name": "주방장", "spec_rows": [{"spec_width": "3000", "spec_depth": "600", "spec_height": "2300"}]}],
        "schedule": {}}}
    client.put("/api/erp/order-draft", data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
               content_type="application/json")

    submit = client.post("/api/erp/order-draft/submit", data=json.dumps({"draft_key": key}),
                         content_type="application/json")

    assert submit.status_code == 200, submit.get_data(as_text=True)
    created = _events(submit.get_json()["data"]["order_id"], _CREATED)
    assert len(created) == 1
    assert created[0].payload["open_order_ids"] == [existing_id]
    assert created[0].payload["status"] == "RECEIVED"


def test_legacy_form_records_in_progress_orders(client):
    _login(client, _make_user("c7_legacy_form", role="STAFF", team="SALES"))
    phone = "010-4444-5555"
    existing_id = _open_order(phone, stage="MEASURE")

    resp = client.post("/add", data={
        "create_mode": "LEGACY", "received_date": "2026-11-20", "received_time": "10:00",
        "customer_name": "옛 폼 고객", "phone": phone, "address": "서울 강남대로 1", "product": "옛 제품",
    }, follow_redirects=False)

    assert resp.status_code in (301, 302), resp.get_data(as_text=True)
    order = db_session.query(Order).filter(Order.customer_name == "옛 폼 고객").one()
    assert _events(order.id, _CREATED)[0].payload["open_order_ids"] == [existing_id]


def test_create_order_records_by_address_and_skips_itself(app):
    owner = _make_user("c7_direct_owner", role="STAFF", team="SALES")
    home = "경기도 화성시 시험대로10길 20 (가상동) 2505동 1103호"
    family = Order(
        received_date="2026-11-01", customer_name="가족", phone="010-1010-2020", address=home, product="장",
        status="DRAWING", is_erp_order=True, erp_stage_code="DRAWING", erp_phone_digits="01010102020",
        structured_data={"workflow": {"stage": "DRAWING"}},
    )
    db_session.add(family)
    db_session.commit()

    order = create_order(
        db_session, actor_user_id=owner.id, owner_user_id=owner.id, is_erp_order=True,
        order_fields=dict(received_date="2026-11-20", customer_name="본인", phone="010-3030-4040",
                          address="시험대로10길 20 합성아파트 2505동 1103호", product="장", status="RECEIVED"),
        structured_data={"parties": {"customer": {"name": "본인", "phone": "010-3030-4040"}},
                         "items": [{"product_name": "장"}]},
    )
    db_session.commit()

    event = db_session.query(OrderEvent).filter_by(order_id=order.id, event_type=_CREATED).one()
    assert event.payload == {"owner_user_id": owner.id, "status": "RECEIVED", "open_order_ids": [family.id]}


def test_lookup_failure_never_blocks_creation(app, monkeypatch):
    owner = _make_user("c7_failopen_owner", role="STAFF", team="SALES")

    def boom(*_args, **_kwargs):
        raise RuntimeError("찾기 실패")

    monkeypatch.setattr(open_order_lookup, "_matches", boom)

    order = create_order(
        db_session, actor_user_id=owner.id, owner_user_id=owner.id, is_erp_order=False,
        order_fields=dict(received_date="2026-11-20", customer_name="실패해도", phone="010-5050-6060",
                          address="-", product="장", status="RECEIVED"),
    )
    db_session.commit()

    event = db_session.query(OrderEvent).filter_by(order_id=order.id, event_type=_CREATED).one()
    assert event.payload == {"owner_user_id": owner.id, "status": "RECEIVED"}, "못 셌으면 열쇠를 넣지 않는다"


def _savepoint_calls(engine):
    """연결 단계 저장점 신호(열기 · 되돌리기 · 풀기)를 센다."""
    calls: list[str] = []
    listeners = {
        "savepoint": lambda conn, name: calls.append("savepoint"),
        "rollback_savepoint": lambda conn, name, context: calls.append("rollback_savepoint"),
        "release_savepoint": lambda conn, name, context: calls.append("release_savepoint"),
    }
    for name, fn in listeners.items():
        event.listen(engine, name, fn)
    return calls, listeners


def test_db_error_inside_lookup_rolls_back_only_its_savepoint(app, monkeypatch):
    owner = _make_user("c7_sql_error_owner", role="STAFF", team="SALES")
    engine = db_session.get_bind()

    def broken_query(db, *_args, **_kwargs):
        db.execute(text("select * from c3_no_such_table"))  # 진짜 SQL 오류
        return []

    monkeypatch.setattr(open_order_lookup, "_by_phone", broken_query)
    calls, listeners = _savepoint_calls(engine)
    try:
        order = create_order(
            db_session, actor_user_id=owner.id, owner_user_id=owner.id, is_erp_order=False,
            order_fields=dict(received_date="2026-11-20", customer_name="오류 뒤에도", phone="010-5050-7070",
                              address="-", product="장", status="RECEIVED"),
        )
        db_session.commit()
    finally:
        for name, fn in listeners.items():
            event.remove(engine, name, fn)

    assert calls == ["savepoint", "rollback_savepoint"], "찾기만 저장점 안에서 되돌린다"
    event_row = db_session.query(OrderEvent).filter_by(order_id=order.id, event_type=_CREATED).one()
    assert "open_order_ids" not in event_row.payload, "못 셌으면 열쇠를 넣지 않는다"
    # 세션은 그대로 쓸 수 있다.
    assert db_session.get(Order, order.id).customer_name == "오류 뒤에도"
    db_session.add(OrderEvent(order_id=order.id, event_type="C3_AFTER", payload={}))
    db_session.commit()


def test_successful_lookup_releases_its_savepoint(app):
    owner = _make_user("c7_sql_ok_owner", role="STAFF", team="SALES")
    engine = db_session.get_bind()
    calls, listeners = _savepoint_calls(engine)
    try:
        create_order(
            db_session, actor_user_id=owner.id, owner_user_id=owner.id, is_erp_order=False,
            order_fields=dict(received_date="2026-11-20", customer_name="잘 셈", phone="010-5050-8080",
                              address="-", product="장", status="RECEIVED"),
        )
        db_session.commit()
    finally:
        for name, fn in listeners.items():
            event.remove(engine, name, fn)

    assert calls == ["savepoint", "release_savepoint"]


def test_lookup_does_not_flush_pending_changes(app):
    """초안 승격 길은 바꾼 칸을 flush 하지 않은 채 부른다 — ``Session.begin_nested()`` 는 여기서 flush 한다."""
    existing_id = _open_order("010-6060-7070")
    pending = Order(received_date="2026-11-20", customer_name="아직 안 밀어 넣음", phone="010-6060-7070",
                    address="-", product="장", status="RECEIVED")
    db_session.add(pending)

    payload = open_order_lookup.created_event_payload(db_session, pending, {"via": "test"})

    assert pending in db_session.new, "찾기가 만드는 중인 줄을 flush 했다"
    assert payload == {"via": "test", "open_order_ids": [existing_id]}
    db_session.rollback()
