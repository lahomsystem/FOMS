"""협력사 주문 화면 영발 · 발주 PUSH — 보낼 글 · 버튼 상태(사용자 결정 2026-10-29).

본사는 시공 스케줄을 채널톡 영발방 · 발주방을 보고 짠다. 협력사 주문도 같은 방에 같은 모양으로 들어가야 한다.
글은 서버가 저장된 주문으로 만든다(협력사 화면엔 ERP 폼이 없다) — PC 변환 글의 서버판
:func:`build_measure_push_text` 에 영발 · 발주 자르기(:func:`slice_for_channel_push`)를 건다. 확정 전 협력사
희망 시공일은 '시공일' 줄에 '협력사 희망 … · 확정 대기'로 싣는다(스케줄 짜는 데 필요하다).

언제: 영발은 처음 저장할 때 묻고(고칠 수 있으니) 그 뒤엔 버튼, 발주는 "이대로 만들어 주세요" 뒤에 자동으로
한 번 보내고 다시 보내기는 버튼. 보내기 자체는 ERP 와 같은 ``run_manual_push``(API 층)다 — 이력 칸도 같아서
ERP 에서 보낸 뒤 협력사가 누르면(또는 그 반대) 재전송으로 본다.
스펙: docs/specs/2026-10-29-partner-channel-push_SPEC.md
"""
from __future__ import annotations

import datetime
from typing import Any

from foms.services.channel_as_message import format_schedule_date_korean
from foms.services.channel_measure_message import build_measure_push_text, slice_for_channel_push
from foms.services.partners.schedule_request import pending_request

#: 협력사가 쓰는 PUSH 종류 → (이력 칸 — ERP 와 같다, 화면 이름).
KINDS = {
    "measurement": ("channeltalk_push", "영발"),
    "drawing": ("channeltalk_push_drawing", "발주"),
}
# 승인 단추 글자("이대로 만들어 주세요")를 그대로 쓰지 않는다 — 그 글자가 화면에 있으면 승인 차례로 읽힌다.
DRAWING_CLOSED_REASON = "도면 승인(제작 요청) 뒤에 보낼 수 있습니다."
_NO_CONSTRUCTION_LINE = "시공일 : 상담"
_KST = datetime.timezone(datetime.timedelta(hours=9))


def _sd(order: Any) -> dict:
    return order.structured_data if isinstance(order.structured_data, dict) else {}


def drawing_push_open(sd: dict) -> bool:
    """발주 PUSH 를 열까 — 협력사가 "이대로 만들어 주세요"로 도면을 확정했을 때만."""
    blueprint = sd.get("blueprint") if isinstance(sd.get("blueprint"), dict) else {}
    return bool(blueprint.get("customer_confirmed"))


def build_partner_push_text(order: Any) -> str:
    """영발 · 발주방에 보낼 글(두 방 같은 글 — ERP 와 같다)."""
    sd = _sd(order)
    text = slice_for_channel_push(build_measure_push_text(sd))
    request = pending_request(sd, getattr(order, "erp_stage_code", None) or "")
    if request:
        wish = " ".join(v for v in (format_schedule_date_korean(request.get("date")), str(request.get("time") or "")) if v)
        text = text.replace(_NO_CONSTRUCTION_LINE, f"시공일 : 협력사 희망 {wish} · 확정 대기", 1)
    return text


def _sent_label(raw: Any) -> str:
    """이력의 UTC 시각 → '10/29 14:05'(한국 시간). 읽지 못하면 빈 문자열."""
    try:
        at = datetime.datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return ""
    if at.tzinfo is None:
        at = at.replace(tzinfo=datetime.timezone.utc)
    at = at.astimezone(_KST)
    return f"{at.month}/{at.day} {at:%H:%M}"


def push_state(order: Any) -> dict[str, dict[str, Any]]:
    """종류별 {pushed, sent_label, open, reason} — 화면 버튼과 API 가 같은 판정을 쓴다."""
    sd = _sd(order)
    state = {}
    for kind, (history_key, _label) in KINDS.items():
        history = sd.get(history_key) if isinstance(sd.get(history_key), dict) else {}
        is_open = kind != "drawing" or drawing_push_open(sd)
        state[kind] = {
            "pushed": bool(history.get("pushed")),
            "sent_label": _sent_label(history.get("sent_at")) if history.get("pushed") else "",
            "open": is_open,
            "reason": "" if is_open else DRAWING_CLOSED_REASON,
        }
    return state
