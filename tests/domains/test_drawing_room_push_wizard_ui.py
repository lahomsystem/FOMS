"""도면 마법사 [도면방 PUSH] 프론트 계약 (W3).

마법사 앱바에 `#dws-btn-room-push` 가 렌더되고, `static/js/drawing/wizard.js` 가
기존 채널톡 라우트 2개(`/api/channel/push-preview`, `/api/channel/push-manual`)만
`push_kind='drawing_room'` 으로 부르는지 문자·렌더 계약으로 못박는다.

백엔드(W1) 완성 여부와 무관하게 통과해야 한다 — 여기서는 실제 전송을 하지 않는다.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

REPO_ROOT = Path(__file__).resolve().parents[2]
WIZARD_TPL = REPO_ROOT / "templates" / "drawing" / "wizard.html"
WIZARD_JS = REPO_ROOT / "static" / "js" / "drawing" / "wizard.js"

#: wizard.js 안에서 호출하는 채널톡 라우트(신규 라우트 신설 금지 — 이 2개뿐).
_CHANNEL_URL_RE = re.compile(r"/api/channel/[A-Za-z0-9_\-/]+")
_ALLOWED_CHANNEL_URLS = {"/api/channel/push-preview", "/api/channel/push-manual"}


def _login_admin(client, username="wizard-room-push-admin"):
    """도면팀 관리자로 로그인시킨다(마법사 편집 권한 = can_save True)."""
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="DRAWING",
        name="도면관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _erp_order():
    """마법사 렌더에 필요한 최소 ERP 주문 1건."""
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="서으뜸",
        phone="010-1111-2222",
        address="대구",
        product="붙박이장",
        status="DRAWING",
        manager_name="하우드 김성일",
        is_erp_order=True,
        structured_data={"parties": {"customer": {"name": "서으뜸"}}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _wizard_body(client):
    """마법사 페이지를 200 으로 받아 본문 텍스트를 돌려준다."""
    _login_admin(client)
    order = _erp_order()
    resp = client.get(f"/erp/drawing-workbench/{order.id}/wizard")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_wizard_appbar_has_drawing_room_push_button(client):
    """앱바에 [도면방 PUSH] 버튼(#dws-btn-room-push)이 렌더된다."""
    body = _wizard_body(client)

    assert 'id="dws-btn-room-push"' in body
    assert "도면방 PUSH" in body


def test_room_push_button_is_edit_gated(client):
    """열람 전용 자동 잠금 축 — 버튼 줄에 dws-edit-ctl 클래스가 있다.

    applyPermissions() 가 `.dws-edit-ctl` 을 can_save 로 일괄 disabled 처리하므로
    새 권한 축을 만들지 않는다.
    """
    body = _wizard_body(client)

    button_line = next(
        line for line in body.splitlines() if 'id="dws-btn-room-push"' in line
    )
    assert "dws-edit-ctl" in button_line


def test_wizard_js_asset_pin_bumped() -> None:
    """wizard.js 내용이 바뀌었으므로 ?v= 핀을 올렸다(SW staticCacheFirst 스테일 봉합).

    2026-09-11: 자동저장 하이드레이션 가드(hydrated·userDirty·autosaveSuspended)를
    넣으면서 wizard.js 가 바뀌었다 — 스테일 캐시가 옛 자동저장을 계속 돌리면
    가드가 없는 것과 같으므로 핀을 함께 올린다.
    """
    tpl = WIZARD_TPL.read_text(encoding="utf-8")

    assert "js/drawing/wizard.js') }}?v=20260910a" not in tpl
    assert "js/drawing/wizard.js') }}?v=20260911a" in tpl


def test_wizard_js_calls_push_manual_and_preview_with_drawing_room_kind() -> None:
    """전송·사전점검 호출이 계약된 push_kind 와 기존 라우트 2개를 쓴다."""
    js = WIZARD_JS.read_text(encoding="utf-8")

    assert "push_kind: 'drawing_room'" in js
    assert "'/api/channel/push-manual'" in js
    assert "'/api/channel/push-preview?order_id='" in js
    assert "push_kind=drawing_room" in js


def test_wizard_js_has_resend_change_note_recovery() -> None:
    """재전송 회수 규약 — 서버 문구 '재전송 시 변경 내용' 감지 후 change_note 1회 재시도."""
    js = WIZARD_JS.read_text(encoding="utf-8")

    assert "'재전송 시 변경 내용'" in js
    assert "payload.change_note = changeNote" in js


def test_wizard_js_introduces_no_new_channel_route() -> None:
    """신규 라우트 신설 금지 — wizard.js 가 부르는 채널톡 URL 은 허용 2개뿐이다."""
    js = WIZARD_JS.read_text(encoding="utf-8")

    found = set(_CHANNEL_URL_RE.findall(js))
    assert found == _ALLOWED_CHANNEL_URLS, f"예상 밖 채널톡 URL: {sorted(found - _ALLOWED_CHANNEL_URLS)}"
