"""PARTNER-AS-02: 협력사 AS 접수 · 수정 — 판정 · 접수 창 값 · AS방 PUSH 머리말.

협력사 고객의 AS 는 협력사를 통해서만 받는다(사용자 결정 2026-10-08). 쓰기는 API 층이 **본사 접수 정본**
(``foms/api/cs/as_orders.py`` ``register_as_from_payload``)을 그대로 부른다 — 새 건이면 ``register_as_cycle``,
열린 건이면 같은 건 갱신. 이 모듈은 그 앞뒤의 협력사 몫(언제 열리나 · 무슨 글 · AS방 머리말)만 정한다
(services 는 api 를 부르지 않는다: 층 의존 규칙).

설계서: docs/specs/2026-11-13-partner-as-intake-edit-push_SPEC.md (1판: 2026-10-08-partner-portal_SPEC.md §14)
"""
from __future__ import annotations

import datetime
from typing import Any

from foms.services.as_content_safety import as_content_html_to_text
from foms.services.orders.as_cycle_service import AS_IN_PROGRESS, AS_RECEIVED, current_cycle, cycle_status
from foms.services.orders.as_cycle_view import (
    current_cycle_ordinal,
    last_closed_cycle_summary,
    with_cycle_detail_extras,
)
from foms.services.orders.as_log import current_reception_entry
from foms.services.partners.channel_push import sent_label

MAX_CONTENT = 2000
MAX_CHANGE_NOTE = 500
# AS 를 받을 수 있는 단계 — 시공이 시작된 뒤(우리가 시공을 간다).
AS_OPEN_STAGES = frozenset({"CONSTRUCTION", "CS", "COMPLETED", "AS", "AS_RECEIVED", "AS_COMPLETED"})
OPEN_STATUSES = (AS_RECEIVED, AS_IN_PROGRESS)

MODE_NEW = "new"            # 처음 접수
MODE_REINTAKE = "reintake"  # 지난 AS 가 끝난 뒤 새 건(2번째 AS …)
MODE_EDIT = "edit"          # 진행 중인 건 고치기(AS 끝나기 전까지 — 사용자 2026-11-13)

PARTNER_TAIL = " (협력사)"
SYSTEM_TEXT_NEW = "AS 접수됨 (협력사)"
SYSTEM_TEXT_EDIT = "AS 접수 수정됨 (협력사)"
REF_LINE_PREFIX = "[완공 사진 참고] "
# AS PUSH 이력 칸 — 본사 AS PUSH 와 같은 칸(channel_integration._PUSH_KIND_CONFIG['as']).
PUSH_HISTORY_KEY = "channeltalk_push_as"
DEFAULT_RESEND_NOTE = "협력사가 접수 내용을 다시 보냈습니다"


class PartnerASError(ValueError):
    """협력사 화면에 그대로 보여 줄 수 있는 거부 사유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def _sd(order: Any) -> dict:
    sd = getattr(order, "structured_data", None)
    return sd if isinstance(sd, dict) else {}


def as_mode(order: Any) -> str | None:
    """지금 협력사가 할 수 있는 AS 일. 열린 건이 있으면 고치기, 시공 뒤면 접수 · 재접수, 아니면 None."""
    sd = _sd(order)
    cycle = current_cycle(sd)
    if cycle is not None and cycle_status(cycle) in OPEN_STATUSES:
        return MODE_EDIT
    if (getattr(order, "erp_stage_code", None) or "").upper() not in AS_OPEN_STAGES:
        return None
    return MODE_REINTAKE if last_closed_cycle_summary(sd) is not None else MODE_NEW


def clean_content(raw: Any) -> str:
    text = str(raw or "").strip()[:MAX_CONTENT]
    if not text:
        raise PartnerASError("AS 내용을 적어 주세요.", 400)
    return text


def clean_change_note(raw: Any) -> str:
    note = str(raw or "").strip()[:MAX_CHANGE_NOTE]
    if not note:
        raise PartnerASError("바뀐 내용을 한 줄 적어 주세요. AS방에 [수정]으로 같이 갑니다.", 400)
    return note


def reception_text(text: str, ref_photos: list[tuple[int, str]]) -> str:
    """접수 원문 — 고른 완공 사진이 있으면 이름을 한 줄 덧붙인다(우리 AS 화면 · AS방 글에서 바로 보이게)."""
    if not ref_photos:
        return text
    return f"{text}\n{REF_LINE_PREFIX}" + ", ".join(name for _id, name in ref_photos)


def _split_ref_line(text: str) -> str:
    """고치기 창에 채울 글 — 끝의 "[완공 사진 참고]" 줄은 뺀다(저장 때 같은 사진으로 다시 붙인다)."""
    lines = text.rstrip().split("\n")
    if lines and lines[-1].startswith(REF_LINE_PREFIX.strip()):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def current_reception(order: Any) -> dict | None:
    return current_reception_entry(_sd(order))


def current_content(order: Any) -> str:
    """현재 건 접수 글(협력사 화면에 보일 평문)."""
    entry = current_reception(order)
    if not entry:
        return ""
    return _split_ref_line(as_content_html_to_text(entry.get("text"), already_sanitized=True))


def edit_carry(order: Any) -> tuple[str, dict | None]:
    """고치기 때 앞 접수 줄에서 이어 갈 것 — 글 끝에 다시 붙일 완공 사진 줄, 접수 줄 ``ref_attachment_ids``."""
    entry = current_reception(order) or {}
    ref_ids = [i for i in entry.get("ref_attachment_ids") or [] if isinstance(i, int)]
    text = as_content_html_to_text(entry.get("text"), already_sanitized=True).rstrip()
    last = text.split("\n")[-1] if text else ""
    ref_line = last if last.startswith(REF_LINE_PREFIX.strip()) else ""
    return ref_line, ({"ref_attachment_ids": ref_ids} if ref_ids else None)


def _utc(raw: Any) -> datetime.datetime | None:
    try:
        at = datetime.datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo else at.replace(tzinfo=datetime.timezone.utc)


def push_status(order: Any) -> dict[str, Any]:
    """AS방 줄 — 보낸 적 · 마지막 시각 · 보낼 게 남았나(지금 접수 줄이 마지막 PUSH 보다 새것)."""
    sd = _sd(order)
    history = sd.get(PUSH_HISTORY_KEY) if isinstance(sd.get(PUSH_HISTORY_KEY), dict) else {}
    pushed = bool(history.get("pushed"))
    entry = current_reception_entry(sd)
    sent, written = _utc(history.get("sent_at")), _utc((entry or {}).get("ts"))
    needs = bool(entry) and (not pushed or (written is not None and (sent is None or written > sent)))
    return {"pushed": pushed, "sent_label": sent_label(history.get("sent_at")) if pushed else "", "needs_push": needs}


def push_change_note(order: Any, given: str = "") -> str:
    """AS방 재전송 머리말([수정] 아래 줄). 처음 보내면 빈 문자열.

    AS PUSH 이력 칸은 주문마다 하나라 2번째 AS 의 첫 PUSH 도 본사처럼 재전송이다(설계서 D7) — 이 건이 열린 뒤
    보낸 적이 없으면 "새 AS 접수 (N번째 AS)"로 가른다.
    """
    sd = _sd(order)
    history = sd.get(PUSH_HISTORY_KEY) if isinstance(sd.get(PUSH_HISTORY_KEY), dict) else {}
    if not history.get("pushed"):
        return ""
    cycle = current_cycle(sd) or {}
    opened, sent = _utc(cycle.get("opened_at")), _utc(history.get("sent_at"))
    if opened is not None and sent is not None and sent < opened:
        return f"새 AS 접수 ({current_cycle_ordinal(sd)}번째 AS)"
    return given or DEFAULT_RESEND_NOTE


def _prev_view(order: Any) -> dict | None:
    """지난 AS 요약(재접수 창) — 본사 창과 같은 줄이되 비용은 뺀다(우리 몫)."""
    sd = _sd(order)
    summary = with_cycle_detail_extras(sd, last_closed_cycle_summary(sd))
    if not summary:
        return None
    return {
        "ordinal": summary.get("ordinal") or 0,
        "received": summary.get("received_date") or "",
        "completed": summary.get("completed_date") or "",
        "symptom": summary.get("symptom_text") or "",
        "rounds": summary.get("max_round") or 0,
    }


def form_view(order: Any) -> dict[str, Any]:
    """접수 창 값(완공 사진 주소는 웹 · API 층이 붙인다)."""
    mode = as_mode(order)
    sd = _sd(order)
    ordinal = current_cycle_ordinal(sd)
    return {
        "mode": mode,
        "order_id": order.id,
        "customer_name": getattr(order, "customer_name", "") or "",
        "product": getattr(order, "product", "") or "",
        # 새 건이면 이번이 몇 번째 AS 인지(제목 "2번째 AS"), 고치기면 지금 건 순번.
        "cycle_no": ordinal if mode == MODE_EDIT else ordinal + 1 if mode == MODE_REINTAKE else 1,
        "content": current_content(order) if mode == MODE_EDIT else "",
        "prev": _prev_view(order) if mode == MODE_REINTAKE else None,
        "push": push_status(order),
    }
