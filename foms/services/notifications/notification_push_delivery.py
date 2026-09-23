"""SIDEFX ``NOTIFICATION`` handler — 긴급 멘션 outbox 행을 실제 OS 웹 푸시로 내보낸다.

긴급 멘션(``foms/api/notifications/__init__.py`` 의 URGENT_MENTION)은 알림 생성과 같은 tx 로
``effect_type="NOTIFICATION"`` 행을 넣는다. 그런데 이 타입의 소비자가 등록돼 있지 않아서 OS
푸시가 한 번도 나가지 않았고, 행은 NoHandler 로 10회 재시도한 뒤 DEAD 가 됐다(기존 결함 ②).

이 handler 가 그 소비자다. 워커 정지 감시자 선례처럼 rq 를 거치지 않고 SIDEFX 세션으로
:func:`foms.services.notifications.push_sender.send_push_for_notification` 을 직접 부른다.

* **세션 소유권**: commit 하지 않는다(worker 가 DONE 과 함께 commit).
* **오래된 행**: 알림 생성 뒤 30분이 지났으면 보내지 않고 끝낸다 — 배포 직후 밀린 PENDING 이
  한꺼번에 잠금화면에 쏟아지는 것을 막는다.
* **고칠 수 없는 사유**: 웹 푸시 꺼짐·pywebpush 없음은 재시도해도 같으므로 로그만 남기고
  끝낸다. 그 밖의 DB 예외는 그대로 올려 재시도시킨다.
* **재시도 중복 방지**: 이미 ``PUSH_ATTEMPTED`` 인 수신자는 건너뛴다(``skip_attempted``).
* **환경 확인**: SIDEFX 서비스에 ``FOMS_WEB_PUSH_ENABLED``·``VAPID_PRIVATE_KEY``·
  ``VAPID_CLAIMS_SUB`` 가 없으면 프로세스당 한 번 WARNING 을 남긴다(웹 서비스와 env 가 다르다).
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.notifications import push_sender
from models import DomainSideEffectOutbox, Notification

_LOGGER = logging.getLogger("sidefx_notification_push")

__all__ = [
    "NOTIFICATION_EFFECT_TYPE",
    "REQUIRED_ENV",
    "STALE_AFTER",
    "NotificationPushDeliveryError",
    "handle_notification_push",
]

NOTIFICATION_EFFECT_TYPE = "NOTIFICATION"
#: 이보다 오래된 알림은 OS 푸시를 보내지 않는다.
STALE_AFTER = _dt.timedelta(minutes=30)
_PERMANENT_REASONS = frozenset({"flag_off", "pywebpush_unavailable"})
#: SIDEFX 에서 웹 푸시를 보내려면 있어야 하는 환경변수.
REQUIRED_ENV = ("FOMS_WEB_PUSH_ENABLED", "VAPID_PRIVATE_KEY", "VAPID_CLAIMS_SUB")
_ENV_WARNED = False


def _warn_missing_env_once() -> None:
    global _ENV_WARNED
    if _ENV_WARNED:
        return
    missing = [name for name in REQUIRED_ENV if not (os.environ.get(name) or "").strip()]
    if not missing:
        return
    _ENV_WARNED = True
    _LOGGER.warning(
        "[notif-push] SIDEFX 환경변수 없음: %s — 긴급 멘션·당일 실측 OS 푸시가 나가지 않을 수 있습니다",
        ", ".join(missing),
    )


class NotificationPushDeliveryError(RuntimeError):
    """행을 처리할 세션이 없다(worker 가 재시도/DEAD 처리)."""


def _notification_id(row: DomainSideEffectOutbox) -> Optional[int]:
    payload: Any = row.payload if isinstance(row.payload, dict) else {}
    raw = payload.get("notification_id")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def handle_notification_push(row: DomainSideEffectOutbox) -> None:
    """``NOTIFICATION`` 행 1개를 처리한다(commit 은 worker 소유).

    Args:
        row: PROCESSING 으로 claim 된 outbox 행(worker 세션 attach).

    Raises:
        NotificationPushDeliveryError: 세션 미attach.
    """
    _warn_missing_env_once()
    session = Session.object_session(row)
    if session is None:
        raise NotificationPushDeliveryError(f"outbox row {row.id} is not attached to a session")

    nid = _notification_id(row)
    if nid is None:
        _LOGGER.info("[notif-push] notification_id 없음(id=%s) — skip", row.id)
        return
    notif = session.get(Notification, nid)
    if notif is None:
        _LOGGER.info("[notif-push] 알림 %s 없음(id=%s) — skip", nid, row.id)
        return
    created_at = getattr(notif, "created_at", None)
    if created_at is None or created_at < now_utc_naive() - STALE_AFTER:
        _LOGGER.info("[notif-push] 알림 %s 이 30분 넘게 지남(created_at=%s) — skip", nid, created_at)
        return

    summary = push_sender.send_push_for_notification(nid, db=session, skip_attempted=True)
    reason = (summary or {}).get("reason")
    if reason in _PERMANENT_REASONS:
        _LOGGER.error("[notif-push] 웹 푸시 발송 불가(reason=%s, notification=%s)", reason, nid)
        return
    _LOGGER.info("[notif-push] notification=%s summary=%s", nid, summary)
