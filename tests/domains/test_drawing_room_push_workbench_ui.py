"""도면방 PUSH — 워크벤치 상세 프론트 계약.

버튼 id·권한 게이트·0장 차단·전송 계약(push_kind='drawing_room')·전역 리스너 무증가·
자산 핀 고정을 템플릿 문자와 실제 렌더 결과 두 축으로 못 박는다.
"""

from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "templates/drawing/partials/workbench_detail_body.html"
)

DESKTOP_ID = 'id="dw-btn-drawing-room-push"'
MOBILE_ID = 'id="dw-btn-drawing-room-push-mobile"'
PERMISSION_GATE = "{% if can_toggle_revision_check %}"
EMPTY_GATE = "{% if not drawing_files %}disabled"
EMPTY_MESSAGE = "전달된 도면이 없습니다. 도면을 먼저 전달해주세요."

# 착수 전 값(도면방 PUSH 배선 이전)과 같아야 한다 — fragment 재실행 시 중복 누적을
# 막기 위해 새 코드는 전역(document) 리스너를 하나도 늘리지 않는다.
BASELINE_DOCUMENT_LISTENERS = 2


def _template_text() -> str:
    """워크벤치 상세 파셜 원문을 읽어 돌려준다."""
    return TEMPLATE.read_text(encoding="utf-8")


def test_drawing_room_push_buttons_exist_once_each():
    """데스크톱·모바일 버튼이 각각 하나씩만 있고 id 가 겹치지 않는다."""
    text = _template_text()

    assert DESKTOP_ID in text
    assert MOBILE_ID in text
    # 'dw-btn-drawing-room-push"' 는 데스크톱 id 에서만 끝나는 형태다(모바일은 '-mobile"').
    assert text.count('dw-btn-drawing-room-push"') == 1
    assert text.count('dw-btn-drawing-room-push-mobile"') == 1


def test_drawing_room_push_buttons_use_existing_participant_gate():
    """새 권한 축을 만들지 않고 워크벤치 참여자 판정(can_toggle_revision_check)을 그대로 쓴다."""
    text = _template_text()

    for button_id in (DESKTOP_ID, MOBILE_ID):
        head = text[max(0, text.index(button_id) - 200) : text.index(button_id)]
        assert PERMISSION_GATE in head, button_id

    # can_transfer(도면팀 AND 배정자)는 더 좁으므로 이 버튼의 게이트가 되면 안 된다.
    for button_id in (DESKTOP_ID, MOBILE_ID):
        head = text[max(0, text.index(button_id) - 200) : text.index(button_id)]
        assert "{% if can_transfer %}" not in head, button_id


def test_drawing_room_push_buttons_blocked_when_no_transferred_drawing():
    """전달본 0장이면 두 버튼 모두 disabled + 같은 안내 문구를 단다(함정 7)."""
    text = _template_text()

    assert text.count(EMPTY_GATE) == 2
    for button_id in (DESKTOP_ID, MOBILE_ID):
        tail = text[text.index(button_id) : text.index(button_id) + 300]
        assert EMPTY_GATE in tail, button_id
        assert EMPTY_MESSAGE in tail, button_id


def test_drawing_room_push_handler_calls_shared_contract():
    """전송은 기존 라우트에 push_kind='drawing_room' 으로 나가고 재전송 회수 규약을 지킨다."""
    text = _template_text()

    assert "push_kind: 'drawing_room'" in text
    assert "'/api/channel/push-manual'" in text
    assert "재전송 시 변경 내용" in text
    assert "change_note" in text
    assert "!data.success" in text
    # 본문·첨부는 서버가 조립한다 — 클라이언트가 text/attachment_ids 를 보내면 안 된다.
    handler = text[text.index("async function sendDrawingRoomPush") : text.index("async function pushDrawingRoom")]
    assert "attachment_ids" not in handler
    assert "text:" not in handler


def test_drawing_room_push_adds_no_document_level_listener():
    """프래그먼트 재실행 화면이라 전역 리스너를 늘리면 안 된다(perf 가드 G4)."""
    text = _template_text()

    assert text.count("document.addEventListener(") == BASELINE_DOCUMENT_LISTENERS

    start = text.index("async function pushDrawingRoom")
    end = text.index("dw-btn-drawing-room-push-mobile')?.addEventListener")
    added_block = text[start:end]
    assert "document.addEventListener(" not in added_block
    assert "getElementById('dw-btn-drawing-room-push')?.addEventListener" in text
    assert "getElementById('dw-btn-drawing-room-push-mobile')?.addEventListener" in text


def test_drawing_room_push_does_not_move_static_asset_pins():
    """이 파일의 ?v= 핀은 해당 .js 를 실제로 고칠 때만 움직인다.

    drawing-handoff.js 핀은 2026-09-12 에 한 번 움직였다 — 모바일 도면 미리보기가
    한 장만 열던 것을 주문의 도면 전체를 넘길 수 있게 고치면서 파일이 바뀌었고,
    캐시 무효화를 위해 함께 올렸다(핀을 안 올리면 옛 스크립트가 그대로 뜬다).

    2026-09-13: focusTimeline 가시성 결함 수정 + 리본 CSS 반영을 위해 범프.
    """
    text = _template_text()

    assert "filename='js/drawing/order-change-banner.js') }}?v=20260913a" in text
    assert "filename='js/foms/drawing-handoff.js') }}?v=20260912a" in text


def _login_drawing_admin(client) -> User:
    """도면팀 관리자로 로그인시키고 그 사용자를 돌려준다."""
    user = User(
        username="drawing_room_push_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="DRAWING",
        name="Drawing Room Push Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _drawing_order(current_files: list) -> Order:
    """현재 전달본 파일 목록만 다른 도면 주문을 만든다."""
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="도면방 PUSH 고객",
        phone="010-3333-4444",
        address="Seoul",
        product="붙박이장",
        status="DRAWING",
        manager_name="담당A",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "도면방 PUSH 고객"}},
            "workflow": {"stage": "DRAWING"},
            "drawing": {"status": "TRANSFERRED" if current_files else "IN_PROGRESS"},
            "drawing_current_files": current_files,
            "drawing_transfer_history": [],
            "drawing_assignees": [],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_drawing_room_push_button_renders_enabled_with_transferred_files(client):
    """전달본이 있으면 상세 화면에 두 버튼이 활성 상태로 렌더된다."""
    _login_drawing_admin(client)
    order = _drawing_order(
        [
            {
                "key": "drawings/room-a.png",
                "filename": "room-a.png",
                "view_url": "/api/files/view/drawings/room-a.png",
            }
        ]
    )

    body = client.get(f"/erp/drawing-workbench/{order.id}").get_data(as_text=True)

    assert DESKTOP_ID in body
    assert MOBILE_ID in body
    desktop = body[body.index(DESKTOP_ID) : body.index(DESKTOP_ID) + 200]
    assert "disabled" not in desktop


def test_drawing_room_push_button_renders_disabled_without_transferred_files(client):
    """전달본이 0장이면 두 버튼 모두 disabled 로 렌더되고 안내 문구가 붙는다."""
    _login_drawing_admin(client)
    order = _drawing_order([])

    body = client.get(f"/erp/drawing-workbench/{order.id}").get_data(as_text=True)

    for button_id in (DESKTOP_ID, MOBILE_ID):
        assert button_id in body
        tail = body[body.index(button_id) : body.index(button_id) + 200]
        assert "disabled" in tail, button_id
        assert EMPTY_MESSAGE in tail, button_id
