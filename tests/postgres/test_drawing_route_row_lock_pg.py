"""2a-1② PostgreSQL 두 세션 테스트 — 도면 라우트는 첫 조회부터 행 잠금 아래에서 판정·쓰기한다.

도면 라우트들은 예전에 잠그기 **전에** ``structured_data`` 를 deepcopy 하고 상태 검사까지
끝냈다. REV-00 엔진(``execute_order_mutation``)은 잠금 전에 clean 객체를 비우지만, 라우트가
이미 만들어 둔 dict 는 못 고친다 — 그래서 잠금을 기다리는 사이 커밋된 남의 도면 쓰기를 못
본 채 옛 dict 를 되쓰는 lost update 가 났다(설계서 §4.1 설계 ②, 리뷰 A-5).

여기서는 연결 B 가 주문 행을 ``FOR UPDATE`` 로 쥐고 도면 쓰기를 한 뒤 커밋 전에 기다리는
동안, 실제 Flask 라우트(스레드 A)를 부른다. A 는 잠금에서 기다렸다가 B 의 결과 **위에서**
판정·쓰기해야 한다.

* 수정요청(B) 대 반영 체크(A) — 최종 이력에 두 동작이 모두 남는다.
* 수령 확정(B) 대 수정요청(A) — 두 동작이 모두 남고 상태는 마지막 동작(RETURNED)과 같다.
* 수정요청(B) 대 수령 확정 단계 유지(A) — A 는 B 가 만든 RETURNED 를 보고 400 으로 거절한다.

음성 대조(``mode="plain"``): 라우트의 첫 조회를 잠금 도우미 대신 일반 조회로 바꾸면 같은
시나리오에서 B 의 쓰기가 사라진다(lost update)는 것을 **같은 테스트가** 단언한다 — 시나리오가
결함을 실제로 잡는다는 증거다.

라우트는 전역 ``db_session``(scoped) 을 쓰므로, 테스트 동안만 그 바인딩을 PG 엔진으로
바꾸고 끝나면 되돌린다. ``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 레인을 skip 한다.
"""
from __future__ import annotations

import copy
import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_draftsman as draftsman_api
import foms.api.drawing.erp_orders_revision as revision_api
import foms.platform.http as platform_http
from models import Order, User

_HOLD_SECONDS = 1.0
_SEQ = [0]


class _Storage:
    def delete_file(self, key):
        return True


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
    monkeypatch.setattr(revision_api, "get_storage", lambda: _Storage())
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda *a, **k: None)
    # 마지막 접속 기록은 전역 기본 엔진에 따로 붙어(SQLite, 테이블 없음) 로그만 시끄럽다 — 끈다.
    monkeypatch.setattr(platform_http, "touch_last_seen", lambda user: False)
    try:
        yield flask_app
    finally:
        db_session.remove()
        db_session.configure(bind=default_engine)


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _seed(pg_engine, *, stage, drawing_status, history):
    """영업·도면 담당 두 명과 주문 1건을 커밋한다. (order_id, sales, drafter) 를 돌려준다."""
    _SEQ[0] += 1
    tag = f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"
    s = _session(pg_engine)
    try:
        sales = User(username=f"lk_s_{tag}", password=generate_password_hash("pw"),
                     role="STAFF", team="SALES", name="영업", is_active=True)
        drafter = User(username=f"lk_d_{tag}", password=generate_password_hash("pw"),
                       role="STAFF", team="DRAWING", name="도면", is_active=True)
        s.add_all([sales, drafter])
        s.flush()
        files = [{"key": "orders/0/drawing_wizard/exports/v1.png", "filename": "v1.png"}]
        order = Order(
            received_date="2026-09-29", customer_name="잠금고객", phone="010-0000-0000",
            address="서울", product="붙박이장", status=stage, is_erp_order=True,
            erp_stage_code=stage, manager_name="영업",
            structured_data={
                "parties": {"customer": {"name": "잠금고객"}, "manager": {"name": "영업"}},
                "workflow": {"stage": stage},
                "drawing_status": drawing_status,
                "drawing_current_files": files,
                "drawing_transfer_history": history,
                "assignments": {"sales_assignee_user_ids": [sales.id],
                                "drawing_assignee_user_ids": [drafter.id]},
            },
        )
        s.add(order)
        s.commit()
        return (order.id, (sales.id, sales.username, sales.role),
                (drafter.id, drafter.username, drafter.role))
    finally:
        s.close()


def _hold_and_write(pg_engine, order_id, mutate, started, done):
    """연결 B: 행을 FOR UPDATE 로 쥐고 도면 쓰기(+버전) 뒤 커밋 전 대기 → 커밋."""
    s = _session(pg_engine)
    try:
        o = s.query(Order).filter(Order.id == order_id).with_for_update().one()
        sd = copy.deepcopy(o.structured_data)
        mutate(sd)
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


def _race(pg_engine, app, order_id, mutate_b, user_a, url, body):
    """B 가 잠금을 쥔 동안 A(실제 라우트)를 부른다. (A 응답 상태, A 응답 JSON, A 대기 시간)."""
    started, done = threading.Event(), threading.Event()
    tb = threading.Thread(target=_hold_and_write,
                          args=(pg_engine, order_id, mutate_b, started, done))
    tb.start()
    assert started.wait(5.0), "연결 B 가 잠금을 잡지 못했다"
    out = {}

    def _call():
        client = app.test_client()
        uid, username, role = user_a
        with client.session_transaction() as sess:
            sess["user_id"], sess["username"], sess["role"] = uid, username, role
        t0 = time.monotonic()
        resp = client.post(url, json=body)
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
        return dict(o.structured_data), int(o.mutation_version)
    finally:
        s.close()


def _actions(sd):
    return [h.get("action") for h in sd.get("drawing_transfer_history") or []]


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_revision_check_waits_for_concurrent_revision_request(pg_engine, pg_app, monkeypatch, mode):
    """B=새 수정요청(RETURNED) · A=옛 수정요청 반영 체크 → 두 동작 모두 남는다."""
    history = [
        {"action": "TRANSFER", "transferred_at": "2026-09-20 10:00:00", "files": []},
        {"action": "REQUEST_REVISION", "at": "2026-09-21 10:00:00", "by_user_id": None, "files": []},
        {"action": "TRANSFER", "transferred_at": "2026-09-22 10:00:00", "files": []},
    ]
    oid, _sales, drafter = _seed(pg_engine, stage="DRAWING", drawing_status="TRANSFERRED",
                                 history=history)
    if mode == "plain":
        monkeypatch.setattr(revision_api, "lock_order_row", _plain_fetch)

    def _b_revision(sd):
        sd["drawing_status"] = "RETURNED"
        sd["drawing_transfer_history"].append(
            {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "B", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_revision, drafter,
                f"/api/orders/{oid}/request-revision-check",
                {"request_at": "2026-09-21 10:00:00", "checked": True})
    assert out["status"] == 200, out
    sd, version = _final(pg_engine, oid)
    notes = [h.get("note") for h in sd["drawing_transfer_history"]]
    if mode == "plain":
        # 음성 대조: 잠그기 전에 읽은 옛 dict 를 되써서 B 의 수정요청이 사라진다.
        assert "B" not in notes and sd["drawing_status"] == "TRANSFERRED", sd
        return
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out  # 잠금에서 기다렸다
    assert "B" in notes, _actions(sd)
    assert sd["drawing_status"] == "RETURNED"
    assert sd["drawing_transfer_history"][1]["review_check"]["checked"] is True
    assert version == 3  # 1(생성) → B +1 → A +1


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_revision_request_waits_for_concurrent_receipt(pg_engine, pg_app, monkeypatch, mode):
    """B=수령 확정(CONFIRMED) · A=수정요청 → 이력에 둘 다, 상태는 마지막 동작(RETURNED)."""
    history = [{"action": "TRANSFER", "transferred_at": "2026-09-28 10:00:00", "files": []}]
    oid, sales, _drafter = _seed(pg_engine, stage="CONFIRM", drawing_status="TRANSFERRED",
                                 history=history)
    if mode == "plain":
        monkeypatch.setattr(revision_api, "lock_order_row", _plain_fetch)

    def _b_confirm(sd):
        sd["drawing_status"] = "CONFIRMED"
        sd["drawing_transfer_history"].append(
            {"action": "CONFIRM_RECEIPT", "at": "2026-09-29 09:00:00", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_confirm, sales,
                f"/api/orders/{oid}/request-revision", {"note": "A 수정"})
    assert out["status"] == 200, out
    sd, version = _final(pg_engine, oid)
    if mode == "plain":
        assert _actions(sd) == ["TRANSFER", "REQUEST_REVISION"], _actions(sd)  # 확정이 사라짐
        return
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert _actions(sd) == ["TRANSFER", "CONFIRM_RECEIPT", "REQUEST_REVISION"]
    assert sd["drawing_status"] == "RETURNED"
    assert version == 3


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_receipt_waits_for_concurrent_revision_request(pg_engine, pg_app, monkeypatch, mode):
    """B=수정요청(RETURNED) · A=단계 유지 수령 확정 → A 는 B 의 RETURNED 를 보고 400."""
    history = [{"action": "TRANSFER", "transferred_at": "2026-09-28 10:00:00", "files": []}]
    oid, sales, _drafter = _seed(pg_engine, stage="CONFIRM", drawing_status="TRANSFERRED",
                                 history=history)
    if mode == "plain":
        monkeypatch.setattr(draftsman_api, "lock_order_row", _plain_fetch)

    def _b_revision(sd):
        sd["drawing_status"] = "RETURNED"
        sd["drawing_transfer_history"].append(
            {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "B", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_revision, sales,
                f"/api/orders/{oid}/confirm-drawing-receipt", {})
    sd, version = _final(pg_engine, oid)
    if mode == "plain":
        # 음성 대조: 옛 TRANSFERRED 로 판정해 확정하고, B 의 수정요청을 덮어쓴다.
        assert out["status"] == 200, out
        assert sd["drawing_status"] == "CONFIRMED"
        assert "REQUEST_REVISION" not in _actions(sd), _actions(sd)
        return
    assert out["status"] == 400, out
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert _actions(sd) == ["TRANSFER", "REQUEST_REVISION"]
    assert sd["drawing_status"] == "RETURNED"
    assert version == 2  # B 만 올렸다(거절된 A 는 쓰지 않음)
