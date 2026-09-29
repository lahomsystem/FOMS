"""도면 수정요청 출처·받은 경로 + 수령 확정의 고객 OK 기록(설계서 2026-09-29 §4.1 · §4.2).

수정요청 본문의 선택 키 ``source``(``customer``·``sales``)·``received_via``(``phone``·``kakao``·
``store``)는 **엄격**하다 — 목록 밖 값이면 쓰기 전에 400(``INVALID_REVISION_SOURCE``). 키가
없거나 null 이면 지금과 같은 항목을 쓴다(태블릿 도면 검토·ERP 대시보드는 안 보낸다). 옛
항목(키 없음)은 영업 의견으로 본다.

수령 확정의 고객 OK 기록(``customer_ok``·``customer_ok_via``·``customer_ok_note``)은 **너그럽다** —
설명용 값이라 이상하면 버리고 확정은 진행한다.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

SOURCE_CUSTOMER = "customer"
SOURCE_SALES = "sales"
REVISION_SOURCES: tuple[str, ...] = (SOURCE_CUSTOMER, SOURCE_SALES)

#: 받은 경로 코드 → 화면 이름(수정요청 받은 경로 · 고객 OK 확인 경로 공용).
RECEIVED_VIA_LABELS: dict[str, str] = {"phone": "전화", "kakao": "카톡 답장", "store": "매장 방문"}

INVALID_REVISION_SOURCE = "INVALID_REVISION_SOURCE"

#: 고객 OK 메모 최대 길이(넘으면 자른다).
CUSTOMER_OK_NOTE_MAX = 200

_CUSTOMER_OK_KEYS = ("customer_ok", "customer_ok_via", "customer_ok_note")


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def parse_revision_source(data: Any) -> tuple[dict[str, str], str | None]:
    """수정요청 본문에서 출처·받은 경로를 읽는다.

    Returns:
        ``(이력 항목에 더할 필드, 오류 코드)``. 키가 없거나 null·빈 문자열이면 ``({}, None)``.
        값이 목록 밖(문자열이 아닌 값 포함)이면 ``({}, INVALID_REVISION_SOURCE)``.
        ``source="sales"`` 거나 출처가 없으면 받은 경로는 버린다(고객 요청에만 뜻이 있다).
    """
    if not isinstance(data, Mapping):
        return {}, None
    source = data.get("source")
    via = data.get("received_via")
    if not _blank(source) and (not isinstance(source, str) or source.strip() not in REVISION_SOURCES):
        return {}, INVALID_REVISION_SOURCE
    if not _blank(via) and (not isinstance(via, str) or via.strip() not in RECEIVED_VIA_LABELS):
        return {}, INVALID_REVISION_SOURCE
    if _blank(source):
        return {}, None
    fields = {"source": source.strip()}
    if fields["source"] == SOURCE_CUSTOMER and not _blank(via):
        fields["received_via"] = via.strip()
    return fields, None


def is_customer_request(entry: Any) -> bool:
    """이력 항목이 고객 요청인가(옛 항목·영업 의견은 False)."""
    return isinstance(entry, Mapping) and entry.get("source") == SOURCE_CUSTOMER


def received_via_label(entry: Any) -> str:
    """받은 경로 화면 이름(없거나 모르는 값이면 "")."""
    if not isinstance(entry, Mapping):
        return ""
    return RECEIVED_VIA_LABELS.get(str(entry.get("received_via") or ""), "")


def revision_source_tag(entry: Any, round_no: int) -> str:
    """고객 요청이면 "고객 요청 · 1차 · 카톡 답장"(받은 경로 없으면 생략), 아니면 ""."""
    if not is_customer_request(entry):
        return ""
    parts = ["고객 요청"]
    if round_no and round_no > 0:
        parts.append(f"{round_no}차")
    via = received_via_label(entry)
    if via:
        parts.append(via)
    return " · ".join(parts)


def notification_title(fields: Any, *, edited: bool = False) -> str:
    """도면팀 알림 제목 — 고객 요청이면 "고객 요청 · 도면 수정". 고치기면 "수정요청 고침"."""
    customer = is_customer_request(fields)
    if edited:
        return "고객 요청 · 수정요청 고침" if customer else "도면 수정요청 고침"
    return "고객 요청 · 도면 수정" if customer else "도면 수정 요청"


def notification_message_prefix(fields: Any) -> str:
    """알림 메시지 앞머리 — "[고객 요청 · 카톡 답장] " / "[고객 요청] " / ""."""
    if not is_customer_request(fields):
        return ""
    via = received_via_label(fields)
    return f"[고객 요청 · {via}] " if via else "[고객 요청] "


def request_rounds(history: Any) -> dict[int, int]:
    """이력의 REQUEST_REVISION 위치 → 그 요청이 가리킨 회차.

    회차 규칙은 :func:`~foms.services.orders.drawing_customer_send.drawing_round_info` 와 같다 —
    요청 시점의 회차 = 1 + 그 요청 앞 마지막 TRANSFER 보다 앞선 수정요청 수. 전달 앞 요청은 0.
    """
    out: dict[int, int] = {}
    if not isinstance(history, list):
        return out
    requests_seen = 0
    round_now = 0
    for idx, h in enumerate(history):
        if not isinstance(h, Mapping):
            continue
        action = h.get("action")
        if action == "TRANSFER":
            round_now = 1 + requests_seen
        elif action == "REQUEST_REVISION":
            out[idx] = round_now
            requests_seen += 1
    return out


def attach_customer_ok(sd: Any, body: Any) -> None:
    """마지막 ``CONFIRM_RECEIPT`` 이력 항목에 ``customer_ok`` 를 붙인다(제자리 수정).

    본문에 고객 OK 키가 하나도 없으면 아무것도 안 한다(지금과 같은 항목). 목록 밖 ``via`` 는
    버리고(경고 로그 1줄), 메모는 문자열일 때만 200자로 잘라 남긴다. 호출자는 ``sd`` 를 이미
    deepcopy 한 사본으로 넘긴다(``drawing_receipt_command.write_receipt_structured``).
    """
    if not isinstance(sd, dict) or not isinstance(body, Mapping):
        return
    if not any(key in body for key in _CUSTOMER_OK_KEYS):
        return
    history = sd.get("drawing_transfer_history")
    if not isinstance(history, list):
        return
    target = next((h for h in reversed(history)
                   if isinstance(h, dict) and h.get("action") == "CONFIRM_RECEIPT"), None)
    if target is None:
        return
    via_raw = body.get("customer_ok_via")
    via = via_raw.strip() if isinstance(via_raw, str) and via_raw.strip() in RECEIVED_VIA_LABELS else None
    if via is None and not _blank(via_raw):
        logger.warning("customer_ok_via 목록 밖 값을 버림: %r", via_raw)
    note_raw = body.get("customer_ok_note")
    note = note_raw.strip()[:CUSTOMER_OK_NOTE_MAX] if isinstance(note_raw, str) else ""
    target["customer_ok"] = {
        "confirmed_by_customer": bool(body.get("customer_ok")),
        "via": via,
        "note": note,
    }


__all__ = [
    "CUSTOMER_OK_NOTE_MAX",
    "INVALID_REVISION_SOURCE",
    "RECEIVED_VIA_LABELS",
    "REVISION_SOURCES",
    "SOURCE_CUSTOMER",
    "SOURCE_SALES",
    "attach_customer_ok",
    "is_customer_request",
    "notification_message_prefix",
    "notification_title",
    "parse_revision_source",
    "received_via_label",
    "request_rounds",
    "revision_source_tag",
]
