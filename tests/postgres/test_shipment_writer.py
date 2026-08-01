"""SHIPMENT-WRITER-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

per-order 출고 쓰기(AS 추천 apply/cancel)의 원자성을 실 PostgreSQL 다중 커밋 세션으로
고정한다:

* **apply 한 tx**: as_cycle_service schedule(방문일) + crew replace(ID command) + 출고
  Order snapshot 이 한 커밋에 보이고, rollback 시 방문·crew·snapshot·version 이 함께
  사라진다(원자성).
* **If-Match**: stale ``as_version`` 은 :class:`ASRecommendationError`(409)로 거부되고 DB
  변화 0.
* **cancel 이전 crew 복원**: released worker 를 이전 crew 로 재배정하는 복원은
  ``uq_order_installation_active`` partial-unique 하에서만 가능하므로 PG lane 이 검증한다
  (sqlite domains lane 은 partial-unique 미지원이라 이 경로를 다루지 않는다).

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다(dev DSN 은 env 로만
주입, 커밋 파일에 비밀번호 금지). 그 경우 sqlite domains lane
(``tests/domains/test_shipment_writer.py`` · ``tests/domains/test_shipment_as_recommendations.py``)
이 동일 계약(partial-unique 재배정 제외)을 대체 검증한다.
"""
from __future__ import annotations

import time

from sqlalchemy.orm import sessionmaker

from foms.services.crew.assignments import active_worker_ids, assign_worker
from foms.services.orders.as_cycle_service import (
    project_current_as_cycle,
    register_as_cycle,
    schedule_as_cycle,
)
from foms.services.shipment.as_recommendation import (
    ASRecommendationError,
    apply_as_recommendation,
    cancel_as_recommendation,
)
from models import InstallationWorker, Order, OrderEvent, User

_H = "a" * 64
_SEQ = [0]
_SHIP_DATE = "2026-08-01"


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _make_actor(session) -> User:
    _SEQ[0] += 1
    user = User(
        username=f"shipw_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password="pw-not-committed", name="출고작업자", role="STAFF", team="CS",
        is_active=True,
    )
    session.add(user)
    session.commit()
    return user


def _make_worker(session, ext: str, name: str) -> InstallationWorker:
    worker = InstallationWorker(external_worker_id=ext, display_name=name, is_active=True)
    session.add(worker)
    session.commit()
    return worker


def _make_ship(session, crew_ids: list[int]) -> Order:
    order = Order(
        received_date="2026-07-24", customer_name="출고 기준", phone="010-0000-0000",
        address="서울", product="장", is_erp_order=True, status="IN_CONSTRUCTION",
        erp_stage_code="IN_CONSTRUCTION",
        structured_data={"schedule": {"construction": {"date": _SHIP_DATE}}, "shipment": {}},
    )
    session.add(order)
    session.commit()
    for wid in crew_ids:
        assign_worker(session, order_id=order.id, worker_id=wid)
    session.commit()
    return order


def _make_as(session, actor_id: int) -> Order:
    order = Order(
        received_date="2026-07-24", customer_name="AS 대상", phone="010-1111-2222",
        address="서울", product="AS", is_erp_order=True, status="AS_RECEIVED",
        erp_stage_code="CS", structured_data={"workflow": {"stage": "CS"}, "shipment": {}},
    )
    session.add(order)
    session.commit()
    register_as_cycle(
        session, order_id=order.id, actor_user_id=actor_id, as_content="문 파손",
        received_date="2026-07-24", scope_hash=_H, request_hash=_H,
    )
    session.commit()
    return order


def test_pg_apply_schedules_crew_and_snapshot_one_tx(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        w1 = _make_worker(s, "PGW1", "철수")
        w2 = _make_worker(s, "PGW2", "영희")
        crew = sorted([w1.id, w2.id])
        ship = _make_ship(s, crew)
        as_order = _make_as(s, actor.id)
        ship_id, as_id = ship.id, as_order.id
        apply_as_recommendation(
            s, shipment_order_id=ship_id, as_order_id=as_id, actor_user_id=actor.id,
        )
        s.commit()
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        as_o = check.query(Order).filter_by(id=as_id).one()
        assert project_current_as_cycle(as_o)["visit_date"] == _SHIP_DATE
        assert active_worker_ids(check, as_id) == crew  # crew IDs via command
        ship_o = check.query(Order).filter_by(id=ship_id).one()
        recs = (ship_o.structured_data.get("shipment") or {}).get("recommendations")
        assert len(recs) == 1 and recs[0]["as_order_id"] == as_id
        assert recs[0]["applied_crew_ids"] == crew
        events = [e.event_type for e in check.query(OrderEvent).filter_by(order_id=as_id).all()]
        assert "AS_SCHEDULED" in events  # version/receipt/event 한 tx
    finally:
        check.close()


def test_pg_apply_rolls_back_atomically(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        w1 = _make_worker(s, "PGRB1", "철수")
        ship = _make_ship(s, [w1.id])
        as_order = _make_as(s, actor.id)
        ship_id, as_id = ship.id, as_order.id
        as_version_before = as_order.mutation_version
        apply_as_recommendation(
            s, shipment_order_id=ship_id, as_order_id=as_id, actor_user_id=actor.id,
        )
        s.rollback()
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        as_o = check.query(Order).filter_by(id=as_id).one()
        assert project_current_as_cycle(as_o)["visit_date"] is None  # 방문 미기록
        assert active_worker_ids(check, as_id) == []  # crew 미배정
        assert as_o.mutation_version == as_version_before
        ship_o = check.query(Order).filter_by(id=ship_id).one()
        assert (ship_o.structured_data.get("shipment") or {}).get("recommendations") in (None, [])
    finally:
        check.close()


def test_pg_apply_stale_if_match_rejected(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        w1 = _make_worker(s, "PGIM1", "철수")
        ship = _make_ship(s, [w1.id])
        as_order = _make_as(s, actor.id)
        ship_id, as_id = ship.id, as_order.id
        raised = False
        try:
            apply_as_recommendation(
                s, shipment_order_id=ship_id, as_order_id=as_id, actor_user_id=actor.id,
                as_version=999,
            )
        except ASRecommendationError as err:
            raised = True
            assert err.status_code == 409
        s.rollback()
        assert raised
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        as_o = check.query(Order).filter_by(id=as_id).one()
        assert project_current_as_cycle(as_o)["visit_date"] is None
    finally:
        check.close()


def test_pg_cancel_restores_nonempty_previous_crew(pg_engine):
    """released worker 재배정 복원(partial-unique 경로) — PG lane 전용."""
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        orig = _make_worker(s, "PGORIG", "원래작업자")
        w1 = _make_worker(s, "PGNEW1", "새작업자")
        ship = _make_ship(s, [w1.id])
        as_order = _make_as(s, actor.id)
        ship_id, as_id, orig_id = ship.id, as_order.id, orig.id
        # AS 원래: 방문일 2026-06-01 + orig 작업자 1명
        assign_worker(s, order_id=as_id, worker_id=orig_id)
        schedule_as_cycle(
            s, order_id=as_id, visit_date="2026-06-01",
            cycle_id=project_current_as_cycle(as_order)["cycle_id"], actor_user_id=actor.id,
            scope_hash=_H, request_hash=_H,
        )
        s.commit()
        apply_as_recommendation(
            s, shipment_order_id=ship_id, as_order_id=as_id, actor_user_id=actor.id, force=True,
        )
        s.commit()
        assert active_worker_ids(s, as_id) == [w1.id]  # 적용 후 crew=출고 crew
        cancel_as_recommendation(
            s, shipment_order_id=ship_id, as_order_id=as_id, actor_user_id=actor.id,
        )
        s.commit()
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        as_o = check.query(Order).filter_by(id=as_id).one()
        assert project_current_as_cycle(as_o)["visit_date"] == "2026-06-01"  # 이전 방문 복원
        assert active_worker_ids(check, as_id) == [orig_id]  # 이전 crew 재배정 복원
        ship_o = check.query(Order).filter_by(id=ship_id).one()
        assert (ship_o.structured_data.get("shipment") or {}).get("recommendations") in (None, [])
    finally:
        check.close()
