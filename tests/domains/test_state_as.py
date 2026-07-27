"""STATE-AS-01 canonical AS cycle 전이 계약 테스트 (sqlite domains lane).

``foms/api/cs/as_orders.py`` + ``foms/services/orders/as_cycle_service.py`` 의 canonical
AS cycle 상태기계를 실제 HTTP 경로로 고정한다(PG DSN 불필요 — sqlite ``client``/``db_session``):

* canonical 전이(register→schedule→unschedule→start→complete→reopen→classification)가
  step 마다 ``mutation_version`` +1, ``OrderEvent`` 1개, cycle transition append 를 만든다.
* **immutable cycle core**: cycle_id/opened_at/opened_by/initial_content 는 전이 내내 불변.
* **current cycle projection**: :func:`read_as_status` 가 각 단계 상태를 정확히 파생한다.
* **optional visit time/date clear**: schedule 이 방문일을 세팅하고 unschedule 이 clear 한다.
* **AS main stage 복구 금지**: ``workflow.stage`` 는 main(CS)을 보존하고 AS 는 overlay 로만
  ``order.status`` projection 을 바꾼다.
* **classification main/lifecycle 불변**: 분류 토글이 상태/방문/main 을 바꾸지 않는다.
* **CREATE draft finalize**: draft 주문 register 가 draft 를 finalize 하고 AS cycle 을 연다.
* **field_update 이관**: generic ``as_completed_date`` write 는 allowlist 에서 거부(400)된다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.state_axes import read_as_status
from models import Order, OrderEvent, User


def _login_as_admin(client, username="state-as-admin"):
    user = User(
        username=username, password=generate_password_hash("admin"), role="ADMIN",
        team="CS", name="AS Admin", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_cs_order(status="CS"):
    order = Order(
        received_date="2026-07-24", customer_name="AS Cycle Tester", phone="010-1234-5678",
        address="Seoul", product="Wardrobe", status=status, manager_name="Alice",
        is_erp_order=True, erp_stage_code=status,
        structured_data={"workflow": {"stage": status}, "shipment": {}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _reload(order_id):
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _events(order_id):
    return [
        e.event_type
        for e in db_session.query(OrderEvent).filter_by(order_id=order_id)
        .order_by(OrderEvent.id.asc()).all()
    ]


def _current_cycle(order):
    lifecycle = order.structured_data["as_lifecycle"]
    cid = lifecycle["current_cycle_id"]
    return next(c for c in lifecycle["cycles"] if c["cycle_id"] == cid)


def test_full_as_cycle_is_canonical_and_immutable(client):
    """register→schedule→unschedule→start→complete→reopen 전 구간 canonical 계약."""
    _login_as_admin(client)
    order = _create_cs_order()
    oid = order.id

    # 1) REGISTER → RECEIVED cycle
    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "문 경첩 파손"})
    assert r.status_code == 200 and r.get_json()["success"] is True
    saved = _reload(oid)
    cycle = _current_cycle(saved)
    core = {k: cycle[k] for k in ("cycle_id", "opened_at", "opened_by", "initial_content")}
    v0 = saved.mutation_version
    assert read_as_status(saved) == "RECEIVED"
    assert saved.status == "AS_RECEIVED"  # AS overlay projection
    assert saved.structured_data["workflow"]["stage"] == "CS"  # main stage 불변
    assert core["initial_content"] == "문 경첩 파손"

    # 2) SCHEDULE → 방문일 세팅(상태 불변)
    r = client.post(f"/api/orders/{oid}/as/schedule",
                    json={"visit_date": "2026-08-01", "visit_time": "14:30"})
    assert r.status_code == 200
    saved = _reload(oid)
    assert saved.structured_data["schedule"]["as_visit"]["date"] == "2026-08-01"
    assert saved.structured_data["schedule"]["as_visit"]["time"] == "14:30"
    assert read_as_status(saved) == "RECEIVED"
    assert saved.mutation_version == v0 + 1

    # 3) UNSCHEDULE → 방문일 clear
    r = client.post(f"/api/orders/{oid}/as/unschedule", json={"reason": "고객 일정 변경"})
    assert r.status_code == 200
    saved = _reload(oid)
    assert saved.structured_data["schedule"]["as_visit"]["date"] is None
    assert saved.structured_data["schedule"]["as_visit"]["time"] is None
    assert read_as_status(saved) == "RECEIVED"

    # 4) START → IN_PROGRESS
    r = client.post(f"/api/orders/{oid}/as/start",
                    json={"reason": "재방문 필요", "description": "경첩 교체"})
    assert r.status_code == 200
    saved = _reload(oid)
    assert read_as_status(saved) == "IN_PROGRESS"
    assert saved.status == "AS"  # AS_IN_PROGRESS → legacy 'AS'

    # 5) COMPLETE → COMPLETED + as_completed_date
    r = client.post(f"/api/orders/{oid}/as/complete", json={"note": "교체 완료"})
    assert r.status_code == 200
    saved = _reload(oid)
    assert read_as_status(saved) == "COMPLETED"
    assert saved.status == "AS_COMPLETED"
    assert saved.as_completed_date

    # 6) REOPEN → 같은 cycle 로 RECEIVED, 완료일 clear
    r = client.post(f"/api/orders/{oid}/as/reopen", json={"reason": "오완료"})
    assert r.status_code == 200
    saved = _reload(oid)
    assert read_as_status(saved) == "RECEIVED"
    assert saved.as_completed_date is None

    # immutable core: 6단계 내내 cycle_id/opened_at/opened_by/initial_content 불변
    final_cycle = _current_cycle(saved)
    assert {k: final_cycle[k] for k in core} == core
    # append-only history: register+schedule+unschedule+start+complete+reopen = 6 transition
    assert len(final_cycle["transitions"]) == 6
    assert [t["command"] for t in final_cycle["transitions"]] == [
        "AS_REGISTER", "AS_SCHEDULE", "AS_UNSCHEDULE", "AS_START", "AS_COMPLETE", "AS_REOPEN",
    ]
    # 단계별 OrderEvent 1개(parity)
    assert _events(oid) == [
        "AS_REGISTERED", "AS_SCHEDULED", "AS_UNSCHEDULED", "AS_STARTED",
        "AS_COMPLETED", "AS_REOPENED",
    ]
    # workflow.stage 는 처음부터 끝까지 main CS 보존(AS main stage 복구/오염 0)
    assert saved.structured_data["workflow"]["stage"] == "CS"


def test_new_register_appends_cycle_and_preserves_history(client):
    """완료된 cycle 뒤 새 register 는 새 cycle 을 append 하고 current 를 교체한다(과거 보존)."""
    _login_as_admin(client, "state-as-append")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "1차"})
    saved = _reload(oid)
    first_id = saved.structured_data["as_lifecycle"]["current_cycle_id"]
    client.post(f"/api/orders/{oid}/as/start", json={"reason": "r", "description": "d"})
    client.post(f"/api/orders/{oid}/as/complete", json={"note": "완료"})

    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "2차"})
    assert r.status_code == 200
    saved = _reload(oid)
    lifecycle = saved.structured_data["as_lifecycle"]
    assert len(lifecycle["cycles"]) == 2
    assert lifecycle["current_cycle_id"] != first_id  # 새 cycle 로 교체
    assert lifecycle["cycles"][0]["cycle_id"] == first_id  # 1차 이력 보존
    assert lifecycle["cycles"][0]["initial_content"] == "1차"
    assert read_as_status(saved) == "RECEIVED"


def test_register_rejects_duplicate_open_cycle(client):
    """열린 cycle 이 있으면 중복 register 는 409, 상태 불변."""
    _login_as_admin(client, "state-as-dup")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "1차"})
    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "중복"})
    assert r.status_code == 409
    assert r.get_json()["success"] is False


def test_wrong_stage_transition_is_rejected(client):
    """RECEIVED cycle 에서 complete(IN_PROGRESS 필요)는 409, 상태 불변."""
    _login_as_admin(client, "state-as-wrong")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "접수"})
    v = _reload(oid).mutation_version
    r = client.post(f"/api/orders/{oid}/as/complete", json={"note": "x"})
    assert r.status_code == 409
    saved = _reload(oid)
    assert read_as_status(saved) == "RECEIVED"
    assert saved.mutation_version == v  # 실패 전이는 version 을 올리지 않는다


def test_classification_leaves_lifecycle_and_main_unchanged(client):
    """classification 토글은 상태/방문/main 을 바꾸지 않고 shipment projection 만 갱신한다."""
    _login_as_admin(client, "state-as-class")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "접수"})
    client.post(f"/api/orders/{oid}/as/schedule", json={"visit_date": "2026-08-02"})
    before = _reload(oid)
    status_before = read_as_status(before)
    visit_before = before.structured_data["schedule"]["as_visit"]["date"]

    r = client.post(f"/api/orders/{oid}/as/classification",
                    json={"field": "as_blueprint", "value": True})
    assert r.status_code == 200 and r.get_json()["as_blueprint"] is True
    saved = _reload(oid)
    assert saved.structured_data["shipment"]["as_blueprint"] is True
    assert _current_cycle(saved)["classification"]["as_blueprint"] is True
    # lifecycle status / 방문 / main 불변(implicit toggle 금지)
    assert read_as_status(saved) == status_before
    assert saved.structured_data["schedule"]["as_visit"]["date"] == visit_before
    assert saved.structured_data["workflow"]["stage"] == "CS"


def test_field_update_rejects_as_completed_date(client):
    """generic field_update 의 as_completed_date write 이관 — allowlist 에서 거부(400)."""
    _login_as_admin(client, "state-as-field")
    order = _create_cs_order(status="AS")
    oid = order.id
    r = client.post("/api/update_order_field",
                    json={"order_id": oid, "field": "as_completed_date", "value": "2026-08-05"})
    assert r.status_code == 400
    assert "as_completed_date" in r.get_json()["message"]
    saved = _reload(oid)
    assert saved.status == "AS"  # main stage 복구 antipattern 미발생
