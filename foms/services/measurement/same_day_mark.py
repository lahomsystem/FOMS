"""실측 모바일 목록·카드의 "당일" 표시 — 그날 긴급 추가된 실측을 하루 내내 알아보게 한다.

판정: 보는 날짜(KST)에 만들어진 ``MEASURE_SAME_DAY_ADDED`` 알림이 그 주문에 있다.
알림은 주문·날짜당 1건만 예약된다(outbox 멱등 키 ``meas_same_day:{order_id}:{date}``) —
그래서 알림 생성 시각의 KST 날짜가 곧 "오늘 새로 들어온 실측일" 이다.

목록 전체를 한 번에 읽는다(행 수와 무관한 1쿼리).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable

from models import Notification
from foms.services.datetime_kst import format_datetime_kst
from foms.services.notifications.measure_same_day_payload import NOTIFICATION_TYPE

#: KST = UTC+9 (서머타임 없음). Notification.created_at 은 naive UTC.
_KST_OFFSET = _dt.timedelta(hours=9)


def load_same_day_marks(db: Any, order_ids: Iterable[int], date_iso: str) -> dict[int, dict[str, str]]:
    """``date_iso`` 에 긴급 추가된 주문 → ``{"at": "HH:MM", "by": 추가한 사람}``.

    Args:
        db: SQLAlchemy 세션.
        order_ids: 목록에 보이는 주문 id.
        date_iso: 보는 날짜 ``YYYY-MM-DD``(KST). 잘못된 값이면 빈 dict.

    Returns:
        주문 id → 표시용 dict. 같은 주문에 여러 건이면 가장 이른 것.
    """
    ids = sorted({int(i) for i in order_ids if i})
    if not ids:
        return {}
    try:
        day = _dt.datetime.strptime(str(date_iso or ""), "%Y-%m-%d")
    except ValueError:
        return {}
    start_utc = day - _KST_OFFSET
    rows = (
        db.query(Notification.order_id, Notification.created_at, Notification.created_by_name)
        .filter(
            Notification.notification_type == NOTIFICATION_TYPE,
            Notification.order_id.in_(ids),
            Notification.created_at >= start_utc,
            Notification.created_at < start_utc + _dt.timedelta(days=1),
        )
        .order_by(Notification.created_at.asc())
        .all()
    )
    marks: dict[int, dict[str, str]] = {}
    for order_id, created_at, created_by in rows:
        if order_id in marks:
            continue
        marks[int(order_id)] = {
            "at": format_datetime_kst(created_at, "%H:%M") or "",
            "by": str(created_by or "").strip(),
        }
    return marks
