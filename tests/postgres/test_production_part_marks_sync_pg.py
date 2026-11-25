"""PostgreSQL — 30초 받아 오기 한 번 읽기(주문 ⟕ 표시 줄 · ``row_number() = 1`` 인 줄에만 주문 JSON, 비평 C06).

SQLite 레인은 창 함수 · JSONB 를 PG 와 다르게 다룬다. 운영과 같은 PG 에서: 바뀐 표시 줄이 둘인 주문도 막힘 · JSON 은 한 번, 표시 줄이 안
바뀐 보류 주문도 막힘을 싣고, 읽기는 표시 줄 쪽 한 문장이다. ``FOMS_TEST_DATABASE_URL`` 미설정이면 레인을 건너뛴다. 이름은 지어낸 값이다.
"""
from __future__ import annotations

import datetime
import time

import pytest
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

import foms.platform.http as platform_http
from foms.services.datetime_kst import now_utc_naive
from foms.services.production.part_mark_gates import HOLD_MESSAGE
from models import Order, ProductionPartMark, ProductionRun, User


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


def _order(s, tag: str, n: int, *, hold: bool = False) -> tuple[int, list[str]]:
    files = [{"key": f"sync{tag}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"sync{tag}-s{j}"} for j in range(n)]
    production = {"hold": {"active": True, "reason": "자재 기다림"}} if hold else {}
    order = Order(received_date="2026-11-26", customer_name="가짜고객", phone="010-0000-0000", address="가짜시", product="가짜장",
                  status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                  structured_data={"workflow": {"stage": "PRODUCTION"}, "drawing_current_files": files,
                                   "parties": {"customer": {"name": "가짜고객"}}, "production": production})
    s.add(order)
    s.flush()
    s.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    return order.id, [f["key"] for f in files]


def test_sync_reads_blocks_with_marks_in_one_statement_on_postgres(pg_engine, pg_app):
    tag = str(int(time.time() * 1000) % 1000000)
    s = sessionmaker(bind=pg_engine)()
    try:
        kim = User(username=f"sync_kim_{tag}", password=generate_password_hash("pw"), role="STAFF", team="PRODUCTION",
                   name="김재단", is_active=True, production_part="cut")
        s.add(kim)
        s.flush()
        busy, keys = _order(s, tag + "a", 3)
        held, _ = _order(s, tag + "b", 2, hold=True)
        now = now_utc_naive()
        for key in keys[:2]:  # 바뀐 표시 줄이 둘 — 주문 JSON 은 한 줄에만
            s.add(ProductionPartMark(order_id=busy, drawing_key=key, part="cut", state="NEED", picked_by_user_id=kim.id,
                                     picked_by_name="김재단", picked_at=now, updated_by_user_id=kim.id, updated_at=now))
        s.commit()
        uid, username, role = kim.id, kim.username, kim.role
    finally:
        s.close()
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, username, role
    since = (now - datetime.timedelta(minutes=1)).isoformat()
    url = f"/api/production/part-marks?order_ids={busy},{held}&since={since}"
    assert client.get(url).status_code == 200  # 세션 첫 요청 치우기
    seen: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _before)
    try:
        resp = client.get(url)
    finally:
        event.remove(pg_engine, "before_cursor_execute", _before)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert sorted(m["drawing_key"] for m in data["marks"]) == sorted(keys[:2])
    assert data["blocks"][str(busy)] == {"all": None, "keys": {}}
    assert data["blocks"][str(held)]["all"] == {"kind": "hold", "text": "보류 · 자재 기다림", "why": HOLD_MESSAGE, "code": "HOLD_ACTIVE"}
    reads = [st for st in seen if "production_part_marks" in st]
    assert len(reads) == 1 and "row_number() OVER" in reads[0] and "LEFT OUTER JOIN production_part_marks" in reads[0]
