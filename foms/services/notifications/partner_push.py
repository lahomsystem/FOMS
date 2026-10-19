"""PARTNER-FOMS 6: 협력사 직원 알림 종류 · 푸시 문구 · 누르면 열 주소.

협력사 알림은 협력사 화면(``/partner/orders/<id>``)을 연다 — 우리 ``/erp`` 화면은 협력사에게 막혀 있다.
문구는 알림 행의 ``message`` 를 쓴다. 우리 직원 알림과 달리 협력사 알림 message 는 협력사 알림 서비스
(:mod:`foms.services.partners.notify`)가 주소 · 메모 없이 만든 문장이라 잠금 화면에 보여도 된다.
설계서: docs/specs/2026-10-20-partner-notifications_SPEC.md §4 · §5-2
"""
from __future__ import annotations

PARTNER_DRAWING_READY = "PARTNER_DRAWING_READY"
PARTNER_CONSTRUCTION_DATE = "PARTNER_CONSTRUCTION_DATE"
PARTNER_AS_VISIT = "PARTNER_AS_VISIT"
PARTNER_CONSTRUCTION_DONE = "PARTNER_CONSTRUCTION_DONE"

PARTNER_PUSH_TITLES = {
    PARTNER_DRAWING_READY: "도면 확인 차례",
    PARTNER_CONSTRUCTION_DATE: "시공일 안내",
    PARTNER_AS_VISIT: "AS 방문 안내",
    PARTNER_CONSTRUCTION_DONE: "시공 끝",
}
PARTNER_NOTIFICATION_TYPES = frozenset(PARTNER_PUSH_TITLES)


def is_partner_notification_type(ntype: str) -> bool:
    return (ntype or "").strip().upper() in PARTNER_NOTIFICATION_TYPES


def partner_deep_link(order_id: int) -> str:
    return f"/partner/orders/{int(order_id)}"


def mask_customer_name(name: str) -> str:
    """잠금 화면용 고객 이름 — 가운데를 가린다(``홍길동`` → ``홍*동``, ``홍길`` → ``홍*``)."""
    text = (name or "").strip()
    if len(text) <= 1:
        return text
    if len(text) == 2:
        return text[0] + "*"
    return text[0] + "*" * (len(text) - 2) + text[-1]


def partner_push_text(ntype: str, message: str | None) -> tuple[str, str]:
    """푸시 (제목, 본문). 본문이 비면 제목만으로도 뜻이 통하게 한다."""
    key = (ntype or "").strip().upper()
    title = f"협력사 주문 · {PARTNER_PUSH_TITLES.get(key, '알림')}"
    return title, (message or "").strip() or "협력사 주문 화면에서 확인해 주세요."
