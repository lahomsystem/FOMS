"""제품마다 '시공 끝' — [시공 시작] · [시공 완료] 나눠 시공 갈래 API 계약.

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md`` 4.2 · 5.2 · 5.3 (N2 · N3 · N6).

* 생산 단계 [시공 시작]은 스위치 켜짐 + 나눠 시공 + 남은 제품 있음일 때만(단계 그대로).
* 부분 방문은 방문 줄을 ``VISITED`` 로 봉인하고 사진 · 서명 칸을 비운다. 단계 · 상태 · 단계 기록 없음.
* 마지막 날 문은 그날 사진 · 서명만 센다. 남은 0개면 같은 거래에서 CONSTRUCTION→CS, 찍은 표시가
  전이 엔진의 잠금 아래 재조회에도 보인다.
* 나눠 시공이 아니거나 스위치가 꺼져 있으면 ``done_item_uids`` 를 무시하고 지금과 같다.
"""

from __future__ import annotations

import copy
import itertools
import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.services.orders.order_transition_service as transition_module
from db import db_session, engine
from foms.services.orders.construction_visit import PARTIAL_VISIT_NOTE_PREFIX
from foms.services.orders.item_construction_done import DONE_KEY, is_partial_open
from foms.services.orders.state_axes import read_main_stage
from models import Order, OrderConstructionAttempt, OrderEvent, SecurityLog, User

UID_A, UID_B, UID_C = (str(uuid.uuid4()) for _ in range(3))
FIRST_DAY, LAST_DAY = "2026-11-05", "2026-11-17"
_counter = itertools.count(1)
_CURRENT_INDEX = "uq_construction_attempt_current"


@pytest.fixture
def visit_history(app):
    """한 주문에 방문 줄 여러 개(닫힌 줄 + 열린 줄 하나)를 둘 수 있게 한다.

    SQLite 는 ``postgresql_where`` 를 버려 '열린 줄은 하나' 색인이 주문당 줄 하나가 된다(기존 시험이
    새 방문 append 를 PG 레인으로 미룬 까닭). 이 시험 동안만 운영(PG)과 같은 부분 색인으로 바꾸고 되돌린다.
    """
    sqlite = engine.dialect.name == "sqlite"
    if sqlite:
        with engine.begin() as conn:
            conn.execute(text(f"DROP INDEX IF EXISTS {_CURRENT_INDEX}"))
            conn.execute(text(f"CREATE UNIQUE INDEX {_CURRENT_INDEX} "
                              "ON order_construction_attempts (order_id) WHERE is_current"))
    yield
    if sqlite:
        db_session.remove()
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM order_construction_attempts"))
            conn.execute(text(f"DROP INDEX IF EXISTS {_CURRENT_INDEX}"))
            conn.execute(text(f"CREATE UNIQUE INDEX {_CURRENT_INDEX} ON order_construction_attempts (order_id)"))


def _login(client, *, role: str = "STAFF", team: str | None = "CONSTRUCTION") -> int:
    n = next(_counter)
    user = User(username=f"icd-{n}", password=generate_password_hash("pw"), role=role, team=team,
                name=f"시공{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user.id


def _split_items() -> list[dict]:
    return [
        {"uid": UID_A, "product_name": "화장대", "construction_date": FIRST_DAY},
        {"uid": UID_B, "product_name": "베란다장", "construction_date": FIRST_DAY},
        {"uid": UID_C, "product_name": "부엌가구", "construction_date": LAST_DAY},
    ]


def _make_order(stage: str, *, items: list[dict] | None = None, extra: dict | None = None) -> int:
    sd = {
        "workflow": {"stage": stage},
        "schedule": {"construction": {"date": f"{FIRST_DAY}, {LAST_DAY}"}},
        "items": items if items is not None else _split_items(),
    }
    sd.update(extra or {})
    order = Order(received_date=date.today().isoformat(), customer_name="나눠 시공 고객",
                  phone="010-0000-0000", address="Seoul", product="붙박이장", status=stage,
                  manager_name="Bob", is_erp_order=True, structured_data=sd, erp_stage_code=stage)
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _seed_evidence(order_id: int, after=(9001, 9002), signature=9003) -> None:
    """사진 · 서명 문을 채운다(라우트는 live ``construction.evidence`` 만 본다)."""
    order = _fresh(order_id)
    sd = copy.deepcopy(order.structured_data or {})
    sd.setdefault("construction", {})["evidence"] = {
        "before": [], "after": list(after), "signature_att_id": signature,
    }
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _set_stage(order_id: int, stage: str) -> None:
    """[제작 완료]를 흉내 낸다 — 단계 칸만 옮긴다."""
    order = _fresh(order_id)
    sd = copy.deepcopy(order.structured_data or {})
    sd.setdefault("workflow", {})["stage"] = stage
    order.structured_data = sd
    order.erp_stage_code = stage
    order.status = stage
    flag_modified(order, "structured_data")
    db_session.commit()


def _attempts(order_id: int) -> list[OrderConstructionAttempt]:
    db_session.expire_all()
    return (db_session.query(OrderConstructionAttempt)
            .filter(OrderConstructionAttempt.order_id == order_id)
            .order_by(OrderConstructionAttempt.created_at.asc()).all())


def _events(order_id: int, event_type: str) -> int:
    return db_session.query(OrderEvent).filter_by(order_id=order_id, event_type=event_type).count()


def _start(client, oid):
    return client.post(f"/api/orders/{oid}/construction/start", json={})


def _complete(client, oid, refs, **extra):
    return client.post(f"/api/orders/{oid}/construction/complete",
                       json={"done_item_uids": refs, "visit_date": FIRST_DAY, **extra})


# --------------------------------------------------------------------------- #
# [시공 시작] — 생산 단계(N3)
# --------------------------------------------------------------------------- #
def test_start_in_production_opens_visit_for_split_order(client):
    _login(client)
    oid = _make_order("PRODUCTION")

    resp = _start(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    order = _fresh(oid)
    assert read_main_stage(order) == "PRODUCTION" and order.erp_stage_code == "PRODUCTION"
    attempts = _attempts(oid)
    assert len(attempts) == 1 and attempts[0].status == "IN_PROGRESS" and attempts[0].is_current
    last = order.structured_data["workflow"]["history"][-1]
    assert last["note"] == "시공 시작" and last["stage"] == "PRODUCTION"


def test_start_in_production_is_409_when_flag_off(client, monkeypatch):
    monkeypatch.setenv("FOMS_ITEM_CONSTRUCTION_DONE_ENABLED", "0")
    _login(client)
    oid = _make_order("PRODUCTION")

    resp = _start(client, oid)
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "INVALID_STAGE"
    assert _attempts(oid) == []


def test_start_in_production_is_409_for_non_split_order(client):
    """제품 칸 날짜가 없으면 모두 주문 날짜를 물려받아 나눠 시공이 아니다(이틀 연속 주문, 대조군)."""
    _login(client)
    oid = _make_order("PRODUCTION", items=[{"uid": UID_A, "product_name": "화장대"},
                                           {"uid": UID_B, "product_name": "부엌가구"}])
    resp = _start(client, oid)
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE"


def test_start_in_production_is_409_when_no_item_remains(client):
    _login(client)
    marks = {uid: {"date": FIRST_DAY, "source": "visit"} for uid in (UID_A, UID_B, UID_C)}
    oid = _make_order("PRODUCTION", extra={DONE_KEY: marks})
    resp = _start(client, oid)
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE"


def test_start_keeps_already_started_rule_in_production(client):
    _login(client)
    oid = _make_order("PRODUCTION")
    assert _start(client, oid).status_code == 200
    resp = _start(client, oid)
    assert resp.status_code == 409 and resp.get_json()["code"] == "ALREADY_STARTED"


# --------------------------------------------------------------------------- #
# [시공 완료] — 부분 방문(4.2)
# --------------------------------------------------------------------------- #
def test_partial_visit_seals_attempt_clears_evidence_and_keeps_stage(client, visit_history):
    _login(client)
    oid = _make_order("PRODUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    before_status = _fresh(oid).status

    resp = _complete(client, oid, [UID_A, UID_B], completion_note="첫날")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    assert body["data"]["mode"] == "visit"
    assert body["data"]["remaining_summary"] == "11/17 부엌가구"
    assert body["data"]["remaining"] == [{"name": "부엌가구", "date": LAST_DAY}]

    order = _fresh(oid)
    sd = order.structured_data
    assert read_main_stage(order) == "PRODUCTION" and order.status == before_status
    assert sd["construction"]["evidence"] == {"before": [], "after": []}
    attempt = _attempts(oid)[0]
    assert attempt.status == "VISITED" and attempt.is_current is False
    assert attempt.evidence["after"] == [9001, 9002] and attempt.evidence["signature_att_id"] == 9003
    assert attempt.evidence["visit"] == {"date": FIRST_DAY, "item_uids": [UID_A, UID_B]}
    assert attempt.completed_at is not None and attempt.completed_by and attempt.completion_note == "첫날"
    assert set(sd[DONE_KEY]) == {UID_A, UID_B}
    assert sd[DONE_KEY][UID_A]["date"] == FIRST_DAY and sd[DONE_KEY][UID_A]["attempt_id"] == attempt.id
    note = sd["workflow"]["history"][-1]["note"]
    assert note.startswith(PARTIAL_VISIT_NOTE_PREFIX)
    assert note.startswith("부분 시공 끝 (화장대 · 베란다장) — 남은 시공 11/17")
    # 단계 기록 · 알림이 없다 — 시공 완료 이벤트 0, 방문 · 제품 이벤트 1씩.
    assert _events(oid, "CONSTRUCTION_COMPLETED") == 0
    assert _events(oid, "CONSTRUCTION_VISIT_DONE") == 1 and _events(oid, "ITEM_CONSTRUCTION_DONE") == 1
    assert db_session.query(SecurityLog).filter_by(action="CONSTRUCTION_VISIT_DONE", target_id=oid).count() == 1

    # 다음 방문은 [시공 시작]부터 — 새 방문 줄이 열린다.
    resp = _start(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    statuses = [a.status for a in _attempts(oid)]
    assert statuses == ["VISITED", "IN_PROGRESS"]


def test_partial_visit_needs_evidence_too(client):
    _login(client)
    oid = _make_order("CONSTRUCTION")
    assert _start(client, oid).status_code == 200

    resp = _complete(client, oid, [UID_A])
    assert resp.status_code == 400
    assert set(resp.get_json()["data"]["missing"]) == {"after", "signature"}
    assert DONE_KEY not in _fresh(oid).structured_data
    assert _attempts(oid)[0].status == "IN_PROGRESS"


def test_partial_visit_same_idempotency_key_replays(client):
    _login(client)
    oid = _make_order("CONSTRUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    key = {"Idempotency-Key": "3b1f7a52-2b1e-4b1f-9d1c-1a2b3c4d5e6f"}
    payload = {"done_item_uids": [UID_A], "visit_date": FIRST_DAY}

    first = client.post(f"/api/orders/{oid}/construction/complete", json=payload, headers=key)
    assert first.status_code == 200
    version = _fresh(oid).mutation_version
    again = client.post(f"/api/orders/{oid}/construction/complete", json=payload, headers=key)
    assert again.status_code == 200 and again.get_json()["data"]["mode"] == "visit"
    assert _fresh(oid).mutation_version == version
    assert _events(oid, "CONSTRUCTION_VISIT_DONE") == 1
    assert [a.status for a in _attempts(oid)] == ["VISITED"]


def test_partial_visit_without_open_attempt_leaves_closed_visit_row(client):
    """[시공 시작] 없이 끝낸 옛 흐름도 방문 사진 · 서명이 남도록 닫힌 줄 하나를 만든다."""
    _login(client)
    oid = _make_order("CONSTRUCTION")
    _seed_evidence(oid)
    assert _complete(client, oid, [UID_A]).status_code == 200
    attempts = _attempts(oid)
    assert len(attempts) == 1 and attempts[0].status == "VISITED" and attempts[0].is_current is False
    assert attempts[0].evidence["visit"]["item_uids"] == [UID_A]


# --------------------------------------------------------------------------- #
# [시공 완료] — 마지막 날 · 오류 코드
# --------------------------------------------------------------------------- #
def test_final_day_gate_counts_only_that_days_evidence_and_reaches_cs(client, monkeypatch, visit_history):
    _login(client)
    oid = _make_order("PRODUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    assert _complete(client, oid, [UID_A, UID_B]).status_code == 200
    _set_stage(oid, "CONSTRUCTION")  # [제작 완료]
    assert _start(client, oid).status_code == 200

    # 첫날 사진 · 서명은 봉인됐다 — 마지막 날 문을 통과시키지 못한다.
    resp = client.post(f"/api/orders/{oid}/construction/complete", json={"done_item_uids": [UID_C]})
    assert resp.status_code == 400
    assert set(resp.get_json()["data"]["missing"]) == {"after", "signature"}

    # 전이 엔진이 잠금 아래에서 다시 읽은 주문에 찍은 표시가 보이는지(문지기 자리) 엿본다.
    seen: list = []
    real = transition_module.read_state_axes

    def _spy(order):
        sd = order.structured_data or {}
        seen.append((copy.deepcopy(sd.get(DONE_KEY) or {}), is_partial_open(sd)))
        return real(order)

    monkeypatch.setattr(transition_module, "read_state_axes", _spy)
    _seed_evidence(oid, after=(9101, 9102), signature=9103)
    resp = client.post(f"/api/orders/{oid}/construction/complete", json={"done_item_uids": [UID_C]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["new_status"] == "CS" and body["data"]["mode"] == "complete"
    assert seen and set(seen[0][0]) == {UID_A, UID_B, UID_C} and seen[0][1] is False

    order = _fresh(oid)
    assert read_main_stage(order) == "CS"
    assert set(order.structured_data[DONE_KEY]) == {UID_A, UID_B, UID_C}
    attempts = _attempts(oid)
    assert [a.status for a in attempts] == ["VISITED", "READY"]
    assert attempts[1].evidence["after"] == [9101, 9102]
    assert attempts[1].evidence["visit"]["item_uids"] == [UID_C]
    assert _events(oid, "CONSTRUCTION_COMPLETED") == 1 and _events(oid, "ITEM_CONSTRUCTION_DONE") == 2


def test_done_items_required_when_nothing_valid_is_chosen(client):
    _login(client)
    oid = _make_order("CONSTRUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    for refs in ([], ["no-such-ref"], None):
        resp = client.post(f"/api/orders/{oid}/construction/complete", json={"done_item_uids": refs})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "DONE_ITEMS_REQUIRED" and body["error"] == "오늘 끝낸 제품을 골라 주세요"
    assert DONE_KEY not in _fresh(oid).structured_data
    assert _attempts(oid)[0].status == "IN_PROGRESS"


def test_production_stage_cannot_finish_the_last_item(client):
    _login(client)
    oid = _make_order("PRODUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    resp = _complete(client, oid, [UID_A, UID_B, UID_C])
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "PRODUCTION_NOT_DONE" and body["error"] == "제작 완료를 먼저 눌러 주세요"
    order = _fresh(oid)
    assert DONE_KEY not in order.structured_data and read_main_stage(order) == "PRODUCTION"


def test_non_split_order_ignores_done_item_uids(client):
    """제품 칸 날짜가 없는 주문(대조군)은 지금과 똑같다 — 응답 모양도 그대로, 표시 없음."""
    _login(client)
    oid = _make_order("CONSTRUCTION", items=[{"uid": UID_A, "product_name": "화장대"},
                                             {"uid": UID_B, "product_name": "부엌가구"}])
    _seed_evidence(oid)
    resp = _complete(client, oid, [UID_A])
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == {"success", "message", "new_status"} and body["new_status"] == "CS"
    assert DONE_KEY not in _fresh(oid).structured_data


def test_flag_off_split_order_completes_like_today(client, monkeypatch):
    monkeypatch.setenv("FOMS_ITEM_CONSTRUCTION_DONE_ENABLED", "0")
    _login(client)
    oid = _make_order("CONSTRUCTION")
    _seed_evidence(oid)
    resp = _complete(client, oid, [UID_A])
    assert resp.status_code == 200
    assert set(resp.get_json()) == {"success", "message", "new_status"}
    order = _fresh(oid)
    assert read_main_stage(order) == "CS" and DONE_KEY not in order.structured_data
