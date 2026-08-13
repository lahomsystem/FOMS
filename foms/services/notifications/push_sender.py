"""ERP 알림 Web Push 발송 서비스 (Phase 3C).

RQ worker 에서 실행되는 순수 발송 함수와, 알림 생성 트랜잭션 커밋 이후 push job 을
enqueue 하는 헬퍼를 제공한다. 설계 원칙:

- job payload 에는 ``notification_id`` 만 싣는다. endpoint/p256dh/auth 같은 구독 비밀은
  worker 가 DB 에서 재조회하며, 절대 payload·로그·이벤트에 원문을 남기지 않는다(sha256 hex 만).
- payload 본문은 **generic**: 고객명·주문번호·현장정보·사유를 담지 않는다. 상세는 앱을
  열어 확인한다. deep_link 는 same-origin ``/erp/...`` 경로만 담는다.
- severity 게이트: 긴급(is_urgent)=P0 항상 발송, 지정된 P1 유형만 발송, 그 외 P2 는 no-op.
- ``pywebpush`` 는 lazy import(함수 내부) 한다 — 미설치 환경에서 app import 가 죽지 않게 한다.
"""

from __future__ import annotations

import datetime as _dt

from foms.services.datetime_kst import now_utc_naive
import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from db import db_session, get_db
from models import (
    Notification,
    NotificationDeliveryStatus,
    NotificationEvent,
    NotificationEventType,
    NotificationPushSubscription,
    NotificationUserState,
)

logger = logging.getLogger(__name__)

# RQ enqueue 시 사용하는 canonical task 경로 접두어(queue.py 와 동일 규약).
_TASK_PATH_PREFIX = "foms.services.jobs.tasks"
_PUSH_TASK = f"{_TASK_PATH_PREFIX}.send_push_for_notification_task"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# 비긴급 알림 중 push 를 발송하는 P1 유형 기본 집합(env 로 override 가능).
_DEFAULT_P1_TYPES = frozenset(
    {
        "DRAWING_TRANSFERRED",
        "DRAWING_REVISION",
        "QUEST_ASSIGNED",
        "ERP_ORDER_CHANGED",
        # 시공일 이동은 상차·차량·팀 배정을 즉시 무효로 만든다 — 화면을 안 보고 있어도 알린다.
        # (미등록이면 enqueue 해도 조용히 no-op 된다 — 등록 누락 = 무음 push 의 유일한 기전.)
        "SHIPMENT_ORDER_CHANGED",
        # 생산 진행 중 주문의 시공일·도면 변경/취소도 같은 성질이다(재작업·자재 낭비 직결).
        "PRODUCTION_ORDER_CHANGED",
        # 에스컬레이션 row 는 is_urgent=False(재진입 방지)이므로 P1 로 OS push 허용.
        "URGENT_ESCALATION",
        # 앱 인증 만료는 화면을 안 보고 있어도 알려야 한다 — 만료되면 주문 수집이
        # 조용히 전면 중단되고 우리 화면엔 아무 에러도 안 뜬다(NAVER-INGEST-01 §5).
        "NAVER_APP_EXPIRY",
    }
)

# 이미 더 진행된 상태이면 last_delivery_status 를 push 결과로 덮어쓰지 않는다.
_TERMINAL_STATUSES = frozenset(
    {
        NotificationDeliveryStatus.OPENED,
        NotificationDeliveryStatus.ACK,
        NotificationDeliveryStatus.RESOLVED,
    }
)


# ---------------------------------------------------------------------------
# env / helpers
# ---------------------------------------------------------------------------

def _web_push_enabled() -> bool:
    """``FOMS_WEB_PUSH_ENABLED`` env 가 truthy 인지 반환(기본 off)."""
    return (os.environ.get("FOMS_WEB_PUSH_ENABLED", "") or "").strip().lower() in _TRUTHY


def _vapid_private_key() -> str:
    """VAPID 개인키 문자열(미설정 시 빈 문자열)."""
    return (os.environ.get("VAPID_PRIVATE_KEY", "") or "").strip()


def _vapid_claims_sub() -> str:
    """VAPID ``sub`` 클레임(mailto). 미설정 시 운영 기본 주소."""
    return (
        os.environ.get("VAPID_CLAIMS_SUB", "") or ""
    ).strip() or "mailto:lahomsystem@gmail.com"


def _p1_types() -> frozenset:
    """push 대상 P1 유형 집합. env ``FOMS_PUSH_P1_TYPES``(콤마구분)로 override."""
    raw = (os.environ.get("FOMS_PUSH_P1_TYPES", "") or "").strip()
    if not raw:
        return _DEFAULT_P1_TYPES
    return frozenset({t.strip().upper() for t in raw.split(",") if t.strip()})


def _endpoint_hash(endpoint: str) -> str:
    """push endpoint 원문의 sha256 hex(로그/이벤트용, 원문 유출 방지)."""
    return hashlib.sha256((endpoint or "").encode("utf-8")).hexdigest()


def _now() -> _dt.datetime:
    """현재 시각(naive UTC — 모델 기본값 now_utc_naive 와 동일 규약)."""
    return now_utc_naive()


def _import_pywebpush() -> Tuple[Any, Any]:
    """``(webpush, WebPushException)`` 반환. 미설치면 ImportError 를 그대로 전파."""
    from pywebpush import WebPushException, webpush  # lazy import

    return webpush, WebPushException


def _should_push(notif: Notification) -> bool:
    """severity 게이트: 긴급이거나 지정 P1 유형이면 True(그 외 P2 no-op)."""
    if bool(notif.is_urgent):
        return True
    return (notif.notification_type or "").strip().upper() in _p1_types()


def _deep_link(notif: Notification) -> str:
    """same-origin deep link. 도면 주문변경/수정요청은 워크벤치, 그 외 주문은 상세."""
    if notif.order_id:
        ntype = (notif.notification_type or "").strip().upper()
        oid = int(notif.order_id)
        if ntype == "ERP_ORDER_CHANGED":
            return f"/erp/drawing-workbench/{oid}?tab=timeline"
        if ntype in ("DRAWING_TRANSFERRED", "DRAWING_REVISION"):
            tab = "timeline" if ntype == "DRAWING_TRANSFERRED" else "requests"
            return f"/erp/drawing-workbench/{oid}?tab={tab}"
        if ntype == "SHIPMENT_ORDER_CHANGED":
            # 날짜는 붙이지 않는다 — push payload 는 generic 규약이고 Notification 모델에도
            # 날짜 컬럼이 없다. 대시보드는 오늘로 열리며, 정확한 날짜 링크는 벨 목록 API
            # (`_resolve_notification_deep_link`)가 주문 현재 시공일에서 파생해 준다.
            return "/erp/shipment"
        if ntype == "PRODUCTION_ORDER_CHANGED":
            # 생산 칸반이 이 알림의 작업 화면이다(주문 상세가 아니라). 출고와 같은 이유로
            # 파라미터는 붙이지 않는다 — payload 는 generic 규약.
            return "/erp/production/dashboard"
        return f"/erp/orders/{oid}"
    return "/erp"


def _generic_title(urgent: bool, ntype: str) -> str:
    """유형별 일반 제목(민감정보 없음)."""
    if urgent:
        return "긴급 알림"
    if ntype == "ERP_ORDER_CHANGED":
        return "도면·주문 변경"
    if ntype in ("DRAWING_TRANSFERRED", "DRAWING_REVISION"):
        return "도면 알림"
    if ntype == "SHIPMENT_ORDER_CHANGED":
        return "출고 일정 변경"
    if ntype == "PRODUCTION_ORDER_CHANGED":
        # 시공일/도면/취소 세 종류를 묶는 제목 — 고객명·주문번호·사유는 넣지 않는다.
        return "생산 주문 변경"
    if ntype == "QUEST_ASSIGNED":
        return "업무 배정 알림"
    if ntype == "URGENT_ESCALATION":
        return "에스컬레이션"
    return "새 알림"


def _build_payload(notif: Notification) -> Dict[str, Any]:
    """generic push payload 구성(고객명/주문번호/사유 금지)."""
    urgent = bool(notif.is_urgent)
    ntype = (notif.notification_type or "").strip().upper()
    payload: Dict[str, Any] = {
        "title": _generic_title(urgent, ntype),
        "body": (
            "긴급 확인이 필요한 알림이 있습니다."
            if urgent
            else (
                "미확인 긴급 알림이 에스컬레이션되었습니다."
                if ntype == "URGENT_ESCALATION"
                else "확인이 필요한 새 알림이 있습니다."
            )
        ),
        "data": {"notification_id": int(notif.id), "deep_link": _deep_link(notif)},
    }
    if urgent:
        payload["requireInteraction"] = True
        payload["tag"] = f"foms-urgent-{int(notif.id)}"
        payload["renotify"] = True
    return payload


def _test_payload() -> Dict[str, Any]:
    """구독 검증용 generic 테스트 payload."""
    return {
        "title": "테스트 알림",
        "body": "푸시 알림이 정상적으로 동작합니다.",
        "data": {"test": True, "deep_link": "/erp"},
    }


# ---------------------------------------------------------------------------
# DB 조회 헬퍼
# ---------------------------------------------------------------------------

def _pending_states(db: Any, notification_id: int) -> List[NotificationUserState]:
    """아직 열람/확인/해결되지 않은 수신자 state 목록."""
    return (
        db.query(NotificationUserState)
        .filter(
            NotificationUserState.notification_id == int(notification_id),
            ~NotificationUserState.last_delivery_status.in_(_TERMINAL_STATUSES),
        )
        .all()
    )


def _active_subscriptions(db: Any, user_id: int) -> List[NotificationPushSubscription]:
    """대상 사용자의 활성(미revoke) 구독 전체(다중 디바이스 지원)."""
    return (
        db.query(NotificationPushSubscription)
        .filter(
            NotificationPushSubscription.user_id == int(user_id),
            NotificationPushSubscription.revoked_at.is_(None),
        )
        .all()
    )


def _record_event(
    db: Any,
    notif: Notification,
    state: NotificationUserState,
    event_type: str,
    endpoint_hash: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """append-only push 이벤트 1건 기록(endpoint 원문 금지, hash 만)."""
    db.add(
        NotificationEvent(
            notification_id=notif.id,
            user_state_id=state.id,
            recipient_user_id=state.user_id,
            event_type=event_type,
            channel="webpush",
            endpoint_hash=endpoint_hash,
            metadata_json=metadata,
        )
    )


def _update_state_status(state: NotificationUserState, any_success: bool) -> None:
    """구독 발송 결과를 state 에 반영(더 진행된 상태는 덮어쓰지 않음)."""
    if state.last_delivery_status in _TERMINAL_STATUSES:
        return
    state.last_delivery_status = (
        NotificationDeliveryStatus.PUSH_ATTEMPTED
        if any_success
        else NotificationDeliveryStatus.PUSH_FAILED
    )


# ---------------------------------------------------------------------------
# 발송 core
# ---------------------------------------------------------------------------

def _deliver_one(
    db: Any,
    notif: Notification,
    state: NotificationUserState,
    sub: NotificationPushSubscription,
    payload_json: str,
    webpush: Any,
    web_push_exc: Any,
) -> str:
    """단일 구독 발송. 'sent' / 'revoked' / 'failed' 중 하나를 반환(예외 미전파)."""
    ep_hash = _endpoint_hash(sub.endpoint)
    sub_info = {
        "endpoint": sub.endpoint,
        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
    }
    try:
        webpush(
            sub_info,
            payload_json,
            vapid_private_key=_vapid_private_key(),
            vapid_claims={"sub": _vapid_claims_sub()},
        )
    except web_push_exc as exc:  # 구독 만료/유효성 실패
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code in (404, 410):
            if sub.revoked_at is None:
                sub.revoked_at = _now()
            _record_event(db, notif, state, NotificationEventType.PUSH_FAILED,
                          ep_hash, {"code": code, "reason": "gone"})
            return "revoked"
        logger.warning("[push] webpush failed hash=%s code=%s", ep_hash, code)
        _record_event(db, notif, state, NotificationEventType.PUSH_FAILED,
                      ep_hash, {"code": code})
        return "failed"
    except Exception as exc:  # noqa: BLE001 - 다음 구독 계속(raise 안 함)
        logger.error("[push] unexpected send error hash=%s: %s", ep_hash, exc)
        _record_event(db, notif, state, NotificationEventType.PUSH_FAILED,
                      ep_hash, {"error": "send_error"})
        return "failed"
    _record_event(db, notif, state, NotificationEventType.PUSH_ATTEMPTED, ep_hash)
    return "sent"


def _send_push_impl(db: Any, notification_id: int) -> Dict[str, Any]:
    """실제 발송 로직(주어진 세션 사용, commit 은 호출자 책임)."""
    notif = (
        db.query(Notification).filter(Notification.id == int(notification_id)).first()
    )
    if notif is None:
        return {"sent": 0, "failed": 0, "revoked": 0, "reason": "notification_not_found"}
    if not _should_push(notif):
        return {"sent": 0, "failed": 0, "revoked": 0, "reason": "severity_skipped"}

    states = _pending_states(db, notif.id)
    if not states:
        return {"sent": 0, "failed": 0, "revoked": 0, "reason": "no_pending_states"}

    try:
        webpush, web_push_exc = _import_pywebpush()
    except ImportError:
        logger.error("[push] pywebpush 미설치 - 발송 불가")
        return {"sent": 0, "failed": 0, "revoked": 0, "reason": "pywebpush_unavailable"}

    payload_json = json.dumps(_build_payload(notif), ensure_ascii=False)
    sent = failed = revoked = 0
    for state in states:
        subs = _active_subscriptions(db, state.user_id)
        if not subs:
            continue
        any_success = False
        for sub in subs:
            outcome = _deliver_one(
                db, notif, state, sub, payload_json, webpush, web_push_exc
            )
            if outcome == "sent":
                sent += 1
                any_success = True
            elif outcome == "revoked":
                revoked += 1
                failed += 1
            else:
                failed += 1
        _update_state_status(state, any_success)
    db.flush()
    return {"sent": sent, "failed": failed, "revoked": revoked, "reason": None}


def send_push_for_notification(
    notification_id: int, db: Any = None
) -> Dict[str, Any]:
    """알림 1건을 대상 수신자들에게 Web Push 발송(RQ task 진입점).

    job payload 는 ``notification_id`` 만 전달되며, 구독 비밀은 여기서 DB 재조회한다.
    발송 성공/실패는 append-only 이벤트와 user_state 상태로 기록한다. 개별 구독 실패는
    다음 구독으로 계속 진행하고 전체를 raise 하지 않는다(알림 자체는 영향 없음).

    :param notification_id: 발송 대상 알림 id
    :param db: 테스트/재사용용 세션(기본 None → worker db_session 자체 관리)
    :return: {sent, failed, revoked, reason} 요약
    """
    owns_session = db is None
    if owns_session:
        db = db_session()
    try:
        result = _send_push_impl(db, int(notification_id))
        if owns_session:
            db.commit()
        return result
    except Exception:
        if owns_session:
            db.rollback()
        raise
    finally:
        if owns_session:
            db_session.remove()


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------

def _mark_queue_unavailable(db: Any, notification_id: int) -> None:
    """큐/worker 미가용 시 대상 state 를 queue_unavailable 로 표시 + 이벤트 기록."""
    notif = (
        db.query(Notification).filter(Notification.id == int(notification_id)).first()
    )
    if notif is None:
        return
    for state in _pending_states(db, notif.id):
        if state.last_delivery_status not in _TERMINAL_STATUSES:
            state.last_delivery_status = NotificationDeliveryStatus.QUEUE_UNAVAILABLE
        db.add(
            NotificationEvent(
                notification_id=notif.id,
                user_state_id=state.id,
                recipient_user_id=state.user_id,
                event_type=NotificationEventType.PUSH_QUEUE_UNAVAILABLE,
                channel="webpush",
            )
        )
    db.flush()


def enqueue_push_for_notification(
    notification_id: int, db: Any = None
) -> Dict[str, Any]:
    """알림 생성 커밋 이후 push job 을 enqueue.

    - flag off → 조용히 skip(이벤트 없음).
    - 큐 없음/worker 0 → 대상 state 를 queue_unavailable 로 표시하고 이벤트를 남긴다
      (조용히 버리지 않음). 호출측 API 는 이 reason 으로 os_push 미보장을 노출할 수 있다.
    - 정상 → RQ 문자열 경로로 enqueue.

    :param notification_id: enqueue 대상 알림 id
    :param db: queue_unavailable 표기에 쓸 세션(기본 None → 요청 컨텍스트 get_db)
    :return: {enqueued: bool, reason: Optional[str]}
    """
    if not _web_push_enabled():
        return {"enqueued": False, "reason": "flag_off"}

    from foms.services.jobs.queue import get_rq_queue, get_rq_runtime_status

    if db is None:
        db = get_db()

    q = get_rq_queue()
    status = get_rq_runtime_status()
    if q is None or int(status.get("worker_count", 0) or 0) == 0:
        _mark_queue_unavailable(db, int(notification_id))
        db.commit()
        return {"enqueued": False, "reason": "queue_unavailable"}

    try:
        q.enqueue(_PUSH_TASK, int(notification_id), job_timeout="2m")
        return {"enqueued": True, "reason": None}
    except Exception as exc:  # noqa: BLE001 - enqueue 실패도 미보장으로 표기
        logger.error("[push] enqueue failed id=%s: %s", notification_id, exc, exc_info=True)
        _mark_queue_unavailable(db, int(notification_id))
        db.commit()
        return {"enqueued": False, "reason": "queue_unavailable"}


# ---------------------------------------------------------------------------
# 테스트 발송(구독 직접 발송, notification row 없음)
# ---------------------------------------------------------------------------

def _send_test_impl(db: Any, subscription_id: int, owns: bool) -> Dict[str, Any]:
    """구독 1건에 generic 테스트 payload 를 즉시 발송."""
    try:
        webpush, web_push_exc = _import_pywebpush()
    except ImportError:
        return {"sent": False, "reason": "pywebpush_unavailable"}
    if not _vapid_private_key():
        return {"sent": False, "reason": "vapid_not_configured"}

    sub = (
        db.query(NotificationPushSubscription)
        .filter(
            NotificationPushSubscription.id == int(subscription_id),
            NotificationPushSubscription.revoked_at.is_(None),
        )
        .first()
    )
    if sub is None:
        return {"sent": False, "reason": "no_active_subscription"}

    ep_hash = _endpoint_hash(sub.endpoint)
    sub_info = {
        "endpoint": sub.endpoint,
        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
    }
    payload = json.dumps(_test_payload(), ensure_ascii=False)
    try:
        webpush(
            sub_info,
            payload,
            vapid_private_key=_vapid_private_key(),
            vapid_claims={"sub": _vapid_claims_sub()},
        )
    except web_push_exc as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code in (404, 410):
            if sub.revoked_at is None:
                sub.revoked_at = _now()
            if owns:
                db.commit()
            return {"sent": False, "reason": "subscription_expired", "code": code}
        logger.warning("[push] test webpush failed hash=%s code=%s", ep_hash, code)
        return {"sent": False, "reason": "push_failed", "code": code}
    except Exception as exc:  # noqa: BLE001
        logger.error("[push] test send error hash=%s: %s", ep_hash, exc)
        return {"sent": False, "reason": "push_failed"}
    return {"sent": True, "reason": None}


def send_test_push(subscription_id: int, db: Any = None) -> Dict[str, Any]:
    """구독 id 로 즉시 테스트 푸시 발송(알림 row 없이 generic payload).

    :param subscription_id: 대상 활성 구독 id
    :param db: 재사용 세션(기본 None → 요청 컨텍스트 get_db 사용, remove 안 함)
    :return: {sent: bool, reason: Optional[str], code?: int}
    """
    owns = db is None
    if owns:
        db = get_db()
    return _send_test_impl(db, int(subscription_id), owns)


__all__ = [
    "send_push_for_notification",
    "enqueue_push_for_notification",
    "send_test_push",
]
