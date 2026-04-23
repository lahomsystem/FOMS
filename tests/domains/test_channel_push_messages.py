from werkzeug.security import generate_password_hash

from foms.api import measurement as erp_measurement
from db import db_session
from models import ChannelDeliveryLog, Order, User
import foms.services.channel_dispatch as channel_dispatch
import foms.services.channel_security as channel_security
import foms.services.channel_policy as channel_policy
from foms.services.channel_delivery import mark_order_updated_for_channel
from foms.services.channel_event_payloads import build_structured_update_payload


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


def test_build_message_template_renders_change_lines_and_wam_link(monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    message = channel_policy.build_message_template(
        "stage_changed",
        {
            "order_id": 2762,
            "customer_name": "윤인선",
            "event_title": "상태 변경",
            "change_lines": [
                "상태: 실측 -> 도면",
                "담당자: 이시영 -> 망고",
            ],
            "changed_by": "관리자A",
        },
    )

    assert "[알림] 주문 #2762 - 윤인선 상태 변경" in message
    assert "- 상태: 실측 -> 도면" in message
    assert "- 담당자: 이시영 -> 망고" in message
    assert "변경자: 관리자A" in message
    assert "https://example.com/w/short-123" in message


def test_build_message_blocks_renders_labeled_link(monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    blocks = channel_policy.build_message_blocks(
        "stage_changed",
        {
            "order_id": 2762,
            "customer_name": "윤인선",
            "event_title": "정보 변경",
            "change_lines": ["상태: 실측 -> 도면"],
            "changed_by": "이시영",
        },
    )

    assert any(block.get("type") == "bullets" for block in blocks)
    assert blocks and "윤인선" in blocks[0].get("value", "")
    link_blocks = [block for block in blocks if block.get("type") == "text" and "주문 보기" in block.get("value", "")]
    assert len(link_blocks) == 1
    assert '<link type="url" value="https://example.com/w/short-123">주문 보기</link>' in link_blocks[0]["value"]


def test_mark_order_updated_for_channel_stores_template_key_and_payload(app):
    order = Order(
        received_date="2026-03-27",
        customer_name="테스터",
        phone="010-0000-0000",
        address="서울",
        product="붙박이장",
    )
    db_session.add(order)
    db_session.commit()

    payload = {
        "event_type": "stage_changed",
        "event_title": "상태 변경",
        "change_lines": ["상태: 실측 -> 도면"],
    }
    delivery_id = mark_order_updated_for_channel(order, "stage_changed", payload=payload)
    db_session.commit()

    log = db_session.get(ChannelDeliveryLog, delivery_id)
    assert log is not None
    assert log.template_key == "stage_changed"
    assert log.masked_request_payload["change_lines"] == ["상태: 실측 -> 도면"]


def test_dispatch_channel_push_uses_stored_payload_for_multiword_event(app, monkeypatch):
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-1")
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    captured = {}

    def _fake_send_group_message(**kwargs):
        captured.update(kwargs)
        return {"success": True, "message_id": "msg-1"}

    monkeypatch.setattr(channel_dispatch, "send_group_message", _fake_send_group_message)

    order = Order(
        received_date="2026-03-27",
        customer_name="윤인선",
        phone="010-1111-2222",
        address="경기 용인시",
        product="주방",
        status="RECEIVED",
        channel_source_seq=1,
    )
    db_session.add(order)
    db_session.commit()

    log = ChannelDeliveryLog(
        event_key=f"order_{order.id}_stage_changed_1",
        source_type="order_event",
        source_id=order.id,
        target_type="group",
        target_id="group-1",
        status="pending",
        order_id=order.id,
        source_version=1,
        template_key="stage_changed",
        masked_request_payload={
            "event_type": "stage_changed",
            "event_title": "상태 변경",
            "change_lines": ["상태: 실측 -> 도면"],
            "changed_by": "관리자A",
        },
    )
    db_session.add(log)
    db_session.commit()
    log_id = log.id

    channel_dispatch.dispatch_channel_push(log_id)
    db_session.expire_all()

    saved = db_session.get(ChannelDeliveryLog, log_id)
    assert captured["group_id"] == "group-1"
    assert "- 상태: 실측 -> 도면" in captured["plain_text"]
    assert "변경자: 관리자A" in captured["plain_text"]
    assert any(block.get("type") == "text" and "주문 보기" in block.get("value", "") for block in captured["blocks"])
    assert saved.status == "sent"
    assert "상태: 실측 -> 도면" in (saved.rendered_text_snapshot or "")


def test_legacy_erp_order_route_redirects_to_edit(client):
    _login_admin(client)
    order = Order(
        received_date="2026-03-27",
        customer_name="레거시 링크",
        phone="010-0000-0000",
        address="서울",
        product="붙박이장",
    )
    db_session.add(order)
    db_session.commit()

    response = client.get(f"/erp/orders/{order.id}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/edit/{order.id}?open=erp-order")


def test_measurement_manager_update_records_change_payload(client, monkeypatch):
    _login_admin(client)

    enqueued = []

    def _capture_enqueue(delivery_id):
        enqueued.append(delivery_id)
        return True

    monkeypatch.setattr(erp_measurement, "enqueue_channeltalk_push", _capture_enqueue)

    order = Order(
        received_date="2026-03-27",
        customer_name="담당 변경 테스트",
        phone="010-0000-0000",
        address="서울",
        product="붙박이장",
        is_erp_order=True,
        structured_data={"parties": {"manager": {"name": "이시영"}}},
        manager_name="이시영",
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        f"/api/erp/measurement/update/{order.id}",
        json={"field": "manager", "value": "망고"},
    )

    assert response.status_code == 200
    assert len(enqueued) == 1
    log = db_session.get(ChannelDeliveryLog, enqueued[0])
    assert log.template_key == "manager_changed"
    assert "이시영" in log.masked_request_payload["change_lines"][0]
    assert "망고" in log.masked_request_payload["change_lines"][0]


def test_build_structured_update_payload_includes_stage_and_manager_changes():
    payload = build_structured_update_payload(
        {
            "workflow": {"stage": "MEASURE"},
            "parties": {"manager": {"name": "이시영"}},
        },
        {
            "workflow": {"stage": "DRAWING"},
            "parties": {"manager": {"name": "망고"}},
        },
        actor_name="관리자A",
    )

    assert payload["event_type"] == "order_updated"
    assert "상태: 실측 -> 도면" in payload["change_lines"]
    assert "담당자: 이시영 -> 망고" in payload["change_lines"]
    assert payload["changed_by"] == "관리자A"


def test_build_structured_update_payload_payment_only_uses_payment_event():
    payload = build_structured_update_payload(
        {"payment": {"deposit_confirmed": False}},
        {"payment": {"deposit_confirmed": True}},
        actor_name="이시영",
    )
    assert payload["event_type"] == "payment_confirmation_changed"
    assert payload["event_title"] == "결제 확인 변경"
    assert "계약금 확인: 미확인 -> 확인" in payload["change_lines"]
    assert payload["changed_by"] == "이시영"


def test_build_structured_update_payload_merges_payment_with_other_fields():
    payload = build_structured_update_payload(
        {
            "workflow": {"stage": "RECEIVED"},
            "payment": {"deposit_confirmed": False},
        },
        {
            "workflow": {"stage": "MEASURE"},
            "payment": {"deposit_confirmed": True},
        },
    )
    assert payload["event_type"] == "order_updated"
    assert payload["event_title"] == "정보 변경"
    lines = payload["change_lines"]
    assert any("상태:" in ln for ln in lines)
    assert any("계약금 확인:" in ln for ln in lines)
