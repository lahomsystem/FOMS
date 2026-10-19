"""긴급 호출 보낸 사람 기준 발송 상한 (SPEC ``docs/specs/2026-10-19-urgent-call-send-limit_SPEC.md``).

주문이 있든 없든 보낸 사람 한 명이 짧은 시간에 보낼 수 있는 긴급 호출 횟수를 묶는다.
세는 단위는 호출 1회(요청 1건)다 — 받는 사람 수가 아니다. 한 호출의 알림 행은 모두 같은
``created_at`` 을 갖도록 발송 쪽이 맞춰 넣으므로, 서로 다른 ``created_at`` 개수가 곧 호출 횟수다.
실패한 요청은 알림 행을 남기지 않으므로 세지 않는다.
"""

from __future__ import annotations

import datetime as dt_mod
from typing import Any

from sqlalchemy import func

from models import Notification

#: 보낸 사람 한 명이 창 안에서 보낼 수 있는 긴급 호출 횟수. 기존 주문 상한(주문당 시간당 5건)이
#: 짧은 시간에 먼저 걸리고 다른 주문은 따로 센다는 규칙이 가려지지 않도록 주문 두 개 분량으로 둔다.
URGENT_CALL_SENDER_LIMIT = 10
#: 위 횟수를 세는 창(분). 연타·화면 반복 호출은 몇 초~몇 분 안에 몰린다.
URGENT_CALL_SENDER_WINDOW_MINUTES = 10


def urgent_sender_limit_message() -> str:
    """보낸 사람 상한을 넘었을 때 화면에 보일 문구를 돌려준다."""
    return (f"긴급 호출은 {URGENT_CALL_SENDER_WINDOW_MINUTES}분에 {URGENT_CALL_SENDER_LIMIT}번까지만 "
            "보낼 수 있습니다. 잠시 뒤 다시 보내 주세요.")


def urgent_sender_limit_exceeded(db: Any, sender_id: int, now: dt_mod.datetime) -> bool:
    """세션·보낸 사람 id·기준 시각(UTC naive)으로 이번 호출이 상한을 넘는지 반환.

    최근 창 안에 이미 보낸 호출(서로 다른 ``created_at``)이 상한 이상이면 ``True``.
    """
    since = now - dt_mod.timedelta(minutes=URGENT_CALL_SENDER_WINDOW_MINUTES)
    sent = db.query(func.count(func.distinct(Notification.created_at))).filter(
        Notification.created_by_user_id == sender_id,
        Notification.notification_type == "URGENT_MENTION",
        Notification.created_at >= since,
    ).scalar() or 0
    return sent >= URGENT_CALL_SENDER_LIMIT
