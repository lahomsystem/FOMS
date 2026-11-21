"""제품마다 '시공 끝'(2단계) — 처음부터 끝까지 실제 라우트로 걷는 시험.

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md`` 1 · 4.2 · 5 · 7 · 10절.
주문 5687 모양: 화장대 · 베란다장은 첫날, 부엌가구는 칸이 비어 마지막 시공일이 둘째 날. 생산 단계에서 시작.

* 첫 방문: 생산 단계 [시공 시작] → 사진 2장 · 서명(첨부 category=construction) → [오늘 시공 끝].
* 그 사이 CS · 완료로 가는 길은 모두 ``ITEMS_CONSTRUCTION_OPEN`` 으로 막힌다. [제작 완료]는 된다.
* 둘째 방문: 첫날 사진은 다시 못 건다 → 새 사진 · 서명 → [시공 완료] → CS.

날짜는 오늘(KST) 기준(방문 날은 지난 14일 안, 앞날 금지). 준비물 ``visit_history`` 는 api 시험 것을 쓴다.
"""

from __future__ import annotations

import copy
import datetime
import itertools
import uuid
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.construction_dates import short_date_label
from foms.services.orders.construction_visit import PARTIAL_VISIT_NOTE_PREFIX
from foms.services.orders.item_construction_done import DONE_KEY, SOURCE_ADMIN_OVERRIDE, SOURCE_VISIT
from foms.services.orders.items_construction_gate import ITEMS_CONSTRUCTION_OPEN
from foms.services.orders.state_axes import read_main_stage
from models import Order, OrderAttachment, OrderConstructionAttempt, OrderEvent, User
from tests.domains.test_item_construction_done_api import visit_history  # noqa: F401 - 준비물

FLAG = "FOMS_ITEM_CONSTRUCTION_DONE_ENABLED"
UID_A, UID_B, UID_C = (str(uuid.uuid4()) for _ in range(3))
_TODAY = get_today_kst()
DAY1 = (_TODAY - datetime.timedelta(days=1)).isoformat()   # 첫 방문(어제)
DAY2 = _TODAY.isoformat()                                   # 둘째 방문(오늘)
L1, L2 = short_date_label(DAY1), short_date_label(DAY2)
REMAINING = f"{L2} 부엌가구"
BLOCKED = f"{REMAINING} 시공이 남아 있어요"
_PUNCH = {"admin_override": True, "override_reason": "관리자 뚫기"}
_counter = itertools.count(1)


# --------------------------------------------------------------------------- #
# 자료 · 로그인
# --------------------------------------------------------------------------- #
def _login(client, *, role: str = "STAFF", team: str | None = "CONSTRUCTION") -> int:
    """새 직원으로 로그인한다. 기본은 시공팀 직원(시공 권한)."""
    n = next(_counter)
    user = User(username=f"icd-e2e-{n}", password=generate_password_hash("pw"), role=role, team=team,
                name=f"직원{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user.id


def _admin(client) -> int:
    return _login(client, role="ADMIN", team="CS")


def _items_5687() -> list[dict]:
    return [
        {"uid": UID_A, "product_name": "화장대", "construction_date": DAY1},
        {"uid": UID_B, "product_name": "베란다장", "construction_date": DAY1},
        {"uid": UID_C, "product_name": "부엌가구"},   # 칸이 비어 주문 날짜(첫날 · 둘째 날)를 물려받는다
    ]


def _sd(stage: str, items: list[dict]) -> dict:
    return {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": "나눠 시공 고객", "phone": "010-0000-0000"}},
        "site": {"address_full": "서울 테헤란로 1", "address_main": "서울 테헤란로 1"},
        "schedule": {"construction": {"date": f"{DAY1}, {DAY2}"}},
        "items": items,
    }


def _make_order(stage: str = "PRODUCTION", *, items: list[dict] | None = None, regional: bool = False) -> int:
    order = Order(received_date=date.today().isoformat(), customer_name="나눠 시공 고객",
                  phone="010-0000-0000", address="서울 테헤란로 1", product="붙박이장", status=stage,
                  manager_name="Bob", is_erp_order=True, erp_stage_code=stage,
                  structured_data=_sd(stage, items if items is not None else _items_5687()))
    if regional:
        order.is_regional = True
        order.construction_type = "하우드 시공"
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _attempts(order_id: int) -> list[OrderConstructionAttempt]:
    db_session.expire_all()
    return (db_session.query(OrderConstructionAttempt)
            .filter(OrderConstructionAttempt.order_id == order_id)
            .order_by(OrderConstructionAttempt.created_at.asc()).all())


def _events(order_id: int, event_type: str) -> int:
    return db_session.query(OrderEvent).filter_by(order_id=order_id, event_type=event_type).count()


def _attachment(order_id: int, name: str) -> int:
    att = OrderAttachment(order_id=order_id, filename=name, file_type="image", category="construction",
                          file_size=10, storage_key=f"orders/{order_id}/{name}")
    db_session.add(att)
    db_session.commit()
    return att.id


# --------------------------------------------------------------------------- #
# 라우트
# --------------------------------------------------------------------------- #
def _start(client, oid):
    return client.post(f"/api/orders/{oid}/construction/start", json={})


def _evidence(client, oid, kind: str, att_id: int):
    return client.post(f"/api/orders/{oid}/construction/evidence", json={"kind": kind, "attachment_id": att_id})


def _register_evidence(client, oid, tag: str) -> tuple[int, int, int]:
    """시공 첨부 셋(전후 사진 2 · 서명 1)을 올리고 이번 방문 증빙으로 건다."""
    a1, a2, sig = (_attachment(oid, f"{tag}_{name}") for name in ("after1.jpg", "after2.jpg", "signature.png"))
    for kind, att in (("after", a1), ("after", a2), ("signature", sig)):
        resp = _evidence(client, oid, kind, att)
        assert resp.status_code == 200, resp.get_data(as_text=True)
    return a1, a2, sig


def _complete(client, oid, refs=None, day: str | None = None, **extra):
    body = dict(extra)
    if refs is not None:
        body["done_item_uids"] = refs
    if day:
        body["visit_date"] = day
    return client.post(f"/api/orders/{oid}/construction/complete", json=body)


def _visit_items(client, oid, day: str) -> dict:
    resp = client.get(f"/api/orders/{oid}/construction/visit-items?date={day}")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    return body["data"]


def _status_write(client, oid, target: str, **extra):
    return client.post("/api/update_order_status", json={"order_id": oid, "status": target, **extra})


def _stage_override(client, oid, to: str = "CS", **extra):
    body = {"to_stage": to, "reason": "남은 제품은 지난주에 끝냈음", "confirm": True, **extra}
    return client.post(f"/api/orders/{oid}/workflow/stage-override", json=body)


def _production_complete(client, oid):
    resp = client.post(f"/api/orders/{oid}/production/complete", json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["new_status"] == "CONSTRUCTION"


# --------------------------------------------------------------------------- #
# 기대값 · 판정
# --------------------------------------------------------------------------- #
def _cand(uid: str, name: str, last: str, precheck: bool) -> dict:
    return {"ref": uid, "name": name, "last_date": last, "last_label": short_date_label(last), "precheck": precheck}


def _done(uid: str, name: str, day: str) -> dict:
    return {"uid": uid, "name": name, "date": day, "date_label": short_date_label(day)}


def _assert_visit_items_after_day_one(client, oid) -> None:
    data = _visit_items(client, oid, DAY2)
    assert data["enabled"] is True and data["split"] is True and data["date"] == DAY2
    assert data["items"] == [_cand(UID_C, "부엌가구", DAY2, True)]
    assert data["done"] == [_done(UID_A, "화장대", DAY1), _done(UID_B, "베란다장", DAY1)]
    assert data["remaining_summary"] == REMAINING


def _assert_items_open(resp) -> None:
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is False
    assert body["code"] == ITEMS_CONSTRUCTION_OPEN, body
    assert body["message"] == BLOCKED, body


def _assert_untouched(oid: int, stage: str) -> None:
    order = _fresh(oid)
    assert read_main_stage(order) == stage and order.erp_stage_code == stage and order.status == stage
    assert set(order.structured_data[DONE_KEY]) == {UID_A, UID_B}


def _day_one(client, oid) -> tuple[tuple[int, int, int], dict]:
    """첫 방문 — 생산 단계 [시공 시작] → 사진 · 서명 → [오늘 시공 끝](화장대 · 베란다장)."""
    _login(client)
    resp = _start(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    photos = _register_evidence(client, oid, "day1")
    resp = _complete(client, oid, [UID_A, UID_B], DAY1, completion_note="첫날")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return photos, resp.get_json()


# --------------------------------------------------------------------------- #
# 1. 5687 모양 — 두 번 방문해 CS 까지
# --------------------------------------------------------------------------- #
def test_5687_shape_two_visits_from_production_to_cs(client, visit_history):
    oid = _make_order("PRODUCTION")
    _login(client)

    # 창을 열기 전 — 첫날 끝나는 둘은 미리 체크, 부엌가구는 둘째 날이 남아 빈 칸.
    data = _visit_items(client, oid, DAY1)
    assert data["enabled"] is True and data["split"] is True
    assert data["items"] == [_cand(UID_A, "화장대", DAY1, True), _cand(UID_B, "베란다장", DAY1, True),
                             _cand(UID_C, "부엌가구", DAY2, False)]
    assert data["done"] == []
    assert data["remaining_summary"] == f"{L1} 화장대 · {L1} 베란다장 · {L2} 부엌가구"

    # ── 첫 방문(생산 단계) ──
    resp = _start(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert read_main_stage(_fresh(oid)) == "PRODUCTION"
    day1 = _register_evidence(client, oid, "day1")
    resp = _complete(client, oid, [UID_A, UID_B], DAY1, completion_note="첫날")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    assert body["data"]["mode"] == "visit" and body["data"]["remaining_summary"] == REMAINING
    assert body["data"]["remaining"] == [{"name": "부엌가구", "date": DAY2}]

    order = _fresh(oid)
    sd = order.structured_data
    assert read_main_stage(order) == "PRODUCTION" and order.erp_stage_code == "PRODUCTION"
    assert order.status == "PRODUCTION"
    assert sd["construction"]["evidence"] == {"before": [], "after": []}
    attempts = _attempts(oid)
    assert [a.status for a in attempts] == ["VISITED"] and attempts[0].is_current is False
    assert attempts[0].evidence["after"] == [day1[0], day1[1]]
    assert attempts[0].evidence["signature_att_id"] == day1[2]
    assert attempts[0].evidence["visit"] == {"date": DAY1, "item_uids": [UID_A, UID_B]}
    note = sd["workflow"]["history"][-1]["note"]
    assert note.startswith(PARTIAL_VISIT_NOTE_PREFIX)
    assert note.startswith(f"부분 시공 끝 (화장대 · 베란다장) — 남은 시공 {L2}")
    assert set(sd[DONE_KEY]) == {UID_A, UID_B}
    assert all(sd[DONE_KEY][u]["date"] == DAY1 and sd[DONE_KEY][u]["source"] == SOURCE_VISIT
               for u in (UID_A, UID_B))
    assert _events(oid, "CONSTRUCTION_COMPLETED") == 0
    _assert_visit_items_after_day_one(client, oid)

    # ── 문지기: CS · 완료로 가는 길이 모두 막힌다 ──
    _admin(client)
    for target in ("CS", "COMPLETED"):
        for extra in ({}, _PUNCH):
            _assert_items_open(_status_write(client, oid, target, **extra))
    resp = _stage_override(client, oid, "CS")
    _assert_items_open(resp)
    assert resp.get_json()["data"]["remaining_summary"] == REMAINING
    # CS 완료: 생산 단계라 단계 문이 먼저 막는다. 관리자 뚫기로 단계 문을 넘겨도 남은 제품 문이 막는다.
    resp = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE", resp.get_data(as_text=True)
    _assert_items_open(client.post(f"/api/orders/{oid}/cs/complete", json=dict(_PUNCH)))
    _assert_untouched(oid, "PRODUCTION")

    # ── [제작 완료]는 된다(PRODUCTION → CONSTRUCTION) ──
    _production_complete(client, oid)
    order = _fresh(oid)
    assert read_main_stage(order) == "CONSTRUCTION" and order.erp_stage_code == "CONSTRUCTION"
    _assert_items_open(_status_write(client, oid, "CS"))    # 시공 단계에서도 CS 는 여전히 막힌다
    _assert_untouched(oid, "CONSTRUCTION")

    # ── 둘째 방문 ──
    _login(client)
    _assert_visit_items_after_day_one(client, oid)
    resp = _start(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    for kind, att in (("after", day1[0]), ("after", day1[1]), ("signature", day1[2])):
        resp = _evidence(client, oid, kind, att)
        assert resp.status_code == 400, (kind, resp.get_data(as_text=True))
        assert resp.get_json()["code"] == "PREVIOUS_VISIT_PHOTO"
    live = _fresh(oid).structured_data["construction"]["evidence"]
    assert live.get("after") == [] and not live.get("signature_att_id")
    day2 = _register_evidence(client, oid, "day2")
    resp = _complete(client, oid, [UID_C], DAY2)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["new_status"] == "CS"
    assert body["data"]["mode"] == "complete" and body["data"]["done_item_uids"] == [UID_C]

    order = _fresh(oid)
    assert read_main_stage(order) == "CS" and order.erp_stage_code == "CS"
    marks = order.structured_data[DONE_KEY]
    assert set(marks) == {UID_A, UID_B, UID_C}
    assert marks[UID_C]["date"] == DAY2 and all(m["source"] == SOURCE_VISIT for m in marks.values())
    attempts = _attempts(oid)
    assert [a.status for a in attempts] == ["VISITED", "READY"]
    assert attempts[1].evidence["after"] == [day2[0], day2[1]]
    assert attempts[1].evidence["signature_att_id"] == day2[2]
    assert attempts[1].evidence["visit"] == {"date": DAY2, "item_uids": [UID_C]}
    assert _events(oid, "CONSTRUCTION_COMPLETED") == 1

    data = _visit_items(client, oid, DAY2)
    assert data["split"] is True and data["items"] == [] and data["remaining_summary"] == ""
    assert data["done"] == [_done(UID_A, "화장대", DAY1), _done(UID_B, "베란다장", DAY1),
                            _done(UID_C, "부엌가구", DAY2)]


def test_regional_direct_complete_is_blocked_after_day_one(client, visit_history):
    """지방 주문은 생산 단계에서 곧장 완료로 간다 — 그 길(cs/complete 지방 갈래)도 막힌다."""
    oid = _make_order("PRODUCTION", regional=True)
    _day_one(client, oid)
    _admin(client)
    _assert_items_open(client.post(f"/api/orders/{oid}/cs/complete", json={}))
    _assert_untouched(oid, "PRODUCTION")


# --------------------------------------------------------------------------- #
# 2. 둘째 날 새 사진 · 서명이 없으면 막힌다(첫날 사진은 세지 않는다)
# --------------------------------------------------------------------------- #
def test_day_two_complete_without_new_evidence_is_blocked(client, visit_history):
    oid = _make_order("PRODUCTION")
    _day_one(client, oid)
    _admin(client)
    _production_complete(client, oid)
    _login(client)

    resp = _complete(client, oid, [UID_C], DAY2)          # [시공 시작] 없이 바로
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert set(resp.get_json()["data"]["missing"]) == {"after", "signature"}
    assert _start(client, oid).status_code == 200
    resp = _complete(client, oid, [UID_C], DAY2)          # 새 방문을 열어도 칸은 비어 있다
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert set(resp.get_json()["data"]["missing"]) == {"after", "signature"}

    _assert_untouched(oid, "CONSTRUCTION")
    assert [a.status for a in _attempts(oid)] == ["VISITED", "IN_PROGRESS"]
    assert _events(oid, "CONSTRUCTION_COMPLETED") == 0


# --------------------------------------------------------------------------- #
# 3. 생산 단계 방문의 [시공 불가] — 방문만 닫고 단계는 그대로
# --------------------------------------------------------------------------- #
def test_production_visit_fail_keeps_stage_and_next_start_works(client, visit_history):
    oid = _make_order("PRODUCTION")
    _login(client)
    assert _start(client, oid).status_code == 200
    early = _attachment(oid, "fail_after.jpg")
    assert _evidence(client, oid, "after", early).status_code == 200

    resp = client.post(f"/api/orders/{oid}/construction/fail", json={"reason": "site_issue", "detail": "고객 부재"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["new_status"] == "PRODUCTION" and body["data"]["mode"] == "visit"

    order = _fresh(oid)
    sd = order.structured_data
    assert read_main_stage(order) == "PRODUCTION" and order.erp_stage_code == "PRODUCTION"
    assert order.status == "PRODUCTION"
    assert sd["construction"]["evidence"] == {"before": [], "after": []}
    assert DONE_KEY not in sd
    assert sd["workflow"]["history"][-1]["note"].startswith("시공 불가 (단계 그대로)")
    assert [a.status for a in _attempts(oid)] == ["REWORKED"]

    # 다음 방문 — [시공 시작]이 새 방문 줄을 연다. 닫힌 방문 사진은 다시 못 건다.
    resp = _start(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert [a.status for a in _attempts(oid)] == ["REWORKED", "IN_PROGRESS"]
    resp = _evidence(client, oid, "after", early)
    assert resp.status_code == 400 and resp.get_json()["code"] == "PREVIOUS_VISIT_PHOTO"
    _register_evidence(client, oid, "retry")
    resp = _complete(client, oid, [UID_A, UID_B], DAY2)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["mode"] == "visit"
    assert read_main_stage(_fresh(oid)) == "PRODUCTION"
    assert [a.status for a in _attempts(oid)] == ["REWORKED", "VISITED"]


# --------------------------------------------------------------------------- #
# 4. 관리자 강제 변경 — 남은 제품도 시공 끝으로 찍고 CS 로
# --------------------------------------------------------------------------- #
def test_admin_override_closes_remaining_items_after_day_one(client, visit_history):
    oid = _make_order("PRODUCTION")
    _day_one(client, oid)
    admin_id = _admin(client)

    _assert_items_open(_stage_override(client, oid, "CS"))
    resp = _stage_override(client, oid, "CS", close_remaining_items=True)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    order = _fresh(oid)
    assert read_main_stage(order) == "CS" and order.status == "CS"
    marks = order.structured_data[DONE_KEY]
    assert set(marks) == {UID_A, UID_B, UID_C}
    assert marks[UID_A]["source"] == SOURCE_VISIT and marks[UID_B]["source"] == SOURCE_VISIT
    assert marks[UID_A]["date"] == DAY1
    assert marks[UID_C]["source"] == SOURCE_ADMIN_OVERRIDE and marks[UID_C]["by_user_id"] == admin_id
    assert marks[UID_C]["date"] == DAY2
    event = (db_session.query(OrderEvent)
             .filter(OrderEvent.order_id == oid, OrderEvent.event_type == "STAGE_OVERRIDE").one())
    assert event.payload["items_closed"] == [UID_C]

    data = _visit_items(client, oid, DAY2)
    assert data["items"] == [] and data["remaining_summary"] == ""
    assert [d["uid"] for d in data["done"]] == [UID_A, UID_B, UID_C]


# --------------------------------------------------------------------------- #
# 5. 대조군 — 제품 칸 날짜 없는 이틀 연속 주문은 지금과 똑같다
# --------------------------------------------------------------------------- #
def test_non_split_two_day_order_completes_like_today(client):
    items = [{"uid": UID_A, "product_name": "화장대"}, {"uid": UID_B, "product_name": "부엌가구"}]
    oid = _make_order("CONSTRUCTION", items=items)
    _login(client)
    for day in (DAY1, DAY2):
        data = _visit_items(client, oid, day)
        assert data["enabled"] is True and data["split"] is False
        assert data["items"] == [] and data["done"] == [] and data["remaining_summary"] == ""

    # 첫날 [시공 시작] — 방문이 이틀 동안 열려 있다(지금과 같다).
    assert _start(client, oid).status_code == 200
    resp = _start(client, oid)
    assert resp.status_code == 409 and resp.get_json()["code"] == "ALREADY_STARTED"
    _register_evidence(client, oid, "plain")

    # 둘째 날 끝낸 제품을 고르지 않고 [시공 완료] → 지금처럼 CS.
    resp = _complete(client, oid, completion_note="이틀째 끝")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert set(body) == {"success", "message", "new_status"} and body["new_status"] == "CS"

    order = _fresh(oid)
    assert read_main_stage(order) == "CS" and DONE_KEY not in order.structured_data
    assert [a.status for a in _attempts(oid)] == ["READY"]
    assert _events(oid, "CONSTRUCTION_COMPLETED") == 1
    assert _events(oid, "CONSTRUCTION_VISIT_DONE") == 0 and _events(oid, "ITEM_CONSTRUCTION_DONE") == 0
    assert _visit_items(client, oid, DAY2)["split"] is False


# --------------------------------------------------------------------------- #
# 6. 스위치 끔 — 생산 단계 [시공 시작]은 지금처럼 409
# --------------------------------------------------------------------------- #
def test_flag_off_production_start_is_invalid_stage_like_today(client, monkeypatch):
    monkeypatch.setenv(FLAG, "0")
    oid = _make_order("PRODUCTION")
    _login(client)

    data = _visit_items(client, oid, DAY1)
    assert data["enabled"] is False and data["split"] is False and data["items"] == []
    resp = _start(client, oid)
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE"
    assert _attempts(oid) == []

    # 사진을 걸고 끝낸 제품을 보내도 지금처럼 단계 문이 막는다(done_item_uids 무시).
    _register_evidence(client, oid, "off")
    resp = _complete(client, oid, [UID_A, UID_B], DAY1)
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE"
    order = _fresh(oid)
    assert read_main_stage(order) == "PRODUCTION" and DONE_KEY not in order.structured_data


# --------------------------------------------------------------------------- #
# 7. 첫 방문 뒤 폼 저장(PUT structured)이 기록 · 이름표를 지우지 못한다
# --------------------------------------------------------------------------- #
def test_form_save_after_day_one_keeps_marks_and_item_uids(client, visit_history):
    oid = _make_order("PRODUCTION")
    _day_one(client, oid)
    marks_before = copy.deepcopy(_fresh(oid).structured_data[DONE_KEY])

    _admin(client)
    incoming = _sd("PRODUCTION", _items_5687())   # 폼은 서버 전용 칸을 모르고 보낸다
    for item in incoming["items"]:
        item.pop("uid")                            # 이름표도 모르고 보내도
    resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": incoming})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    order = _fresh(oid)
    sd = order.structured_data
    assert sd[DONE_KEY] == marks_before
    assert [item.get("uid") for item in sd["items"]] == [UID_A, UID_B, UID_C]
    assert read_main_stage(order) == "PRODUCTION"

    # 저장 뒤에도 문지기 · 목록 · 다음 방문이 그대로다.
    _assert_items_open(_status_write(client, oid, "CS"))
    _login(client)
    _assert_visit_items_after_day_one(client, oid)
    assert _start(client, oid).status_code == 200
