"""[제작 완료] 검수 게이트 PostgreSQL 계약 (PGTEST-00 lane, 사용자 결정 2026-11-21).

SQLite 도메인 시험(``tests/domains/test_production_complete_requires_inspect.py``)과 같은 단언을 실 PostgreSQL
(JSONB ``structured_data``)에서 다시 잰다 — 거절은 별도 세션에서 봐도 단계 · 버전 · 이벤트 · run 이 그대로이고,
공정 칸을 켠 뒤(같은 JSONB 쓰기 규칙: deepcopy → 재대입 → flag_modified) 같은 라우트가 커밋까지 간다.

공정 칸을 쓴 주문만 막는다(11-21 사용자 "공정 칸을 쓴 주문만 막기") — 한 칸도 안 켠 주문은 규칙 밖.

* ① 재단만 켠 주문 → ``POST /api/orders/<id>/production/complete`` 409 STEPS_INCOMPLETE, 아무것도 안 바뀜.
* ② 같은 주문 4칸 켜기 → 200, CONSTRUCTION · PRODUCTION_COMPLETED 1 · run 종결.
* ③ 일반 단계 쓰기(``/api/update_order_status`` 생산 → 시공)도 같은 409.
* ④ 단계 강제 변경(MANAGER)은 검수 전이어도 된다 — 비상구.
* ⑤ 대조군: 칸 없는 옛 주문(규칙 밖)은 완료 API 로 그대로 커밋된다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 레인을 skip 한다.
"""
from __future__ import annotations

import copy
import time

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.platform.http as platform_http
from models import Order, OrderEvent, ProductionRun, User
from tests.support.production_steps_seed import inspected_steps

_SEQ = [0]


@pytest.fixture
def pg_app(pg_engine, monkeypatch):
    """전역 db_session 을 PG 엔진에 묶은 Flask 앱(테스트 끝에 원래 엔진으로 되돌린다)."""
    from app import app as flask_app
    from db import db_session, engine as default_engine

    db_session.remove()
    db_session.configure(bind=pg_engine)
    flask_app.config["TESTING"] = True
    monkeypatch.setattr(platform_http, "touch_last_seen", lambda user: False)
    try:
        yield flask_app
    finally:
        db_session.remove()
        db_session.configure(bind=default_engine)


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _seed(pg_engine, *, role: str = "STAFF", team: str | None = "PRODUCTION",
          steps: list | None = None) -> tuple[int, tuple]:
    """가짜 사람 1 · 생산 단계 주문 1 + current run 1 을 커밋한다. ``steps`` 를 안 주면 칸 없는 옛 주문(규칙 밖)."""
    _SEQ[0] += 1
    tag = f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"
    s = _session(pg_engine)
    try:
        actor = User(username=f"ig_{tag}", password=generate_password_hash("pw"), role=role, team=team,
                     name="가짜작업자", is_active=True)
        s.add(actor)
        s.flush()
        sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": "가짜고객"}}}
        if steps is not None:
            sd["production"] = {"steps": steps}
        order = Order(received_date="2026-11-21", customer_name="가짜고객", phone="010-0000-0000", address="가짜시",
                      product="가짜장", status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                      structured_data=sd)
        s.add(order)
        s.flush()
        s.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        s.commit()
        return order.id, (actor.id, actor.username, actor.role)
    finally:
        s.close()


def _client(app, actor):
    client = app.test_client()
    uid, username, role = actor
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, username, role
    return client


def _state(pg_engine, oid: int) -> dict:
    s = _session(pg_engine)
    try:
        o = s.query(Order).filter(Order.id == oid).one()
        return {
            "stage": o.erp_stage_code,
            "version": o.mutation_version,
            "completed": s.query(OrderEvent).filter_by(order_id=oid, event_type="PRODUCTION_COMPLETED").count(),
            "stage_changed": s.query(OrderEvent).filter_by(order_id=oid, event_type="STAGE_CHANGED").count(),
            "current_runs": s.query(ProductionRun).filter_by(order_id=oid, is_current=True).count(),
        }
    finally:
        s.close()


def _inspect_all(pg_engine, oid: int) -> None:
    s = _session(pg_engine)
    try:
        o = s.query(Order).filter(Order.id == oid).with_for_update().one()
        sd = copy.deepcopy(o.structured_data)
        sd.setdefault("production", {})["steps"] = inspected_steps()
        o.structured_data = sd
        flag_modified(o, "structured_data")
        s.commit()
    finally:
        s.close()


_UNTOUCHED = {"stage": "PRODUCTION", "version": 1, "completed": 0, "stage_changed": 0, "current_runs": 1}
#: 공정 칸을 쓴(한 칸 이상 켠) 검수 전 주문 — 재단만 켬
_CUT_ONLY = inspected_steps(upto="cut")


def test_pg_complete_blocked_until_inspected_then_commits(pg_engine, pg_app):
    oid, actor = _seed(pg_engine, steps=_CUT_ONLY)
    client = _client(pg_app, actor)

    blocked = client.post(f"/api/orders/{oid}/production/complete", json={})
    assert blocked.status_code == 409, blocked.get_data(as_text=True)
    assert blocked.get_json()["code"] == "STEPS_INCOMPLETE"
    assert _state(pg_engine, oid) == _UNTOUCHED

    _inspect_all(pg_engine, oid)
    done = client.post(f"/api/orders/{oid}/production/complete", json={})
    assert done.status_code == 200, done.get_data(as_text=True)
    after = _state(pg_engine, oid)
    assert after["stage"] == "CONSTRUCTION" and after["completed"] == 1 and after["current_runs"] == 0


def test_pg_generic_status_write_has_same_gate(pg_engine, pg_app):
    oid, actor = _seed(pg_engine, role="ADMIN", team="CS", steps=_CUT_ONLY)
    client = _client(pg_app, actor)

    resp = client.post("/api/update_order_status", json={"order_id": oid, "status": "CONSTRUCTION"})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "STEPS_INCOMPLETE"
    assert _state(pg_engine, oid) == _UNTOUCHED


def test_pg_stage_override_is_the_exit(pg_engine, pg_app):
    oid, actor = _seed(pg_engine, role="MANAGER", team=None, steps=_CUT_ONLY)
    client = _client(pg_app, actor)

    resp = client.post(f"/api/orders/{oid}/workflow/stage-override",
                       json={"to_stage": "CONSTRUCTION", "reason": "공정 칸을 안 쓰던 주문 정리", "confirm": True})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _state(pg_engine, oid)["stage"] == "CONSTRUCTION"


def test_pg_order_without_steps_is_outside_the_rule(pg_engine, pg_app):
    """대조군(규칙 밖): 공정 칸을 한 칸도 안 켠 옛 주문은 완료 API 로 그대로 커밋된다."""
    oid, actor = _seed(pg_engine)
    client = _client(pg_app, actor)

    done = client.post(f"/api/orders/{oid}/production/complete", json={})
    assert done.status_code == 200, done.get_data(as_text=True)
    after = _state(pg_engine, oid)
    assert after["stage"] == "CONSTRUCTION" and after["completed"] == 1 and after["current_runs"] == 0
