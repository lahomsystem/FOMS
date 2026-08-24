"""커머스API 애플리케이션 인증 만료 알림 (NAVER-INGEST-01 §5 T7).

리스크 표 1순위: **앱 인증 기한이 지나면 애플리케이션이 자동 휴면**되고 API 가 전면
중단된다. 그런데 아무 에러도 우리 화면에 뜨지 않는다 — 수집이 조용히 0건이 되고,
주문이 안 들어오는 걸 사람이 나중에 눈치챈다. 그래서 만료 **전에** 알리는 장치가 필요하다.

만료일은 API 로 조회할 수 있는 값이 아니라 커머스API센터 화면에서 사람이 확인하는 값이다.
따라서 `system_settings` 에 사람이 적어두고(또는 환경변수), 이 모듈이 매 수집 스윕마다
남은 일수를 보고 임계값에서 한 번씩만 알린다.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import Notification, SystemSetting, User

logger = logging.getLogger(__name__)

SETTING_KEY = "naver_app_expiry"
ENV_KEY = "NAVER_COMMERCE_APP_EXPIRES_ON"
NOTIFICATION_TYPE = "NAVER_APP_EXPIRY"

#: 남은 일수가 이 값 **이하**가 되는 순간 한 번씩 알린다. D-7 이 스펙 요구선이고,
#: 그 뒤로 좁혀가며 다시 알린다(한 번 놓쳐도 또 온다).
THRESHOLDS = (7, 3, 1, 0)


def _state(session: Session) -> tuple[Optional[SystemSetting], dict[str, Any]]:
    """(setting row, 값 dict) — 행이 없으면 (None, {})."""
    row = session.get(SystemSetting, SETTING_KEY)
    value = row.setting_value if row is not None else None
    return (row, dict(value) if isinstance(value, dict) else {})


def read_expiry_date(session: Session) -> Optional[date]:
    """만료일을 준다. setting 우선, 없으면 환경변수. 형식이 깨지면 None.

    None 이면 알림을 보내지 않는다 — 만료일을 모르는 상태를 "만료 임박"으로 오해해
    매 스윕마다 알림을 쏘면 알림이 잡음이 되고 정작 진짜 경고를 못 본다.
    """
    _row, state = _state(session)
    raw = str(state.get("expires_on") or os.environ.get(ENV_KEY) or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        logger.warning("[NAVER] 앱 만료일 형식 오류(무시): %r", raw)
        return None


def set_expiry_date(session: Session, expires_on: date) -> None:
    """만료일을 기록한다(관리 화면/운영자용). 날짜가 바뀌면 알림 이력을 초기화한다."""
    row, state = _state(session)
    new_value = expires_on.strftime("%Y-%m-%d")
    if state.get("expires_on") != new_value:
        # 인증을 갱신했으면 이전 임계값 알림 이력은 의미가 없다(다시 알려야 한다).
        state["notified"] = []
    state["expires_on"] = new_value
    if row is None:
        session.add(SystemSetting(
            setting_key=SETTING_KEY, setting_value=state,
            description="네이버 커머스API 앱 인증 만료일 (NAVER-INGEST-01)",
        ))
    else:
        row.setting_value = state
        row.version = int(row.version or 1) + 1
    session.flush()


def _mark_notified(session: Session, threshold: int) -> None:
    """이 임계값은 알렸다고 기록한다(같은 임계값 중복 발송 방지)."""
    row, state = _state(session)
    notified = [int(x) for x in (state.get("notified") or []) if str(x).lstrip("-").isdigit()]
    if threshold not in notified:
        notified.append(threshold)
    state["notified"] = notified
    if row is None:
        session.add(SystemSetting(setting_key=SETTING_KEY, setting_value=state))
    else:
        row.setting_value = state
        row.version = int(row.version or 1) + 1
    session.flush()


def _due_threshold(days_left: int, notified: list[int]) -> Optional[int]:
    """지금 알려야 할 임계값(가장 촘촘한 미발송 임계값). 없으면 None."""
    for threshold in sorted(THRESHOLDS):
        if days_left <= threshold and threshold not in notified:
            return threshold
    return None


def check_and_notify(
    session: Session, *, today: Optional[date] = None, now: Optional[datetime] = None
) -> Optional[int]:
    """만료가 임박했으면 ADMIN 전원에게 1회 알린다.

    알림은 ADMIN **사용자별 1건**(``target_user_id``)으로 만든다. 팀 타깃은 role 이 아니라
    team 으로 풀려서 ADMIN 만 고르는 경로가 없다.

    Args:
        session: DB 세션(커밋은 호출자).
        today: 기준일(테스트 주입).
        now: 생성 시각(테스트 주입).

    Returns:
        이번에 발송한 임계값(예: 7). 보낼 게 없으면 None.
    """
    expires_on = read_expiry_date(session)
    if expires_on is None:
        return None

    reference = today or now_utc_naive().date()
    days_left = (expires_on - reference).days
    _row, state = _state(session)
    notified = [int(x) for x in (state.get("notified") or []) if str(x).lstrip("-").isdigit()]
    threshold = _due_threshold(days_left, notified)
    if threshold is None:
        return None

    admins = (
        session.query(User)
        .filter(User.role == "ADMIN", User.is_active.is_(True))
        .all()
    )
    if not admins:
        logger.warning("[NAVER] 앱 만료 D-%d 알림 대상 ADMIN 이 없다", days_left)
        return None

    title = (
        "네이버 커머스API 인증 만료됨" if days_left <= 0
        else f"네이버 커머스API 인증 만료 D-{days_left}"
    )
    message = (
        f"커머스API 애플리케이션 인증 만료일이 {expires_on:%Y-%m-%d} 입니다. "
        "만료되면 애플리케이션이 자동 휴면되어 스마트스토어 주문 수집이 **전면 중단**됩니다. "
        "커머스API센터에서 인증을 갱신한 뒤 만료일을 다시 등록하세요."
    )
    created_at = now or now_utc_naive()
    from foms.services.notifications.recipients import fan_out_new_notification

    for admin in admins:
        notification = Notification(
            order_id=None,
            notification_type=NOTIFICATION_TYPE,
            target_type="USER",
            target_user_id=int(admin.id),
            is_urgent=True,
            title=title,
            message=message,
            created_at=created_at,
        )
        session.add(notification)
        session.flush()
        fan_out_new_notification(session, notification)

    _mark_notified(session, threshold)
    logger.warning("[NAVER] 앱 인증 만료 D-%d 알림 발송(ADMIN %d명)", days_left, len(admins))
    return threshold


__all__ = [
    "ENV_KEY",
    "NOTIFICATION_TYPE",
    "SETTING_KEY",
    "THRESHOLDS",
    "check_and_notify",
    "read_expiry_date",
    "set_expiry_date",
]
