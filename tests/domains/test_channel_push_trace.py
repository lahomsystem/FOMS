"""채널톡 PUSH 발송 흔적 계약 (2026-09-23) — 이벤트 라벨·사본 갱신.

칩 표시는 알림톡과 합쳐 erp-send-trace.js 가 그린다(tests/domains/test_send_trace.py).

PUSH 를 보내도 화면에 흔적이 남지 않았다(버튼 글자만 3초 '전송완료'). 서버는 이미
``structured_data['channeltalk_push*']`` 와 ``OrderEvent(CHANNELTALK_PUSH)`` 를 남기므로,
주문 화면은 그 사본만 읽어 칩을 그리고, 이력 화면은 이벤트를 한국어로 읽는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from foms.services.order_event_display import (
    format_timeline_description,
    generate_change_description,
    translate_event_type_to_korean,
)

ROOT = Path(__file__).resolve().parents[2]
TRACE_JS = "static/js/orders/erp-send-trace.js"


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


# --- PUSH 사본 갱신 계약 (칩은 tests/domains/test_send_trace.py) ----------------------


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
