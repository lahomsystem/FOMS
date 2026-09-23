"""당일 실측 긴급 알림 — 화면 확인창 payload 조립(socket emit 과 pending-interrupts API 가 같이 쓴다).

:mod:`foms.services.notifications.measure_same_day` 에서 떼어냈다(파일 크기 래칫). 호출부는
계속 ``measure_same_day.build_measure_same_day_payload`` 로 쓴다(재수출).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from foms.services.datetime_kst import format_datetime_kst
from foms.services.erp_display import manager_display_name

#: 알림 유형(``Notification.notification_type``).
NOTIFICATION_TYPE = "MEASURE_SAME_DAY_ADDED"
#: 화면 확인창 분기 키.
ALERT_KIND = "measure_same_day"


def _sd(order: Any) -> dict:
    sd = getattr(order, "structured_data", None)
    return sd if isinstance(sd, dict) else {}


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _customer_name(order: Any) -> str:
    name = _dict(_dict(_sd(order).get("parties")).get("customer")).get("name")
    return str(name or getattr(order, "customer_name", "") or "").strip()


def _area(order: Any) -> str:
    site = _dict(_sd(order).get("site"))
    for raw in (site.get("address_full"), site.get("address_main"), getattr(order, "address", None)):
        text = str(raw or "").strip()
        if text and text != "-":
            return " ".join(text.split()[:2])
    return ""


def _measure_time(order: Any) -> str:
    measurement = _dict(_dict(_sd(order).get("schedule")).get("measurement"))
    raw = measurement.get("time") or getattr(order, "measurement_time", None)
    return str(raw or "").strip() or "시간 미정"


def _manager(order: Any) -> str:
    name = manager_display_name(_sd(order).get("parties"))
    return str(name or getattr(order, "manager_name", "") or "").strip()


def _title(order: Any) -> str:
    return f"[긴급 실측] 오늘 {_measure_time(order)} · {_customer_name(order)}"


def _message(order: Any, added_by: str) -> str:
    parts = [p for p in (_area(order), f"담당 {_manager(order)}" if _manager(order) else "") if p]
    if added_by:
        parts.append(f"추가 {added_by}")
    return " · ".join(parts) or "오늘 실측이 긴급 추가됐어요"


def build_measure_same_day_payload(
    order: Any,
    *,
    notification_id: int,
    added_by: str,
    added_at: Optional[_dt.datetime],
) -> dict:
    """화면 확인창 payload 를 만든다(유일한 조립 지점).

    ``urgent`` 키는 넣지 않는다 — 화면 분기에서 전체화면 빨강 경보가 먼저 가로채기 때문이다.

    Args:
        order: 대상 주문.
        notification_id: 알림 id(수신자별 ack 대상).
        added_by: 추가한 사람 표시명.
        added_at: 알림 생성 시각(UTC naive). None 허용.

    Returns:
        socket ``erp_notification`` 이벤트와 재조회 API 가 그대로 쓰는 dict.
    """
    order_id = int(getattr(order, "id", 0) or 0)
    added_by = str(added_by or "").strip()
    return {
        "notification_id": int(notification_id),
        "order_id": order_id,
        "notification_type": NOTIFICATION_TYPE,
        "title": _title(order),
        "message": _message(order, added_by),
        "created_by_name": added_by,
        "interrupt": True,
        "alert_kind": ALERT_KIND,
        "customer_name": _customer_name(order),
        "area": _area(order),
        "time": _measure_time(order),
        "manager": _manager(order),
        "added_by": added_by,
        "added_at": format_datetime_kst(added_at) if added_at else None,
        "order_url": f"/erp/orders/{order_id}",
    }
