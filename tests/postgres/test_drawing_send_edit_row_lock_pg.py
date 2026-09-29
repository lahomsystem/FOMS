"""PostgreSQL 두 세션 — 도면 탭 보내기의 두 쓰기가 행 잠금 아래에서 판정·쓰기한다(설계서 2026-09-29).

* 요청 고치기(Q5-③, A) 대 반영 체크(B): A 는 B 가 체크한 요청을 보고 409 로 거절한다.
  음성 대조(plain — 첫 조회를 잠금 없는 조회로): A 가 옛 dict(체크 전)를 보고 고쳐 되써서 B 의
  반영 체크가 사라진다.
* 알림톡·회사 문자 발송(A) 대 도면 쓰기(B): 발송 흔적(``sd['alimtalk_share']``) 쓰기 바로 앞
  ``lock_order_row``(§4.6) 때문에 A 는 B 커밋을 기다렸다가 B 의 이력 위에 흔적을 쓴다. 음성 대조
  (잠금 제거 + 흔적 쓰기 직전 재조회 뒤에 B 커밋): B 의 이력 항목이 사라진다. 두 라우트 모두 본다.
* 인라인 번호 저장(A, PATCH structured/fields — Q5-② '주문 고객 번호도 저장') 대 도면 쓰기(B):
  첫 조회 행 잠금 때문에 A 는 B 커밋 뒤의 이력 위에 번호를 쓴다. 음성 대조(첫 조회를 잠금 없는
  조회로): A 가 옛 dict 를 통째로 되써 B 의 수정요청이 사라진다.

실행: ``FOMS_TEST_DATABASE_URL`` 이 로컬 PG 를 가리킬 때만(없으면 conftest 가 skip).
"""
from __future__ import annotations

import copy
import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
import foms.api.erp_orders_structured as structured_api
import foms.api.share as share_api
import foms.platform.http as platform_http
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as osvc
from models import Order, User

_HOLD_SECONDS = 1.0
_SEQ = [0]


@pytest.fixture
def pg_app(pg_engine, monkeypatch):
    from app import app as flask_app
    from db import db_session, engine as default_engine

    db_session.remove()
    db_session.configure(bind=pg_engine)
    flask_app.config["TESTING"] = True
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr(platform_http, "touch_last_seen", lambda user: False)
    try:
        yield flask_app
    finally:
        db_session.remove()
        db_session.configure(bind=default_engine)


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _seed(pg_engine, *, drawing_status, history):
    _SEQ[0] += 1
    tag = f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"
    s = _session(pg_engine)
    try:
        sales = User(username=f"se_s_{tag}", password=generate_password_hash("pw"),
                     role="STAFF", team="SALES", name="영업", is_active=True)
        drafter = User(username=f"se_d_{tag}", password=generate_password_hash("pw"),
                       role="STAFF", team="DRAWING", name="도면", is_active=True)
        s.add_all([sales, drafter])
        s.flush()
        order = Order(
            received_date="2026-09-29", customer_name="보내기고객", phone="010-2473-6730",
            address="서울", product="붙박이장", status="DRAWING", is_erp_order=True,
            erp_stage_code="DRAWING", manager_name="영업",
            structured_data={
                "parties": {"customer": {"name": "보내기고객", "phone": "010-2473-6730"},
                            "manager": {"name": "영업"}},
                "workflow": {"stage": "DRAWING"},
                "drawing_status": drawing_status,
                "drawing_current_files": [{"key": "orders/0/drawing_wizard/exports/v1.png", "filename": "v1.png"}],
                "drawing_transfer_history": history,
                "assignments": {"sales_assignee_user_ids": [sales.id],
                                "drawing_assignee_user_ids": [drafter.id]},
            },
        )
        s.add(order)
        s.commit()
        return order.id, (sales.id, sales.username, sales.role)
    finally:
        s.close()


def _hold_and_write(pg_engine, order_id, mutate, started, a_read):
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
        if a_read is not None:
            assert a_read.wait(10.0), "A 가 읽지 않았다"
        else:
            time.sleep(_HOLD_SECONDS)
        s.commit()
    finally:
        s.close()


def _call(app, user, url, body, out, method="post"):
    client = app.test_client()
    uid, username, role = user
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, username, role
    t0 = time.monotonic()
    resp = getattr(client, method)(url, json=body)
    out["elapsed"] = time.monotonic() - t0
    out["status"], out["json"] = resp.status_code, resp.get_json()


def _race(pg_engine, app, order_id, mutate_b, user_a, url, body, a_read=None, method="post"):
    started = threading.Event()
    tb = threading.Thread(target=_hold_and_write, args=(pg_engine, order_id, mutate_b, started, a_read))
    tb.start()
    assert started.wait(5.0)
    out: dict = {}
    ta = threading.Thread(target=_call, args=(app, user_a, url, body, out, method))
    ta.start()
    ta.join(20.0)
    tb.join(20.0)
    assert "status" in out, "라우트 A 가 끝나지 않았다"
    return out


def _final(pg_engine, order_id):
    s = _session(pg_engine)
    try:
        o = s.query(Order).filter(Order.id == order_id).one()
        return dict(o.structured_data), int(o.mutation_version)
    finally:
        s.close()


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_edit_waits_for_concurrent_revision_check(pg_engine, pg_app, monkeypatch, mode):
    history = [
        {"action": "TRANSFER", "transferred_at": "2026-09-28 10:00:00", "files": []},
        {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "원래 요청", "files": [],
         "source": "customer"},
    ]
    oid, sales = _seed(pg_engine, drawing_status="RETURNED", history=history)
    a_read = None
    if mode == "plain":
        a_read = threading.Event()

        def _plain_fetch(db, order_id):
            row = db.query(Order).filter(Order.id == order_id).first()
            if row is not None:
                _ = row.structured_data
            a_read.set()
            return row

        monkeypatch.setattr(revision_api, "lock_order_row", _plain_fetch)

    def _b_check(sd):
        sd["drawing_transfer_history"][-1]["review_check"] = {"checked": True, "checked_by_name": "도면"}

    out = _race(pg_engine, pg_app, oid, _b_check, sales,
                f"/api/orders/{oid}/request-revision/edit", {"note": "고친 요청"}, a_read)
    sd, _version = _final(pg_engine, oid)
    last = sd["drawing_transfer_history"][-1]
    if mode == "plain":
        # 음성 대조: 체크 전 dict 를 보고 고쳐 되써서 B 의 반영 체크가 사라진다.
        assert out["status"] == 200, out
        assert last["note"] == "고친 요청" and not (last.get("review_check") or {}).get("checked"), last
        return
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert out["status"] == 409 and out["json"]["error"] == "REVISION_ALREADY_CHECKED", out
    assert last["note"] == "원래 요청" and last["review_check"]["checked"] is True


@pytest.mark.parametrize("path", ["send-alimtalk", "send-sms"])
@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_share_history_write_waits_for_concurrent_drawing_write(pg_engine, pg_app, monkeypatch, mode, path):
    history = [{"action": "TRANSFER", "transferred_at": "2026-09-28 10:00:00", "files": []}]
    oid, sales = _seed(pg_engine, drawing_status="TRANSFERRED", history=history)
    for name in ("SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD", "SOLAPI_SENDER_PHONE", "SOLAPI_SENDER_FALLBACK_HAUD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SOLAPI_PF_ID_HAUD", "PF-HAUD")
    monkeypatch.setenv("SOLAPI_TEMPLATE_SHARE_ID_HAUD", "TPL-HAUD")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_HAUD", "15660703")
    monkeypatch.setattr(ka, "_solapi_send", lambda **k: "ATA-1")
    monkeypatch.setattr(ka, "_solapi_send_text", lambda **k: "SMS-1")
    s = _session(pg_engine)
    try:
        row, token = osvc.create_share_token(s, oid, "drawing")
        s.commit()
        share_id = row.id
    finally:
        s.close()

    a_read = None
    if mode == "plain":
        a_read = threading.Event()
        real_record = ka.record_share_history
        monkeypatch.setattr(share_api, "lock_order_row", lambda db, order_id: None)

        def _record_after_stale_refresh(session, order, **kwargs):
            real_refresh = session.refresh

            def _refresh(obj, *a, **k):
                real_refresh(obj, *a, **k)
                _ = obj.structured_data
                a_read.set()  # B 는 A 가 옛 행을 다시 읽은 뒤에 커밋한다

            session.refresh = _refresh
            try:
                return real_record(session, order, **kwargs)
            finally:
                del session.refresh

        monkeypatch.setattr(ka, "record_share_history", _record_after_stale_refresh)

    def _b_revision(sd):
        sd["drawing_status"] = "RETURNED"
        sd["drawing_transfer_history"].append(
            {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "B", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_revision, sales,
                f"/api/share/{path}/{share_id}", {"token": token}, a_read)
    assert out["status"] == 200, out
    sd, _version = _final(pg_engine, oid)
    notes = [h.get("note") for h in sd["drawing_transfer_history"]]
    assert sd["alimtalk_share"]["share_id"] == share_id
    if mode == "plain":
        assert "B" not in notes, notes  # 음성 대조: 흔적 쓰기가 B 의 수정요청을 덮었다
        return
    assert "B" in notes and sd["drawing_status"] == "RETURNED", sd


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_inline_phone_save_waits_for_concurrent_drawing_write(pg_engine, pg_app, monkeypatch, mode):
    history = [{"action": "TRANSFER", "transferred_at": "2026-09-28 10:00:00", "files": []}]
    oid, sales = _seed(pg_engine, drawing_status="TRANSFERRED", history=history)
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "1")
    monkeypatch.delenv("FOMS_ALIMTALK_AUTO_ENABLED", raising=False)
    a_read = None
    if mode == "plain":
        a_read = threading.Event()

        def _plain_fetch(db, order_id):
            row = db.query(Order).filter(Order.id == order_id).first()
            if row is not None:
                _ = row.structured_data
            a_read.set()
            return row

        monkeypatch.setattr(structured_api, "lock_order_row", _plain_fetch)

    def _b_revision(sd):
        sd["drawing_status"] = "RETURNED"
        sd["drawing_transfer_history"].append(
            {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "B", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_revision, sales, f"/api/orders/{oid}/structured/fields",
                {"field": "parties.customer.phone", "value": "010-5555-6666"}, a_read, method="patch")
    assert out["status"] == 200, out
    sd, _version = _final(pg_engine, oid)
    notes = [h.get("note") for h in sd["drawing_transfer_history"]]
    assert sd["parties"]["customer"]["phone"] == "010-5555-6666"
    if mode == "plain":
        assert "B" not in notes, notes  # 음성 대조: 옛 dict 를 통째로 되써 B 의 수정요청이 사라졌다
        return
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert "B" in notes and sd["drawing_status"] == "RETURNED", sd
