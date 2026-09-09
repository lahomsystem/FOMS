"""도면방 채널톡 PUSH(push_kind='drawing_room') 계약 테스트.

발주 PUSH(``drawing``, 그룹 229625)와 **다른 방**(도면방 230331)이고, 보내는 파일도 다르다:
category='drawing' 첨부 전량이 아니라 ``structured_data['drawing_current_files']`` 의
**현재 전달본**과의 교집합만 나간다(옛 전달본 혼입 차단). 이력 키도 분리한다 —
발주 PUSH 를 보냈다고 도면방 PUSH 가 재전송으로 취급되면 안 된다.
"""

import foms.api.channel.channel_integration as channel_integration
import foms.services.channel_policy as channel_policy
from db import db_session
from models import Order, OrderAttachment, User
from werkzeug.security import generate_password_hash


class _FakeStorage:
    def get_download_url(self, storage_key, expires_in=3600):
        return f"https://cdn.example.com/{storage_key}?e={expires_in}"


def _login_admin(client, username="drawing-room-admin", password="admin"):
    """ADMIN 세션을 만든다(smoke 테스트와 같은 모양)."""
    user = User(
        username=username,
        password=generate_password_hash(password),
        role="ADMIN",
        name="Drawing Room Admin",
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


def _capture_push(monkeypatch):
    """채널톡 전송을 가짜로 바꾸고 dispatch payload 를 잡는다."""
    monkeypatch.setenv("CHANNEL_GROUP_DRAWING", "group-drawing")
    monkeypatch.setenv("CHANNEL_GROUP_DRAWING_ROOM", "group-drawing-room")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())

    captured = {"calls": 0}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["calls"] += 1
        captured["data"] = data
        return {"success": True, "message_id": f"msg-room-{captured['calls']}"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)
    return captured


def _drawing_entry(order_id, name):
    """``drawing_current_files`` 엔트리(정본 모양 — 키 이름은 ``key`` 다)."""
    key = f"orders/{order_id}/drawing/{name}"
    return {
        "key": key,
        "filename": name,
        "view_url": f"/api/files/view/{key}",
        "download_url": f"/api/files/download/{key}",
    }


def _order_with_drawings(current_names, attachment_names, *, structured_extra=None):
    """도면 첨부 N장 + 현재 전달본 M장을 가진 주문을 만든다.

    Args:
        current_names: ``drawing_current_files`` 에 넣을 파일명(순서 = 도면 번호).
        attachment_names: ``category='drawing'`` 첨부로 만들 파일명.
        structured_extra: structured_data 에 덧붙일 dict(본문 조립용 값 등).

    Returns:
        commit 된 Order.
    """
    order = Order(
        received_date="2026-09-09",
        customer_name="도면방 고객",
        phone="010-0000-0000",
        address="서울시 강남구",
        product="Wardrobe",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add_all([
        OrderAttachment(
            order_id=order.id,
            filename=name,
            file_type="image",
            category="drawing",
            storage_key=f"orders/{order.id}/drawing/{name}",
        )
        for name in attachment_names
    ])
    sd = {"drawing_current_files": [_drawing_entry(order.id, n) for n in current_names]}
    sd.update(structured_extra or {})
    order.structured_data = sd
    db_session.commit()
    return order


def test_drawing_room_routes_to_group_env_with_230331_fallback(monkeypatch):
    """도면방 라우팅: 환경변수 우선, 미설정 시 운영 그룹 230331 폴백."""
    monkeypatch.setenv("CHANNEL_GROUP_DRAWING_ROOM", "group-from-env")
    assert channel_policy.get_routing_group_id(
        "manual", {"push_kind": "drawing_room"}
    ) == "group-from-env"

    monkeypatch.delenv("CHANNEL_GROUP_DRAWING_ROOM", raising=False)
    assert channel_policy.get_routing_group_id(
        "manual", {"push_kind": "drawing_room"}
    ) == "230331"


def test_drawing_room_sends_only_current_transfer_in_transfer_order(client, monkeypatch):
    """category='drawing' 전량이 아니라 현재 전달본만, **전달 순서 그대로** 나간다."""
    _login_admin(client)
    captured = _capture_push(monkeypatch)
    # 첨부는 3장(1차 전달본 old.png 포함), 현재 전달본은 그중 2장 — 순서는 id 역순으로 둬서
    # 정렬이 id 가 아니라 drawing_current_files 를 따르는지 드러나게 한다.
    order = _order_with_drawings(
        current_names=["plan2.png", "plan1.png"],
        attachment_names=["plan1.png", "plan2.png", "old.png"],
    )
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "drawing_room"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["files_count"] == 2
    assert captured["data"]["push_kind"] == "drawing_room"
    urls = [f["url"] for f in captured["data"]["files"]]
    assert urls == [
        f"https://cdn.example.com/orders/{order_id}/drawing/plan2.png?e=3600",
        f"https://cdn.example.com/orders/{order_id}/drawing/plan1.png?e=3600",
    ]


def test_drawing_room_history_key_is_separate_from_order_push(client, monkeypatch):
    """이력 키 분리: 도면방 전송은 발주 PUSH 이력 키를 만들지 않는다."""
    _login_admin(client)
    _capture_push(monkeypatch)
    order = _order_with_drawings(["plan1.png"], ["plan1.png"])
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "drawing_room"},
    )

    assert response.status_code == 200
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["channeltalk_push_drawing_room"]["pushed"] is True
    assert "channeltalk_push_drawing" not in saved.structured_data


def test_drawing_room_without_transfer_is_blocked_before_dispatch(client, monkeypatch):
    """전달본이 없으면 400 — 도면 없이 방에 알림만 가면 안 된다(전송 미호출)."""
    _login_admin(client)
    captured = _capture_push(monkeypatch)
    order = _order_with_drawings([], ["plan1.png"])
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "drawing_room"},
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == (
        "전달된 도면이 없습니다. 도면을 먼저 전달한 뒤 도면방 PUSH 를 눌러주세요."
    )
    assert captured["calls"] == 0


def test_drawing_room_missing_attachment_rows_says_something_different(client, monkeypatch):
    """전달본 key 는 있는데 첨부행이 없으면 다른 문구로 400(옛 전달본은 행이 지워졌을 수 있다)."""
    _login_admin(client)
    captured = _capture_push(monkeypatch)
    order = _order_with_drawings(["gone.png"], ["plan1.png"])
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "drawing_room"},
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == (
        "현재 전달본 도면을 첨부 목록에서 찾지 못했습니다. 도면을 다시 전달한 뒤 시도해주세요."
    )
    assert captured["calls"] == 0


def test_drawing_room_resend_requires_change_note_and_accumulates_change_log(client, monkeypatch):
    """재전송은 변경 내용을 요구하고(문구 고정), 주면 200 + change_log 누적."""
    _login_admin(client)
    _capture_push(monkeypatch)
    order = _order_with_drawings(["plan1.png"], ["plan1.png"])
    order_id = order.id

    first = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "drawing_room"},
    )
    assert first.status_code == 200

    blocked = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "drawing_room"},
    )
    assert blocked.status_code == 400
    # 두 프론트가 이 문구로 재전송 흐름을 판정한다(브리프 §6 회수 규약).
    assert "재전송 시 변경 내용" in blocked.get_json()["message"]

    retried = client.post(
        "/api/channel/push-manual",
        json={
            "order_id": order_id,
            "push_kind": "drawing_room",
            "change_note": "치수 오기재 정정",
        },
    )
    assert retried.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    history = saved.structured_data["channeltalk_push_drawing_room"]
    assert history["is_modified"] is True
    assert history["change_log"][-1]["note"] == "치수 오기재 정정"


def test_drawing_room_body_is_customer_name_only(client, monkeypatch):
    """본문은 고객 이름 한 줄이다 — 금액·연락처·주소는 도면방에 나가면 안 된다."""
    _login_admin(client)
    captured = _capture_push(monkeypatch)
    order = _order_with_drawings(
        ["plan1.png"],
        ["plan1.png"],
        structured_extra={
            "flags": {"factory2": True},
            "schedule": {"measurement": {"date": "2026-08-14", "time": "오후 2시"}},
            "payment": {"shipping_price": 3400000, "deposit": 500000, "balance": 2900000},
        },
    )
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "drawing_room"},
    )

    assert response.status_code == 200
    # 클라이언트 text 없이도 200 — 본문은 서버가 조립한다.
    assert captured["data"]["text"] == "도면방 고객"
    text = captured["data"]["text"]
    for leaked in ("3400000", "3,400,000", "500000", "010-0000-0000", "서울시 강남구", "실측일"):
        assert leaked not in text


def test_drawing_room_body_falls_back_to_order_number_without_name(client, monkeypatch):
    """이름이 비어 있으면 주문번호로 보낸다(400 으로 막지 않는다)."""
    _login_admin(client)
    captured = _capture_push(monkeypatch)
    order = _order_with_drawings(["plan1.png"], ["plan1.png"])
    order.customer_name = "   "
    db_session.commit()
    order_id = order.id

    response = client.post(
        "/api/channel/push-manual",
        json={"order_id": order_id, "push_kind": "drawing_room"},
    )

    assert response.status_code == 200
    assert captured["data"]["text"] == f"주문 #{order_id}"


def test_drawing_room_history_key_is_preserved_and_preview_matches_send(client, monkeypatch):
    """이력 키가 저장 보존 목록에 있고, 미리보기 files_count 가 실제 전송과 같다."""
    from foms.api.erp_orders_structured import _OPERATIONAL_TOP_LEVEL_KEYS

    # 보존 목록에 없으면 주문을 한 번 저장하는 것만으로 발송 이력이 사라진다.
    assert "channeltalk_push_drawing_room" in _OPERATIONAL_TOP_LEVEL_KEYS

    _login_admin(client)
    _capture_push(monkeypatch)
    order = _order_with_drawings(
        current_names=["plan2.png", "plan1.png"],
        attachment_names=["plan1.png", "plan2.png", "old.png"],
    )
    order_id = order.id

    response = client.get(
        f"/api/channel/push-preview?order_id={order_id}&push_kind=drawing_room"
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["files_count"] == 2
    assert [f["filename"] for f in body["files"]] == ["plan2.png", "plan1.png"]
    assert all(f["selected"] is True for f in body["files"])
    assert all(f["source"] == "현재 전달본" for f in body["files"])
    assert body["text"] == "도면방 고객"
