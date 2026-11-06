"""주문 ↔ 프리랜서 연결을 주문 저장 때마다 맞추는 전역 세션 훅 + 배정 알림 ``SALES_ORDER_ASSIGNED``(FCOMM-01 §5 · §7).

왜 전역 훅인가 — :mod:`foms.services.order_date_sync` 와 같은 이유다. ``structured_data`` 를 고치는 쓰기 길이
수십 곳이고(``flag_modified`` 하면서 ``sync_erp_flat_columns`` 를 안 부르는 파일 28개, 오프라인 병합 포함 — 검수
원장 F1 · A19), 모든 ORM 쓰기가 지나는 곳은 flush 하나뿐이다. ``sync_erp_flat_columns`` 에 넣지 않는 까닭은
그 함수가 읽기 전용 점검의 가짜 객체(``erp_flat_audit._DeriveShim``)와 시험용 SimpleNamespace 로도 불리기
때문이다(검수 원장 A7 · F2). 이 훅은 세션에 실제로 든 ``Order`` ORM 객체만 본다.

흐름
1. ``before_flush`` — 새 ERP 주문, 또는 ``structured_data``(초안 승격을 보려고 ``status`` 도)가 바뀐 ERP 주문마다
   :func:`~foms.services.sales_commission.links.desired_links` 로 가져야 할 연결을 구하고 지금 줄과 맞춘다(더하기 ·
   지우기, ``CREATOR`` 는 지우지 않음). 켜진 프리랜서가 없으면 **아무것도 안 한다**(설정 읽기 1번 — 요청이면
   flask ``g``, 아니면 트랜잭션마다 ``session.info`` 에 한 번). 새 주문은 아직 id 가 없어 관계로 붙인다.
   ``CREATOR`` 는 새 주문(또는 이번에 초안에서 승격된 주문)을 저장한 요청 사용자가 켜진 프리랜서일 때.
2. 배정 알림 후보 — 로그인한 사람의 요청 저장에서, 초안 · 삭제가 아닌 주문에 **이전에 없던** 담당 관계가 생긴
   사람(초안이 이번에 승격되면 지금 담당 전부). 저장한 본인은 빼고 ``session.info`` 에 모은다.
   되채우기 · 설정 저장 뒤 다시 맞추기(:func:`~foms.services.sales_commission.links.sync_links_for_orders`)와
   요청 밖 저장(서버 시작 · 스크립트 · 워커)은 후보를 만들지 않는다.
3. ``before_commit`` — 후보마다 연결이 아직 있는지 다시 보고, 같은 트랜잭션의 savepoint 안에서 알림 한 줄 +
   받는 사람 state 를 만든다(:mod:`foms.services.notifications.measure_same_day` 선례). 알림 실패는 그 savepoint 만
   되돌리고 주문 저장은 그대로 커밋된다. 저장이 롤백되면 알림도 없다.
4. ``after_commit`` — 웹 푸시 예약만(새 세션 — 커밋 뒤 세션은 SQL 을 못 낸다).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session, sessionmaker

from db import engine
from foms.services.erp_order_flags import is_erp_draft_structured_data, is_erp_order_draft, is_erp_order_record
from foms.services.notifications import push_sender, recipients
from foms.services.sales_commission import links as link_rules
from foms.services.sales_commission.links import (
    PENDING_INFO_KEY,
    SNAPSHOT_INFO_KEY,
    cached_snapshot,
    clear_snapshot_cache,
    queue_assignment,
    request_g,
)
from models import Notification, Order, OrderFreelancerLink, User

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "SALES_ORDER_ASSIGNED"
NOTIFICATION_TITLE = "새 주문 배정"

#: before_commit 이 만든 알림 id(→ after_commit 푸시).
_READY_KEY = "foms_fcomm_assign_ready"
#: 알림 savepoint 를 여는 동안 켜 둔다(그 savepoint 의 commit 이벤트를 무시하려고).
_RESERVING_KEY = "foms_fcomm_assign_reserving"

_LISTENERS_REGISTERED = False

#: 커밋 뒤 푸시 예약에 쓰는 새 세션(시험에서 바꿀 수 있다 — measure_same_day 선례).
_session_factory = sessionmaker(bind=engine)


# --------------------------------------------------------------------------
# 요청 사용자
# --------------------------------------------------------------------------
def _request_actor_id() -> Optional[int]:
    """로그인한 요청 사용자 id. 요청 밖 · 비로그인(웹훅 등)이면 None."""
    g = request_g()
    user = getattr(g, "current_user", None) if g is not None else None
    try:
        return int(user.id) if user is not None and getattr(user, "is_active", True) else None
    except (TypeError, ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------
# flush 대상
# --------------------------------------------------------------------------
def _attr_changed(order: Any, name: str) -> bool:
    return getattr(sa_inspect(order).attrs, name).history.has_changes()


def _old_value(order: Any, name: str) -> Any:
    hist = getattr(sa_inspect(order).attrs, name).history
    old = list(hist.deleted) or list(hist.unchanged)
    return old[0] if old else None


def _was_draft(order: Any) -> bool:
    """이번 flush 직전 초안이었는가(속성 기록의 옛 값 — 못 읽으면 False)."""
    if str(_old_value(order, "status") or "").upper() == "DRAFT":
        return True
    return is_erp_draft_structured_data(_old_value(order, "structured_data"))


def _flush_targets(session: Any) -> list[tuple[Any, bool]]:
    targets: list[tuple[Any, bool]] = []
    for obj in session.new:
        if isinstance(obj, Order) and is_erp_order_record(obj):
            targets.append((obj, True))
    for obj in session.dirty:
        if not isinstance(obj, Order) or obj in session.deleted or not is_erp_order_record(obj):
            continue
        if getattr(obj, "id", None) is None:
            continue
        if _attr_changed(obj, "structured_data") or _attr_changed(obj, "status"):
            targets.append((obj, False))
    return targets


def _notifiable(order: Any) -> bool:
    if is_erp_order_draft(order) or getattr(order, "deleted_at", None):
        return False
    return str(getattr(order, "status", "") or "").upper() != "DELETED"


def _sync_flushing_orders(session: Any) -> None:
    targets = _flush_targets(session)
    if not targets:
        return
    snapshot = cached_snapshot(session)
    if not snapshot.active_ids:
        return  # 켜진 프리랜서 없음 — 연결 쿼리 0(낡은 줄은 설정 저장 뒤 다시 맞추기가 지웠다)
    actor = _request_actor_id()
    with session.no_autoflush:
        _sync_targets(session, targets, snapshot, actor)


def _sync_targets(session: Any, targets: list[tuple[Any, bool]], snapshot: link_rules.LinkSnapshot,
                  actor: Optional[int]) -> None:
    existing = link_rules.existing_links_by_order(session, [o.id for o, new in targets if not new])
    for order, is_new in targets:
        promoted = (not is_new) and _was_draft(order) and not is_erp_order_draft(order)
        creator = actor if (is_new or promoted) else None
        desired = link_rules.desired_links(order.structured_data, snapshot.match_map, creator)
        current = [] if is_new else existing.get(int(order.id), [])
        link_rules.apply_link_diff(session, order, desired, current)
        if actor is None or not _notifiable(order):
            continue
        before = link_rules.manager_user_ids((int(r.user_id), str(r.relation)) for r in current)
        after = link_rules.manager_user_ids(desired)
        queue_assignment(session, order, after if promoted else after - before, actor)


# --------------------------------------------------------------------------
# 알림 만들기(before_commit) · 푸시(after_commit)
# --------------------------------------------------------------------------
def _customer_name(order: Order) -> str:
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    customer = parties.get("customer") if isinstance(parties.get("customer"), dict) else {}
    name = customer.get("name") or order.customer_name or ""
    return " ".join(str(name).split()) or f"#{order.id}"


def assignment_message(customer: str) -> str:
    """알림 목록 문장(해요체)."""
    return f"{customer} 주문이 배정됐어요"


def _still_assigned(session: Any, order_id: int, user_id: int) -> bool:
    return (session.query(OrderFreelancerLink.id)
            .filter(OrderFreelancerLink.order_id == order_id, OrderFreelancerLink.user_id == user_id,
                    OrderFreelancerLink.relation.in_(sorted(link_rules.MANAGER_RELATIONS)))
            .first()) is not None


def _create_notification(session: Any, order_id: int, user_id: int, actor: Optional[int]) -> Optional[int]:
    order = session.get(Order, order_id)
    if order is None or not _notifiable(order) or not _still_assigned(session, order_id, user_id):
        return None
    actor_user = session.get(User, actor) if actor else None
    notification = Notification(
        order_id=order_id, notification_type=NOTIFICATION_TYPE, target_type="USER", target_user_id=user_id,
        title=NOTIFICATION_TITLE, message=assignment_message(_customer_name(order)),
        created_by_user_id=actor, created_by_name=(getattr(actor_user, "name", None) or "FOMS"),
    )
    session.add(notification)
    session.flush()
    recipients.fan_out_new_notification(session, notification, actor_user_id=actor)
    return int(notification.id)


def _resolve_pending(entries: list[dict[str, Any]]) -> dict[tuple[int, int], Optional[int]]:
    resolved: dict[tuple[int, int], Optional[int]] = {}
    for entry in entries:
        order = entry.get("order")
        oid = order if isinstance(order, int) else getattr(order, "id", None)
        if oid is None:
            continue
        resolved.setdefault((int(oid), int(entry["user_id"])), entry.get("actor"))
    return resolved


def _reserve_pending(session: Any) -> None:
    if session.info.get(_RESERVING_KEY) or session.in_nested_transaction():
        return
    if not session.info.get(PENDING_INFO_KEY):
        return
    session.flush()  # 새 주문 id · 마지막 연결 상태를 확정(before_commit 은 커밋의 flush 보다 먼저 돈다)
    resolved = _resolve_pending(session.info.pop(PENDING_INFO_KEY, None) or [])
    ready: list[int] = []
    session.info[_RESERVING_KEY] = True
    try:
        for (order_id, user_id), actor in resolved.items():
            try:
                with session.begin_nested():
                    notification_id = _create_notification(session, order_id, user_id, actor)
            except Exception:  # noqa: BLE001 — 알림 실패가 주문 저장을 되돌리면 안 된다
                logger.exception("[FCOMM] 배정 알림 만들기 실패 order=%s user=%s", order_id, user_id)
                continue
            if notification_id:
                ready.append(notification_id)
    finally:
        session.info.pop(_RESERVING_KEY, None)
    if ready:
        session.info.setdefault(_READY_KEY, []).extend(ready)


def _dispatch_ready(session: Any) -> None:
    if session.info.get(_RESERVING_KEY) or session.in_nested_transaction():
        return  # savepoint 커밋 — 바깥 커밋 때 한 번만
    session.info.pop(SNAPSHOT_INFO_KEY, None)
    ready = session.info.pop(_READY_KEY, None)
    if not ready:
        return
    for notification_id in ready:
        push_session = _session_factory()
        try:
            push_sender.enqueue_push_for_notification(notification_id, db=push_session)
        except Exception:  # noqa: BLE001 — 알림 줄은 이미 커밋됐다. 푸시만 실패.
            logger.exception("[FCOMM] 배정 알림 푸시 예약 실패 id=%s", notification_id)
        finally:
            push_session.close()


def _reset_after_rollback(session: Any, previous_transaction: Any) -> None:
    if getattr(previous_transaction, "nested", False):
        return  # savepoint 롤백 — 후보는 before_commit 이 연결을 다시 보고 거른다
    for key in (PENDING_INFO_KEY, _READY_KEY, SNAPSHOT_INFO_KEY):
        session.info.pop(key, None)


def _before_flush(session: Any) -> None:
    try:
        _sync_flushing_orders(session)
    except Exception:  # noqa: BLE001 — 연결은 되채우기로 다시 만들 수 있다. 주문 저장을 막지 않는다.
        logger.exception("[FCOMM] 주문 ↔ 프리랜서 연결 맞추기 실패")


def register_freelancer_link_listener() -> None:
    """전역 ``Session`` 에 연결 훅 · 배정 알림 리스너를 **한 번** 건다(여러 번 불러도 한 벌)."""
    global _LISTENERS_REGISTERED
    if _LISTENERS_REGISTERED:
        return
    _LISTENERS_REGISTERED = True

    @event.listens_for(Session, "before_flush")
    def _fcomm_links_before_flush(session, flush_context, instances):
        _before_flush(session)

    @event.listens_for(Session, "before_commit")
    def _fcomm_links_before_commit(session):
        _reserve_pending(session)

    @event.listens_for(Session, "after_commit")
    def _fcomm_links_after_commit(session):
        _dispatch_ready(session)

    @event.listens_for(Session, "after_soft_rollback")
    def _fcomm_links_after_soft_rollback(session, previous_transaction):
        _reset_after_rollback(session, previous_transaction)


def is_freelancer_link_listener_registered() -> bool:
    """이 프로세스에 훅이 걸렸는가(배선 시험 · 진단용)."""
    return _LISTENERS_REGISTERED


__all__ = [
    "NOTIFICATION_TITLE",
    "NOTIFICATION_TYPE",
    "assignment_message",
    "clear_snapshot_cache",
    "is_freelancer_link_listener_registered",
    "queue_assignment",
    "register_freelancer_link_listener",
]
