"""협력사 주문 칸의 영발·발주 PUSH 표시 상태."""

from __future__ import annotations

from typing import Any

from foms.services.datetime_kst import format_datetime_kst

_MEASURE_KEY = "channeltalk_push"
_DRAWING_KEY = "channeltalk_push_drawing"


def partner_channel_push_marks(structured_data: Any) -> list[dict[str, str]]:
    """영발(영발방)과 발주(발주방) PUSH 중 보낸 것만 칸으로 만든다.

    협력사 주문에서만 그린다. 안 보낸 종류는 칸을 만들지 않는다.
    두 번째부터는 라벨에 ``2번째`` 처럼 보낸 차례를 붙인다.

    Args:
        structured_data: 주문 structured_data. dict 가 아니면 빈 목록.

    Returns:
        보낸 항목만. 각 항목은 label, state(``sent`` | ``stale``),
        mark(``check`` | ``none``), title, aria.
    """
    sd = structured_data if isinstance(structured_data, dict) else {}
    slots = [
        _push_slot("영발", sd.get(_MEASURE_KEY), allow_stale=False),
        _push_slot("발주", sd.get(_DRAWING_KEY), allow_stale=True),
    ]
    return [slot for slot in slots if slot is not None]


def _push_slot(label: str, record: Any, *, allow_stale: bool) -> dict[str, str] | None:
    """PUSH 이력 하나 → 표시 칸. 안 보냈으면 ``None``.

    Args:
        label: 칸에 보일 이름.
        record: ``structured_data`` 이력. dict 가 아니면 미발송.
        allow_stale: 발주만 도면 변경(``stale_drawing_at``)을 붉은 칸으로 본다.

    Returns:
        label, state, mark, title, aria. 미발송이면 ``None``.
    """
    rec = record if isinstance(record, dict) else {}
    if not (rec.get("pushed") or rec.get("sent_at")):
        return None
    shown = _shown_label(label, _send_ordinal(rec))
    if allow_stale and rec.get("stale_drawing_at"):
        return _fields(
            shown, "stale", "none",
            f"{shown} PUSH 뒤 도면이 바뀌었습니다.",
            f"{shown} 푸시, 도면이 바뀌어 다시 보내야 함",
        )
    when = format_datetime_kst(rec.get("sent_at"), "%m-%d %H:%M") or ""
    when_title = f" · {when}" if when else ""
    when_aria = f" {when}" if when else ""
    return _fields(
        shown, "sent", "check",
        f"{shown} PUSH 보냄{when_title}",
        f"{shown} 푸시 보냄{when_aria}",
    )


def _send_ordinal(rec: dict) -> int:
    """이번 기록이 몇 번째 발송인지. 첫 발송은 1.

    재전송은 ``change_log`` 에 한 줄씩 쌓인다. 로그가 없고 ``is_modified`` 만
    있으면 두 번째로 본다.

    Args:
        rec: 한 종류의 PUSH 이력.

    Returns:
        1 이상의 차례.
    """
    log = rec.get("change_log")
    extra = len(log) if isinstance(log, list) else 0
    if extra == 0 and rec.get("is_modified"):
        return 2
    return 1 + extra


def _shown_label(label: str, ordinal: int) -> str:
    """두 번째부터 ``영발 2번째`` 처럼 차례를 붙인다."""
    if ordinal >= 2:
        return f"{label} {ordinal}번째"
    return label


def _fields(label: str, state: str, mark: str, title: str, aria: str) -> dict[str, str]:
    """칸 딕셔너리. 템플릿이 키 이름으로만 읽는다."""
    return {"label": label, "state": state, "mark": mark, "title": title, "aria": aria}
