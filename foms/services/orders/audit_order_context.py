"""주문 감사 기록의 대상 표기 컨텍스트 SSOT (AUDIT-LOG P4 B1).

로그에 남는 주문 식별자는 번호뿐이라, 나중에 "누구 건인지"를 알려면 매번 주문을 열어야
했다(운영 실측: 최근 30일 변경 로그 전량이 ``주문 #4382`` 형태). 기록 시점에 **고객명과
주문 성격**을 함께 남겨 로그만으로 대상을 특정할 수 있게 한다.

주문이 나중에 삭제돼도 기록은 남아야 하므로 값을 **스냅샷**으로 저장한다. 다만 담는 것은
고객명까지다 — 연락처·주소는 넣지 않는다(감사 원장 PII 최소화; 기존 혼입분은 별건 이월).
"""

from __future__ import annotations

from typing import Any

__all__ = ["order_audit_context"]


def order_audit_context(order: Any) -> dict[str, Any]:
    """감사 기록에 함께 남길 주문 표기 컨텍스트를 만든다.

    :param order: :class:`~models.Order` 인스턴스(``None`` 허용).
    :return: ``{'customer_name': str|None, 'order_type': str}`` — 문장 생성기
        (:func:`foms.services.audit_message_display.describe_field_change`)와
        ``security_logs.detail`` 양쪽에 그대로 넘길 수 있는 형태.
    """
    if order is None:
        return {"customer_name": None, "order_type": "주문"}

    if getattr(order, "is_self_measurement", False):
        order_type = "자가실측 주문"
    elif getattr(order, "is_regional", False):
        order_type = "지방 주문"
    else:
        order_type = "주문"

    name = getattr(order, "customer_name", None)
    return {
        "customer_name": (name or None),
        "order_type": order_type,
    }
