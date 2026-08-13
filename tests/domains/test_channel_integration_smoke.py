"""Smoke tests for ChannelTalk Integration (Phase 0)."""

import io

import foms.api.channel.channel_integration as channel_integration
import foms.services.channel_policy as channel_policy
from db import db_session
from models import Order, OrderAttachment, User
from foms.services.jobs import queue as queue_module
from werkzeug.security import generate_password_hash


class _FakeStorage:
    def get_download_url(self, storage_key, expires_in=3600):
        return f"https://cdn.example.com/{storage_key}?e={expires_in}"


class _FakeEstimateStorage:
    """upload_file + get_download_url를 모두 지원하는 견적서 푸쉬용 fake 스토리지."""

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
    """ADMIN 세션 detail은 200/503 + readiness/environment/flags를 반환한다.

    OPS-ROUTE-01 이후 운영 detail은 ADMIN/MANAGER 세션 뒤에서만 노출된다
    (무인증 공개 응답은 coarse readiness만 → test_ops_route_containment.py).
    """
    _login_admin(client)
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
    _login_admin(client)
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
    _login_admin(client)
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


def test_push_manual_rejects_retired_group_before_dispatch(client, monkeypatch):
    """554075 방으로 라우팅되면 수동 PUSH 기능은 삭제 상태(410)로 끝난다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "554075")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)

    def _dispatch_should_not_run(event_type, data, raise_on_error=False):
        raise AssertionError("retired group must be blocked before dispatch")

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _dispatch_should_not_run)

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": 999999, "text": "전송 금지"},
    )

    assert response.status_code == 410
    body = response.get_json()
    assert body["success"] is False
    assert "554075" in body["message"]


def test_push_manual_rejects_retired_drawing_group_before_dispatch(client, monkeypatch):
    """발주 PUSH도 554075 방으로 라우팅되면 dispatch 전에 차단된다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_DRAWING", "554075")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)

    def _dispatch_should_not_run(event_type, data, raise_on_error=False):
        raise AssertionError("retired drawing group must be blocked before dispatch")

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _dispatch_should_not_run)

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": 999999, "text": "전송 금지", "push_kind": "drawing"},
    )

    assert response.status_code == 410
    body = response.get_json()
    assert body["success"] is False
    assert "554075" in body["message"]


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


def test_push_manual_as_kind_filters_as_attachments_and_routes_as_group(client, monkeypatch):
    """AS PUSH(push_kind=as)는 AS 첨부만 골라 AS 그룹으로 dispatch하고 별도 이력 키에 기록한다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-measure")
    monkeypatch.setenv("CHANNEL_GROUP_AS", "group-as")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())

    captured = {}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["data"] = data
        return {"success": True, "message_id": "msg-as-1"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)

    order = Order(
        received_date="2026-03-27",
        customer_name="AS Push",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        structured_data={
            "parties": {"customer": {"name": "AS Push", "phone": "010-0000-0000"}, "orderer": {"name": "숨고"}},
            "site": {"address_full": "Seoul"},
            "schedule": {"construction": {"date": "2026-08-14"}},
            "shipment": {"as_content": "문짝 처짐"},
        },
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
                storage_key="orders/2/measure.jpg",
            ),
            OrderAttachment(
                order_id=order.id,
                filename="as-defect.jpg",
                file_type="image",
                category="as",
                storage_key="orders/2/as-defect.jpg",
            ),
        ]
    )
    db_session.commit()
    order_id = order.id

    # 본문은 서버가 조립한다 — 클라이언트가 보낸 text 는 이 경로에서 무시된다.
    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "text": "무시되어야 하는 클라 본문", "push_kind": "as"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["files_count"] == 1
    assert captured["data"]["push_kind"] == "as"
    sent_text = captured["data"]["text"]
    assert "무시되어야 하는" not in sent_text
    assert "고객명 : AS Push" in sent_text
    assert "발주사 : 숨고" in sent_text
    assert "시공일 : 8월 14일" in sent_text
    assert "내용 : 문짝 처짐" in sent_text
    assert len(captured["data"]["files"]) == 1
    assert captured["data"]["files"][0]["url"].endswith("orders/2/as-defect.jpg?e=3600")

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["channeltalk_push_as"]["pushed"] is True
    assert "channeltalk_push" not in saved.structured_data
    assert "channeltalk_push_drawing" not in saved.structured_data


def test_push_manual_as_resend_marks_corrected_reception_as_modified(client, monkeypatch):
    """AS 재접수 후 재전송은 공통 [수정] 헤더와 AS 전용 변경 이력을 남긴다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_AS", "group-as")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())

    captured = {}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["data"] = data
        return {"success": True, "message_id": "msg-as-corrected"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)

    order = Order(
        received_date="2026-03-27",
        customer_name="AS Corrected",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        structured_data={
            "shipment": {"as_content": "문짝 처짐 위치를 우측 문으로 정정"},
            "channeltalk_push_as": {"pushed": True, "message_id": "msg-as-original"},
        },
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={
            "order_id": order_id,
            "push_kind": "as",
            "change_note": "AS 접수 위치 오기재 정정",
        },
    )

    assert response.status_code == 200
    assert captured["data"]["is_retry"] is True
    assert captured["data"]["change_note"] == "AS 접수 위치 오기재 정정"
    message = channel_policy.build_message_template("manual", captured["data"])
    assert message.startswith("[수정]\nAS 접수 위치 오기재 정정\n\n")
    assert "내용 : 문짝 처짐 위치를 우측 문으로 정정" in message

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    push_history = saved.structured_data["channeltalk_push_as"]
    assert push_history["is_modified"] is True
    assert push_history["change_log"][0]["note"] == "AS 접수 위치 오기재 정정"
    assert push_history["change_log"][0]["message_id"] == "msg-as-corrected"


def test_push_manual_as_kind_rejects_order_without_as_content(client, monkeypatch):
    """AS 접수 내용이 없으면 전송을 거부한다(내용 없는 AS 알림 방지)."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_AS", "group-as")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())

    def _fail_dispatch(event_type, data, raise_on_error=False):
        raise AssertionError("dispatch must not run without AS content")

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fail_dispatch)

    order = Order(
        received_date="2026-03-27",
        customer_name="No AS Content",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        structured_data={"parties": {"customer": {"name": "No AS Content"}}},
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order.id, "push_kind": "as"},
    )

    assert response.status_code == 400
    assert "AS 접수 내용이 없습니다" in response.get_json()["message"]


def test_routing_group_as_kind_uses_as_env(monkeypatch):
    """push_kind='as'는 CHANNEL_GROUP_AS(미설정 시 230351)로 라우팅된다."""
    monkeypatch.delenv("CHANNEL_GROUP_AS", raising=False)
    assert channel_policy.get_routing_group_id("manual", {"push_kind": "as"}) == "230351"

    monkeypatch.setenv("CHANNEL_GROUP_AS", "group-as")
    assert channel_policy.get_routing_group_id("manual", {"push_kind": "as"}) == "group-as"


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

def test_routing_group_estimate_kind_uses_estimate_env(monkeypatch):
    """push_kind='estimate'는 CHANNEL_GROUP_ESTIMATE(미설정 시 230395)로 라우팅된다."""
    monkeypatch.delenv("CHANNEL_GROUP_ESTIMATE", raising=False)
    assert channel_policy.get_routing_group_id("manual", {"push_kind": "estimate"}) == "230395"

    monkeypatch.setenv("CHANNEL_GROUP_ESTIMATE", "group-estimate")
    assert channel_policy.get_routing_group_id("manual", {"push_kind": "estimate"}) == "group-estimate"


def _png_upload(content=b"\x89PNG\r\n\x1a\nfake-estimate-bytes"):
    return (io.BytesIO(content), "estimate.png", "image/png")


def test_push_estimate_uploads_image_and_dispatches_estimate_group(client, monkeypatch):
    """견적서 푸쉬는 업로드 PNG의 presigned URL을 push_kind='estimate'로 dispatch한다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_ESTIMATE", "group-estimate")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    fake_storage = _FakeEstimateStorage()
    monkeypatch.setattr(channel_integration, "get_storage", lambda: fake_storage)

    captured = {}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["event_type"] = event_type
        captured["data"] = data
        captured["raise_on_error"] = raise_on_error
        return {"success": True, "message_id": "msg-est-1"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)

    order = Order(
        received_date="2026-07-03",
        customer_name="견적 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    response = client.post(
        "/api/channel/push-estimate",
        data={"order_id": str(order_id), "image": _png_upload()},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True

    assert captured["event_type"] == "manual"
    assert captured["raise_on_error"] is True
    assert captured["data"]["push_kind"] == "estimate"
    assert captured["data"]["pushed_by_name"] == "Channel Admin"
    assert captured["data"]["text"].startswith("[견적서]")
    assert len(captured["data"]["files"]) == 1
    assert captured["data"]["files"][0]["mime"] == "image/png"
    assert captured["data"]["files"][0]["url"].endswith("?e=3600")

    # 업로드는 주문별 폴더로 저장된다.
    assert fake_storage.uploaded
    assert fake_storage.uploaded[0]["folder"] == f"estimate_push/{order_id}"
    assert fake_storage.uploaded[0]["size"] > 0

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["channeltalk_push_estimate"]["pushed"] is True
    assert saved.structured_data["channeltalk_push_estimate"]["message_id"] == "msg-est-1"
    assert saved.structured_data["channeltalk_push_estimate"]["group_id"] == "group-estimate"
    # 견적서 이력은 영발/발주 이력과 분리된 별도 키에 저장된다.
    assert "channeltalk_push" not in saved.structured_data
    assert "channeltalk_push_drawing" not in saved.structured_data


def test_push_estimate_rejects_retired_group_before_upload(client, monkeypatch):
    """견적서 PUSH 대상이 554075면 스토리지 업로드도 시작하지 않는다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_ESTIMATE", "554075")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    fake_storage = _FakeEstimateStorage()
    monkeypatch.setattr(channel_integration, "get_storage", lambda: fake_storage)

    response = client.post(
        "/api/channel/push-estimate",
        data={"order_id": "999999", "image": _png_upload()},
        content_type="multipart/form-data",
    )

    assert response.status_code == 410
    body = response.get_json()
    assert body["success"] is False
    assert "554075" in body["message"]
    assert fake_storage.uploaded == []


def test_push_estimate_rejects_non_png(client, monkeypatch):
    """PNG가 아닌 이미지는 400으로 거부한다."""
    _login_admin(client)
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)

    order = Order(
        received_date="2026-07-03",
        customer_name="견적 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        "/api/channel/push-estimate",
        data={
            "order_id": str(order.id),
            "image": (io.BytesIO(b"jpegbytes"), "estimate.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "PNG" in response.get_json()["message"]


def test_push_estimate_rejects_spoofed_png_magic_bytes(client, monkeypatch):
    """mimetype이 image/png여도 실제 PNG 시그니처가 아니면 400으로 거부한다."""
    _login_admin(client)
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    fake_storage = _FakeEstimateStorage()
    monkeypatch.setattr(channel_integration, "get_storage", lambda: fake_storage)

    order = Order(
        received_date="2026-07-03",
        customer_name="견적 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        "/api/channel/push-estimate",
        data={
            "order_id": str(order.id),
            # mimetype은 PNG로 위조했지만 매직 바이트가 없는 임의 바이너리
            "image": (io.BytesIO(b"NOTPNG-arbitrary-binary-payload"), "estimate.png", "image/png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "PNG" in response.get_json()["message"]
    # 검증 실패 시 스토리지 업로드는 아예 일어나지 않아야 한다.
    assert fake_storage.uploaded == []


def test_push_estimate_cleans_up_upload_when_dispatch_fails(client, monkeypatch):
    """채널톡 전송 실패 시 방금 업로드한 오브젝트를 정리(고아 방지)하고 502를 반환한다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_ESTIMATE", "group-estimate")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    fake_storage = _FakeEstimateStorage()
    monkeypatch.setattr(channel_integration, "get_storage", lambda: fake_storage)

    def _boom(event_type, data, raise_on_error=False):
        raise RuntimeError("channel 502")

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _boom)

    order = Order(
        received_date="2026-07-03",
        customer_name="견적 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    response = client.post(
        "/api/channel/push-estimate",
        data={"order_id": str(order_id), "image": _png_upload()},
        content_type="multipart/form-data",
    )

    assert response.status_code == 502
    # 업로드된 오브젝트 키가 정리(delete_file) 대상으로 넘어가야 한다.
    assert fake_storage.uploaded
    assert fake_storage.deleted == [f"estimate_push/{order_id}/estimate_{order_id}.png"]

    # 전송 실패 시 이력은 기록되지 않는다.
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert "channeltalk_push_estimate" not in (saved.structured_data or {})


def test_push_estimate_resend_requires_change_note(client, monkeypatch):
    """재전송(prev pushed) 시 change_note 없으면 400."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_ESTIMATE", "group-estimate")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeEstimateStorage())
    monkeypatch.setattr(
        channel_integration,
        "dispatch_order_event",
        lambda event_type, data, raise_on_error=False: {"success": True, "message_id": "msg-x"},
    )

    order = Order(
        received_date="2026-07-03",
        customer_name="재전송 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        structured_data={"channeltalk_push_estimate": {"pushed": True, "message_id": "old"}},
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        "/api/channel/push-estimate",
        data={"order_id": str(order.id), "image": _png_upload()},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "변경 내용" in response.get_json()["message"]


def test_push_estimate_resend_stores_change_log_and_dispatches_note(client, monkeypatch):
    """재전송 시 change_note를 dispatch에 전달하고 change_log에 저장한다."""
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_ESTIMATE", "group-estimate")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeEstimateStorage())

    captured = {}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["data"] = data
        return {"success": True, "message_id": "msg-est-resend"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)

    order = Order(
        received_date="2026-07-03",
        customer_name="재전송 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        structured_data={"channeltalk_push_estimate": {"pushed": True, "message_id": "old"}},
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    response = client.post(
        "/api/channel/push-estimate",
        data={
            "order_id": str(order_id),
            "image": _png_upload(),
            "change_note": "잔금 금액 정정",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert captured["data"]["is_retry"] is True
    assert captured["data"]["change_note"] == "잔금 금액 정정"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    log = saved.structured_data["channeltalk_push_estimate"]["change_log"]
    assert len(log) == 1
    assert log[0]["note"] == "잔금 금액 정정"
    assert log[0]["message_id"] == "msg-est-resend"


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


def _as_order_with_attachments(count: int, *, structured_extra=None):
    """AS 접수 내용이 있는 주문 + AS 첨부 count장(업로드 순 id 증가)을 만든다."""
    sd = {
        "parties": {"customer": {"name": "AS Fresh", "phone": "010-0000-0000"}},
        "site": {"address_full": "Seoul"},
        "shipment": {"as_content": "문짝 처짐"},
    }
    if structured_extra:
        sd.update(structured_extra)
    order = Order(
        received_date="2026-08-13",
        customer_name="AS Fresh",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        structured_data=sd,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add_all(
        [
            OrderAttachment(
                order_id=order.id,
                filename=f"as-{i}.jpg",
                file_type="image",
                category="as",
                storage_key=f"orders/{order.id}/as-{i}.jpg",
            )
            for i in range(1, count + 1)
        ]
    )
    db_session.commit()
    return order


def _capture_as_push(monkeypatch):
    """AS PUSH 전송을 가로채는 공통 배선. 반환 dict 의 'data' 에 dispatch payload."""
    monkeypatch.setenv("CHANNEL_GROUP_AS", "group-as")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())
    captured = {"calls": 0}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["calls"] += 1
        captured["data"] = data
        return {"success": True, "message_id": f"msg-fresh-{captured['calls']}"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)
    return captured


def test_push_manual_as_keeps_newest_attachments_when_over_cap(client, monkeypatch):
    """첨부가 상한을 넘으면 잘리는 쪽은 **오래된** 파일이다.

    기존 구현은 id 오름차순으로 앞 20장을 보내 21번째(방금 올린) 사진을 통째로 빠뜨렸다 —
    AS-FRESH-01 이 고친 '최신 탈락' 회귀의 핀.
    """
    _login_admin(client)
    captured = _capture_as_push(monkeypatch)
    order = _as_order_with_attachments(21)
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual", json={"order_id": order_id, "push_kind": "as"}
    )

    assert response.status_code == 200
    assert response.get_json()["files_count"] == channel_policy.MAX_MANUAL_ATTACHMENTS
    names = [f["fileName"] for f in captured["data"]["files"]]
    assert "as-21.jpg" in names  # 최신 보존
    assert "as-1.jpg" not in names  # 가장 오래된 것만 탈락


def test_push_manual_as_resend_sends_only_new_attachments(client, monkeypatch):
    """재전송은 마지막 발송 이후 올라온 첨부만 보낸다(옛 파일 혼입 차단)."""
    _login_admin(client)
    captured = _capture_as_push(monkeypatch)
    order = _as_order_with_attachments(2)
    order_id = order.id

    first = client.post(
        "/api/channel/push-manual", json={"order_id": order_id, "push_kind": "as"}
    )
    assert first.status_code == 200
    assert first.get_json()["files_count"] == 2

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    history = saved.structured_data["channeltalk_push_as"]
    assert len(history["attachment_ids"]) == 2
    assert history["max_attachment_id"] == max(history["attachment_ids"])

    db_session.add(
        OrderAttachment(
            order_id=order_id,
            filename="as-new.jpg",
            file_type="image",
            category="as",
            storage_key=f"orders/{order_id}/as-new.jpg",
        )
    )
    db_session.commit()

    second = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "as", "change_note": "사진 추가"},
    )

    assert second.status_code == 200
    assert second.get_json()["files_count"] == 1
    assert [f["fileName"] for f in captured["data"]["files"]] == ["as-new.jpg"]


def test_push_manual_as_honors_explicit_attachment_ids(client, monkeypatch):
    """전송 확인창이 고른 첨부가 기본 선정을 이긴다(사용자 최종 판단 우선)."""
    _login_admin(client)
    captured = _capture_as_push(monkeypatch)
    order = _as_order_with_attachments(3)
    order_id = order.id
    ids = [
        a.id
        for a in db_session.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order_id)
        .order_by(OrderAttachment.id.asc())
        .all()
    ]

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "as", "attachment_ids": [ids[0]]},
    )

    assert response.status_code == 200
    assert [f["fileName"] for f in captured["data"]["files"]] == ["as-1.jpg"]


def test_push_manual_as_rejects_foreign_attachment_ids(client, monkeypatch):
    """다른 주문/분류 첨부 id 는 400 — 지정 경로가 소속 검증 우회로가 되면 안 된다."""
    _login_admin(client)
    _capture_as_push(monkeypatch)
    order = _as_order_with_attachments(1)
    order_id = order.id
    other = _as_order_with_attachments(1)
    foreign_id = (
        db_session.query(OrderAttachment)
        .filter(OrderAttachment.order_id == other.id)
        .first()
        .id
    )

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "as", "attachment_ids": [foreign_id]},
    )

    assert response.status_code == 400
    assert "AS 첨부가 아닌" in response.get_json()["message"]


def test_push_manual_as_rejects_malformed_attachment_ids(client, monkeypatch):
    _login_admin(client)
    _capture_as_push(monkeypatch)
    order = _as_order_with_attachments(1)

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order.id, "push_kind": "as", "attachment_ids": "1,2"},
    )

    assert response.status_code == 400


def test_push_preview_returns_body_and_default_selection(client, monkeypatch):
    """확인창 미리보기는 실제 전송과 **같은 선정 함수**를 써야 한다(규칙 갈림 방지)."""
    _login_admin(client)
    _capture_as_push(monkeypatch)
    order = _as_order_with_attachments(3)
    order_id = order.id

    # 1·2번을 이미 보낸 상태로 만들어 델타 판정을 태운다.
    ids = [
        a.id
        for a in db_session.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order_id)
        .order_by(OrderAttachment.id.asc())
        .all()
    ]
    sd = dict(order.structured_data)
    sd["channeltalk_push_as"] = {"pushed": True, "max_attachment_id": ids[1]}
    order.structured_data = sd
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(order, "structured_data")
    db_session.commit()

    response = client.get(
        f"/api/channel/push-preview?order_id={order_id}&push_kind=as"
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert "내용 : 문짝 처짐" in body["text"]
    by_id = {f["id"]: f for f in body["files"]}
    assert by_id[ids[2]]["selected"] is True  # 마지막 발송 이후 = 기본 선택
    assert by_id[ids[0]]["selected"] is False  # 옛 파일도 후보로는 내려온다(되살리기용)
    assert by_id[ids[1]]["selected"] is False


def test_push_preview_rejects_non_as_kind(client, monkeypatch):
    _login_admin(client)
    _capture_as_push(monkeypatch)
    order = _as_order_with_attachments(1)

    response = client.get(
        f"/api/channel/push-preview?order_id={order.id}&push_kind=drawing"
    )

    assert response.status_code == 400
