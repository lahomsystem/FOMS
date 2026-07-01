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
            "change_note": "손잡이 오기재 → 푸쉬로 정정",
        },
    )

    assert "[ERP 푸시]" not in message
    assert "주문 #2762" not in message
    assert message.startswith("[수정]\n손잡이 오기재 → 푸쉬로 정정\n\n고객명 : 윤인선")
    assert "내부 변경" not in message.split("🔗")[0]


def test_build_message_blocks_resend_includes_modify_prefix_and_full_note(monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    blocks = channel_policy.build_message_blocks(
        "manual",
        {
            "order_id": 1,
            "text": "고객명 : 박은정",
            "is_retry": True,
            "change_note": "규격 오타 수정",
        },
    )

    values = [block["value"] for block in blocks]
    # One line == one block: [수정] / note / (blank) / body / link
    assert values[0] == "[수정]"
    assert values[1] == "규격 오타 수정"
    # [수정] 헤더와 본문 사이 빈 줄은 nbsp block으로 보존된다.
    assert values[2] == "\u00a0"
    assert values[3] == "고객명 : 박은정"
    assert not any("내부 변경" in value for value in values)
    # No block carries an intra-block newline (line breaks are structural).
    assert all(value.count("\n") == 0 for value in values if "주문 보기" not in value)


def test_build_message_template_resend_preserves_long_multiline_note(monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    long_note = "손잡이 오기재 → 푸쉬로 정정, 시공일 7/17 유지"
    message = channel_policy.build_message_template(
        "manual",
        {
            "order_id": 1,
            "text": "고객명 : 박은정",
            "is_retry": True,
            "change_note": long_note,
        },
    )

    assert message.startswith(f"[수정]\n{long_note}\n\n고객명 : 박은정")
    assert "내부 변경" not in message.split("🔗")[0]


def test_build_message_blocks_one_block_per_line_preserves_line_breaks(monkeypatch):
    """Regression guard: ChannelTalk renders each block on its own line but ignores a raw
    ``\\n`` inside a single block value. Line breaks must be structural (one block per line),
    never collapsed into a single joined block, or the group message clumps together."""
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    raw_text = "\n".join([
        "고객명 : 채효진",
        "발주사 : 라홈",
        "시공일 : 7월 10일",
        "주  소 : 경기도 파주시 청암로 50",
        "연락처 : 010-5444-0427",
        "1.",
        "제품명 : 로라 무몰딩 여닫이",
        "잔금 : 1,061,830원",
    ])
    body_line_count = len(raw_text.split("\n"))

    blocks = channel_policy.build_message_blocks(
        "manual",
        {"order_id": 2762, "text": raw_text},
    )

    values = [block["value"] for block in blocks]
    link_values = [value for value in values if "주문 보기" in value]
    body_values = [value for value in values if "주문 보기" not in value]

    assert len(link_values) == 1
    # One block per conversion line — no line is merged with another.
    assert len(body_values) == body_line_count
    assert body_values[0] == "고객명 : 채효진"
    assert body_values[1] == "발주사 : 라홈"
    # Absolutely no intra-block newline: relying on it is what broke rendering.
    assert all(value.count("\n") == 0 for value in body_values)


def test_build_message_blocks_preserves_blank_lines_between_sections(monkeypatch):
    """Regression guard: 섹션 구분용 빈 줄(줄 띄움)은 nbsp block으로 보존돼야 한다.

    ChannelTalk는 block ``value``를 HTML로 렌더하므로 빈/공백-only value는 zero-height로
    collapse된다. 과거 ``if line.strip()`` 필터가 빈 줄을 통째로 버려 발주방/실측 PUSH가
    다닥 붙어 보였다. 빈 줄은 반드시 non-breaking space block으로 살아남아야 한다."""
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id=None: "short-123")

    source_lines = [
        "고객명 : 김대용",
        "발주사 : 강민경",
        "연락처 : 010-3240-7586",
        "",
        "1.",
        "제품명 : 슬라이딩",
        "항목 견적 : 1,116,000원",
        "",
        "2.",
        "제품명 : 슬라이딩",
        "항목 견적 : 1,427,570원",
        "",
        "담당자 : 강민경",
        "잔금 : 3,559,570원",
    ]
    raw_text = "\n".join(source_lines)

    blocks = channel_policy.build_message_blocks("manual", {"order_id": 2762, "text": raw_text})
    values = [block["value"] for block in blocks]
    body_values = [value for value in values if "주문 보기" not in value]

    nbsp = "\u00a0"
    expected = [line if line.strip() else nbsp for line in source_lines]
    # 변환 텍스트를 줄 순서·빈 줄 위치까지 그대로 재현한다.
    assert body_values == expected
    # 빈 줄은 정확히 3곳(섹션 사이), 각각 nbsp 한 block으로 보존.
    assert body_values.count(nbsp) == 3
    # 항목 헤더 1./2. 및 담당자 앞에는 빈 줄 block이 온다.
    assert body_values[body_values.index("1.") - 1] == nbsp
    assert body_values[body_values.index("2.") - 1] == nbsp
    assert body_values[body_values.index("담당자 : 강민경") - 1] == nbsp
    # 내용 줄에는 intra-block 개행이 없어야 한다(줄바꿈은 구조적).
    assert all(value.count("\n") == 0 for value in body_values)


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

    # Each source line becomes its own block; special characters stay raw (unescaped).
    values = [block.get("value", "") for block in blocks]
    joined = "\n".join(values)
    assert "SK Leaders' VIEW" in joined
    assert "&#x27;" not in joined
    assert "&quot;" not in joined
    assert "&amp;" not in joined
    assert '6" 핸들 & "특수"' in joined
    assert any(value.startswith("주  소 :") for value in values)
    assert any(value.startswith("옵 션 :") for value in values)


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
