"""PostgreSQL 두 세션 — 도면 마법사 부가 쓰기 3곳이 행 잠금 아래에서 판정·쓰기한다(2026-09-30).

시트 PNG 전달 대기 등록(POST sheet-png) · 전달 대기 삭제(DELETE pending/<sheet_id>) · 버전
스냅샷(POST version-snapshot) 은 예전에 잠금 없이 읽은 ``structured_data`` 를 통째로 되써서,
그 사이 커밋된 남의 도면 쓰기(전달·수정요청)를 지웠다(lost update). 지금은 첫 조회(또는
업로드 뒤 기록 직전 조회)를 ``lock_order_row`` 로 잠그고 ``execute_single_order_write`` 로
쓰며 버전을 1 올린다.

연결 B 가 주문 행을 ``FOR UPDATE`` 로 쥐고 수정요청 이력(REQUEST_REVISION)을 붙인 뒤 커밋
전에 기다리는 동안 실제 Flask 라우트(스레드 A)를 부른다.

* lock: A 는 B 커밋을 기다렸다가(경과 ≥ 보유시간 절반) B 의 이력 **위에** 자기 변경을
  얹는다 — 최종 sd 에 B 의 이력과 A 의 변경이 모두 있고 버전은 시작 +2.
* plain(음성 대조): ``wizard.lock_order_row`` 를 잠금 없는 조회로 바꾸면 A 는 B 커밋 전의
  옛 dict 로 계산해 통째로 되써서 B 의 이력이 사라진다. 엔진(``execute_order_mutation``)이
  잠금 전에 clean 객체를 비우고 최신 행을 다시 읽어도, 콜백이 재대입하는 dict 는 라우트가
  미리 만든 옛 것이라 손실을 못 막는다 — 이 대조가 그것을 보인다. B 는 A 의 일반 조회가
  끝났다는 신호를 받은 뒤 커밋한다(느린 러너에서도 대조가 흔들리지 않게).

실행: ``FOMS_TEST_DATABASE_URL`` 이 로컬 PG 를 가리킬 때만(없으면 conftest 가 skip).
"""
from __future__ import annotations

import copy
import io
import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.api.drawing.wizard as wizard_api
import foms.platform.http as platform_http
from models import Order, User

_HOLD_SECONDS = 1.0
_SEQ = [0]


class _FakeStorage:
    """업로드는 ``<folder>/<filename>`` key 를 돌려주고, 삭제는 기록만 한다."""

    def __init__(self):
        self.uploaded: list = []
        self.deleted: list = []

    def upload_file(self, file_obj, filename, folder):
        key = f"{folder}/{int(time.time() * 1000)}_{filename}"
        self.uploaded.append(key)
        return {"success": True, "key": key}

    def delete_file(self, key):
        self.deleted.append(key)
        return True


@pytest.fixture
def pg_app(pg_engine, monkeypatch):
    """전역 db_session 을 PG 엔진에 묶은 Flask 앱(테스트 끝에 원래 엔진으로 되돌린다)."""
    from app import app as flask_app
    from db import db_session, engine as default_engine

    db_session.remove()
    db_session.configure(bind=pg_engine)
    flask_app.config["TESTING"] = True
    monkeypatch.setattr(platform_http, "touch_last_seen", lambda user: False)
    storage = _FakeStorage()
    monkeypatch.setattr(wizard_api, "get_storage", lambda: storage)
    try:
        yield flask_app
    finally:
        db_session.remove()
        db_session.configure(bind=default_engine)


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _sheet(sheet_id, name):
    return {"id": sheet_id, "name": name, "form": {}, "objects": []}


def _seed(pg_engine):
    """도면팀 작업자 + 시트 2장·전달 대기 1건(s-1)·버전 1개를 가진 ERP 주문. (order_id, user, version)."""
    _SEQ[0] += 1
    tag = f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"
    s = _session(pg_engine)
    try:
        drafter = User(username=f"wl_d_{tag}", password=generate_password_hash("pw"),
                       role="STAFF", team="DRAWING", name="도면", is_active=True)
        s.add(drafter)
        s.flush()
        order = Order(
            received_date="2026-09-30", customer_name="마법사고객", phone="010-2473-6730",
            address="서울", product="붙박이장", status="DRAWING", is_erp_order=True,
            erp_stage_code="DRAWING", manager_name="영업", structured_data={},
        )
        s.add(order)
        s.flush()
        oid = order.id
        exports = f"orders/{oid}/drawing_wizard/exports"
        order.structured_data = {
            "workflow": {"stage": "DRAWING"},
            "drawing_status": "TRANSFERRED",
            "drawing_current_files": [{"key": f"{exports}/cur.png", "filename": "cur.png"}],
            "drawing_transfer_history": [
                {"action": "TRANSFER", "transferred_at": "2026-09-29 10:00:00", "files": []},
            ],
            "assignments": {"drawing_assignee_user_ids": [drafter.id]},
            "drawing_wizard": {
                "v": 1,
                "sheets": [_sheet("s-1", "도면 1"), _sheet("s-2", "도면 2")],
                "pending": {
                    "s-1": {"key": f"{exports}/1_s1.png", "filename": "s1.png",
                            "at": "2026-09-30 09:00", "sheet_name": "도면 1"},
                },
                "versions": [
                    {"v": 1, "sheet_id": "s-1", "sheet_name": "도면 1",
                     "key": f"orders/{oid}/drawing_wizard/versions/v1_s-1.json",
                     "at": "2026-09-29 10:00", "by_name": "도면"},
                ],
                "updated_at": "2026-09-30 09:00:00",
            },
        }
        flag_modified(order, "structured_data")
        s.commit()
        return oid, (drafter.id, drafter.username, drafter.role), int(order.mutation_version or 0)
    finally:
        s.close()


def _b_revision(sd):
    sd["drawing_status"] = "RETURNED"
    sd["drawing_transfer_history"].append(
        {"action": "REQUEST_REVISION", "at": "2026-09-30 10:00:00", "note": "B", "files": []})


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


def _call(app, user, method, url, kwargs_factory, out):
    client = app.test_client()
    uid, username, role = user
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, username, role
    t0 = time.monotonic()
    resp = getattr(client, method)(url, **kwargs_factory())
    out["elapsed"] = time.monotonic() - t0
    out["status"], out["json"] = resp.status_code, resp.get_json()


def _race(pg_engine, app, order_id, user_a, method, url, kwargs_factory, a_read=None):
    started = threading.Event()
    tb = threading.Thread(target=_hold_and_write,
                          args=(pg_engine, order_id, _b_revision, started, a_read))
    tb.start()
    assert started.wait(5.0)
    out: dict = {}
    ta = threading.Thread(target=_call, args=(app, user_a, method, url, kwargs_factory, out))
    ta.start()
    ta.join(20.0)
    tb.join(20.0)
    assert "status" in out, "라우트 A 가 끝나지 않았다"
    return out


def _final(pg_engine, order_id):
    s = _session(pg_engine)
    try:
        o = s.query(Order).filter(Order.id == order_id).one()
        return copy.deepcopy(o.structured_data), int(o.mutation_version)
    finally:
        s.close()


def _arm_plain(monkeypatch, mode):
    """mode=plain 이면 ``wizard.lock_order_row`` 를 잠그지 않는 일반 조회로 바꾸고 읽음 신호를 준다."""
    if mode != "plain":
        return None
    a_read = threading.Event()

    def _plain_fetch(db, order_id):
        row = db.query(Order).filter(Order.id == order_id).first()
        if row is not None:
            _ = row.structured_data  # 판정·계산에 쓸 값을 지금 읽어 둔다
        a_read.set()
        return row

    monkeypatch.setattr(wizard_api, "lock_order_row", _plain_fetch)
    return a_read


def _assert_outcome(out, sd, version, start_version, mode):
    notes = [h.get("note") for h in sd["drawing_transfer_history"]]
    assert out["status"] == 200, out
    assert version == start_version + 2, (version, start_version)
    if mode == "plain":
        # 음성 대조: A 가 B 커밋 전 dict 로 계산해 되써서 B 의 수정요청이 사라졌다.
        assert "B" not in notes and sd["drawing_status"] == "TRANSFERRED", sd
        return
    assert out["elapsed"] >= _HOLD_SECONDS * 0.5, out
    assert "B" in notes and sd["drawing_status"] == "RETURNED", sd


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_sheet_png_pending_write_waits_for_concurrent_drawing_write(pg_engine, pg_app, monkeypatch, mode):
    oid, user, start_version = _seed(pg_engine)
    a_read = _arm_plain(monkeypatch, mode)

    def _kwargs():
        return {
            "data": {"file": (io.BytesIO(b"\x89PNG\r\n\x1a\nfake"), "sheet2.png"),
                     "sheet_id": "s-2", "sheet_name": "도면 2"},
            "content_type": "multipart/form-data",
        }

    out = _race(pg_engine, pg_app, oid, user, "post",
                f"/api/orders/{oid}/drawing-wizard/sheet-png", _kwargs, a_read)
    sd, version = _final(pg_engine, oid)
    _assert_outcome(out, sd, version, start_version, mode)
    pending = sd["drawing_wizard"]["pending"]
    assert pending["s-2"]["key"] == out["json"]["data"]["key"], pending
    assert "s-1" in pending, pending


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_pending_delete_waits_for_concurrent_drawing_write(pg_engine, pg_app, monkeypatch, mode):
    oid, user, start_version = _seed(pg_engine)
    a_read = _arm_plain(monkeypatch, mode)
    out = _race(pg_engine, pg_app, oid, user, "delete",
                f"/api/orders/{oid}/drawing-wizard/pending/s-1", dict, a_read)
    sd, version = _final(pg_engine, oid)
    _assert_outcome(out, sd, version, start_version, mode)
    assert "s-1" not in (sd["drawing_wizard"].get("pending") or {}), sd["drawing_wizard"]
    # 시트 편집 상태는 보존된다.
    assert [x["id"] for x in sd["drawing_wizard"]["sheets"]] == ["s-1", "s-2"]


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_version_snapshot_waits_for_concurrent_drawing_write(pg_engine, pg_app, monkeypatch, mode):
    oid, user, start_version = _seed(pg_engine)
    a_read = _arm_plain(monkeypatch, mode)

    def _kwargs():
        return {"json": {"sheet": _sheet("s-2", "도면 2"), "sheet_id": "s-2", "sheet_name": "도면 2"}}

    out = _race(pg_engine, pg_app, oid, user, "post",
                f"/api/orders/{oid}/drawing-wizard/version-snapshot", _kwargs, a_read)
    sd, version = _final(pg_engine, oid)
    _assert_outcome(out, sd, version, start_version, mode)
    assert out["json"]["data"]["v"] == 2, out
    versions = sd["drawing_wizard"]["versions"]
    assert [p["v"] for p in versions] == [1, 2], versions
    assert versions[-1]["sheet_id"] == "s-2"
