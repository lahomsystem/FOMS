"""PARTNER-FOMS 6-2: 시공일이 정해지거나 바뀌면 협력사 직원에게 웹 푸시.

시공일 변경은 저장 경로가 많아(ERP 폼 · 대시보드 칸 · 시공 실패 재예약 · 옛 폼) 날짜 동기화 훅이 한 곳에서
``CONSTRUCTION_DATE_CHANGED`` 를 남긴다(``order_date_sync``). 시공팀 출고 알림(``shipment_change``)과 같은
방식으로 그 결과를 읽는다 — ``before_commit`` 에서 같은 트랜잭션에 알림 줄을 만들고(고아 알림 0),
``after_commit`` 에서 푸시를 예약한다. 협력사 주문만, 처음 정해질 때도 알린다(사용자 결정).
설계서 docs/specs/2026-10-20-partner-notifications_SPEC.md §4 · §5-3
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

from foms.services.error_logging import log_handled_exception
from foms.services.notifications.partner_push import PARTNER_CONSTRUCTION_DATE
from foms.services.notifications.push_sender import enqueue_push_for_notification
from foms.services.partners.notify import create_partner_notifications
from models import Order

_PENDING = "partner_construction_date_notification_ids"
_LISTENERS_REGISTERED = False
# 시공일 변경 읽기 함수(``order_date_sync.pending_construction_date_changes``). 등록할 때 받는다 —
# 이 모듈이 order_date_sync 를 import 하면 서로를 부르는 고리가 생긴다(그쪽이 이 모듈을 등록한다).
_pending_reader: Callable[[Session], dict[int, dict[str, str]]] | None = None


def _apply_pending(session: Session) -> None:
    if _pending_reader is None:
        return
    session.flush()  # before_commit 은 커밋 flush 보다 먼저 돈다 — 방금 바뀐 시공일을 보려면 한 번 flush
    changes = _pending_reader(session)
    if not changes:
        return
    ids = session.info.setdefault(_PENDING, set())
    for order_id, change in changes.items():
        order = session.get(Order, order_id)
        if order is None or order in session.deleted or not order.partner_org_id or not change["to"]:
            continue
        rows = create_partner_notifications(
            session, order, PARTNER_CONSTRUCTION_DATE, {"before": change["from"], "after": change["to"]},
        )
        ids.update(n.id for n in rows)


def _before_commit(session: Session) -> None:
    try:
        _apply_pending(session)
    except Exception:  # noqa: BLE001 — 협력사 알림 실패가 시공일 저장을 막으면 안 된다
        log_handled_exception("partner construction date notify")


def _after_commit(session: Session) -> None:
    ids = session.info.pop(_PENDING, None)  # enqueue 가 다시 커밋할 수 있어 먼저 꺼낸다(재진입 no-op)
    for notification_id in sorted(ids or ()):
        try:
            enqueue_push_for_notification(notification_id, db=session)
        except Exception:  # noqa: BLE001 — 푸시 예약 실패는 알림 줄을 지우지 않는다
            log_handled_exception("partner construction date push")


def register_partner_construction_date_listener(pending_reader: Callable[[Session], dict[int, dict[str, str]]]) -> None:
    """전역 ``Session`` 에 협력사 시공일 알림 리스너를 **1회** 등록한다.

    Args:
        pending_reader: 이번 트랜잭션의 주문별 시공일 변경 ``{order_id: {"from", "to"}}`` 을 돌려주는 함수.
    """
    global _LISTENERS_REGISTERED, _pending_reader
    _pending_reader = pending_reader
    if _LISTENERS_REGISTERED:
        return
    _LISTENERS_REGISTERED = True
    event.listen(Session, "before_commit", _before_commit)
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_soft_rollback", lambda session, previous: session.info.pop(_PENDING, None))
