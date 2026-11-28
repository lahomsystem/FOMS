"""생산 현장 알람 다시 받기 API(설계서 2026-11-28 생산 현장 알람 §4-2 의 4 · §4-4 · §6-2 약속 7).

``GET /api/production/alarms/pending`` → ``{success, data: {urgent: [...], notices: [...]}, error}``.

* 내 것 · 안 누름(``ack_at`` 없음) · 보관 안 됨 · 생산 알람 종류(``PRODUCTION_FLOOR_…``)만. 긴급 = 72시간 안 5건, 띠 = 12시간 안 5건,
  둘 다 오래된 것부터. 한 줄 모양은 실시간 값과 같다(약속 6 — :func:`~foms.services.production.floor_alarm.payload`).
* 쿼리 1(72시간 안 내 생산 알람을 한 번 읽어 긴급 · 띠로 가른다). 스위치가 꺼져 있거나 로그인 안 했으면 쿼리 0 · 빈 목록.
* 문: 생산 첫 화면을 볼 수 있는 우리 직원(협력사 · 켜진 프리랜서는 문지기가 먼저 막는다). 남의 알람은 줄 수 없다 — 조건이 늘 로그인한 계정이다.
* 읽기라 쓰기 정책 가드 · CSRF 대상이 아니다(GET). [확인]은 지금 있는 ``POST /erp/api/notifications/<id>/ack`` 그대로.

이 모듈이 앱에 실릴 때 알람 모듈에 종 숫자 캐시 비우는 함수를 꽂는다(서비스 층은 api 층을 부르지 못한다 — 레이어 래칫).
"""

from __future__ import annotations

import datetime
from typing import Any

from flask import Blueprint, g, jsonify
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.api.notifications import invalidate_badge_cache_for_user_ids
from foms.services.datetime_kst import now_utc_naive
from foms.services.production import floor_alarm
from foms.services.production.floor_alarm_text import LIKE_ESCAPE, LIKE_PATTERN
from foms.services.production.home_access import can_view_production_home
from models import Notification, NotificationUserState

URGENT_WINDOW = datetime.timedelta(hours=72)
NOTICE_WINDOW = datetime.timedelta(hours=12)
URGENT_LIMIT = 5
NOTICE_LIMIT = 5

production_alarms_bp = Blueprint("production_alarms", __name__, url_prefix="/api/production")
floor_alarm.set_badge_hook(invalidate_badge_cache_for_user_ids)


def pending_for(db: Any, user_id: int, now: datetime.datetime) -> dict[str, list[dict[str, Any]]]:
    """그 계정의 안 누른 생산 알람 — 긴급(72시간 · 5건) · 띠(12시간 · 5건), 오래된 것부터. 쿼리 1."""
    rows = (db.query(Notification)
            .join(NotificationUserState, NotificationUserState.notification_id == Notification.id)
            .filter(NotificationUserState.user_id == user_id, NotificationUserState.ack_at.is_(None),
                    NotificationUserState.archived_at.is_(None), Notification.created_at >= now - URGENT_WINDOW,
                    Notification.notification_type.like(LIKE_PATTERN, escape=LIKE_ESCAPE))
            .order_by(Notification.created_at.asc(), Notification.id.asc()).all())
    urgent = [floor_alarm.payload(n) for n in rows if n.is_urgent]
    notices = [floor_alarm.payload(n) for n in rows if not n.is_urgent and n.created_at >= now - NOTICE_WINDOW]
    return {"urgent": urgent[:URGENT_LIMIT], "notices": notices[:NOTICE_LIMIT]}


@production_alarms_bp.route("/alarms/pending", methods=["GET"])
def api_production_alarms_pending():
    """내(본인) 안 누른 생산 알람 — 화면을 열 때 · 다시 보일 때 · 소켓이 다시 붙을 때 · [확인]으로 줄이 비었을 때만 묻는다."""
    empty = {"urgent": [], "notices": []}
    user = getattr(g, "current_user", None)
    if user is None or not floor_alarm.enabled():
        return _answer(empty)
    if not can_view_production_home(user):
        return jsonify({"success": False, "data": {"code": "FORBIDDEN"}, "error": "생산 화면을 볼 수 있는 직원만 받을 수 있어요."}), 403
    db = get_db()
    try:
        return _answer(pending_for(db, int(user.id), now_utc_naive()))
    except SQLAlchemyError:
        db.rollback()
        return jsonify({"success": False, "data": {"code": "READ_FAILED"}, "error": "알람을 받아 오지 못했어요. 잠시 뒤 다시 열어 주세요."}), 500


def _answer(data: dict[str, Any]):
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response


__all__ = ["NOTICE_LIMIT", "NOTICE_WINDOW", "URGENT_LIMIT", "URGENT_WINDOW", "api_production_alarms_pending", "pending_for",
           "production_alarms_bp"]
