"""공장마다 제작 완료 경합 PostgreSQL 계약(설계서 2026-11-23 §4-14 '같은 때', 3단계 ⑥ — PGTEST-00 lane).

두 공장 마지막 사람이 같은 때 ``POST /api/orders/<id>/production/factory-done`` 을 누른다. 주문 행 잠금(``lock_order_row`` →
``transition_order`` 안 다시 잠금, 같은 tx)이 줄을 세워 먼저 온 쪽은 '마지막 아님'으로 표지만, 뒤에 온 쪽이 잠금 아래에서 그 표지를
읽고 '마지막'으로 시공 대기까지 옮긴다 — 한쪽만 마지막, 제작 완료 이벤트 1, 표지 둘.

* lock: 다른 연결이 행을 잡은 채 두 요청을 띄우고 놓는다 → 둘 다 200 · final 은 정확히 하나 · CONSTRUCTION · 표지 {1, 2}.
* plain(음성 대조): 서비스의 잠금을 평범한 읽기로 바꾸면 둘 다 낡은 JSON(표지 없음)으로 '마지막 아님'을 정해 표지 둘인데
  단계는 생산에 남는다(아무도 시공 대기로 안 옮김) — 잠금이 실제로 이 경합을 막는다는 증거.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 레인을 skip 한다. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

import foms.platform.http as platform_http
import foms.services.production.factory_complete as factory_complete
from models import Order, OrderEvent, ProductionPartMark, ProductionRun, User

_SEQ = [0]
_HOLD_SECONDS = 1.2


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


def _user(s, tag: str, name: str, factory: int | None) -> tuple:
    user = User(username=f"fd_{tag}_{name}", password=generate_password_hash("pw"), role="STAFF", team="PRODUCTION",
                name=name, is_active=True, production_part="inspect", production_parts=["inspect"],
                production_factory=factory)
    s.add(user)
    s.flush()
    return user.id, user.username, user.role


def _seed(pg_engine) -> tuple[int, tuple, tuple]:
    """섞인 주문(1공장 2장 · 2공장 1장) — 세 장 모두 네 파트 완료(표시 줄), 공정 칸은 카드 동기화로 켜짐."""
    _SEQ[0] += 1
    tag = f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"
    s = _session(pg_engine)
    try:
        insp1, insp2 = _user(s, tag, "윤검수", None), _user(s, tag, "강검수", 2)
        files = [{"key": f"fd{tag}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"fd{tag}-s{j}"} for j in range(3)]
        steps = [{"key": k, "label": k, "done": True, "at": "2026-11-24T00:00:00+00:00", "by_name": "윤검수", "via": "part_marks"}
                 for k in ("cut", "edge", "assemble", "inspect")]
        sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": "가짜고객"}}, "drawing_current_files": files,
              "drawing_factory": {"sheets": {files[2]["sheet_id"]: 2}}, "production": {"steps": steps}}
        order = Order(received_date="2026-11-24", customer_name="가짜고객", phone="010-0000-0000", address="가짜시",
                      product="가짜장", status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION", structured_data=sd)
        s.add(order)
        s.flush()
        s.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        for f in files:
            for part in ("cut", "edge", "assemble", "inspect"):
                s.add(ProductionPartMark(order_id=order.id, drawing_key=f["key"], sheet_id=f["sheet_id"], part=part,
                                         state="DONE", done_by_user_id=insp1[0], done_by_name="윤검수"))
        s.commit()
        return order.id, insp1, insp2
    finally:
        s.close()


def _hold(pg_engine, order_id: int, started: threading.Event) -> None:
    """다른 연결이 주문 행을 잠근 채 잠깐 쥔다 — 두 요청이 같은 잠금 앞에 줄을 선다."""
    s = _session(pg_engine)
    try:
        s.execute(text("SELECT id FROM orders WHERE id = :id FOR UPDATE"), {"id": order_id})
        started.set()
        time.sleep(_HOLD_SECONDS)
        s.commit()
    finally:
        s.close()


def _race(pg_engine, app, order_id: int, people: list[tuple[tuple, int]]) -> list[dict]:
    started = threading.Event()
    holder = threading.Thread(target=_hold, args=(pg_engine, order_id, started))
    holder.start()
    assert started.wait(5.0), "잠금을 잡지 못했다"
    outs: list[dict] = [{} for _ in people]

    def _call(i: int, actor: tuple, factory: int) -> None:
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"], sess["username"], sess["role"] = actor
        resp = client.post(f"/api/orders/{order_id}/production/factory-done", json={"factory": factory, "done": True})
        outs[i].update(status=resp.status_code, json=resp.get_json())

    threads = [threading.Thread(target=_call, args=(i, actor, f)) for i, (actor, f) in enumerate(people)]
    for t in threads:
        t.start()
    for t in threads + [holder]:
        t.join(20.0)
    assert all("status" in o for o in outs), outs
    return outs


def _final(pg_engine, order_id: int) -> tuple[str, dict, int]:
    s = _session(pg_engine)
    try:
        o = s.query(Order).filter(Order.id == order_id).one()
        done = (o.structured_data.get("production") or {}).get("factory_done") or {}
        completed = s.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_COMPLETED").count()
        return o.erp_stage_code, done, completed
    finally:
        s.close()


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_two_factories_at_once_only_one_is_last(pg_engine, pg_app, monkeypatch, mode):
    oid, insp1, insp2 = _seed(pg_engine)
    if mode == "plain":
        from db import db_session

        monkeypatch.setattr(factory_complete, "lock_order_row", lambda db, order_id: db_session.get(Order, order_id))

    outs = _race(pg_engine, pg_app, oid, [(insp1, 1), (insp2, 2)])

    stage, done, completed = _final(pg_engine, oid)
    assert set(done) == {"1", "2"}, (outs, done)
    if mode == "plain":
        # 음성 대조: 둘 다 낡은 JSON 으로 '마지막 아님' — 표지는 둘인데 단계는 생산에 남는다
        assert [o["json"]["data"]["final"] for o in outs] == [False, False] and stage == "PRODUCTION", outs
        return
    assert [o["status"] for o in outs] == [200, 200], outs
    assert sorted(o["json"]["data"]["final"] for o in outs) == [False, True], outs
    assert stage == "CONSTRUCTION" and completed == 1
