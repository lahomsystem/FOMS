"""도면 작업실 — 주문 변경 신호의 자리 계약(모바일 + 데스크톱).

상단 배너(`dw-order-change-banner`)를 걷어내고 상태 리본 한 줄로 옮긴 뒤의 계약을 고정한다.
핵심은 세 가지다.

1. 값(이전 → 이후 실수치)을 쓰는 블록은 화면에 하나뿐이다(타임라인). 리본은 이름과 줄 수만 말한다.
2. 확인(ack) 버튼은 값 바로 아래 하나뿐이고, 확인 권한이 없는 사람에게는 아예 렌더되지 않는다.
3. 타임라인이 없는 목록 뷰에서도 미확인 변경이 보인다 — 배너가 사라져도 침묵하지 않는다.
"""

from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.web.drawing.workbench import _build_order_change_line
from models import Order, User

CHANGES = [
    {"path": "items.0.spec", "label": "항목1 스펙", "from": "1170", "to": "1165*620*2311"},
    {
        "path": "items.0.product_name",
        "label": "항목1 제품명",
        "from": "여닫이 붙박이장",
        "to": "몰딩여닫이",
    },
]


def _login(client, *, role="ADMIN", team="DRAWING", username="dw_change_admin", name="도면 담당"):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, pending=True, acked=False, files=1):
    event = {
        "action": "ERP_ORDER_CHANGED",
        "at": "2026-09-11 04:58:00",
        "by_user_name": "최진호",
        "changes": CHANGES,
    }
    if acked:
        event.update(
            {
                "acked": True,
                "acked_at": "2026-09-11 05:32:00",
                "acked_by_name": "최상용",
                "acked_by_user_id": 1,
            }
        )
    drawing_files = [
        {
            "key": f"drawings/sheet-{i}.png",
            "filename": f"sheet-{i}.png",
            "view_url": f"/api/files/view/drawings/sheet-{i}.png",
        }
        for i in range(1, files + 1)
    ]
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="최승희",
        phone="010-0000-0000",
        address="송파구 충민로4길 19",
        product="몰딩여닫이",
        status="DRAWING",
        manager_name="최진호",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "최승희"}, "manager": {"name": "최진호"}},
            "workflow": {"stage": "DRAWING"},
            "drawing": {"status": "IN_PROGRESS", "order_change_pending": pending},
            "drawing_current_files": drawing_files,
            "drawing_transfer_history": [event],
            "drawing_assignees": [],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _render_full(client, order, monkeypatch, user, query=""):
    """응답 전체(데스크톱 본문 + 모바일 partial)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    response = client.get(f"/erp/drawing-workbench/{order.id}{query}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _render(client, order, monkeypatch, user, query=""):
    """모바일 partial 구간만 돌려준다(같은 응답에 데스크톱 본문도 함께 온다)."""
    body = _render_full(client, order, monkeypatch, user, query)
    start = body.index("erp-mobile-shell foms-drawing-handoff")
    end = body.index('class="foms-drawing-action-bar"', start)
    return body[start:end]


def test_mobile_banner_markup_is_gone(client, monkeypatch):
    """옛 상단 배너는 어떤 이름으로도 부활하지 않는다."""
    user = _login(client)
    body = _render(client, _order(), monkeypatch, user)

    assert "dw-order-change-banner" not in body
    assert "dwOrderChangeBanner" not in body
    assert "주문 내용 변경" not in body
    # 거짓 숫자였던 리본 보조 문구의 하드코딩 상수도 함께 사라진다.
    assert "주문 단위 상태 1개" not in body


def test_turn_line_names_the_change_without_repeating_values(client, monkeypatch):
    """리본 한 줄은 '무엇이 몇 줄'까지만 말하고, 값은 타임라인 한 곳에만 남는다."""
    user = _login(client)
    body = _render(client, _order(), monkeypatch, user)

    assert 'id="dwOrderChangeLine"' in body
    assert "미확인" in body
    assert "스펙, 제품명 2줄" in body
    # 값은 화면 전체에서 한 번뿐이다 — 중복 제거가 이번 변경의 목적이다.
    assert body.count("1165*620*2311") == 1


def test_ack_button_sits_below_the_values(client, monkeypatch):
    """확인 버튼은 값 바로 아래 하나뿐이다(대조 없이 누르는 지름길을 만들지 않는다)."""
    user = _login(client)
    body = _render(client, _order(), monkeypatch, user)

    assert body.count("data-dw-order-change-ack") == 1
    assert "/drawing/ack-order-change" in body
    assert "이 주문 변경 2줄 확인" in body
    assert "확인은 주문 단위입니다" in body
    # 버튼이 자기 주소를 직접 싣는다 — 옛 JS 는 배너 조상에서 주소를 읽었다.
    ack_at = body.index("data-dw-order-change-ack")
    assert 'data-ack-url="/api/orders/' in body[ack_at - 200 : ack_at + 400]
    assert body.index("1165*620*2311") < ack_at


def test_list_view_keeps_the_change_signal(client, monkeypatch):
    """도면이 여러 장이면 목록 뷰로 열린다 — 타임라인이 없어도 변경은 보인다."""
    user = _login(client)
    body = _render(client, _order(files=2), monkeypatch, user)

    assert 'data-handoff-mode="list"' in body
    assert 'id="dwOrderChangeLine"' in body
    assert "스펙, 제품명 2줄" in body
    # 목록 뷰에는 값도 확인 버튼도 없다. 대신 값이 있는 화면으로 가는 링크를 준다.
    assert "1165*620*2311" not in body
    assert "data-dw-order-change-ack" not in body
    assert "1번 도면에서 보기" in body


def test_sales_viewer_sees_state_but_no_ack_button(client, monkeypatch):
    """확인 권한이 없는 영업 시점에는 버튼 대신 상태만 보인다(옛 배너는 403 을 만들었다)."""
    user = _login(client, role="USER", team="SALES", username="dw_change_sales", name="최진호")
    body = _render(client, _order(), monkeypatch, user)

    assert 'id="dwOrderChangeLine"' in body
    assert "도면팀 확인 대기" in body
    assert "data-dw-order-change-ack" not in body


def test_acked_state_keeps_who_and_when(client, monkeypatch):
    """확인 후에도 줄은 사라지지 않는다 — 누가 언제 확인했는지가 남는다."""
    user = _login(client)
    body = _render(client, _order(pending=False, acked=True), monkeypatch, user)

    assert "확인함" in body
    assert "최상용" in body
    assert "09-11 14:32" in body  # 05:32 UTC → KST
    assert "data-dw-order-change-ack" not in body
    assert "is-acked" in body


def test_ack_api_returns_actor_and_time(client, monkeypatch):
    """모바일 리본을 '확인함 · 누가 언제'로 바꾸려면 응답에 두 값이 있어야 한다."""
    _login(client)
    order = _order()

    response = client.post(f"/api/orders/{order.id}/drawing/ack-order-change", json={})
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["acked"] is True
    assert data["acked_by_name"] == "도면 담당"
    assert len(data["acked_at"]) == 11  # 'MM-DD HH:MM'


@pytest.mark.parametrize(
    "labels,expected",
    [
        (["항목1 스펙"], "스펙"),
        (["항목1 스펙", "항목2 스펙"], "스펙"),
        (["항목1 스펙", "항목1 제품명"], "스펙, 제품명"),
        (["항목1 스펙", "항목1 제품명", "시공일", "주소"], "스펙, 제품명 외 2개"),
    ],
)
def test_field_text_dedupes_and_caps_at_two_names(labels, expected):
    """이름은 항목 번호를 걷어 중복을 없애고 2개까지만 쓴다 — 리본이 부풀지 않게."""
    events = [{"changes": [{"label": label, "from": "a", "to": "b"} for label in labels]}]

    line = _build_order_change_line(events)

    assert line["state"] == "pending"
    assert line["field_text"] == expected
    assert line["line_count"] == len(labels)


def test_desktop_banner_is_gone_and_ack_lives_in_the_feed(client, monkeypatch):
    """데스크톱도 같은 규칙 — 배너를 걷고, 확인 버튼은 변경 값이 있는 카드 안으로 내린다."""
    user = _login(client)
    body = _render_full(client, _order(), monkeypatch, user)

    assert "dw-order-change-banner" not in body
    assert "dwOrderChangeBanner" not in body
    assert "주문 내용 변경 — 도면 반영 필요" not in body
    # 확인 버튼은 화면당 하나씩 — 모바일 타임라인 1 + 데스크톱 변경 이력 카드 1.
    assert body.count("data-dw-order-change-ack") == 2
    feed_at = body.index('id="dwOrderChangeFeed"')
    # 앞쪽 <style> 블록에도 같은 이름이 있으니 마크업만 센다.
    desktop_ack_at = body.index('class="dw-order-change-ack-row"', feed_at)
    # 값(표)은 여전히 카드 안에 한 번, 머리글은 이름과 줄 수까지만 말한다.
    assert "스펙, 제품명 2줄" in body[feed_at:desktop_ack_at]


def test_desktop_feed_shows_who_acked(client, monkeypatch):
    """확인 후에는 머리글이 '누가 언제'를 말한다(미확인 배지는 사라진다)."""
    user = _login(client)
    body = _render_full(client, _order(pending=False, acked=True), monkeypatch, user)

    feed_at = body.index('id="dwOrderChangeFeed"')
    head = body[feed_at : body.index('class="dw-order-change-feed__body"', feed_at)]
    assert "최상용 확인 · 09-11 14:32" in head
    assert "미확인" not in head
    assert "data-dw-order-change-ack" not in body
