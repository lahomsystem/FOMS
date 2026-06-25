from werkzeug.security import generate_password_hash

from foms.api import measurement as erp_measurement
from db import db_session
from models import ChannelDeliveryLog, Order, User
import foms.services.channel_security as channel_security
import foms.services.channel_policy as channel_policy


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


def test_build_message_template_renders_manual_push_and_wam_link(monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    message = channel_policy.build_message_template(
        "manual",
        {
            "order_id": 2762,
            "customer_name": "윤인선",
            "text": "발주방 변환 텍스트",
        },
    )

    assert "[ERP 푸시]" not in message
    assert "주문 #2762" not in message
    assert message.startswith("발주방 변환 텍스트")
    assert "https://example.com/w/short-123" in message


def test_build_message_template_retry_uses_modify_prefix_only(monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    message = channel_policy.build_message_template(
        "manual",
        {
            "order_id": 2762,
            "customer_name": "윤인선",
            "text": "고객명 : 윤인선",
            "is_retry": True,
        },
    )

    assert "[ERP 푸시]" not in message
    assert "주문 #2762" not in message
    assert message.startswith("[수정]\n\n고객명 : 윤인선")


def test_build_message_blocks_preserves_special_characters_in_push_text(monkeypatch):
    """Apostrophes, quotes, and ampersands in ERP conversion text must not be HTML-escaped."""
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    raw_text = (
        "고객명 : 윤인선\n"
        "주  소 : 인천 서구 봉오대로 270, 루원시티2차 SK Leaders' VIEW 102-203\n"
        '옵 션 : 6" 핸들 & "특수"\n'
    )
    blocks = channel_policy.build_message_blocks(
        "manual",
        {"order_id": 2762, "text": raw_text},
    )

    body_blocks = [block for block in blocks if "SK Leaders' VIEW" in block.get("value", "")]
    assert len(body_blocks) == 1
    body_block = body_blocks[0]["value"]
    assert "SK Leaders' VIEW" in body_block
    assert "&#x27;" not in body_block
    assert "&quot;" not in body_block
    assert "&amp;" not in body_block
    assert '6" 핸들 & "특수"' in body_block


def test_build_message_blocks_escapes_link_url_attribute(monkeypatch):
    """Link markup attribute values must stay escaped; body text must not."""
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")

    blocks = channel_policy.build_message_blocks(
        "manual",
        {
            "order_id": 1,
            "text": "주  소 : SK Leaders' VIEW",
            "detail_url": 'https://x.example/?a=1&b=2"',
        },
    )

    body_blocks = [block for block in blocks if "SK Leaders' VIEW" in block.get("value", "")]
    assert body_blocks[0]["value"] == "주  소 : SK Leaders' VIEW"
    link_blocks = [block for block in blocks if "주문 보기" in block.get("value", "")]
    assert len(link_blocks) == 1
    assert 'value="https://x.example/?a=1&amp;b=2&quot;"' in link_blocks[0]["value"]


def test_build_message_template_preserves_special_characters_in_push_text(monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    raw_text = "주  소 : SK Leaders' VIEW 102-203"
    message = channel_policy.build_message_template("manual", {"order_id": 1, "text": raw_text})

    assert "SK Leaders' VIEW" in message
    assert "&#x27;" not in message


def test_build_message_blocks_renders_manual_push_link(monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    blocks = channel_policy.build_message_blocks(
        "manual",
        {
            "order_id": 2762,
            "customer_name": "윤인선",
            "text": "발주방 변환 텍스트",
        },
    )

    assert blocks and blocks[0].get("value") == "발주방 변환 텍스트"
    assert not any("[ERP 푸시]" in block.get("value", "") for block in blocks)
    assert not any("주문 #2762" in block.get("value", "") for block in blocks)
    link_blocks = [block for block in blocks if block.get("type") == "text" and "주문 보기" in block.get("value", "")]
    assert len(link_blocks) == 1
    assert '<link type="url" value="https://example.com/w/short-123">주문 보기</link>' in link_blocks[0]["value"]


def test_build_message_template_rejects_auto_event_types():
    try:
        channel_policy.build_message_template("stage_changed", {"order_id": 1})
    except ValueError as exc:
        assert "Unsupported ChannelTalk event_type" in str(exc)
    else:
        raise AssertionError("expected ValueError for retired auto event type")


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


def test_measurement_manager_update_does_not_create_channel_delivery_log(client):
    _login_admin(client)

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
    order_id = order.id

    response = client.post(
        f"/api/erp/measurement/update/{order_id}",
        json={"field": "manager", "value": "망고"},
    )

    assert response.status_code == 200
    assert (
        db_session.query(ChannelDeliveryLog)
        .filter(ChannelDeliveryLog.order_id == order_id)
        .count()
        == 0
    )
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.manager_name == "망고"
    assert saved.structured_data["parties"]["manager"]["name"] == "망고"
