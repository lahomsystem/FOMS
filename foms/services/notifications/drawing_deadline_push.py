"""도면 마감 알림(``DRAWING_DEADLINE_DUE``) — 종류 이름 · 제목 셋 · 누르면 여는 곳 · 폰 배너 글.

알림을 만드는 곳은 :mod:`foms.services.notifications.drawing_deadline_alert`. 이 파일은 폰 알림(``push_sender``)과
벨 목록 링크(``foms.api.notifications``)가 함께 읽는 작은 조각만 둔다(설계서
``docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md`` §9-4 · §9-5).

폰 배너는 알림 줄의 글(본문)을 읽지 않는다 — 제목이 이 파일의 세 글 가운데 하나일 때만 그 제목을 쓰고, 본문은
``주문 #번호 (고객명) …`` 로 새로 만든다(돈 · 전화 · 주소 없음).
"""

from __future__ import annotations

from typing import Any, Tuple

NOTIFICATION_TYPE = "DRAWING_DEADLINE_DUE"

#: 마감 날 아침 칸 · 저녁 칸 · 마감 뒤 일하는 날 아침(§9-4 · §9-7).
TITLE_MORNING = "오늘 도면 마감이에요"
TITLE_EVENING = "도면 마감 — 아직 안 내려왔어요"
TITLE_LATE = "도면 마감이 지났어요"
TITLES = (TITLE_MORNING, TITLE_EVENING, TITLE_LATE)
#: 제목을 모를 때(옛 줄 · 손으로 만든 줄)의 폰 제목.
GENERIC_TITLE = "도면 마감 알림"

_PUSH_BODY = {
    TITLE_MORNING: "오늘까지 도면이 생산으로 내려와야 해요",
    TITLE_EVENING: "도면이 아직 생산으로 안 내려왔어요",
    TITLE_LATE: "도면 마감이 지났어요",
}


def is_drawing_deadline_type(notification_type: Any) -> bool:
    """도면 마감 알림 종류인가(대소문자 · 앞뒤 빈칸 무관)."""
    return str(notification_type or "").strip().upper() == NOTIFICATION_TYPE


def drawing_deadline_deep_link(order_id: Any) -> str:
    """누르면 여는 곳 = 도면 작업실 그 주문(까닭 다섯 가운데 넷 — 그리기 · 고치기 · 담당 정하기 · 수령 확정 — 을 거기서 한다).

    Args:
        order_id: 주문 번호(없으면 도면 작업실 목록).

    Returns:
        같은 출처 경로.
    """
    try:
        oid = int(order_id) if order_id else 0
    except (TypeError, ValueError):
        oid = 0
    return f"/erp/drawing-workbench/{oid}" if oid > 0 else "/erp/drawing-workbench"


def drawing_deadline_push_text(title: Any, order_id: Any, customer_name: str) -> Tuple[str, str]:
    """폰 배너 (제목, 본문). 제목은 알려진 세 글만 그대로 쓰고, 본문은 번호 · 고객 이름 · 고정 글로 만든다.

    Args:
        title: 알림 줄 제목(이 파일의 :data:`TITLES` 가운데 하나여야 그대로 쓴다).
        order_id: 주문 번호.
        customer_name: 배너용 고객 이름(이미 다듬은 값 — 비면 번호만).

    Returns:
        ``('오늘 도면 마감이에요 · 김가짜', '주문 #12 (김가짜) 오늘까지 도면이 생산으로 내려와야 해요')`` 꼴.
    """
    known = str(title or "") if str(title or "") in TITLES else ""
    head = known or GENERIC_TITLE
    body = _PUSH_BODY.get(known, "도면 마감 확인이 필요해요")
    name = str(customer_name or "").strip()
    label = f"주문 #{int(order_id)}" if order_id else "주문"
    if name:
        return f"{head} · {name}", f"{label} ({name}) {body}"
    return head, f"{label} {body}"


__all__ = [
    "GENERIC_TITLE",
    "NOTIFICATION_TYPE",
    "TITLES",
    "TITLE_EVENING",
    "TITLE_LATE",
    "TITLE_MORNING",
    "drawing_deadline_deep_link",
    "drawing_deadline_push_text",
    "is_drawing_deadline_type",
]
