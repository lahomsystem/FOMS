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
* 수령 확정(B) 대 전달 취소(A) — A 는 CONFIRMED 를 보고 400, B 의 확정이 남는다.
* 수정요청(B) 대 재전달(A) — A 는 반영 체크 안 된 RETURNED 를 보고 400.
* 반영 체크(B) 대 수정요청 취소(A) — 두 동작 모두 남는다.
* 수정요청(B) 대 주문 변경 확인 ack(A) — 두 동작 모두 남는다.
* 작업실 대기 전달의 스냅샷 쓰기 경합은 ``test_drawing_transfer_pending_snapshot_pg.py``.

음성 대조(``mode="plain"``): 라우트의 첫 조회를 잠금 도우미 대신 일반 조회로 바꾸면 같은
시나리오에서 B 의 쓰기가 사라진다(lost update)는 것을 **같은 테스트가** 단언한다 — 시나리오가
결함을 실제로 잡는다는 증거다. plain 모드에서 B 는 고정 시간 대신 **A 의 일반 조회가 끝났다는
신호**를 받은 뒤 커밋한다 — 느린 러너에서 A 가 B 커밋 뒤에 읽어 음성 대조가 흔들리지 않게.

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
import foms.api.drawing.erp_orders_drawing as drawing_api
import foms.api.drawing.erp_orders_revision as revision_api
import foms.platform.http as platform_http
from models import Order, User

_HOLD_SECONDS = 1.0
_SEQ = [0]


class _Storage:
    def delete_file(self, key):
        return True


def _arm_plain(monkeypatch, module, mode):
    """mode=plain 이면 ``module.lock_order_row`` 를 잠그지 않는 일반 조회로 바꾼다.

    돌려주는 Event 는 A 가 일반 조회로 structured_data 까지 읽은 순간 켜진다 — B 는 이것을
    기다린 뒤 커밋하므로 "A 가 B 커밋 전에 읽었다"가 시간과 무관하게 성립한다. lock 모드면 None.
    """
    if mode != "plain":
        return None
    a_read = threading.Event()

    def _plain_fetch(db, order_id):
        row = db.query(Order).filter(Order.id == order_id).first()
        if row is not None:
            _ = row.structured_data  # 판정에 쓸 값을 지금 읽어 둔다(지연 로딩 금지)
        a_read.set()
        return row

    monkeypatch.setattr(module, "lock_order_row", _plain_fetch)
    return a_read


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


def _hold_and_write(pg_engine, order_id, mutate, started, done, a_read=None):
    """연결 B: 행을 FOR UPDATE 로 쥐고 도면 쓰기(+버전) 뒤 커밋 전 대기 → 커밋.

    ``a_read`` 가 있으면(plain) A 의 일반 조회 신호까지, 없으면(lock) 고정 시간 기다린다.
    """
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
            assert a_read.wait(10.0), "A 가 일반 조회를 하지 않았다"
        else:
            time.sleep(_HOLD_SECONDS)
        s.commit()
    finally:
        s.close()
        done.set()


def _race(pg_engine, app, order_id, mutate_b, user_a, url, body, a_read=None):
    """B 가 잠금을 쥔 동안 A(실제 라우트)를 부른다. (A 응답 상태, A 응답 JSON, A 대기 시간)."""
    started, done = threading.Event(), threading.Event()
    tb = threading.Thread(target=_hold_and_write,
                          args=(pg_engine, order_id, mutate_b, started, done, a_read))
    tb.start()
    assert started.wait(5.0), "연결 B 가 잠금을 잡지 못했다"
    out = {}

    ta = threading.Thread(target=_call_route, args=(app, user_a, url, body, out))
    ta.start()
    ta.join(15.0)
    tb.join(15.0)
    assert "status" in out, "라우트 A 가 끝나지 않았다"
    return out


def _call_route(app, user_a, url, body, out):
    """스레드 A: 로그인 세션을 심고 실제 라우트를 POST 한다. 결과는 ``out`` 에 담는다."""
    client = app.test_client()
    uid, username, role = user_a
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, username, role
    t0 = time.monotonic()
    resp = client.post(url, json=body)
    out["elapsed"] = time.monotonic() - t0
    out["status"], out["json"] = resp.status_code, resp.get_json()


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
    a_read = _arm_plain(monkeypatch, revision_api, mode)

    def _b_revision(sd):
        sd["drawing_status"] = "RETURNED"
        sd["drawing_transfer_history"].append(
            {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "B", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_revision, drafter,
                f"/api/orders/{oid}/request-revision-check",
                {"request_at": "2026-09-21 10:00:00", "checked": True}, a_read)
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
    a_read = _arm_plain(monkeypatch, revision_api, mode)

    def _b_confirm(sd):
        sd["drawing_status"] = "CONFIRMED"
        sd["drawing_transfer_history"].append(
            {"action": "CONFIRM_RECEIPT", "at": "2026-09-29 09:00:00", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_confirm, sales,
                f"/api/orders/{oid}/request-revision", {"note": "A 수정"}, a_read)
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
    a_read = _arm_plain(monkeypatch, draftsman_api, mode)

    def _b_revision(sd):
        sd["drawing_status"] = "RETURNED"
        sd["drawing_transfer_history"].append(
            {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "B", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_revision, sales,
                f"/api/orders/{oid}/confirm-drawing-receipt", {}, a_read)
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


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_cancel_transfer_waits_for_concurrent_receipt(pg_engine, pg_app, monkeypatch, mode):
    """B=수령 확정(CONFIRMED) · A=전달 취소 → A 는 CONFIRMED 를 보고 400, B 의 확정이 남는다.

    전달 취소는 엔진을 타지 않고 같은 잠금 아래에서 버전을 직접 올린다 — 첫 조회 잠금이 lost
    update 를 막는 유일한 장치다.
    """
    history = [{"action": "TRANSFER", "transferred_at": "2026-09-28 10:00:00", "files": [],
                "previous_current_files": []}]
    oid, _sales, drafter = _seed(pg_engine, stage="CONFIRM", drawing_status="TRANSFERRED",
                                 history=history)
    a_read = _arm_plain(monkeypatch, drawing_api, mode)

    def _b_confirm(sd):
        sd["drawing_status"] = "CONFIRMED"
        sd["drawing_transfer_history"].append(
            {"action": "CONFIRM_RECEIPT", "at": "2026-09-29 09:00:00", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_confirm, drafter,
                f"/api/orders/{oid}/cancel-transfer", {}, a_read)
    sd, version = _final(pg_engine, oid)
    if mode == "plain":
        # 음성 대조: 옛 TRANSFERRED 로 판정해 취소하고, B 의 확정을 지운다.
        assert out["status"] == 200, out
        assert "CONFIRM_RECEIPT" not in _actions(sd) and sd["drawing_status"] == "PENDING", sd
        return
    assert out["status"] == 400, out
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert _actions(sd) == ["TRANSFER", "CONFIRM_RECEIPT"]
    assert sd["drawing_status"] == "CONFIRMED"
    assert version == 2  # B 만 올렸다


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_retransfer_waits_for_concurrent_revision_request(pg_engine, pg_app, monkeypatch, mode):
    """B=수정요청(RETURNED, 반영 체크 전) · A=도면 전달 → A 는 반영 체크 안 된 요청을 보고 400."""
    history = [{"action": "TRANSFER", "transferred_at": "2026-09-28 10:00:00", "files": []}]
    oid, _sales, drafter = _seed(pg_engine, stage="CONFIRM", drawing_status="TRANSFERRED",
                                 history=history)
    a_read = _arm_plain(monkeypatch, drawing_api, mode)

    def _b_revision(sd):
        sd["drawing_status"] = "RETURNED"
        sd["drawing_transfer_history"].append(
            {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "B", "files": []})

    key = f"orders/{oid}/drawing_wizard/exports/v2.png"
    out = _race(pg_engine, pg_app, oid, _b_revision, drafter,
                f"/api/orders/{oid}/transfer-drawing",
                {"files": [{"key": key, "filename": "v2.png"}]}, a_read)
    sd, version = _final(pg_engine, oid)
    if mode == "plain":
        # 음성 대조: 옛 TRANSFERRED 로 판정해 전달하고, B 의 수정요청을 지운다.
        assert out["status"] == 200, out
        assert "REQUEST_REVISION" not in _actions(sd), _actions(sd)
        return
    assert out["status"] == 400, out
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert _actions(sd) == ["TRANSFER", "REQUEST_REVISION"]
    assert sd["drawing_status"] == "RETURNED"
    assert version == 2


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_cancel_revision_waits_for_concurrent_revision_check(pg_engine, pg_app, monkeypatch, mode):
    """B=옛 수정요청 반영 체크 · A=최신 수정요청 취소 → 두 동작 모두 남는다."""
    history = [
        {"action": "TRANSFER", "transferred_at": "2026-09-20 10:00:00", "files": []},
        {"action": "REQUEST_REVISION", "at": "2026-09-21 10:00:00", "note": "옛", "files": []},
        {"action": "TRANSFER", "transferred_at": "2026-09-22 10:00:00", "files": []},
        {"action": "REQUEST_REVISION", "at": "2026-09-23 10:00:00", "note": "새", "files": []},
    ]
    oid, sales, _drafter = _seed(pg_engine, stage="CONFIRM", drawing_status="RETURNED",
                                 history=history)
    a_read = _arm_plain(monkeypatch, revision_api, mode)

    def _b_check(sd):
        sd["drawing_transfer_history"][1]["review_check"] = {"checked": True, "at": "B"}

    out = _race(pg_engine, pg_app, oid, _b_check, sales,
                f"/api/orders/{oid}/cancel-revision-request", {}, a_read)
    assert out["status"] == 200, out
    sd, version = _final(pg_engine, oid)
    notes = [h.get("note") for h in sd["drawing_transfer_history"]]
    assert "새" not in notes, notes  # A 의 취소는 두 모드 모두 반영된다
    if mode == "plain":
        # 음성 대조: 옛 dict 를 되써서 B 의 반영 체크가 사라진다.
        assert "review_check" not in sd["drawing_transfer_history"][1], sd
        return
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert sd["drawing_transfer_history"][1]["review_check"]["checked"] is True
    assert sd["drawing_status"] == "TRANSFERRED"
    assert version == 3


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_ack_order_change_waits_for_concurrent_revision_request(pg_engine, pg_app, monkeypatch,
                                                                mode):
    """B=수정요청 · A=주문 변경 확인(ack) → 두 동작 모두 남고 버전은 둘 다 올린다.

    ack 는 확인 표시 계산 자체를 엔진 콜백 안에서(엔진이 다시 잠가 읽은 최신 행 위에서) 하므로
    첫 조회를 일반 조회로 바꿔도(plain) B 가 남는다 — 첫 조회는 "바꿀 것이 있나" 판정에만 쓴다.
    이 경로의 음성 대조는 고치기 전 코드(db.get 후 잠금·버전 없이 통째로 되쓰기)로 돌려 lock
    모드가 빨갛던 것이다(B 의 REQUEST_REVISION 이 사라짐).
    """
    history = [
        {"action": "TRANSFER", "transferred_at": "2026-09-28 10:00:00", "files": []},
        {"action": "ERP_ORDER_CHANGED", "at": "2026-09-28 11:00:00", "acked": False,
         "note": "수량 변경"},
    ]
    oid, _sales, drafter = _seed(pg_engine, stage="CONFIRM", drawing_status="TRANSFERRED",
                                 history=history)
    a_read = _arm_plain(monkeypatch, revision_api, mode)

    def _b_revision(sd):
        sd["drawing_status"] = "RETURNED"
        sd["drawing_transfer_history"].append(
            {"action": "REQUEST_REVISION", "at": "2026-09-29 09:00:00", "note": "B", "files": []})

    out = _race(pg_engine, pg_app, oid, _b_revision, drafter,
                f"/api/orders/{oid}/drawing/ack-order-change", {}, a_read)
    assert out["status"] == 200, out
    sd, version = _final(pg_engine, oid)
    if mode == "lock":
        assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert _actions(sd) == ["TRANSFER", "ERP_ORDER_CHANGED", "REQUEST_REVISION"]
    assert sd["drawing_transfer_history"][1]["acked"] is True
    assert sd["drawing_status"] == "RETURNED"
    assert version == 3

