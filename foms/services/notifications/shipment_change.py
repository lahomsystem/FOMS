"""시공일 변경 → 출고/시공 담당 팀 벨 알림 + 푸시 (T6).

출고 대시보드는 특정 날짜의 시공 건을 보고 상차·팀 배정·차량을 준비한다. 그 시공일이 다른
화면에서 바뀌면 화면(T4·T5)에는 배너·행 배지가 뜨지만 **화면을 열지 않은 사람은 모른다**.
그 구멍을 벨(알림센터) + OS 푸시로 메운다.

형태는 ``production_change`` 미러(얇은 emitter, ``structured_data`` 무변경)지만 그 모듈의
결함 2가지는 답습하지 않는다.

1. **merge 손실**: 생산은 debounce merge 때 title/message 를 통째로 덮어써 이전 변경의
   ``from`` 이 사라진다(``8/5 → 8/12`` 직후 ``8/12 → 8/20`` 이면 8/5 가 소실). 여기서는
   ``drawing_order_change._merge_change_lists`` 와 같은 규약 — **최초 ``from`` 보존 + 최신
   ``to`` 갱신** — 을 쓴다. 되읽는 근거는 :data:`_MESSAGE_RE`(본문 canonical 포맷).
2. **푸시 미등록**: ``PRODUCTION_ORDER_CHANGED`` 는 ``push_sender._DEFAULT_P1_TYPES`` 에
   없어 enqueue 해도 발송되지 않는다. :data:`NOTIFICATION_TYPE` 은 그 집합에 등록했고
   테스트로 고정한다.

호출 계약 — 쓰기 경로별 명시 호출을 두지 않는다:
    T1(:mod:`foms.services.order_date_sync`)이 시공일 변경 이벤트를 **전역 ``before_flush``
    한 지점**으로 모은 이유가 경로별 emit 의 구멍 6종이었다. 소비자인 이 알림도 같은 이유로
    경로에 손대지 않고 세션 이벤트에 붙는다(:func:`register_shipment_change_alert_listener`).

시각 규약: ``Notification.created_at`` 모델 기본값도 ``now_utc_naive``(2026-08-06 정합)이며 이
모듈은 생성 시 ``now_utc_naive()`` 를 **명시 주입**한다. debounce 가 같은 축(UTC naive)끼리만
비교되게 하려는 것이다 — 로컬 TZ 가 UTC 가 아닌 개발 머신에서 9시간 어긋나 merge 가 죽는 것을
막는다.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from dataclasses import dataclass, replace
from typing import Any, Optional

from flask import has_app_context, has_request_context
from flask import session as flask_session
from sqlalchemy import event
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_display import _normalize_date_to_yyyymmdd
from foms.services.shipment_change_alerts import (
    _chip_customer_name,
    _dates_to_md,
    _is_initial_date_assignment,
)
from models import Notification, Order, User

logger = logging.getLogger(__name__)

__all__ = [
    "DEBOUNCE_SECONDS",
    "NOTIFICATION_TYPE",
    "TARGET_TEAM",
    "ShipmentAlertDispatch",
    "apply_shipment_change_alert",
    "finalize_shipment_change_alert",
    "register_shipment_change_alert_listener",
    "shipment_change_deep_link",
]

#: 벨/푸시 알림 유형(``push_sender._DEFAULT_P1_TYPES`` 에 반드시 함께 등록돼 있어야 한다).
NOTIFICATION_TYPE = "SHIPMENT_ORDER_CHANGED"
#: 수신 팀 코드. ``foms/web/auth/routes.py`` ``TEAMS`` canonical enum 값이며
#: ``recipients.resolve_recipients_for_notification`` 이 ``upper(User.team)`` 로 매칭한다.
#: 운영 DB 활성 사용자 분포(2026-08-05 조회): CONSTRUCTION 10 · SALES 8 · CS 6 · DRAWING 3 ·
#: ADMIN(팀 공란) 2, **SHIPMENT 0명**. '출고팀'(SHIPMENT)은 enum 에만 있고 실사용자가 없어
#: 그쪽을 쓰면 ``PRODUCTION_ORDER_CHANGED``(PRODUCTION 팀 0명)처럼 팬아웃 0건이 된다.
TARGET_TEAM = "CONSTRUCTION"
#: 같은 주문의 연속 변경을 한 줄로 합치는 창(초).
DEBOUNCE_SECONDS = 60

#: 커밋 전 만들어 둔 finalize 입력(주문별). ``Session.info`` 키.
_PENDING_DISPATCH = "foms_shipment_change_alert_dispatch"
#: 전역 ``Session`` 리스너 중복 등록 방지(두 번 등록되면 알림도 2배로 난다).
_LISTENERS_REGISTERED = False

#: 본문 canonical 포맷. merge 시 최초 ``from`` 을 되읽는 유일한 근거이므로 함께 유지한다.
_MESSAGE_TEMPLATE = "주문 #{order_id} — 시공일 {from_md} → {to_md}"
_MESSAGE_RE = re.compile(r"^주문 #\d+ — 시공일 (?P<from_md>.+?) → (?P<to_md>.+)$")


@dataclass(frozen=True)
class ShipmentAlertDispatch:
    """커밋 이후 finalize 가 쓰는 값 묶음(ORM 객체를 담지 않는다).

    세션은 ``expire_on_commit=True`` 라 커밋 뒤 ORM 속성을 읽으면 refresh SELECT 가 나가
    ``after_commit`` 안에서 새 트랜잭션이 열린다. 그래서 필요한 값만 커밋 전에 굳혀 옮긴다.
    """

    notification_id: int
    order_id: int
    title: str
    message: str
    recipient_user_ids: tuple[int, ...]
    created_new: bool


# --------------------------------------------------------------------------- #
# 본문 조립
# --------------------------------------------------------------------------- #
def _customer_name(order: Order) -> str:
    """제목에 쓸 고객명(flat 컬럼 → ``structured_data`` 폴백). 없으면 ``'-'``.

    Args:
        order: 대상 주문.

    Returns:
        고객명 문자열(항상 비어 있지 않다).
    """
    return _chip_customer_name(order) or "-"


def _format_message(order_id: int, from_md: str, to_md: str) -> str:
    """본문 canonical 1줄(``주문 #12 — 시공일 8/5 → 8/12``).

    Args:
        order_id: 주문 id.
        from_md: 이전 시공일 표기(``M/D``, 다중값 가능).
        to_md: 이후 시공일 표기.

    Returns:
        알림 본문 문자열.
    """
    return _MESSAGE_TEMPLATE.format(order_id=int(order_id), from_md=from_md, to_md=to_md)


def _original_from(previous_message: Optional[str], fallback_from_md: str) -> str:
    """merge 대상 본문에서 **최초 ``from``** 을 되읽는다(생산 emitter 의 결함 교정).

    Args:
        previous_message: 기존 알림 본문(손상·구형이어도 예외를 던지지 않는다).
        fallback_from_md: 파싱 실패 시 사용할 이번 변경의 ``from``.

    Returns:
        보존할 ``from`` 표기.
    """
    match = _MESSAGE_RE.match((previous_message or "").strip())
    if match is None:
        logger.debug("[SHIPMENT_BELL] 이전 본문 파싱 실패 — 이번 from 사용: %r", previous_message)
        return fallback_from_md
    return match.group("from_md")


# --------------------------------------------------------------------------- #
# 딥링크 (모델에 링크 컬럼이 없어 읽는 시점 파생)
# --------------------------------------------------------------------------- #
def _current_construction_date(order_structured_data: Any) -> str:
    """주문의 현재 시공일 1개를 ``YYYY-MM-DD`` 로 뽑는다(못 읽으면 빈 문자열).

    ``schedule.construction.date`` 를 우선하고, 비어 있으면 품목별 ``construction_date`` 를
    순서대로 훑는다(출고 대시보드가 실제로 날짜 필터에 쓰는 두 표현형).

    Args:
        order_structured_data: 주문 ``structured_data``(dict 가 아니어도 죽지 않는다).

    Returns:
        정규화된 날짜 문자열 또는 빈 문자열.
    """
    sd = order_structured_data if isinstance(order_structured_data, dict) else {}
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    construction = schedule.get("construction") if isinstance(schedule.get("construction"), dict) else {}
    candidates = [construction.get("date")]
    for item in sd.get("items") or []:
        if isinstance(item, dict):
            candidates.append(item.get("construction_date"))
    for raw in candidates:
        for token in str(raw or "").split(","):
            normalized = _normalize_date_to_yyyymmdd(token.strip())
            if normalized:
                return str(normalized)
    return ""


def shipment_change_deep_link(order_structured_data: Any) -> str:
    """벨 항목 → **옮겨간 시공일의 출고 대시보드** same-origin 딥링크.

    ``Notification`` 모델에는 링크/날짜 컬럼이 **없다**(스키마 무변경 원칙 — 없는 필드를
    지어내지 않는다). 그래서 링크는 목록 API 가 이미 로드하는 주문 ``structured_data`` 에서
    **읽는 시점에** 파생한다. 변경 직후의 현재 시공일이 곧 "옮겨간 날짜"다. 날짜를 못 읽으면
    날짜 없는 대시보드로 보낸다(오늘 기준으로 열린다).

    Args:
        order_structured_data: 알림이 가리키는 주문의 ``structured_data``.

    Returns:
        ``/erp/shipment?date=YYYY-MM-DD`` 또는 ``/erp/shipment``.
    """
    date = _current_construction_date(order_structured_data)
    return f"/erp/shipment?date={date}" if date else "/erp/shipment"


# --------------------------------------------------------------------------- #
# apply / finalize
# --------------------------------------------------------------------------- #
def _find_recent_notification(
    db: Session, order_id: int, *, now: _dt.datetime
) -> Optional[Notification]:
    """동일 order+type 의 60초 내 최근 알림(actor 무관). 없으면 ``None``.

    Args:
        db: 활성 세션.
        order_id: 대상 주문 id.
        now: 비교 기준 시각(UTC naive).

    Returns:
        merge 대상 :class:`~models.Notification` 또는 ``None``.
    """
    prev = (
        db.query(Notification)
        .filter(
            Notification.order_id == order_id,
            Notification.notification_type == NOTIFICATION_TYPE,
        )
        .order_by(Notification.id.desc())
        .first()
    )
    if prev is None or prev.created_at is None:
        return None
    if (now - prev.created_at).total_seconds() > DEBOUNCE_SECONDS:
        return None
    return prev


def _recipient_user_ids(db: Session) -> tuple[int, ...]:
    """배지 무효화·realtime 대상(팀원 + ADMIN)을 커밋 전에 굳힌다.

    ``after_commit`` 에서 조회하면 새 트랜잭션이 열리므로 여기서 미리 확정한다.

    Args:
        db: 활성 세션.

    Returns:
        오름차순 user id 튜플.
    """
    from foms.api.notifications import resolve_notification_recipient_user_ids

    ids = resolve_notification_recipient_user_ids(
        db,
        target_type="TEAM",
        target_team=TARGET_TEAM,
        target_manager_name=None,
        include_admin=True,
    )
    return tuple(sorted(int(uid) for uid in ids))


def _create_notification(
    db: Session,
    order: Order,
    *,
    title: str,
    message: str,
    actor_user_id: Optional[int],
    actor_name: str,
    now: _dt.datetime,
) -> Notification:
    """신규 알림 row 를 만들고 **같은 트랜잭션에서** 팀 팬아웃한다.

    공유 ``notification_user_states`` row 를 직접 만들지 않고 반드시
    ``fan_out_new_notification`` 훅을 경유한다(알림 SSOT 규약).

    Args:
        db: 활성 세션.
        order: 대상 주문.
        title: 알림 제목.
        message: 알림 본문.
        actor_user_id: 변경자 id(요청 밖이면 ``None``).
        actor_name: 변경자 표시명.
        now: 생성 시각(UTC naive).

    Returns:
        flush 되어 id 가 채워진 :class:`~models.Notification`.
    """
    from foms.services.notifications.recipients import fan_out_new_notification

    notif = Notification(
        order_id=int(order.id),
        notification_type=NOTIFICATION_TYPE,
        target_type="TEAM",
        target_team=TARGET_TEAM,
        title=title,
        message=message,
        created_by_user_id=actor_user_id,
        created_by_name=actor_name or None,
        created_at=now,
    )
    db.add(notif)
    db.flush()
    fan_out_new_notification(db, notif, actor_user_id=actor_user_id)
    return notif


def _upsert_alert_notification(
    db: Session,
    order: Order,
    *,
    from_md: str,
    to_md: str,
    title: str,
    actor_user_id: Optional[int],
    actor_name: str,
) -> tuple[Notification, bool]:
    """60초 debounce — merge 대상이 있으면 갱신하고, 없으면 새로 만든다.

    merge 는 최초 ``from`` 을 보존하고 ``to`` 만 최신으로 올린다.

    Args:
        db: 활성 세션.
        order: 대상 주문.
        from_md: 이번 변경의 이전 시공일 표기.
        to_md: 이번 변경의 이후 시공일 표기.
        title: 알림 제목.
        actor_user_id: 변경자 id.
        actor_name: 변경자 표시명.

    Returns:
        ``(notification, created_new)``.
    """
    order_id = int(order.id)
    now = now_utc_naive()
    prev = _find_recent_notification(db, order_id, now=now)
    if prev is not None:
        prev.title = title
        prev.message = _format_message(order_id, _original_from(prev.message, from_md), to_md)
        return prev, False
    notif = _create_notification(
        db,
        order,
        title=title,
        message=_format_message(order_id, from_md, to_md),
        actor_user_id=actor_user_id,
        actor_name=actor_name,
        now=now,
    )
    return notif, True


def apply_shipment_change_alert(
    db: Session,
    order: Order,
    *,
    from_dates: Any,
    to_dates: Any,
    actor_user_id: Optional[int] = None,
    actor_name: str = "",
) -> Optional[ShipmentAlertDispatch]:
    """커밋 **전** 호출: 알림을 생성하거나 60초 debounce merge 한다.

    연속 이동(``8/5 → 8/12`` 뒤 ``8/12 → 8/20``)은 ``8/5 → 8/20`` 한 줄로 남는다.
    **최초 지정**(``미정 → 날짜``)은 변경이 아니라서 ``None`` 을 돌려 알림을 만들지 않는다.

    Args:
        db: 활성 세션(호출자 트랜잭션, 커밋하지 않는다).
        order: 대상 주문(영속 상태, ``id`` 필요).
        from_dates: T1 payload 의 ``from``(정규화·콤마 연결 문자열).
        to_dates: T1 payload 의 ``to``.
        actor_user_id: 변경자 id(요청 밖이면 ``None``).
        actor_name: 변경자 표시명.

    Returns:
        커밋 후 :func:`finalize_shipment_change_alert` 에 그대로 넘길 dispatch.
        최초 지정이면 ``None``.
    """
    if _is_initial_date_assignment(from_dates):
        logger.debug(
            "[SHIPMENT_BELL] 최초 시공일 지정은 알림 제외: order=%s from=%r to=%r",
            getattr(order, "id", None),
            from_dates,
            to_dates,
        )
        return None
    order_id = int(order.id)
    notif, created_new = _upsert_alert_notification(
        db,
        order,
        from_md=_dates_to_md(from_dates),
        to_md=_dates_to_md(to_dates),
        title=f"[출고] 시공일 변경 — {_customer_name(order)}",
        actor_user_id=actor_user_id,
        actor_name=actor_name,
    )
    return ShipmentAlertDispatch(
        notification_id=int(notif.id),
        order_id=order_id,
        title=notif.title,
        message=notif.message,
        recipient_user_ids=_recipient_user_ids(db),
        created_new=created_new,
    )


def finalize_shipment_change_alert(db: Session, dispatch: ShipmentAlertDispatch) -> None:
    """커밋 **후** 호출: push enqueue(신규만) + 배지 무효화 + realtime emit.

    debounce merge(``created_new=False``)는 OS push 만 생략한다 — 60초 안에 두 번 울리지
    않게 하되 배지/실시간 갱신은 유지한다.

    Args:
        db: push enqueue 가 큐 미가용 표기에 쓸 세션.
        dispatch: :func:`apply_shipment_change_alert` 가 돌려준 값 묶음.

    Returns:
        None.
    """
    from foms.api.notifications import invalidate_badge_cache_for_user_ids

    # 배지 캐시는 in-process dict 라 앱 컨텍스트가 없어도 안전하다.
    invalidate_badge_cache_for_user_ids(dispatch.recipient_user_ids)
    if not has_app_context():
        logger.debug(
            "[SHIPMENT_BELL] 앱 컨텍스트 밖 — push/realtime 생략(id=%s)",
            dispatch.notification_id,
        )
        return

    if dispatch.created_new:
        from foms.services.notifications.push_sender import enqueue_push_for_notification

        enqueue_push_for_notification(dispatch.notification_id, db=db)

    from foms.services.notifications.realtime_notifications import (
        emit_erp_notification_to_users,
    )

    emit_erp_notification_to_users(
        dispatch.recipient_user_ids,
        {
            "notification_id": dispatch.notification_id,
            "order_id": dispatch.order_id,
            "notification_type": NOTIFICATION_TYPE,
            "title": dispatch.title,
            "message": dispatch.message,
        },
    )


# --------------------------------------------------------------------------- #
# 세션 이벤트 배선
# --------------------------------------------------------------------------- #
def _resolve_actor(db: Session) -> tuple[Optional[int], str]:
    """변경자(id·표시명). 요청 컨텍스트가 없으면 ``(None, "")``.

    Args:
        db: 활성 세션(사용자 표시명 조회용, 대개 identity map 적중).

    Returns:
        ``(actor_user_id, actor_name)``.
    """
    if not has_request_context():
        return None, ""
    raw_user_id = flask_session.get("user_id")
    if not str(raw_user_id or "").strip().isdigit():
        return None, ""
    actor_id = int(raw_user_id)
    user = db.get(User, actor_id)
    return actor_id, str(getattr(user, "name", "") or "").strip()


def _apply_pending_alerts(session: Session) -> None:
    """``before_commit``: T1 이 이번 트랜잭션에 남긴 시공일 변경마다 알림을 반영한다.

    같은 트랜잭션에서 before_commit 이 두 번 돌아도(savepoint 커밋 등) 주문별 dispatch 를
    덮어쓰며 ``created_new`` 만 OR 로 유지하므로 중복 발송이 나지 않는다.

    Args:
        session: 커밋 직전 세션.

    Returns:
        None.
    """
    from foms.services.order_date_sync import pending_construction_date_changes

    # ``before_commit`` 은 커밋이 수행하는 flush 보다 **먼저** 돈다. T1 은 ``before_flush``
    # 에서 변경을 기록하므로, 여기서 한 번 flush 해 주지 않으면 방금 바뀐 시공일을 못 본다.
    # 커밋이 직후에 같은 flush 를 하고 flush() 는 clean 세션에서 즉시 반환하므로 추가 비용은 없다.
    session.flush()
    changes = pending_construction_date_changes(session)
    if not changes:
        return
    actor_user_id, actor_name = _resolve_actor(session)
    pending = session.info.setdefault(_PENDING_DISPATCH, {})
    for order_id, change in changes.items():
        order = session.get(Order, order_id)
        if order is None or order in session.deleted:
            continue
        dispatch = apply_shipment_change_alert(
            session,
            order,
            from_dates=change["from"],
            to_dates=change["to"],
            actor_user_id=actor_user_id,
            actor_name=actor_name,
        )
        if dispatch is None:
            continue
        previous = pending.get(order_id)
        if previous is not None and previous.created_new:
            dispatch = replace(dispatch, created_new=True)
        pending[order_id] = dispatch


def _finalize_pending_alerts(session: Session) -> None:
    """``after_commit``: 굳혀 둔 dispatch 를 소비한다.

    push enqueue 는 큐 미가용 시 자체적으로 ``db.commit()`` 을 한 번 더 한다. 그래서 처리
    **전에** ``session.info`` 에서 먼저 꺼내 재진입이 no-op 이 되게 한다.

    Args:
        session: 커밋 직후 세션.

    Returns:
        None.
    """
    pending = session.info.pop(_PENDING_DISPATCH, None)
    if not pending:
        return
    for dispatch in pending.values():
        finalize_shipment_change_alert(session, dispatch)


def register_shipment_change_alert_listener() -> None:
    """전역 ``Session`` 에 출고 벨 알림 리스너를 **1회** 등록한다.

    왜 T1 의 ``before_flush`` 안에서 알림을 만들지 않는가:
    ``fan_out_new_notification`` 은 수신자 조회 후 ``flush()`` 를 부르고, 알림 row 도 새로
    add 한다. 그것을 flush 훅 안에서 하면 같은 flush 에 재진입하며 T1 이 어렵게 세운
    "경로당 이벤트 정확히 1건" 상태기계를 흔든다. 대신 두 지점으로 나눈다.

    * ``before_commit`` — 아직 **같은 트랜잭션**이고, SQLAlchemy 가 이 훅 직후 세션이
      clean 해질 때까지 flush 를 반복하므로 여기서 add/flush 해도 안전하다. 알림 row 와
      주문 변경이 원자적으로 함께 커밋된다(고아 알림 0).
    * ``after_commit`` — push enqueue·배지 무효화·realtime(커밋 후에만 의미가 있는 것들).

    쓰기 경로마다 명시 호출을 심는 대안은 채택하지 않는다. T1 이 바로 그 방식의 구멍 6종
    (재예약·품목별 날짜·레거시 폼 등)을 없애려고 이벤트를 한 지점으로 모았는데, 소비자를
    경로별로 흩으면 같은 구멍이 알림 쪽에 그대로 되살아난다.

    생성(신규 주문)에는 반응하지 않는다 — T1 이 ``session.new`` 를 이벤트 대상에서 제외해
    애초에 pending 상태가 만들어지지 않는다.

    Returns:
        None.
    """
    global _LISTENERS_REGISTERED
    if _LISTENERS_REGISTERED:
        return
    _LISTENERS_REGISTERED = True

    @event.listens_for(Session, "before_commit")
    def _shipment_alert_before_commit(session):
        _apply_pending_alerts(session)

    @event.listens_for(Session, "after_commit")
    def _shipment_alert_after_commit(session):
        _finalize_pending_alerts(session)

    @event.listens_for(Session, "after_soft_rollback")
    def _shipment_alert_after_soft_rollback(session, previous_transaction):
        # 롤백된 트랜잭션의 알림 id 는 존재하지 않는다 — 다음 커밋으로 새어가면 안 된다.
        session.info.pop(_PENDING_DISPATCH, None)
