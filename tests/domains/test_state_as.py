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

import copy

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.as_cycle_service import (
    ASCycleError,
    _visit_projection,
    register_as_cycle,
)
from foms.services.orders.as_schedule_link import SOURCE_SHIPMENT, read_link, write_link
from foms.services.orders.state_axes import read_as_status
from models import Order, OrderEvent, OrderScheduleDate, User


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


# ---------------------------------------------------------------------------
# AS 재접수 S1 저장 계층: 건(cycle) 스냅샷 봉인 · as_log 건 스탬프 · 재발 표식
# ---------------------------------------------------------------------------
_H64 = "a" * 64


def _cycle_by_id(order, cycle_id):
    """as_lifecycle.cycles 에서 지정 cycle_id dict 를 꺼낸다(지난 건 조회용)."""
    return next(
        c for c in order.structured_data["as_lifecycle"]["cycles"]
        if c["cycle_id"] == cycle_id
    )


def test_reregister_seals_previous_cycle_completed_date_and_billing(client):
    """완료 → 재접수 시 직전 건에 완료일·비용 스냅샷이 봉인된다(컬럼 1칸·1슬롯은 새 건이 덮는다).

    ``as_completed_date`` 는 컬럼 한 칸, ``shipment.as_billing`` 은 주문당 한 슬롯이라
    새 건이 열리면 지난 건의 완료일·유무상 판정이 복원 불가능하게 사라졌다. 봉인은 깊은
    복사라 이후 판정 전환이 지난 건 값을 바꾸지 않아야 한다.
    """
    _login_as_admin(client, "state-as-seal")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register",
                json={"as_content": "1차", "billing_type": "paid", "amount": 50000})
    client.post(f"/api/orders/{oid}/as/start", json={"reason": "r", "description": "d"})
    client.post(f"/api/orders/{oid}/as/complete", json={"note": "완료"})
    saved = _reload(oid)
    first_id = saved.structured_data["as_lifecycle"]["current_cycle_id"]
    completed = saved.as_completed_date
    received = saved.as_received_date
    assert completed and _current_cycle(saved)["completed_date"] == completed

    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "2차 재접수"})
    assert r.status_code == 200 and r.get_json()["success"] is True
    saved = _reload(oid)
    first = _cycle_by_id(saved, first_id)
    assert first["completed_date"] == completed        # 지난 건 완료일 보존
    assert first["received_date"] == received          # 지난 건 접수일 보존
    assert first["billing_snapshot"]["type"] == "paid"
    assert first["billing_snapshot"]["amount"] == 50000
    assert saved.as_completed_date is None             # 컬럼은 새 건 기준으로 초기화

    # 깊은 복사 검증: 새 건에서 판정을 무상으로 전환해도 지난 건 스냅샷은 불변
    r = client.post(f"/api/orders/{oid}/as/billing",
                    json={"type": "free", "reason": "2차는 무상 처리"})
    assert r.status_code == 200
    saved = _reload(oid)
    assert saved.structured_data["shipment"]["as_billing"]["type"] == "free"
    first = _cycle_by_id(saved, first_id)
    assert first["billing_snapshot"]["type"] == "paid"
    assert first["billing_snapshot"]["amount"] == 50000


def test_new_cycle_stamps_new_as_log_entries_and_leaves_old_ones(client):
    """새 건으로 append 된 as_log 항목은 새 cycle_id 로 묶이고, 옛 항목은 소급 스탬프 0."""
    _login_as_admin(client, "state-as-logstamp")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "1차 하자"})
    saved = _reload(oid)
    first_id = saved.structured_data["as_lifecycle"]["current_cycle_id"]
    client.post(f"/api/orders/{oid}/as/start", json={"reason": "r", "description": "d"})
    client.post(f"/api/orders/{oid}/as/complete", json={"note": "완료"})

    saved = _reload(oid)
    before = {e["id"]: e.get("cycle_id") for e in saved.structured_data["shipment"]["as_log"]}
    assert before and set(before.values()) == {first_id}  # 1차 건 기록은 전부 1차 cycle

    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "2차 하자"})
    assert r.status_code == 200 and r.get_json()["success"] is True
    saved = _reload(oid)
    second_id = saved.structured_data["as_lifecycle"]["current_cycle_id"]
    assert second_id != first_id
    entries = saved.structured_data["shipment"]["as_log"]
    fresh = [e for e in entries if e["id"] not in before]
    assert fresh  # 2차 접수 원문 + "AS 접수됨" 시스템 기록
    assert {e.get("cycle_id") for e in fresh} == {second_id}
    # 옛 항목은 그대로(append-only — 표식 이전 기록은 건드리지 않는다)
    assert {e["id"]: e.get("cycle_id") for e in entries if e["id"] in before} == before


def test_reopen_drops_completed_date_snapshot(client):
    """reopen 하면 그 건은 다시 진행 중이므로 cycle 의 completed_date 스냅샷이 사라진다."""
    _login_as_admin(client, "state-as-reopen-snap")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "접수"})
    client.post(f"/api/orders/{oid}/as/start", json={"reason": "r", "description": "d"})
    client.post(f"/api/orders/{oid}/as/complete", json={"note": "완료"})
    saved = _reload(oid)
    assert _current_cycle(saved)["completed_date"] == saved.as_completed_date

    r = client.post(f"/api/orders/{oid}/as/reopen", json={"reason": "오완료"})
    assert r.status_code == 200 and r.get_json()["success"] is True
    saved = _reload(oid)
    assert "completed_date" not in _current_cycle(saved)
    assert saved.as_completed_date is None


def test_register_persists_recurrence_flag_on_cycle(client):
    """recurrence=True 접수는 재발 표식을 cycle core + AS_REGISTER payload 에 남긴다.

    라우트 배선은 후속 task 소관이라 서비스 계층 계약만 고정한다(기본값은 False).
    """
    user = _login_as_admin(client, "state-as-recurrence")
    order = _create_cs_order()
    oid = order.id
    register_as_cycle(
        db_session, order_id=oid, actor_user_id=user.id, as_content="같은 하자 재발",
        received_date="2026-08-24", recurrence=True, scope_hash=_H64, request_hash=_H64,
    )
    db_session.commit()
    saved = _reload(oid)
    cycle = _current_cycle(saved)
    assert cycle["recurrence"] is True
    assert cycle["received_date"] == "2026-08-24"
    assert saved.as_received_date == "2026-08-24"
    register_tr = cycle["transitions"][0]
    assert register_tr["command"] == "AS_REGISTER"
    assert register_tr["payload"]["recurrence"] is True

    # 기본값 False — 기존 접수 경로(라우트)는 무변경
    plain = _create_cs_order()
    client.post(f"/api/orders/{plain.id}/as/register", json={"as_content": "일반 접수"})
    assert _current_cycle(_reload(plain.id))["recurrence"] is False


# ---------------------------------------------------------------------------
# AS 재접수 T2: 새 건은 직전 건의 방문일을 물려받지 않는다
# ---------------------------------------------------------------------------
def _as_visit_rows(order_id):
    """``order_schedule_dates`` 의 as_visit 파생 행 날짜 목록(before_flush 동기화 결과)."""
    db_session.expire_all()
    return [
        row.date
        for row in db_session.query(OrderScheduleDate)
        .filter_by(order_id=order_id, kind="as_visit")
        .order_by(OrderScheduleDate.date.asc())
        .all()
    ]


def test_new_cycle_clears_previous_visit_date(client):
    """새 cycle 발급은 직전 건의 방문일/시각·일정 링크를 비운다(가능시간은 유지).

    ``schedule.as_visit`` 는 주문당 1슬롯이라, 새 AS 건이 열려도 직전 건 방문일이 그대로
    남아 대시보드가 새 건을 "이미 방문 잡힌 건"으로 보여줬다(운영 #4434). 지난 건의 방문
    이력은 그 cycle 의 transitions 에 남으므로 슬롯을 비워도 복원 가능하다.
    """
    user = _login_as_admin(client, "state-as-visit-reset")
    user_id, user_name = user.id, user.name  # HTTP 요청 뒤에는 세션에서 떨어진다
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "1차"})
    client.post(f"/api/orders/{oid}/as/schedule",
                json={"visit_date": "2026-08-01", "visit_time": "14:30"})
    saved = _reload(oid)
    first_id = saved.structured_data["as_lifecycle"]["current_cycle_id"]

    # 가능시간(주문 속성)과 일정 매칭 링크를 함께 심는다 — 전자는 유지, 후자는 해제 대상.
    sd = copy.deepcopy(saved.structured_data)
    sd["schedule"]["as_visit"]["availability"] = "오후 2시 이후"
    write_link(sd, ref_order_id=oid, ref_date="2026-08-01", source=SOURCE_SHIPMENT,
               user_id=user_id, user_name=user_name, now=now_utc_naive())
    saved.structured_data = sd
    flag_modified(saved, "structured_data")
    db_session.commit()
    assert _as_visit_rows(oid) == ["2026-08-01"]  # 파생 행이 실제로 생겼다

    client.post(f"/api/orders/{oid}/as/start", json={"reason": "r", "description": "d"})
    client.post(f"/api/orders/{oid}/as/complete", json={"note": "완료"})
    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "2차"})
    assert r.status_code == 200 and r.get_json()["success"] is True

    saved = _reload(oid)
    as_visit = saved.structured_data["schedule"]["as_visit"]
    assert not as_visit["date"] and not as_visit["time"]  # 새 건은 방문일 미정
    assert as_visit["availability"] == "오후 2시 이후"  # 가능시간(주문 속성)은 불변
    assert read_link(saved.structured_data) is None  # 지워진 방문일을 가리키던 링크 해제
    assert _as_visit_rows(oid) == []  # sd 파생 행도 함께 사라진다

    # 실제로 지운 접수에만 표식이 남는다(AS_REGISTER payload).
    new_cycle = _current_cycle(saved)
    assert new_cycle["cycle_id"] != first_id
    assert new_cycle["transitions"][0]["command"] == "AS_REGISTER"
    assert new_cycle["transitions"][0]["payload"]["visit_cleared"] is True

    # 지난 건의 방문 이력은 그 cycle transitions 에 그대로 남는다(복원 가능).
    first = _cycle_by_id(saved, first_id)
    assert _visit_projection(first) == {"visit_date": "2026-08-01", "visit_time": "14:30"}
    assert [t["command"] for t in first["transitions"]] == [
        "AS_REGISTER", "AS_SCHEDULE", "AS_START", "AS_COMPLETE",
    ]


def test_new_cycle_without_previous_visit_skips_cleared_stamp(client):
    """지울 방문일도 링크도 없던 접수에는 ``visit_cleared`` 표식을 남기지 않는다."""
    _login_as_admin(client, "state-as-visit-nostamp")
    order = _create_cs_order()
    oid = order.id
    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "첫 접수"})
    assert r.status_code == 200

    cycle = _current_cycle(_reload(oid))
    assert cycle["transitions"][0]["command"] == "AS_REGISTER"
    assert "visit_cleared" not in cycle["transitions"][0]["payload"]


def test_open_cycle_reregistration_keeps_visit_date(client):
    """열린 건 재접수(지방 AS 재상차)는 새 건이 아니므로 방문일을 그대로 둔다."""
    _login_as_admin(client, "state-as-visit-keep")
    order = _create_cs_order()
    oid = order.id
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "1차"})
    client.post(f"/api/orders/{oid}/as/schedule",
                json={"visit_date": "2026-08-03", "visit_time": "10:00"})

    r = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "재상차 접수"})
    assert r.status_code == 200 and r.get_json()["success"] is True
    saved = _reload(oid)
    assert len(saved.structured_data["as_lifecycle"]["cycles"]) == 1  # 같은 건(새 cycle 없음)
    as_visit = saved.structured_data["schedule"]["as_visit"]
    assert as_visit["date"] == "2026-08-03" and as_visit["time"] == "10:00"
    assert _as_visit_rows(oid) == ["2026-08-03"]
