"""ERP 알림 Web Push 구독 API (Phase 3A: 저장소/구독/feature flag).

sender/서비스워커/클라이언트 로직은 범위 밖(Phase 3B/3C). 이 모듈은 구독 endpoint
저장(upsert / soft-delete), VAPID 공개키 노출, feature flag 게이팅, 모바일 CTA 상태
조회만 담당한다. 모든 write 는 same-origin 헤더 guard + login 을 통과해야 한다.

보안 규칙:
- feature flag ``FOMS_WEB_PUSH_ENABLED`` off 면 push API 전부 404.
- push endpoint 원문은 로그/응답/이벤트에 절대 남기지 않는다(sha256 hex 만).
- endpoint 는 https URL, 2048자 이내만 허용. p256dh/auth 는 저장만(로그 금지).
"""

from __future__ import annotations

import datetime as dt_mod
import hashlib
import os
from functools import wraps
from typing import Any, Callable, Optional, Tuple
from urllib.parse import urlparse

from flask import Blueprint, current_app, g, jsonify, request, session
from sqlalchemy import func

from foms.web.auth import login_required
from foms.services.request_write_guard import require_same_origin_write
from db import get_db
from models import NotificationPushSubscription, NotificationUserState

WEB_PUSH_FLAG_ENV = "FOMS_WEB_PUSH_ENABLED"
VAPID_PUBLIC_KEY_ENV = "VAPID_PUBLIC_KEY"
# 알림 write 공용 same-origin guard 헤더(notifications 도메인과 동일 값 재사용).
PUSH_WRITE_HEADER = "X-FOMS-Notification-Write"
MAX_ENDPOINT_LENGTH = 2048

_TRUTHY = frozenset({"1", "true", "yes", "on"})

push_write_guard = require_same_origin_write(PUSH_WRITE_HEADER)

push_bp = Blueprint(
    "notifications_push", __name__, url_prefix="/erp/api/notifications/push"
)
# mobile-state 는 push 하위가 아니라 notifications 루트 아래로 노출한다.
push_state_bp = Blueprint(
    "notifications_push_state", __name__, url_prefix="/erp/api/notifications"
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _web_push_enabled() -> bool:
    """``FOMS_WEB_PUSH_ENABLED`` env 가 truthy 인지 반환(기본 off)."""
    return (os.environ.get(WEB_PUSH_FLAG_ENV, "") or "").strip().lower() in _TRUTHY


def _vapid_public_key() -> str:
    """설정된 VAPID 공개키 문자열(미설정 시 빈 문자열)."""
    return (os.environ.get(VAPID_PUBLIC_KEY_ENV, "") or "").strip()


def _endpoint_hash(endpoint: str) -> str:
    """push endpoint 원문의 sha256 hex(로그/감사용, 원문 유출 방지)."""
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def _current_user_id() -> Optional[int]:
    """현재 세션 사용자 id(없으면 None)."""
    return session.get("user_id")


def _is_admin(user: Any) -> bool:
    """current_user 가 ADMIN 인지 판정."""
    return str(getattr(user, "role", "") or "").upper() == "ADMIN"


def _clip(value: Any, length: int) -> Optional[str]:
    """DB 컬럼 길이에 맞춰 문자열을 자른다(None 은 그대로)."""
    if value is None:
        return None
    return str(value)[:length]


def require_web_push_enabled(f: Callable[..., Any]) -> Callable[..., Any]:
    """feature flag off 면 404 를 반환하는 게이트 데코레이터(최외곽 적용).

    :param f: 감쌀 뷰 함수
    :return: flag on 일 때만 원본 뷰를 실행하는 래퍼
    """

    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not _web_push_enabled():
            return jsonify(
                {"success": False, "data": None, "error": "web_push_disabled"}
            ), 404
        return f(*args, **kwargs)

    return wrapper


def _validate_endpoint(endpoint: Any) -> Tuple[Optional[str], Optional[str]]:
    """endpoint 문자열 검증. ``(정상값, 오류사유)`` 튜플을 반환한다.

    https URL 이면서 2048자 이내여야 한다.
    """
    if not endpoint or not isinstance(endpoint, str):
        return None, "endpoint_required"
    endpoint = endpoint.strip()
    if len(endpoint) > MAX_ENDPOINT_LENGTH:
        return None, "endpoint_too_long"
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        return None, "endpoint_must_be_https"
    return endpoint, None


def _apply_subscription_fields(
    sub: NotificationPushSubscription, keys: dict, data: dict, now: dt_mod.datetime
) -> None:
    """구독 row 에 keys/메타/타임스탬프를 반영(revoked 해제 포함)."""
    sub.p256dh = keys.get("p256dh")
    sub.auth = keys.get("auth")
    sub.platform = _clip(data.get("platform"), 30)
    sub.browser = _clip(data.get("browser"), 50)
    sub.device_label = _clip(data.get("device_label"), 100)
    sub.permission_state = _clip(data.get("permission_state"), 20)
    sub.last_seen_at = now
    sub.revoked_at = None


def _latest_active_subscription(db: Any, user_id: int) -> Optional[NotificationPushSubscription]:
    """대상 사용자의 최신 활성(미revoke) 구독 1건(없으면 None)."""
    return (
        db.query(NotificationPushSubscription)
        .filter(
            NotificationPushSubscription.user_id == user_id,
            NotificationPushSubscription.revoked_at.is_(None),
        )
        .order_by(NotificationPushSubscription.id.desc())
        .first()
    )


def _unread_count(db: Any, user_id: Optional[int]) -> int:
    """현재 사용자 미읽음·미보관 알림 수(배지와 동일 기준)."""
    if user_id is None:
        return 0
    count = (
        db.query(func.count(NotificationUserState.id))
        .filter(
            NotificationUserState.user_id == user_id,
            NotificationUserState.archived_at.is_(None),
            NotificationUserState.read_at.is_(None),
        )
        .scalar()
    )
    return int(count or 0)


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@push_bp.route("/vapid-public-key", methods=["GET"])
@require_web_push_enabled
@login_required
def vapid_public_key() -> Any:
    """VAPID 공개키 반환. 미설정 시 503(구독 진행 불가)."""
    key = _vapid_public_key()
    if not key:
        return jsonify(
            {"success": False, "data": None, "error": "vapid_not_configured"}
        ), 503
    return jsonify({"success": True, "data": {"public_key": key}})


@push_bp.route("/subscribe", methods=["POST", "DELETE"])
@require_web_push_enabled
@login_required
@push_write_guard
def subscribe() -> Any:
    """Web Push 구독 upsert(POST) / soft-revoke(DELETE) 진입점."""
    if request.method == "DELETE":
        return _handle_unsubscribe()
    return _handle_subscribe()


def _handle_subscribe() -> Any:
    """endpoint upsert: 신규 생성 / 동일 owner 갱신 / 타 owner 403.

    타 owner 재등록 시 endpoint 원문 없이 sha256 hex 로만 audit 로그를 남긴다
    (notification_id NOT NULL 제약 때문에 DB 이벤트는 생략).
    """
    db = None
    try:
        db = get_db()
        user_id = _current_user_id()
        data = request.get_json(silent=True) or {}
        endpoint, err = _validate_endpoint(data.get("endpoint"))
        if err:
            return jsonify({"success": False, "data": None, "error": err}), 400
        keys = data.get("keys") or {}

        existing = (
            db.query(NotificationPushSubscription)
            .filter(NotificationPushSubscription.endpoint == endpoint)
            .first()
        )
        if existing is not None and existing.user_id != user_id:
            current_app.logger.warning(
                "push subscribe owner mismatch: endpoint_hash=%s requester=%s",
                _endpoint_hash(endpoint),
                user_id,
            )
            return jsonify(
                {"success": False, "data": None, "error": "endpoint_owned_by_another_user"}
            ), 403

        now = dt_mod.datetime.now()
        sub = existing or NotificationPushSubscription(user_id=user_id, endpoint=endpoint)
        _apply_subscription_fields(sub, keys, data, now)
        if existing is None:
            db.add(sub)
        db.commit()
        return jsonify(
            {"success": True, "data": {"subscription_id": sub.id, "active": True}}
        )
    except Exception as e:  # noqa: BLE001 - 롤백 후 표준 에러 응답
        if db is not None:
            db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 500


def _handle_unsubscribe() -> Any:
    """본인 소유 endpoint soft-revoke(revoked_at=now). 타인/미존재 404."""
    db = None
    try:
        db = get_db()
        user_id = _current_user_id()
        data = request.get_json(silent=True) or {}
        endpoint, err = _validate_endpoint(data.get("endpoint"))
        if err:
            return jsonify({"success": False, "data": None, "error": err}), 400

        sub = (
            db.query(NotificationPushSubscription)
            .filter(NotificationPushSubscription.endpoint == endpoint)
            .first()
        )
        if sub is None or sub.user_id != user_id:
            return jsonify(
                {"success": False, "data": None, "error": "subscription_not_found"}
            ), 404
        if sub.revoked_at is None:
            sub.revoked_at = dt_mod.datetime.now()
        db.commit()
        return jsonify({"success": True, "data": {"revoked": True}})
    except Exception as e:  # noqa: BLE001 - 롤백 후 표준 에러 응답
        if db is not None:
            db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 500


def _resolve_test_target(
    data: dict, user_id: Optional[int], current: Any
) -> Tuple[Optional[int], Any]:
    """테스트 대상 user_id 결정. self 또는 ADMIN 만 타 사용자 지정 가능.

    :return: ``(target_id, error_response)``. error_response 가 None 이 아니면 즉시 반환.
    """
    raw = data.get("user_id")
    if raw in (None, ""):
        return user_id, None
    try:
        target_id = int(raw)
    except (TypeError, ValueError):
        return None, (
            jsonify({"success": False, "data": None, "error": "invalid_user_id"}),
            400,
        )
    if target_id != user_id and not _is_admin(current):
        return None, (
            jsonify({"success": False, "data": None, "error": "forbidden_target_user"}),
            403,
        )
    return target_id, None


@push_bp.route("/test", methods=["POST"])
@require_web_push_enabled
@login_required
@push_write_guard
def push_test() -> Any:
    """활성 구독 대상 즉시 테스트 푸시(Phase 3C sender 배포).

    비관리자는 자신에게만 가능(body user_id 로 타인 지정 시 403). ADMIN 은 임의 대상 허용.
    발송 결과(sent/reason)를 반환한다. VAPID 미설정/라이브러리 미설치 시 reason 으로 노출.
    """
    db = None
    try:
        db = get_db()
        user_id = _current_user_id()
        current = getattr(g, "current_user", None)
        data = request.get_json(silent=True) or {}

        target_id, err_resp = _resolve_test_target(data, user_id, current)
        if err_resp is not None:
            return err_resp

        sub = _latest_active_subscription(db, target_id)
        if sub is None:
            return jsonify(
                {"success": False, "data": None, "error": "no_active_subscription"}
            ), 404

        from foms.services.notifications.push_sender import send_test_push

        result = send_test_push(sub.id)
        return jsonify(
            {
                "success": True,
                "data": {
                    "queued": False,
                    "sent": bool(result.get("sent")),
                    "reason": result.get("reason"),
                },
            }
        )
    except Exception as e:  # noqa: BLE001 - 롤백 후 표준 에러 응답
        if db is not None:
            db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 500


@push_bp.route("/event", methods=["POST"])
@require_web_push_enabled
@login_required
@push_write_guard
def push_event() -> Any:
    """서비스워커 push 상호작용 보고(Phase 3B 사용): opened/closed 이벤트 기록.

    body: {notification_id, event: 'opened'|'closed'}. 본인 소유 user_state 가 있어야 하며
    (없으면 404), opened 시 last_opened_at/last_delivery_status='opened' 로 갱신한다.
    """
    from models import (
        NotificationDeliveryStatus,
        NotificationEvent,
        NotificationEventType,
    )

    db = None
    try:
        db = get_db()
        user_id = _current_user_id()
        data = request.get_json(silent=True) or {}
        try:
            notification_id = int(data.get("notification_id"))
        except (TypeError, ValueError):
            return jsonify(
                {"success": False, "data": None, "error": "invalid_notification_id"}
            ), 400
        event = (data.get("event") or "").strip().lower()
        if event not in ("opened", "closed"):
            return jsonify(
                {"success": False, "data": None, "error": "invalid_event"}
            ), 400

        state = (
            db.query(NotificationUserState)
            .filter(
                NotificationUserState.notification_id == notification_id,
                NotificationUserState.user_id == user_id,
            )
            .first()
        )
        if state is None:
            return jsonify(
                {"success": False, "data": None, "error": "notification_not_found"}
            ), 404

        now = dt_mod.datetime.now()
        if event == "opened":
            event_type = NotificationEventType.OPENED
            state.last_opened_at = now
            _terminal = (
                NotificationDeliveryStatus.ACK,
                NotificationDeliveryStatus.RESOLVED,
            )
            if state.last_delivery_status not in _terminal:
                state.last_delivery_status = NotificationDeliveryStatus.OPENED
        else:
            event_type = NotificationEventType.CLOSED

        db.add(
            NotificationEvent(
                notification_id=notification_id,
                user_state_id=state.id,
                recipient_user_id=user_id,
                event_type=event_type,
                channel="webpush",
            )
        )
        db.commit()
        return jsonify({"success": True, "data": {"recorded": event}})
    except Exception as e:  # noqa: BLE001 - 롤백 후 표준 에러 응답
        if db is not None:
            db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 500


@push_bp.route("/health", methods=["GET"])
@login_required
def push_health() -> Any:
    """ADMIN 전용 push 배포 준비도(flag/vapid/rq state/worker_count). flag 무관 항상 200."""
    current = getattr(g, "current_user", None)
    if not _is_admin(current):
        return jsonify({"success": False, "data": None, "error": "forbidden"}), 403

    from foms.services.jobs.queue import get_rq_runtime_status

    rq_status = get_rq_runtime_status()
    vapid_private = bool((os.environ.get("VAPID_PRIVATE_KEY", "") or "").strip())
    return jsonify(
        {
            "success": True,
            "data": {
                "web_push_enabled": _web_push_enabled(),
                "vapid_public_configured": bool(_vapid_public_key()),
                "vapid_private_configured": vapid_private,
                "rq_state": rq_status.get("state"),
                "rq_worker_count": int(rq_status.get("worker_count", 0) or 0),
                "push_ready": bool(
                    _web_push_enabled()
                    and _vapid_public_key()
                    and vapid_private
                    and rq_status.get("state") == "reachable"
                    and int(rq_status.get("worker_count", 0) or 0) > 0
                ),
            },
        }
    )


@push_state_bp.route("/mobile-state", methods=["GET"])
@login_required
def mobile_state() -> Any:
    """모바일 CTA 노출 판단용 상태(flag/vapid/구독존재/미읽음수). flag 무관 항상 200."""
    try:
        db = get_db()
        user_id = _current_user_id()
        sub_active = False
        if user_id is not None:
            sub_active = (
                db.query(NotificationPushSubscription.id)
                .filter(
                    NotificationPushSubscription.user_id == user_id,
                    NotificationPushSubscription.revoked_at.is_(None),
                )
                .first()
                is not None
            )
        return jsonify(
            {
                "success": True,
                "data": {
                    "web_push_enabled": _web_push_enabled(),
                    "vapid_configured": bool(_vapid_public_key()),
                    "subscription_active": sub_active,
                    "unread_count": _unread_count(db, user_id),
                },
            }
        )
    except Exception as e:  # noqa: BLE001 - 표준 에러 응답
        return jsonify({"success": False, "data": None, "error": str(e)}), 500


__all__ = [
    "push_bp",
    "push_state_bp",
    "require_web_push_enabled",
    "PUSH_WRITE_HEADER",
    "WEB_PUSH_FLAG_ENV",
    "VAPID_PUBLIC_KEY_ENV",
]
