"""첨부 삭제의 도면 보호 + 파일 보존 휴지통 복구(2b, SPEC §4.3.6).

* 지금 전달된 도면(``drawing_current_files``)의 첨부는 첨부 탭에서 지울 수 없다 → 409 DRAWING_IN_USE.
* 이력에만 남은 교체된 옛 도면·참고사진은 행만 휴지통으로 보내고 파일은 남긴다
  (outbox 0, ``ATTACHMENT_DELETED`` 이벤트에 ``file_retained: true``).
* 복구 API 는 예약 행이 없더라도 ``file_retained`` 표시가 있고 파일이 있으면 되살린다.
  파일이 없으면 사실대로 409, 표시가 없으면 지금처럼 409.
"""
from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest

import foms.api.files.order_routes as order_routes
import foms.services.storage_delete_handler as handler_mod
from db import db_session
from foms.services.attachment_visibility import include_deleted
from foms.services.storage_delete_handler import handle_storage_delete
from models import DomainSideEffectOutbox, Order, OrderAttachment, OrderEvent, User

_n = itertools.count(1)


class _Storage:
    def __init__(self, existing=()):
        self.existing = set(existing)

    def object_exists(self, key):
        return key in self.existing

    def delete_file(self, key):  # pragma: no cover - 호출되면 계약 위반
        raise AssertionError(f"첨부 삭제·복구는 R2 를 동기 삭제하면 안 된다({key!r})")


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(order_routes, "get_storage", lambda: fake)
    return fake


def _admin():
    n = next(_n)
    u = User(username=f"adg-{n}", password="x", role="ADMIN", name=f"adg{n}", is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


def _client(app, user):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = user.id
    return c


def _order_with_drawings():
    o = Order(received_date="2026-09-29", customer_name="첨부도면", phone="010", address="서울",
              product="장", status="DRAWING", is_erp_order=True, structured_data={})
    db_session.add(o)
    db_session.commit()
    cur = f"orders/{o.id}/drawing/current.png"
    old = f"orders/{o.id}/drawing/old.png"
    o.structured_data = {
        "drawing_status": "TRANSFERRED",
        "drawing_current_files": [{"key": cur}],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "files": [{"key": old}], "previous_current_files": []},
            {"action": "TRANSFER", "files": [{"key": cur}], "previous_current_files": [{"key": old}],
             "mode": "REPLACE"},
        ],
    }
    db_session.commit()
    return o.id, cur, old


def _att(oid, key, *, category="drawing", thumb=True):
    a = OrderAttachment(order_id=oid, filename=key.rsplit("/", 1)[-1], file_type="image",
                        category=category, file_size=1, storage_key=key,
                        thumbnail_key=(key.rsplit("/", 1)[0] + "/thumb_" + key.rsplit("/", 1)[1]
                                       if thumb else None))
    db_session.add(a)
    db_session.commit()
    # 요청 뒤 세션이 닫혀 ORM 객체가 분리되므로 값만 들고 다닌다.
    return SimpleNamespace(id=a.id, storage_key=a.storage_key, thumbnail_key=a.thumbnail_key)


def _outbox():
    return db_session.query(DomainSideEffectOutbox).filter_by(effect_type="STORAGE_DELETE").all()


def _deleted_events(oid):
    return (db_session.query(OrderEvent)
            .filter_by(order_id=oid, event_type="ATTACHMENT_DELETED").order_by(OrderEvent.id).all())


def test_current_drawing_attachment_cannot_be_deleted(app, storage):
    user = _admin()
    oid, cur, _ = _order_with_drawings()
    att = _att(oid, cur)
    res = _client(app, user).delete(f"/api/orders/{oid}/attachments/{att.id}")
    assert res.status_code == 409, res.get_data(as_text=True)
    body = res.get_json()
    assert body["success"] is False and body["code"] == "DRAWING_IN_USE"
    assert "지금 전달된 도면" in body["message"]
    db_session.expire_all()
    assert db_session.get(OrderAttachment, att.id).deleted_at is None
    assert _outbox() == []


def test_old_drawing_row_is_trashed_but_file_retained(app, storage):
    user = _admin()
    oid, _, old = _order_with_drawings()
    att = _att(oid, old)
    res = _client(app, user).delete(f"/api/orders/{oid}/attachments/{att.id}")
    assert res.status_code == 200, res.get_data(as_text=True)
    assert _outbox() == [], "이력이 쓰는 옛 도면 파일을 삭제 예약했다"
    payload = _deleted_events(oid)[-1].payload
    assert payload["file_retained"] is True
    assert payload["retained_reason"] == "DRAWING_HISTORY"


def test_general_photo_is_purged_as_before(app, storage):
    user = _admin()
    oid, _, _ = _order_with_drawings()
    att = _att(oid, f"orders/{oid}/attachments/photo.jpg", category="measurement")
    res = _client(app, user).delete(f"/api/orders/{oid}/attachments/{att.id}")
    assert res.status_code == 200
    assert {r.payload["object_key"] for r in _outbox()} == {att.storage_key, att.thumbnail_key}
    assert "file_retained" not in _deleted_events(oid)[-1].payload


def test_retained_trash_row_restores_when_file_exists(app, storage):
    """예약 없는 ``file_retained`` 휴지통 행 → 복구 200."""
    user = _admin()
    oid, _, old = _order_with_drawings()
    att = _att(oid, old)
    c = _client(app, user)
    assert c.delete(f"/api/orders/{oid}/attachments/{att.id}").status_code == 200
    storage.existing.add(old)
    res = c.post(f"/api/orders/{oid}/attachments/{att.id}/restore")
    assert res.status_code == 200, res.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(OrderAttachment, att.id).deleted_at is None
    assert (db_session.query(OrderEvent)
            .filter_by(order_id=oid, event_type="ATTACHMENT_RESTORED").count()) == 1


def test_retained_trash_row_without_file_is_refused_truthfully(app, storage):
    user = _admin()
    oid, _, old = _order_with_drawings()
    att = _att(oid, old)
    c = _client(app, user)
    assert c.delete(f"/api/orders/{oid}/attachments/{att.id}").status_code == 200
    res = c.post(f"/api/orders/{oid}/attachments/{att.id}/restore")
    assert res.status_code == 409
    assert res.get_json()["message"] == "파일이 저장소에 없어 복구할 수 없습니다."
    db_session.expire_all()
    row = include_deleted(db_session.query(OrderAttachment).filter_by(id=att.id)).one()
    assert row.deleted_at is not None


def test_unmarked_trash_row_without_purge_rows_keeps_old_refusal(app, storage):
    """표시 없는 예약 0 행 → 기존 409 문구(지금 문구가 사실)."""
    user = _admin()
    oid, _, _ = _order_with_drawings()
    att = _att(oid, f"orders/{oid}/attachments/p.jpg", category="measurement")
    c = _client(app, user)
    assert c.delete(f"/api/orders/{oid}/attachments/{att.id}").status_code == 200
    for row in _outbox():
        db_session.delete(row)  # 끝난 outbox 가 30일 뒤 정리된 모양
    db_session.commit()
    storage.existing.add(att.storage_key)
    res = c.post(f"/api/orders/{oid}/attachments/{att.id}/restore")
    assert res.status_code == 409
    assert "유예 기간이 지나" in res.get_json()["message"]


def _run_purges_as_worker(monkeypatch):
    """유예가 지나 worker 가 예약을 처리한 모양: 핸들러 실행 뒤 DONE. 실제로 지운 key 를 돌려준다."""
    deleted = []
    monkeypatch.setattr(handler_mod, "get_storage",
                        lambda: SimpleNamespace(delete_file=lambda k: deleted.append(k) or True))
    for row in _outbox():
        handle_storage_delete(row)
        row.status = "DONE"  # sidefx_worker 의 finalize 와 같은 결과
    db_session.commit()
    return deleted


def test_purge_skipped_because_key_reused_restores_when_file_exists(app, storage, monkeypatch):
    """삭제 뒤 유예 안에 같은 key 를 다른 첨부 행이 다시 쓰면 핸들러가 건너뛴다(2b 리뷰 P3).

    파일이 남아 있으니 복구 API 가 '이미 삭제되었습니다' 라고 거짓 거절하면 안 된다 —
    건너뛴 사실을 보고 저장소를 확인해 되살린다. 끝난 예약 행도 지워 다시 지울 때 dedupe 가 풀린다.
    """
    user = _admin()
    oid, _, _ = _order_with_drawings()
    key = f"orders/{oid}/attachments/reuse.jpg"
    att = _att(oid, key, category="measurement")
    c = _client(app, user)
    assert c.delete(f"/api/orders/{oid}/attachments/{att.id}").status_code == 200
    _att(oid, key, category="measurement")  # 같은 본체·썸네일 key 를 쓰는 살아 있는 행
    assert _run_purges_as_worker(monkeypatch) == []
    storage.existing.add(key)
    res = c.post(f"/api/orders/{oid}/attachments/{att.id}/restore")
    assert res.status_code == 200, res.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(OrderAttachment, att.id).deleted_at is None
    assert _outbox() == []


def test_purge_partly_deleted_keeps_truthful_refusal(app, storage, monkeypatch):
    """썸네일은 실제로 지워졌으면(본체만 건너뜀) 복구는 지금처럼 거절한다."""
    user = _admin()
    oid, _, _ = _order_with_drawings()
    key = f"orders/{oid}/attachments/half.jpg"
    att = _att(oid, key, category="measurement")
    c = _client(app, user)
    assert c.delete(f"/api/orders/{oid}/attachments/{att.id}").status_code == 200
    _att(oid, key, category="measurement", thumb=False)  # 본체만 다시 쓴다
    assert _run_purges_as_worker(monkeypatch) == [att.thumbnail_key]
    storage.existing.add(key)
    res = c.post(f"/api/orders/{oid}/attachments/{att.id}/restore")
    assert res.status_code == 409
    assert "유예 기간이 지나" in res.get_json()["message"]
