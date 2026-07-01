"""Smoke tests for ChannelTalk Integration (Phase 0)."""

import foms.api.channel.channel_integration as channel_integration
from db import db_session
from models import Order, OrderAttachment, User
from foms.services.jobs import queue as queue_module
from werkzeug.security import generate_password_hash


class _FakeStorage:
    def get_download_url(self, storage_key, expires_in=3600):
        return f"https://cdn.example.com/{storage_key}?e={expires_in}"


def _login_admin(client, username="channel-admin", password="admin"):
    user = User(
        username=username,
        password=generate_password_hash(password),
        role="ADMIN",
        name="Channel Admin",
    )
    db_session.add(user)
    db_session.commit()
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return user


def test_channel_health_endpoint_exists(client):
    """GET /api/channel/health returns 200 or 503 depending on env vars."""
    r = client.get("/api/channel/health")
    assert r.status_code in (200, 503)
    data = r.get_json()
    assert "readiness" in data
    assert "environment" in data
    assert "flags" in data


def test_channel_admin_delivery_status_requires_auth(client):
    """GET /api/channel/admin/delivery-status requires authentication."""
    r = client.get("/api/channel/admin/delivery-status")
    assert r.status_code in (302, 401)


def test_channel_health_uses_runtime_worker_status(client, monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setenv("CHANNEL_PUSH_ENABLED", "true")
    monkeypatch.setattr(
        channel_integration,
        "get_rq_runtime_status",
        lambda: {"state": "reachable", "worker_count": 2},
    )

    r = client.get("/api/channel/health")

    assert r.status_code == 200
    data = r.get_json()
    assert data["readiness"] == "ready"
    assert data["queue"]["state"] == "reachable"
    assert data["queue"]["worker_count"] == 2


def test_channel_health_returns_json_when_runtime_probe_fails(client, monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")

    def _raise_probe():
        raise RuntimeError("worker probe failed")

    monkeypatch.setattr(channel_integration, "get_rq_runtime_status", _raise_probe)

    r = client.get("/api/channel/health")

    assert r.status_code == 503
    assert r.is_json
    data = r.get_json()
    assert data["readiness"] == "fail"
    assert "CHANNEL_HEALTH_CHECK_FAILED" in data["flag_violations"]
    assert data["error"] == "worker probe failed"


def test_rq_runtime_status_uses_live_worker_count(monkeypatch):
    class DummyConnection:
        def ping(self):
            return True

    class DummyQueue:
        connection = DummyConnection()

    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr(queue_module, "get_rq_queue", lambda: DummyQueue())

    from rq import Worker

    def _fake_count(cls, connection=None, queue=None):
        assert connection is DummyQueue.connection
        assert queue.__class__ is DummyQueue
        return 3

    monkeypatch.setattr(Worker, "count", classmethod(_fake_count))

    status = queue_module.get_rq_runtime_status()

    assert status == {"state": "reachable", "worker_count": 3}


def test_rq_runtime_status_falls_back_to_worker_all(monkeypatch):
    class DummyConnection:
        def ping(self):
            return True

    class DummyQueue:
        connection = DummyConnection()

    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr(queue_module, "get_rq_queue", lambda: DummyQueue())

    from rq import Worker

    def _fake_count(cls, connection=None, queue=None):
        raise TypeError("count not supported")

    def _fake_all(cls, connection=None, job_class=None, queue_class=None, queue=None, serializer=None):
        return [object(), object()]

    monkeypatch.setattr(Worker, "count", classmethod(_fake_count))
    monkeypatch.setattr(Worker, "all", classmethod(_fake_all))

    status = queue_module.get_rq_runtime_status()

    assert status == {"state": "reachable", "worker_count": 2}


def test_push_manual_builds_image_and_video_files_and_dispatches(client, monkeypatch):
    """수동 푸쉬 API는 첨부 URL/MIME을 모아 dispatch_order_event('manual')로 전달한다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-1")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())

    captured = {}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["event_type"] = event_type
        captured["data"] = data
        captured["raise_on_error"] = raise_on_error
        return {"success": True, "message_id": "msg-manual-1"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)

    order = Order(
        received_date="2026-03-27",
        customer_name="Manual Push",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add_all(
        [
            OrderAttachment(
                order_id=order.id,
                filename="photo.jpg",
                file_type="image",
                storage_key="orders/1/photo.jpg",
            ),
            OrderAttachment(
                order_id=order.id,
                filename="clip.mp4",
                file_type="video",
                storage_key="orders/1/clip.mp4",
            ),
        ]
    )
    db_session.commit()
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "text": "발주방 변환 텍스트"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["files_count"] == 2
    assert captured["event_type"] == "manual"
    assert captured["raise_on_error"] is True
    assert captured["data"]["text"] == "발주방 변환 텍스트"
    assert captured["data"]["pushed_by_name"] == "Channel Admin"
    assert len(captured["data"]["files"]) == 2
    assert captured["data"]["files"][0]["mime"] == "image/jpeg"
    assert captured["data"]["files"][1]["mime"] == "video/mp4"
    assert captured["data"]["files"][0]["url"].endswith("orders/1/photo.jpg?e=3600")

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["channeltalk_push"]["pushed"] is True
    assert saved.structured_data["channeltalk_push"]["message_id"] == "msg-manual-1"


def test_push_manual_drawing_kind_filters_drawing_attachments_and_routes_drawing_group(client, monkeypatch):
    """발주 PUSH(push_kind=drawing)는 도면 첨부만 골라 도면 그룹으로 dispatch한다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-measure")
    monkeypatch.setenv("CHANNEL_GROUP_DRAWING", "group-draw")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())

    captured = {}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["data"] = data
        return {"success": True, "message_id": "msg-draw-1"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)

    order = Order(
        received_date="2026-03-27",
        customer_name="Drawing Push",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add_all(
        [
            OrderAttachment(
                order_id=order.id,
                filename="measure.jpg",
                file_type="image",
                category="measurement",
                storage_key="orders/1/measure.jpg",
            ),
            OrderAttachment(
                order_id=order.id,
                filename="plan.png",
                file_type="image",
                category="drawing",
                storage_key="orders/1/plan.png",
            ),
        ]
    )
    db_session.commit()
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "text": "도면 발주 텍스트", "push_kind": "drawing"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    # 도면 첨부 1건만 포함 (실측 제외)
    assert body["files_count"] == 1
    assert captured["data"]["push_kind"] == "drawing"
    assert len(captured["data"]["files"]) == 1
    assert captured["data"]["files"][0]["url"].endswith("orders/1/plan.png?e=3600")

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    # 도면 이력은 별도 키에 저장, 실측 이력 키는 생성되지 않는다.
    assert saved.structured_data["channeltalk_push_drawing"]["pushed"] is True
    assert "channeltalk_push" not in saved.structured_data


def test_push_manual_rejects_unknown_push_kind(client, monkeypatch):
    _login_admin(client)
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)

    order = Order(
        received_date="2026-03-27",
        customer_name="Bad Kind",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order.id, "text": "x", "push_kind": "bogus"},
    )

    assert response.status_code == 400


def test_push_manual_resend_requires_change_note(client, monkeypatch):
    """재전송(prev pushed) 시 change_note 없으면 400."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-1")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())
    monkeypatch.setattr(
        channel_integration,
        "dispatch_order_event",
        lambda event_type, data, raise_on_error=False: {"success": True, "message_id": "msg-1"},
    )

    order = Order(
        received_date="2026-03-27",
        customer_name="Resend Gate",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        structured_data={"channeltalk_push": {"pushed": True, "message_id": "old"}},
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order.id, "text": "고객명 : 테스트"},
    )

    assert response.status_code == 400
    assert "변경 내용" in response.get_json()["message"]


def test_push_manual_resend_stores_change_log_and_dispatches_note(client, monkeypatch):
    """재전송 시 change_note를 dispatch에 전달하고 change_log에 저장한다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-1")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())

    captured = {}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["data"] = data
        return {"success": True, "message_id": "msg-resend-1"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)

    order = Order(
        received_date="2026-03-27",
        customer_name="Resend OK",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        structured_data={"channeltalk_push": {"pushed": True, "message_id": "old"}},
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={
            "order_id": order_id,
            "text": "고객명 : 테스트",
            "change_note": "손잡이 오기재 정정",
        },
    )

    assert response.status_code == 200
    assert captured["data"]["is_retry"] is True
    assert captured["data"]["change_note"] == "손잡이 오기재 정정"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    log = saved.structured_data["channeltalk_push"]["change_log"]
    assert len(log) == 1
    assert log[0]["note"] == "손잡이 오기재 정정"
    assert log[0]["message_id"] == "msg-resend-1"

def test_payment_confirm_does_not_create_channel_delivery_log(client):
    """예약금/잔금 토글 API는 ChannelTalk outbox를 생성하지 않는다."""
    user = User(
        username="channel-admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        name="Channel Admin",
    )
    db_session.add(user)
    db_session.commit()

    login_response = client.post(
        "/login",
        data={"username": "channel-admin", "password": "admin"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    order = Order(
        received_date="2026-03-27",
        customer_name="Tester",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    r = client.post(
        f"/api/orders/{order_id}/payment-confirm",
        json={"type": "deposit", "confirmed": True},
    )

    assert r.status_code == 200
    body = r.get_json()
    assert body["payment"]["deposit_confirmed"] is True
    from models import ChannelDeliveryLog

    assert (
        db_session.query(ChannelDeliveryLog)
        .filter(ChannelDeliveryLog.order_id == order_id)
        .count()
        == 0
    )
