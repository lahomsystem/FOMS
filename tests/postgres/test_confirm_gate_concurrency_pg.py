"""2a-2 PostgreSQL 두 세션 테스트 — 도면 게이트는 행 잠금 아래에서 판정한다(TOCTOU).

예전 고객컨펌 승인·제작 시작 라우트는 잠그기 **전에** ``structured_data`` 를 읽어 게이트를
판정하고, 전이 전에 그 dict 로 객체를 dirty 로 만들었다. REV-00 엔진은 clean 객체만 비우므로
잠금을 기다리는 사이 커밋된 수정요청(RETURNED)을 못 본 채 옛 dict 를 되써, 수정 중인 도면이
생산으로 넘어갔다(설계서 §4.2.2·§4.2.3, 리뷰 A-5).

연결 B 가 주문 행을 ``FOR UPDATE`` 로 쥐고 수정요청(RETURNED + REQUEST_REVISION)을 쓴 뒤 커밋
전에 기다리는 동안 실제 Flask 라우트(스레드 A)를 부른다. A 는 잠금에서 기다렸다가 B 의 결과
위에서 판정해 409 ``DRAWING_STATUS`` 를 돌려줘야 한다.

* ① 수정요청(B) 대 고객컨펌 승인(A) — A 409, 최종 CONFIRM·RETURNED.
* ② 수정요청(B) 대 제작 시작 (a)(A, 생산 대기) — A 409, run 없음, 최종 RETURNED.

음성 대조(``mode="plain"``): 라우트 첫 조회를 잠금 없는 조회로 되돌리면 같은 시나리오에서 A 가
200 으로 통과하고 B 의 RETURNED 가 사라진다(①) — 시나리오가 결함을 실제로 잡는다는 증거다.
``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 레인을 skip 한다.
"""
from __future__ import annotations

import copy
import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.api.production.orders as production_api
import foms.api.quest as quest_api
import foms.platform.http as platform_http
from models import Order, ProductionRun, User
from tests.support.confirm_seed import confirmed_drawing_sd
from tests.support.quest_seed import confirm_quest_open

_HOLD_SECONDS = 1.0
_SEQ = [0]


def _plain_fetch(db, order_id):
    """음성 대조용: 잠그지 않는 일반 조회(예전 라우트의 첫 조회)."""
    return db.query(Order).filter(Order.id == order_id).first()


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


def _seed(pg_engine, *, stage, user_team, extra_sd):
    """영업·실행자 두 명과 주문 1건을 커밋한다. (order_id, (actor id, username, role))."""
    _SEQ[0] += 1
    tag = f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"
    s = _session(pg_engine)
    try:
        sales = User(username=f"cg_s_{tag}", password=generate_password_hash("pw"),
                     role="STAFF", team="SALES", name="영업", is_active=True)
        actor = User(username=f"cg_a_{tag}", password=generate_password_hash("pw"),
                     role="STAFF", team=user_team, name="실행자", is_active=True)
        s.add_all([sales, actor])
        s.flush()
        sd = {
            "parties": {"customer": {"name": "게이트고객"}, "manager": {"name": "영업"}},
            "workflow": {"stage": stage},
            "assignments": {"sales_assignee_user_ids": [sales.id]},
            **confirmed_drawing_sd(),
            **extra_sd,
        }
        order = Order(
            received_date="2026-09-29", customer_name="게이트고객", phone="010-0000-0000",
            address="서울", product="붙박이장", status=stage, is_erp_order=True,
            erp_stage_code=stage, manager_name="영업", structured_data=sd,
        )
        s.add(order)
        s.commit()
        return order.id, (actor.id, actor.username, actor.role)
    finally:
        s.close()


def _b_revision(sd):
    sd["drawing_status"] = "RETURNED"
    sd["drawing_transfer_history"].append(
        {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "B", "files": []})


def _hold_and_write(pg_engine, order_id, started, done):
    """연결 B: 행을 FOR UPDATE 로 쥐고 수정요청(+버전)을 쓴 뒤 커밋 전 대기 → 커밋."""
    s = _session(pg_engine)
    try:
        o = s.query(Order).filter(Order.id == order_id).with_for_update().one()
        sd = copy.deepcopy(o.structured_data)
        _b_revision(sd)
        o.structured_data = sd
        flag_modified(o, "structured_data")
        o.mutation_version = (o.mutation_version or 0) + 1
        s.flush()
        started.set()
        time.sleep(_HOLD_SECONDS)
        s.commit()
    finally:
        s.close()
        done.set()


def _race(pg_engine, app, order_id, user_a, url):
    started, done = threading.Event(), threading.Event()
    tb = threading.Thread(target=_hold_and_write, args=(pg_engine, order_id, started, done))
    tb.start()
    assert started.wait(5.0), "연결 B 가 잠금을 잡지 못했다"
    out = {}

    def _call():
        client = app.test_client()
        uid, username, role = user_a
        with client.session_transaction() as sess:
            sess["user_id"], sess["username"], sess["role"] = uid, username, role
        t0 = time.monotonic()
        resp = client.post(url, json={})
        out["elapsed"] = time.monotonic() - t0
        out["status"], out["json"] = resp.status_code, resp.get_json()

    ta = threading.Thread(target=_call)
    ta.start()
    ta.join(15.0)
    tb.join(15.0)
    assert "status" in out, "라우트 A 가 끝나지 않았다"
    return out


def _final(pg_engine, order_id):
    s = _session(pg_engine)
    try:
        o = s.query(Order).filter(Order.id == order_id).one()
        runs = s.query(ProductionRun).filter(ProductionRun.order_id == order_id).count()
        return dict(o.structured_data), o.erp_stage_code, runs
    finally:
        s.close()


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_confirm_approve_waits_for_concurrent_revision_request(pg_engine, pg_app, monkeypatch, mode):
    """① B=수정요청(RETURNED) · A=고객컨펌 승인 → A 409, 최종 CONFIRM·RETURNED."""
    oid, sales_actor = _seed(pg_engine, stage="CONFIRM", user_team="SALES",
                             extra_sd={"quests": [confirm_quest_open()]})
    if mode == "plain":
        monkeypatch.setattr(quest_api, "lock_order_row", _plain_fetch)

    out = _race(pg_engine, pg_app, oid, sales_actor, f"/api/orders/{oid}/quest/approve")

    sd, stage, _runs = _final(pg_engine, oid)
    if mode == "plain":
        # 음성 대조: 잠그기 전에 읽은 CONFIRMED 로 게이트를 통과하고, 옛 dict 를 되써 RETURNED 가 사라진다.
        assert out["status"] == 200, out
        assert stage == "PRODUCTION" and sd["drawing_status"] == "CONFIRMED", (stage, sd.get("drawing_status"))
        return
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out  # 잠금에서 기다렸다
    assert out["status"] == 409 and out["json"]["code"] == "DRAWING_STATUS", out
    assert stage == "CONFIRM" and sd["drawing_status"] == "RETURNED"
    assert "B" in [h.get("note") for h in sd["drawing_transfer_history"]]


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_production_run_start_waits_for_concurrent_revision_request(pg_engine, pg_app, monkeypatch, mode):
    """② B=수정요청(RETURNED) · A=제작 시작(a, 생산 대기) → A 409, run 없음."""
    oid, prod_actor = _seed(pg_engine, stage="PRODUCTION", user_team="PRODUCTION", extra_sd={})
    if mode == "plain":
        monkeypatch.setattr(production_api, "lock_order_row", _plain_fetch)

    out = _race(pg_engine, pg_app, oid, prod_actor, f"/api/orders/{oid}/production/start")

    sd, stage, runs = _final(pg_engine, oid)
    if mode == "plain":
        # 음성 대조: 잠그기 전 sd(CONFIRMED)로 판정해 수정 중인 도면으로 제작이 시작된다.
        assert out["status"] == 200 and runs == 1, out
        return
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert out["status"] == 409 and out["json"]["code"] == "DRAWING_STATUS", out
    assert runs == 0 and stage == "PRODUCTION" and sd["drawing_status"] == "RETURNED"
