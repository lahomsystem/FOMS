"""CHANNEL-WRITER-01: 채널톡 push 결과 metadata typed command 계약 테스트 (red→green).

drawing/estimate/measurement push 의 send result+metadata 기록을 REV-00
``execute_order_mutation`` 한 transaction 으로 원자화한다: ``structured_data`` 이력 +
``mutation_version`` bump + idempotency receipt + ``OrderEvent`` 1 + side-effect outbox
**dedupe** enqueue. 증명하는 것:

* push send result → Order version++ · receipt 1 · OrderEvent 1 · outbox 1 (measurement/estimate).
* 재시도(같은 send 결과 재기록) → receipt replay + outbox dedupe 로 event/history **정확히 1**.
* metadata(message_id/group_id/push_kind)가 event·outbox·structured_data 이력에 정확 기록.
* auth/transport provider(dispatch_order_event) 무변경 — 전송 계약(event_type='manual',
  raise_on_error=True)은 그대로이고 recording 은 additive(대조).

domains 스위트는 in-memory SQLite 로 돈다(test_call_log/test_channel_integration_smoke 준용).
"""

import io

import pytest
from werkzeug.security import generate_password_hash

import foms.api.channel.channel_integration as channel_integration
from db import db_session
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderEvent,
    OrderMutationReceipt,
    User,
)

_PUSH_EVENT_TYPE = "CHANNELTALK_PUSH"
_PUSH_POLICY_ID = "CHANNEL_PUSH"
_PUSH_EFFECT_TYPE = "CHANNEL_PUSH_RECORDED"


# --------------------------------------------------------------------------
# fake 스토리지 / 로그인 / 헬퍼 (smoke 테스트 패턴 재사용)
# --------------------------------------------------------------------------
class _FakeStorage:
    def get_download_url(self, storage_key, expires_in=3600):
        return f"https://cdn.example.com/{storage_key}?e={expires_in}"


class _FakeEstimateStorage:
    def __init__(self):
        self.uploaded = []
        self.deleted = []

    def upload_file(self, file_obj, filename, folder="uploads"):
        data = file_obj.read()
        self.uploaded.append({"filename": filename, "folder": folder, "size": len(data)})
        return {
            "success": True,
            "key": f"{folder}/{filename}",
            "url": f"https://cdn.example.com/{folder}/{filename}",
            "filename": filename,
        }

    def get_download_url(self, storage_key, expires_in=3600):
        return f"https://cdn.example.com/{storage_key}?e={expires_in}"

    def delete_file(self, storage_key):
        self.deleted.append(storage_key)
        return True


def _login_admin(client, username="cw-admin", password="admin"):
    user = User(
        username=username,
        password=generate_password_hash(password),
        role="ADMIN",
        name="Channel Writer Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    uid = user.id
    resp = client.post(
        "/login", data={"username": username, "password": password}, follow_redirects=False
    )
    assert resp.status_code == 302
    return uid


def _make_user(username="cw-actor"):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        name="Actor",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _make_order(structured_data=None):
    order = Order(
        received_date="2026-07-24",
        customer_name="채널 대상",
        phone="010-1234-5678",
        address="Seoul",
        product="Wardrobe",
        structured_data=structured_data,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def _png_upload(content=b"\x89PNG\r\n\x1a\nfake-estimate-bytes"):
    return (io.BytesIO(content), "estimate.png", "image/png")


def _fake_dispatch_factory(message_id, captured=None, counter=None):
    def _fake_dispatch(event_type, data, raise_on_error=False):
        if captured is not None:
            captured["event_type"] = event_type
            captured["data"] = data
            captured["raise_on_error"] = raise_on_error
        if counter is not None:
            counter.append(1)
        return {"success": True, "message_id": message_id}

    return _fake_dispatch


# --------------------------------------------------------------------------
# 1) push send result → version++ · receipt 1 · OrderEvent 1 · outbox 1 (measurement)
# --------------------------------------------------------------------------
def test_push_manual_records_version_receipt_event_and_outbox(client, app, monkeypatch):
    """수동 push 성공 → mutation_version++ · receipt 1 · OrderEvent 1 · outbox 1 · metadata 정확."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-1")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())
    monkeypatch.setattr(
        channel_integration, "dispatch_order_event", _fake_dispatch_factory("msg-m-1")
    )

    oid = _make_order()
    before = _fresh(oid).mutation_version

    resp = client.post(
        "/api/channel/push-manual", json={"order_id": oid, "text": "발주방 변환 텍스트"}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True

    fresh = _fresh(oid)
    assert fresh.mutation_version == before + 1  # 정확히 1회 bump
    hist = fresh.structured_data["channeltalk_push"]
    assert hist["pushed"] is True
    assert hist["message_id"] == "msg-m-1"
    assert hist["group_id"] == "group-1"

    events = (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type=_PUSH_EVENT_TYPE)
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["message_id"] == "msg-m-1"
    assert events[0].payload["push_kind"] == "measurement"
    assert events[0].payload["group_id"] == "group-1"

    receipts = db_session.query(OrderMutationReceipt).filter_by(policy_id=_PUSH_POLICY_ID).all()
    assert len(receipts) == 1
    assert "resources" in receipts[0].response_body

    outbox = (
        db_session.query(DomainSideEffectOutbox)
        .filter_by(effect_type=_PUSH_EFFECT_TYPE)
        .all()
    )
    assert len(outbox) == 1
    assert outbox[0].source_domain == "ORDER_EVENT"
    assert outbox[0].order_event_id == events[0].id
    assert outbox[0].dedupe_key == f"{_PUSH_EFFECT_TYPE}:measurement:{oid}:msg-m-1"
    assert outbox[0].payload["message_id"] == "msg-m-1"


# --------------------------------------------------------------------------
# 2) 견적서 push send result → version++ · receipt 1 · OrderEvent 1 · outbox 1
# --------------------------------------------------------------------------
def test_push_estimate_records_version_receipt_event_and_outbox(client, app, monkeypatch):
    """견적서 push 성공 → 별도 이력 키 + version++ · receipt 1 · OrderEvent 1 · outbox 1."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_ESTIMATE", "group-estimate")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeEstimateStorage())
    monkeypatch.setattr(
        channel_integration, "dispatch_order_event", _fake_dispatch_factory("msg-est-1")
    )

    oid = _make_order()
    before = _fresh(oid).mutation_version

    resp = client.post(
        "/api/channel/push-estimate",
        data={"order_id": str(oid), "image": _png_upload()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    fresh = _fresh(oid)
    assert fresh.mutation_version == before + 1
    hist = fresh.structured_data["channeltalk_push_estimate"]
    assert hist["pushed"] is True
    assert hist["message_id"] == "msg-est-1"
    assert hist["group_id"] == "group-estimate"
    # 견적서 이력은 영발/발주 이력과 분리된 키다.
    assert "channeltalk_push" not in fresh.structured_data
    assert "channeltalk_push_drawing" not in fresh.structured_data

    assert (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type=_PUSH_EVENT_TYPE)
        .count()
        == 1
    )
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=_PUSH_POLICY_ID).count() == 1
    outbox = db_session.query(DomainSideEffectOutbox).filter_by(effect_type=_PUSH_EFFECT_TYPE).all()
    assert len(outbox) == 1
    assert outbox[0].payload["push_kind"] == "estimate"


# --------------------------------------------------------------------------
# 3) 재시도(같은 send 결과 재기록) → dedupe 로 event/history 정확히 1 (중복 0)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "history_key,push_kind,group_id",
    [
        ("channeltalk_push", "measurement", "group-1"),
        ("channeltalk_push_drawing", "drawing", "group-draw"),
        ("channeltalk_push_estimate", "estimate", "group-estimate"),
    ],
)
def test_recording_retry_same_send_dedupes_to_one(app, history_key, push_kind, group_id):
    """같은 send 결과(message_id)를 두 번 기록해도 receipt replay + dedupe 로 정확히 1."""
    uid = _make_user(username=f"cw-actor-{push_kind}")
    oid = _make_order()
    before = _fresh(oid).mutation_version
    result = {"success": True, "message_id": "msg-dedupe-1"}

    def _record():
        order = db_session.query(Order).filter_by(id=oid).first()
        return channel_integration._record_push_metadata(
            db_session,
            order=order,
            history_key=history_key,
            push_kind=push_kind,
            group_id=group_id,
            result=result,
            is_resend=False,
            change_note="",
            pushed_by_name="Tester",
            actor_user_id=uid,
        )

    first = _record()
    second = _record()  # 같은 push 재시도

    assert first.replayed is False
    assert second.replayed is True  # idempotency replay — business write 미수행

    fresh = _fresh(oid)
    assert fresh.mutation_version == before + 1  # 1회만 bump
    assert fresh.structured_data[history_key]["message_id"] == "msg-dedupe-1"

    assert (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type=_PUSH_EVENT_TYPE)
        .count()
        == 1
    )
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=_PUSH_POLICY_ID).count() == 1
    assert (
        db_session.query(DomainSideEffectOutbox).filter_by(effect_type=_PUSH_EFFECT_TYPE).count()
        == 1
    )


# --------------------------------------------------------------------------
# 4) auth/transport provider 무변경 — 전송 계약 그대로, recording 은 additive (대조)
# --------------------------------------------------------------------------
def test_transport_provider_contract_unchanged(client, app, monkeypatch):
    """dispatch_order_event 전송 계약(event_type='manual', raise_on_error=True) 무변경 + 단일 호출."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-1")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())

    captured, counter = {}, []
    monkeypatch.setattr(
        channel_integration,
        "dispatch_order_event",
        _fake_dispatch_factory("msg-x", captured=captured, counter=counter),
    )

    oid = _make_order()
    resp = client.post("/api/channel/push-manual", json={"order_id": oid, "text": "텍스트"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    # 전송 provider 계약은 그대로다(변경 금지 경계).
    assert captured["event_type"] == "manual"
    assert captured["raise_on_error"] is True
    assert captured["data"]["push_kind"] == "measurement"
    assert "files" in captured["data"]
    assert len(counter) == 1  # push 1건 = provider 1회 호출(중복 전송 없음)

    # recording 은 additive: 전송과 별개로 receipt/event 가 생겼다.
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=_PUSH_POLICY_ID).count() == 1
    assert (
        db_session.query(OrderEvent).filter_by(order_id=oid, event_type=_PUSH_EVENT_TYPE).count()
        == 1
    )


# --------------------------------------------------------------------------
# 5) 실제 재전송(별개 send) → 별개 OrderEvent + change_log 누적 (over-dedup 방지 대조)
# --------------------------------------------------------------------------
def test_genuine_resend_creates_distinct_event_and_appends_change_log(client, app, monkeypatch):
    """별개 send(다른 message_id, is_resend)는 event 2개 · change_log 누적 — 과도 dedupe 아님."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-1")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())

    oid = _make_order()

    monkeypatch.setattr(
        channel_integration, "dispatch_order_event", _fake_dispatch_factory("msg-A")
    )
    r1 = client.post("/api/channel/push-manual", json={"order_id": oid, "text": "1차"})
    assert r1.status_code == 200, r1.get_data(as_text=True)

    monkeypatch.setattr(
        channel_integration, "dispatch_order_event", _fake_dispatch_factory("msg-B")
    )
    r2 = client.post(
        "/api/channel/push-manual",
        json={"order_id": oid, "text": "2차", "change_note": "손잡이 정정"},
    )
    assert r2.status_code == 200, r2.get_data(as_text=True)

    fresh = _fresh(oid)
    hist = fresh.structured_data["channeltalk_push"]
    assert hist["message_id"] == "msg-B"
    assert hist["is_modified"] is True
    assert len(hist["change_log"]) == 1
    assert hist["change_log"][0]["note"] == "손잡이 정정"
    assert hist["change_log"][0]["message_id"] == "msg-B"

    # 별개 send 2건 = 별개 OrderEvent 2건(과도 dedupe 아님).
    assert (
        db_session.query(OrderEvent).filter_by(order_id=oid, event_type=_PUSH_EVENT_TYPE).count()
        == 2
    )
