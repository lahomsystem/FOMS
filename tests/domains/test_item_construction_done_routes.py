"""제품마다 '시공 끝' — 목록 GET · 되돌리기 · 폼 저장 보호 · 남은 시공 한 줄 · 기록 글.

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md`` 4.1 · 5.1 · 5.4 · 5.5 (N5 · N9).
"""

from __future__ import annotations

import datetime
import itertools
import uuid
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import order_event_display as ev
from foms.services.audit_message_display import ACTION_LABELS
from foms.services.orders import construction_dates as cd
from foms.services.orders.construction_visit import PARTIAL_VISIT_NOTE_PREFIX, partial_visit_note
from foms.services.orders.item_construction_done import DONE_KEY
from models import Order, OrderEvent, SecurityLog, User

UID_A, UID_B, UID_C = (str(uuid.uuid4()) for _ in range(3))
FIRST_DAY, LAST_DAY = "2026-11-05", "2026-11-17"
_counter = itertools.count(1)


def _login(client, *, role: str = "STAFF", team: str | None = "CS") -> int:
    n = next(_counter)
    user = User(username=f"icdr-{n}", password=generate_password_hash("pw"), role=role, team=team,
                name=f"직원{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user.id


def _items(dated: bool = True) -> list[dict]:
    rows = [
        {"uid": UID_A, "product_name": "화장대", "construction_date": FIRST_DAY},
        {"uid": UID_B, "product_name": "베란다장", "construction_date": FIRST_DAY},
        {"uid": UID_C, "product_name": "부엌가구", "construction_date": LAST_DAY},
    ]
    if not dated:
        for row in rows:
            row.pop("construction_date")
    return rows


def _mark(uid: str, day: str = FIRST_DAY) -> dict:
    return {uid: {"date": day, "at": f"{day}T17:40:00+09:00", "by_user_id": None, "by_name": "시공팀",
                  "source": "visit", "attempt_id": None}}


def _sd(stage: str = "CONSTRUCTION", *, dated: bool = True, marks: dict | None = None) -> dict:
    sd = {
        "entity_type": "order_structured",
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 테헤란로 1", "address_main": "서울 테헤란로 1"},
        "schedule": {"construction": {"date": f"{FIRST_DAY}, {LAST_DAY}"}},
        "items": _items(dated),
        "flags": {"urgent": False, "urgent_reason": "", "factory2": False},
    }
    if marks:
        sd[DONE_KEY] = marks
    return sd


def _make_order(stage: str = "CONSTRUCTION", **kw) -> int:
    order = Order(received_date=date.today().isoformat(), customer_name="홍길동", phone="010-1234-5678",
                  address="서울 테헤란로 1", product="붙박이장", status=stage, manager_name="Bob",
                  is_erp_order=True, structured_data=_sd(stage, **kw), erp_stage_code=stage)
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _visit_items(client, oid, day=FIRST_DAY):
    return client.get(f"/api/orders/{oid}/construction/visit-items" + (f"?date={day}" if day else ""))


def _undo(client, oid, uid, reason="잘못 눌렀어요"):
    return client.post(f"/api/orders/{oid}/items/{uid}/construction-done/undo", json={"reason": reason})


# --------------------------------------------------------------------------- #
# GET visit-items (약속 1)
# --------------------------------------------------------------------------- #
def test_visit_items_shape_for_split_order(client):
    _login(client, team="CONSTRUCTION")
    oid = _make_order(marks=_mark(UID_A))

    resp = _visit_items(client, oid)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    data = body["data"]
    assert data["enabled"] is True and data["split"] is True and data["date"] == FIRST_DAY
    assert data["items"] == [
        {"ref": UID_B, "name": "베란다장", "last_date": FIRST_DAY, "last_label": "11/5", "precheck": True},
        {"ref": UID_C, "name": "부엌가구", "last_date": LAST_DAY, "last_label": "11/17", "precheck": False},
    ]
    assert data["done"] == [{"uid": UID_A, "name": "화장대", "date": FIRST_DAY, "date_label": "11/5"}]
    assert data["remaining_summary"] == "11/5 베란다장 · 11/17 부엌가구"


def test_visit_items_empty_for_non_split_order_and_flag_off(client, monkeypatch):
    _login(client, team="CONSTRUCTION")
    plain = _make_order(dated=False)
    data = _visit_items(client, plain).get_json()["data"]
    assert data["enabled"] is True and data["split"] is False
    assert data["items"] == [] and data["done"] == [] and data["remaining_summary"] == ""

    monkeypatch.setenv("FOMS_ITEM_CONSTRUCTION_DONE_ENABLED", "0")
    split = _make_order()
    data = _visit_items(client, split).get_json()["data"]
    assert data["enabled"] is False and data["split"] is False and data["items"] == []


def test_visit_items_default_date_bad_date_permission_and_missing(app, client):
    oid = _make_order()
    assert app.test_client().get(f"/api/orders/{oid}/construction/visit-items").status_code == 401  # 로그인 없음
    _login(client, team="CONSTRUCTION")
    resp = _visit_items(client, oid, day=None)
    assert resp.status_code == 200 and resp.get_json()["data"]["date"]  # 오늘(KST)
    assert _visit_items(client, oid, day="2026-02-30").status_code == 400
    assert _visit_items(client, 987654321).status_code == 404

    _login(client, team=None)  # 시공 권한도 ERP 편집도 없는 직원
    assert _visit_items(client, oid).status_code == 403


# --------------------------------------------------------------------------- #
# 되돌리기 (약속 4, N9)
# --------------------------------------------------------------------------- #
def test_undo_by_cs_removes_mark_and_records(client):
    user_id = _login(client, team="CS")
    oid = _make_order(marks={**_mark(UID_A), **_mark(UID_B)})
    version = _fresh(oid).mutation_version

    resp = _undo(client, oid, UID_A)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json() == {"success": True, "data": {"uid": UID_A}, "error": None}

    order = _fresh(oid)
    assert set(order.structured_data[DONE_KEY]) == {UID_B}
    assert order.mutation_version == version + 1
    event = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="ITEM_CONSTRUCTION_DONE_UNDONE").one()
    assert event.payload["uid"] == UID_A and event.payload["name"] == "화장대"
    assert event.payload["reason"] == "잘못 눌렀어요" and event.created_by_user_id == user_id
    log = db_session.query(SecurityLog).filter_by(action="ITEM_CONSTRUCTION_DONE_UNDONE", target_id=oid).one()
    assert log.target_type == "order" and log.user_id == user_id


def test_undo_last_mark_drops_the_key_and_manager_and_admin_may_undo(client):
    _login(client, role="MANAGER", team=None)
    oid = _make_order(stage="PRODUCTION", marks=_mark(UID_A))
    assert _undo(client, oid, UID_A).status_code == 200
    assert DONE_KEY not in _fresh(oid).structured_data

    _login(client, role="ADMIN", team=None)
    oid = _make_order(marks=_mark(UID_C))
    assert _undo(client, oid, UID_C).status_code == 200


def test_undo_permissions_reason_stage_and_unknown_uid(client):
    oid = _make_order(marks=_mark(UID_A))
    for role, team in (("STAFF", "SALES"), ("STAFF", "CONSTRUCTION"), ("VIEWER", "CS")):
        _login(client, role=role, team=team)
        resp = _undo(client, oid, UID_A)
        assert resp.status_code == 403, (role, team)
        assert resp.get_json()["success"] is False

    _login(client, team="CS")
    resp = _undo(client, oid, UID_A, reason="  ")
    assert resp.status_code == 400 and resp.get_json()["code"] == "REASON_REQUIRED"
    resp = _undo(client, oid, UID_B)
    assert resp.status_code == 404 and resp.get_json()["code"] == "NOT_DONE"
    assert _undo(client, 987654321, UID_A).status_code == 404

    cs_order = _make_order(stage="CS", marks=_mark(UID_A))
    resp = _undo(client, cs_order, UID_A)
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE"
    assert set(_fresh(cs_order).structured_data[DONE_KEY]) == {UID_A}
    assert set(_fresh(oid).structured_data[DONE_KEY]) == {UID_A}
    assert db_session.query(OrderEvent).filter_by(event_type="ITEM_CONSTRUCTION_DONE_UNDONE").count() == 0


# --------------------------------------------------------------------------- #
# 폼 저장 보호 (N5)
# --------------------------------------------------------------------------- #
def test_form_save_keeps_item_construction_done(client):
    """PC 폼 전체 저장(PUT structured)은 서버 전용 칸을 지우지 못한다 — 제품 uid 도 자리로 물려받는다."""
    _login(client, role="ADMIN", team="CS")
    oid = _make_order(marks=_mark(UID_A))
    incoming = _sd()
    incoming.pop(DONE_KEY, None)
    for item in incoming["items"]:
        item.pop("uid")  # 폼이 uid 를 모르고 보내도
    resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": incoming})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    sd = _fresh(oid).structured_data
    assert set(sd[DONE_KEY]) == {UID_A}
    assert [item.get("uid") for item in sd["items"]] == [UID_A, UID_B, UID_C]


# --------------------------------------------------------------------------- #
# 남은 시공 한 줄 · history 접두 · 기록 글
# --------------------------------------------------------------------------- #
def test_remaining_note_skips_done_items_dates(monkeypatch):
    today = datetime.date(2026, 11, 4)
    sd = _sd(marks={**_mark(UID_A), **_mark(UID_B)})
    assert cd.remaining_construction_note(sd, today) == "11/17 시공이 남아 있어요"
    assert cd.remaining_construction_note(_sd(), today) == "11/5 · 11/17 시공이 남아 있어요"

    monkeypatch.setenv("FOMS_ITEM_CONSTRUCTION_DONE_ENABLED", "0")
    assert cd.remaining_construction_note(sd, today) == "11/5 · 11/17 시공이 남아 있어요"


def test_partial_visit_note_prefix_is_the_screen_contract():
    sd = _sd(marks={**_mark(UID_A), **_mark(UID_B)})
    note = partial_visit_note(["화장대", "베란다장"], sd)
    assert PARTIAL_VISIT_NOTE_PREFIX == "부분 시공 끝"
    assert note == "부분 시공 끝 (화장대 · 베란다장) — 남은 시공 11/17"
    assert partial_visit_note([], _sd(dated=False, marks=_mark(UID_A))).startswith(PARTIAL_VISIT_NOTE_PREFIX)


def test_event_and_audit_labels_are_plain_korean_and_not_stage_events():
    for code in ("ITEM_CONSTRUCTION_DONE", "ITEM_CONSTRUCTION_DONE_UNDONE", "CONSTRUCTION_VISIT_DONE"):
        assert code not in ev._STAGE_EVENT_TYPES
        assert ev.translate_event_type_to_korean(code) != code
        assert ACTION_LABELS[code]
    assert ev.generate_change_description(
        "ITEM_CONSTRUCTION_DONE", "", "", "", {"names": ["화장대", "베란다장"]}
    ) == "화장대 · 베란다장 시공 끝을 표시했습니다"
    assert ev.generate_change_description(
        "CONSTRUCTION_VISIT_DONE", "", "", "", {"names": ["화장대"], "remaining_summary": "11/17 부엌가구"}
    ) == "오늘 시공을 끝냈습니다 (화장대) — 남은 시공 11/17 부엌가구"
    assert ev.generate_change_description(
        "ITEM_CONSTRUCTION_DONE_UNDONE", "", "", "", {"name": "화장대", "reason": "잘못 눌렀어요"}
    ) == "화장대 시공 끝 표시를 되돌렸습니다 (사유: 잘못 눌렀어요)"
