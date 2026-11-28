"""PostgreSQL — '도면 없음' 주문 카드(key ``@order``)를 쓰고 끝낸 뒤 도면이 처음 올라올 때 한 번 옮기기(설계서
2026-11-28-production-my-steps-flow §3-5 · 사장님 답 27 · 33 · 35).

운영과 같은 PG 에서: 주문 잠금(``FOR UPDATE``) 아래 ``@order`` 쓰기 · 공정 칸 켜기, 바로 반영 전달 한 tx 안의 옮기기(표시 줄 INSERT 한 문장 ·
``@order`` 미정 UPDATE 한 문장 · 손 체크 파트 풀어 쓰기 ``INSERT … ON CONFLICT``) 뒤 공정 칸 맞추기가 칸을 켠 채 두는지.
``FOMS_TEST_DATABASE_URL`` 미설정이면 레인을 건너뛴다. 이름은 지어낸 값이다.
"""
from __future__ import annotations

import pytest

import foms.platform.http as platform_http
from tests.support.drawing_fix_transfer_seed import key, login as dfx_login, make_order, make_user as dfx_user, marks, quiet, send  # noqa: F401
from tests.support.production_part_claim_seed import check_step, login, make_user, step


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


def _press(client, who, oid: int, part: str, action: str, seen: str):
    login(client, who)
    resp = client.post("/api/production/part-marks",
                       json={"order_id": oid, "drawing_key": "@order", "part": part, "action": action, "seen": seen})
    assert resp.status_code == 200, resp.get_json()


def test_order_card_then_first_drawings_keep_done_on_postgres(pg_app, quiet):
    client = pg_app.test_client()
    oid = make_order(0)
    kim, lead, drawer = make_user("김재단", part="cut"), make_user("박반장", lead=True), dfx_user("김도면", team="DRAWING")
    _press(client, kim, oid, "cut", "take", "none")
    _press(client, kim, oid, "cut", "done", "need")
    login(client, lead)
    assert check_step(client, oid, "assemble", True).status_code == 200
    assert step(oid, "cut")["done"] is True and step(oid, "assemble")["done"] is True
    dfx_login(client, drawer)
    resp = send(client, "drawing", oid, "s0", "s1")
    assert resp.status_code == 200, resp.get_json()
    rows = marks(oid)
    new = [key(oid, "s0-v2"), key(oid, "s1-v2")]
    assert [rows[(k, "cut")].state for k in new] == ["DONE", "DONE"] and rows[("@order", "cut")].state == "NONE"
    assert [(rows[(k, "assemble")].state, rows[(k, "assemble")].done_by_name) for k in new] == [("DONE", "박반장")] * 2
    assert step(oid, "cut")["done"] is True and step(oid, "assemble")["done"] is True
    assert step(oid, "edge")["done"] is False and not any((k, "edge") in rows for k in new)
