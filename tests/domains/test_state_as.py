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
* **field_update 이관**: generic ``as_completed_date`` write 는 canonical AS_COMPLETE 브리지로
  위임된다(직접 status/stage 쓰기 0). cycle 이 없는 레거시 AS 주문은 forward-only
  ``LEGACY_BRIDGE`` 로 개시된 뒤 전이한다 — 과거 이력은 복원하지 않는다(감사보고서 §296).
"""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.as_cycle_service import ASCycleError, register_as_cycle
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


def test_register_route_treats_duplicate_as_reregistration(client):
    """열린 cycle 이 있는 재접수는 새 cycle 없이 접수 기록만 갱신한다(지방 AS 재상차 실플로우).

    한 AS 건을 다시 접수하는 것은 정상 업무 흐름이라 새 cycle 을 열면 한 건이 두 건으로
    갈라진다. 서비스의 "중복 open cycle 거부" 불변식은 그대로이고 라우트가 중재한다
    (:func:`test_register_service_still_rejects_duplicate_open_cycle` 이 불변식을 고정).
    """
    _login_as_admin(client, "state-as-dup")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "1차"})
    first_id = _reload(oid).structured_data["as_lifecycle"]["current_cycle_id"]

    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "2차 접수 내용"})
    assert r.status_code == 200 and r.get_json()["success"] is True
    saved = _reload(oid)
    lifecycle = saved.structured_data["as_lifecycle"]
    assert len(lifecycle["cycles"]) == 1  # 새 cycle 미발급
    assert lifecycle["current_cycle_id"] == first_id
    assert read_as_status(saved) == "RECEIVED"
    shipment = saved.structured_data["shipment"]
    assert shipment["as_content"] == "2차 접수 내용"  # 접수 원문 갱신
    receptions = [e["text"] for e in shipment["as_log"] if e["type"] == "reception"]
    assert receptions == ["1차", "2차 접수 내용"]  # 재접수도 타임라인에 남는다


def test_register_service_still_rejects_duplicate_open_cycle(client):
    """서비스 계층 불변식은 불변 — 열린 cycle 위에 새 cycle 발급은 ASCycleError."""
    _login_as_admin(client, "state-as-dup-service")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "1차"})
    db_session.expire_all()

    with pytest.raises(ASCycleError):
        register_as_cycle(
            db_session, order_id=oid, actor_user_id=_reload(oid).structured_data[
                "as_lifecycle"]["cycles"][0]["opened_by"],
            as_content="중복", scope_hash="scope", request_hash="req",
        )
    db_session.rollback()


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


def test_field_update_as_completed_date_uses_canonical_bridge(client):
    """generic field_update 의 as_completed_date 는 canonical AS_COMPLETE 로 위임된다.

    프론트(AS 대시보드·태블릿 비교화면)가 완료 버튼을 이 필드로 보내므로 400 으로 막으면
    완료 자체가 불가능해진다. 직접 ``order.status``/``workflow.stage`` 쓰기 없이 cycle 전이로
    처리하고, cycle 이 없는 레거시 AS 주문은 forward-only LEGACY_BRIDGE 로 개시한 뒤 전이한다
    (현재 축 값만 옮기고 과거 방문·일정·완료 이력은 복원하지 않는다).
    """
    _login_as_admin(client, "state-as-field")
    order = _create_cs_order(status="AS")
    oid = order.id
    r = client.post("/api/update_order_field",
                    json={"order_id": oid, "field": "as_completed_date", "value": "2026-08-05"})
    assert r.status_code == 200 and r.get_json()["success"] is True
    saved = _reload(oid)
    assert saved.as_completed_date == "2026-08-05"
    assert read_as_status(saved) == "COMPLETED"
    assert saved.status == "AS_COMPLETED"  # AS overlay projection
    assert saved.structured_data["workflow"]["stage"] == "AS"  # main stage 직접 쓰기 0
    cycle = _current_cycle(saved)
    assert cycle["origin"] == "LEGACY_BRIDGE"  # provenance 태그
    assert [t["command"] for t in cycle["transitions"]] == ["AS_LEGACY_BRIDGE", "AS_COMPLETE"]


def test_register_after_complete_clears_date_and_projects_received(client):
    """완료된 AS 를 ERP에서 다시 접수로 바꾸면 완료일이 남아 대시보드 삭제가 409 가 되면 안 된다.

    운영 재현(주문 3731): 본공정 드롭다운 AS접수 → register 가 새 RECEIVED cycle 을 연 뒤에도
    ``as_completed_date`` 가 남고, 대시보드 완료일 삭제는 reopen(COMPLETED 전용)이라
    「현재 AS 상태(RECEIVED)에서 수행할 수 없는 작업」으로 거절됐다.
    """
    _login_as_admin(client, "state-as-reregister-date")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "1차"})
    client.post(f"/api/orders/{oid}/as/start", json={"reason": "r", "description": "d"})
    client.post(f"/api/orders/{oid}/as/complete", json={"note": "완료"})
    assert _reload(oid).as_completed_date

    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "2차 재접수"})
    assert r.status_code == 200 and r.get_json()["success"] is True
    saved = _reload(oid)
    assert read_as_status(saved) == "RECEIVED"
    assert saved.status == "AS_RECEIVED"
    assert saved.as_completed_date is None
    assert r.get_json()["new_status"] == "AS_RECEIVED"
    assert isinstance(r.get_json().get("mutation_version"), int)


def test_field_update_can_clear_stale_completed_date_on_received_cycle(client):
    """이미 RECEIVED 인데 완료일만 남은 드리프트는 대시보드 삭제로 정리된다."""
    _login_as_admin(client, "state-as-stale-date")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "접수"})
    saved = _reload(oid)
    saved.as_completed_date = "2026-08-01"
    db_session.commit()

    r = client.post("/api/update_order_field", json={
        "order_id": oid, "field_name": "as_completed_date", "new_value": "",
    })
    assert r.status_code == 200 and r.get_json()["success"] is True
    saved = _reload(oid)
    assert saved.as_completed_date in (None, "")
    assert read_as_status(saved) == "RECEIVED"
    assert saved.status == "AS_RECEIVED"


def test_register_syncs_polluted_as_stage_but_keeps_clean_main_stage(client):
    """레거시로 workflow.stage 가 AS_* 이면 overlay 와 맞추고, 본공정 CS 는 건드리지 않는다."""
    _login_as_admin(client, "state-as-stage-sync")
    polluted = _create_cs_order(status="AS_COMPLETED")
    polluted.structured_data = {
        "workflow": {"stage": "AS_COMPLETED"}, "shipment": {},
    }
    polluted.as_completed_date = "2026-08-01"
    db_session.commit()
    pid = polluted.id
    r = client.post(f"/api/orders/{pid}/as/register", json={"as_content": "재접수"})
    assert r.status_code == 200
    saved = _reload(pid)
    assert saved.status == "AS_RECEIVED"
    assert saved.structured_data["workflow"]["stage"] == "AS_RECEIVED"
    assert saved.as_completed_date is None

    clean = _create_cs_order(status="CS")
    cid = clean.id
    client.post(f"/api/orders/{cid}/as/register", json={"as_content": "신규"})
    saved = _reload(cid)
    assert saved.structured_data["workflow"]["stage"] == "CS"
    assert saved.status == "AS_RECEIVED"
