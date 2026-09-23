"""채널톡 PUSH 발송 흔적 칩 계약 (2026-09-23).

PUSH 를 보내도 화면에 흔적이 남지 않았다(버튼 글자만 3초 '전송완료'). 서버는 이미
``structured_data['channeltalk_push*']`` 와 ``OrderEvent(CHANNELTALK_PUSH)`` 를 남기므로,
주문 화면은 그 사본만 읽어 칩을 그리고, 이력 화면은 이벤트를 한국어로 읽는다.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.order_event_display import (
    format_timeline_description,
    generate_change_description,
    translate_event_type_to_korean,
)
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
TRACE_JS = "static/js/orders/erp-channel-push-trace.js"
TRACE_CSS = "static/css/orders/erp-channel-push-trace.css"
PIN = "?v=20260923a"
CSS_PIN = "?v=20260923b"  # 2026-09-23: 모바일 흔적 한 줄


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --- 이벤트 라벨 ------------------------------------------------------------------


def test_channeltalk_push_event_has_korean_label() -> None:
    """'기타 변경' 으로 뭉개지면 PUSH 를 보냈는지 이력에서 찾을 수 없다."""
    assert translate_event_type_to_korean("CHANNELTALK_PUSH") == "채널톡 PUSH 발송"


def test_channeltalk_push_label_matches_server_event_type() -> None:
    """라벨 키는 서버가 실제로 쓰는 event_type 과 같아야 한다(오타면 조용히 기타 변경)."""
    from foms.api.channel import channel_integration

    assert channel_integration._PUSH_EVENT_TYPE == "CHANNELTALK_PUSH"


@pytest.mark.parametrize(
    ("push_kind", "label"),
    [
        ("measurement", "영발 PUSH"),
        ("measure_room", "실측 PUSH"),
        ("drawing", "발주 PUSH"),
        ("drawing_room", "도면방 PUSH"),
        ("estimate", "견적서 PUSH"),
        ("as", "AS PUSH"),
    ],
)
def test_channeltalk_push_description_names_kind(push_kind: str, label: str) -> None:
    payload = {"push_kind": push_kind, "is_resend": False, "message_id": "m1"}
    text = generate_change_description("CHANNELTALK_PUSH", "", "", "", payload)
    assert text == f"채널톡 {label}를 보냈습니다"
    # WAM 타임라인도 같은 문장(payload 에 from/to·message 가 없어 라벨로 떨어지던 자리).
    assert format_timeline_description("CHANNELTALK_PUSH", payload) == text


def test_channeltalk_push_description_marks_resend() -> None:
    payload = {"push_kind": "drawing", "is_resend": True}
    text = generate_change_description("CHANNELTALK_PUSH", "", "", "", payload)
    assert "발주 PUSH" in text and "재전송" in text


def test_channeltalk_push_description_unknown_kind_is_safe() -> None:
    text = generate_change_description("CHANNELTALK_PUSH", "", "", "", {})
    assert text == "채널톡 PUSH를 보냈습니다"


def test_server_push_kinds_all_have_labels() -> None:
    """서버에 종류가 늘면 라벨·칩 표기도 함께 늘어야 한다."""
    from foms.api.channel import channel_integration
    from foms.services import order_event_display

    kinds = set(channel_integration._PUSH_KIND_CONFIG) | {"estimate"}
    assert kinds <= set(order_event_display._CHANNEL_PUSH_KIND_LABELS)
    js = _read(TRACE_JS)
    history_keys = {cfg["history_key"] for cfg in channel_integration._PUSH_KIND_CONFIG.values()}
    history_keys.add(channel_integration._ESTIMATE_PUSH_HISTORY_KEY)
    for key in history_keys:
        assert f"key: '{key}'" in js, key


# --- 템플릿·자산 계약 ----------------------------------------------------------------


def test_pc_tab_has_push_trace_slot_under_push_buttons() -> None:
    html = _read("templates/orders/partials/erp_order_tab.html")
    assert "data-erp-channel-push-trace>" in html
    assert html.index('id="erp-channeltalk-push-as-btn"') < html.index("data-erp-channel-push-trace")


def test_mobile_tab_has_compact_push_trace_slot_in_action_bar() -> None:
    html = _read("templates/orders/partials/erp_order_tab_mobile.html")
    footer = html[html.index("erp-mobile-sticky-action-bar"):]
    bar = footer[: footer.index("</footer>")]
    assert 'data-erp-channel-push-trace="compact"' in bar
    assert "erp-channel-push-trace-slot--mobile" in bar
    # :empty 로 접히려면 자리 안에 공백조차 없어야 한다.
    assert re.search(r'data-erp-channel-push-trace="compact"></div>', bar)


def test_push_trace_assets_loaded_once_on_order_js_include() -> None:
    order_js = _read("templates/orders/partials/erp_order_js.html")
    for asset, pin in (("css/orders/erp-channel-push-trace.css", CSS_PIN),
                       ("js/orders/erp-channel-push-trace.js", PIN)):
        lines = [row for row in order_js.splitlines() if asset in row]
        assert len(lines) == 1, asset
        assert pin in lines[0], asset
    script_line = next(r for r in order_js.splitlines() if "js/orders/erp-channel-push-trace.js" in r)
    assert "defer" in script_line
    # 전역 레이아웃에도 실으면 같은 파일이 두 번 실행된다.
    assert "erp-channel-push-trace" not in _read("templates/partials/shared/layout_scripts.html")


def _login_admin(client, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="PUSH Trace Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_edit_page_renders_push_trace_slots_on_both_surfaces(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """실제 렌더: PC·모바일 두 표면 모두 칩 자리와 자산을 싣는다(코호트 게이트 포함)."""
    user = _login_admin(client, "push_trace_admin")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = Order(
        received_date=datetime.date.today().isoformat(),
        customer_name="PUSH 흔적 고객",
        phone="010-0000-3333",
        address="서울",
        product="붙박이장",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get(f"/edit/{order.id}?open=erp-order")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    legacy = html[html.index('id="erp-order-form-legacy"'):html.index('id="erp-order-form-mobile"')]
    mobile = html[html.index('id="erp-order-form-mobile"'):]
    assert "data-erp-channel-push-trace>" in legacy
    assert 'data-erp-channel-push-trace="compact"' in mobile
    assert "js/orders/erp-channel-push-trace.js" + PIN in html
    assert "css/orders/erp-channel-push-trace.css" + CSS_PIN in html


# --- JS 계약 --------------------------------------------------------------------------


def test_trace_js_renders_from_structured_data_without_fetch() -> None:
    """칩은 화면이 이미 든 구조화 데이터로만 그린다 — 렌더에 서버 왕복이 없다."""
    js = _read(TRACE_JS)
    assert "window.__FOMS_CHANNEL_PUSH_TRACE_BOUND" in js
    assert "window.__erpLastStructuredData" in js
    assert "fetch(" not in js
    assert "foms:erp-structured-loaded" in js
    assert "foms:channel-push-trace-update" in js
    assert "window.erpChannelPushTraceRender" in js


def test_trace_js_mobile_hides_never_sent_chip() -> None:
    """모바일 축약형은 미발송 칩을 만들지 않는다(2026-09-21 좁은 액션바 제보)."""
    js = _read(TRACE_JS)
    assert "if (!compact) slot.appendChild(_buildNoneChip());" in js
    css = _read(TRACE_CSS)
    assert ".erp-channel-push-trace-slot:empty" in css
    assert "display: none" in css.split(".erp-channel-push-trace-slot:empty")[1].split("}")[0]


def test_trace_js_labels_match_push_buttons() -> None:
    js = _read(TRACE_JS)
    for label in ("영발 PUSH", "발주 PUSH", "실측 PUSH", "AS PUSH", "견적서 PUSH", "' 보냄'",
                  "PUSH 아직 안 보냄"):
        assert label in js, label


def test_trace_css_has_states_and_no_inline_style_in_js() -> None:
    css = _read(TRACE_CSS)
    for state in ("--sent", "--none"):
        assert ".erp-channel-push-trace" + state in css
    assert ".style." not in _read(TRACE_JS)


def test_mark_sent_updates_sent_at_and_announces() -> None:
    """발송 성공 직후 사본의 sent_at 을 고치고 칩에 알린다(추가 조회 없음)."""
    js = _read("static/js/orders/erp-channel-push-confirm.js")
    assert "function erpMarkChannelPushSent(pushKind, sentAt)" in js
    assert "next.sent_at = sentAt;" in js
    assert "foms:channel-push-trace-update" in js


def test_success_paths_pass_sent_time_but_resend_recovery_does_not() -> None:
    """실제 발송 성공만 시각을 넘긴다 — '재전송 메모 필요' 응답은 이미 보낸 기록일 뿐이다."""
    shared = _read("static/js/orders/erp-order-shared.js")
    assert shared.count("erpMarkChannelPushSent(pushKind, new Date().toISOString())") == 2
    assert shared.count("erpMarkChannelPushSent(pushKind);") == 1
    estimate = _read("static/js/orders/estimate-preview.js")
    assert estimate.count("erpMarkChannelPushSent('estimate', new Date().toISOString())") == 1
    assert estimate.count("erpMarkChannelPushSent('estimate');") == 1


def test_mobile_trace_chips_share_one_row() -> None:
    """모바일: 알림톡·PUSH 흔적이 두 줄로 쌓이지 않고 버튼 위 한 줄에 나란히 선다(2026-09-23 사용자 요청)."""
    html = _read("templates/orders/partials/erp_order_tab_mobile.html")
    footer = html[html.index("erp-mobile-sticky-action-bar"):]
    bar = footer[: footer.index("</footer>")]
    row = bar[bar.index("data-erp-mobile-trace-row"):]
    row = row[: row.index("<button")]
    assert 'data-erp-alimtalk-trace="compact"' in row
    assert 'data-erp-channel-push-trace="compact"' in row
    css = _read(TRACE_CSS)
    block = css.split(".erp-mobile-trace-row {")[1].split("}")[0]
    assert "flex: 1 0 100%" in block and "display: flex" in block
    # 두 자리는 한 줄 안에서 폭을 나눠 갖는다(각자 100% 를 차지하면 다시 두 줄이 된다).
    assert "flex: 0 1 auto" in css.split(".erp-mobile-trace-row > .erp-channel-push-trace-slot--mobile {")[1].split("}")[0]
    # 둘 다 비면 줄째 접힌다.
    assert (".erp-mobile-trace-row:not(:has(.erp-alimtalk-trace:not(.erp-alimtalk-trace--none), "
            ".erp-channel-push-trace)) {\n  display: none;") in css
    # 둘 다 있으면 시각을 빼서 이름이 읽히게 한다.
    assert ".erp-channel-push-trace__when) {\n  display: none;" in css


def test_drawing_room_push_trace_survives_save_and_draft_restore() -> None:
    """도면방 PUSH 는 주문 화면이 보내지 않는 서버 소유 기록이다 — 저장·이어쓰기 뒤에도 칩이 남아야 한다.

    PUT 에 되싣는 preservedTopLevelKeys 가 아니라 화면 사본에만 옮겨 담는 목록에 둔다(실으면 마법사가
    그 사이 쓴 기록을 덮는다). 서버는 _OPERATIONAL_TOP_LEVEL_KEYS 로 이미 지킨다.
    """
    shared = _read("static/js/orders/erp-order-shared.js")
    local_only = shared.split("var ERP_LOCAL_ONLY_TRACE_KEYS = [")[1].split("]")[0]
    assert "'channeltalk_push_drawing_room'" in local_only
    preserved = shared.split("const preservedTopLevelKeys = [")[1].split("]")[0]
    assert "channeltalk_push_drawing_room" not in preserved
    server = _read("foms/api/erp_orders_structured.py")
    assert "'channeltalk_push_drawing_room'," in server
    autosave = _read("static/js/orders/erp-order-autosave.js")
    restore = autosave[: autosave.index("window.__erpLastStructuredData = sd;")]
    assert "window.erpCarryLocalOnlyKeys(sd, window.__erpLastStructuredData);" in restore[-400:]
