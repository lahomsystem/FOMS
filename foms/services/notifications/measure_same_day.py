"""당일 실측 긴급 추가 → 영업 전원 알림(감지·예약·화면 payload).

실측 방문 시간은 **전날 확정**이 원칙이다. 그런데 오늘(KST) 실측이 새로 생기거나 오늘로
바뀌면, 영업이 그 사실을 모른 채 하루 동선을 짜게 된다. 그 순간을 세 길로 알린다.

* 채널톡 긴급방 — SIDEFX ``MEAS_SAME_DAY_ALERT`` 핸들러
  (:mod:`foms.services.notifications.measure_same_day_delivery`).
* FOMS 화면 가운데 확인창 — 커밋 뒤 socket emit(``interrupt: True``). 수신자마다 각자 확인.
* 웹 푸시 — 커밋 뒤 RQ enqueue(다른 알림과 같은 길).

감지 흐름(세 단계로 나눈 이유):

1. **before_flush** — :mod:`foms.services.order_date_sync` 의 전역 훅이 주문마다 실측일
   before/after 집합과 드래프트 여부를 :func:`detect_same_day_additions` 에 넘긴다. 모든 ORM
   저장 경로가 이 한 점을 지나므로 경로별 호출을 심지 않는다. 여기서는 DB I/O 가 없다.
2. **before_commit** — 한 번 flush 해 마지막 상태를 확정하고, 판정이 참인 주문마다 **같은
   업무 트랜잭션의 savepoint** 안에서 기준 OrderEvent → outbox(멱등 키) → Notification +
   팬아웃을 만든다. 주문 저장과 함께 커밋되므로 저장은 됐는데 알림이 빠지는 일이 없고,
   롤백되면(after_soft_rollback) 함께 사라진다.
3. **after_commit** — 푸시 enqueue·배지 무효화·화면 emit 만 한다(단계마다 따로 삼킨다).

중복 방지는 outbox 멱등 키 ``meas_same_day:{order_id}:{YYYY-MM-DD}`` 하나다. 같은 날 지웠다
다시 넣으면 예약 전에 기존 행을 보고 건너뛴다. 동시 저장 경합은 부분 고유 인덱스가
IntegrityError 로 막고, 그 savepoint 만 되돌린다(Notification 도 만들지 않는다).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import has_app_context
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import ObjectDeletedError

from db import engine
from foms.services import order_date_sync
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_order_flags import is_erp_order_draft
from foms.services.notifications import push_sender, realtime_notifications
from foms.services.notifications.measure_same_day_payload import (  # noqa: F401 - 재수출
    ALERT_KIND,
    NOTIFICATION_TYPE,
    _message,
    _title,
    build_measure_same_day_payload,
)
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.sidefx_outbox import enqueue_side_effect
from models import DomainSideEffectOutbox, Notification, Order, OrderEvent, User

logger = logging.getLogger(__name__)

__all__ = [
    "ALERT_KIND",
    "EFFECT_TYPE",
    "EVENT_TYPE",
    "NOTIFICATION_TYPE",
    "TARGET_TEAM",
    "build_dedupe_key",
    "build_measure_same_day_payload",
    "detect_same_day_additions",
    "dispatch_measure_same_day_alert",
    "register_measure_same_day_listener",
    "reserve_measure_same_day_alert",
]

#: SIDEFX outbox effect(채널톡 긴급방 발송).
EFFECT_TYPE = "MEAS_SAME_DAY_ALERT"
#: 수신 팀(MEASURE 표기 계정은 recipients 에서 SALES 로 정규화된다).
TARGET_TEAM = "SALES"
#: outbox 출처 FK 로 쓰는 기준 OrderEvent 유형.
EVENT_TYPE = "MEASURE_SAME_DAY_ADDED"

#: 트랜잭션 동안의 주문별 판정 상태(``Session.info``).
_STATE = "foms_meas_same_day_state"
#: before_commit 이 굳힌 발송 목록(``Session.info``).
_PENDING = "foms_meas_same_day_pending"

#: 예약 savepoint 를 여는 동안 켜 둔다(그 savepoint 의 commit 이벤트를 무시하려고).
_RESERVING = "foms_meas_same_day_reserving"

_LISTENERS_REGISTERED = False

#: 테스트에서 monkeypatch 할 수 있는 새 세션 팩토리(kakao_alimtalk 선례).
_session_factory = sessionmaker(bind=engine)


def build_dedupe_key(order_id: int, date_str: str) -> str:
    """outbox 멱등 키. 같은 주문·같은 날짜는 하루 1회만 예약된다.

    Args:
        order_id: 주문 id.
        date_str: ``YYYY-MM-DD``(KST 오늘).

    Returns:
        ``meas_same_day:{order_id}:{date_str}``.
    """
    return f"meas_same_day:{int(order_id)}:{date_str}"


def detect_same_day_additions(
    session: Any,
    order: Any,
    before_dates: set[str],
    after_dates: set[str],
    was_draft: bool,
    is_draft: bool,
) -> Optional[str]:
    """이번 flush 결과로 "실측일에 오늘이 새로 들어왔다"를 판정한다(DB I/O 없음).

    한 트랜잭션이 여러 번 flush 해도(레거시 컬럼 먼저 → JSONB 나중) 비교 기준은 트랜잭션
    **처음** 값(origin)이다. origin 은 주문별 첫 호출 때만 기록하고, 판정은 매번 마지막
    flush 결과로 갱신한다. 그래서 지웠다 다시 넣거나 두 번 저장해도 결과는 하나다.

    Args:
        session: flush 중인 세션(``session.info`` 에 상태를 둔다).
        order: 대상 주문.
        before_dates: sync 전 실측일 집합(신규 주문이면 빈 집합).
        after_dates: sync 후 실측일 집합.
        was_draft: 이번 flush 직전 드래프트였는지(신규 주문이면 False).
        is_draft: 지금 드래프트인지.

    Returns:
        알림 대상이면 오늘 날짜 문자열(``YYYY-MM-DD``), 아니면 None.
    """
    today = get_today_kst().isoformat()
    state = session.info.get(_STATE)
    if not isinstance(state, dict):
        state = {}
        session.info[_STATE] = state
    entry = state.get(id(order))
    if entry is None:
        entry = {
            "order": order,
            "origin_before": set(before_dates or ()),
            "origin_was_draft": bool(was_draft),
            "verdict": None,
        }
        state[id(order)] = entry
    verdict = _verdict(entry, today, set(after_dates or ()), bool(is_draft))
    entry["verdict"] = verdict
    return verdict


def _verdict(entry: dict, today: str, after: set[str], is_draft: bool) -> Optional[str]:
    """today∈after ∧ ¬is_draft ∧ (today∉origin_before ∨ origin_was_draft) 이면 today."""
    if today in after and not is_draft and (
        today not in entry["origin_before"] or entry["origin_was_draft"]
    ):
        return today
    return None


def _final_verdict(entry: dict) -> Optional[str]:
    """before_commit 에서 **지금 주문 상태**로 판정을 다시 계산한다.

    savepoint 롤백은 flush 된 변경 일부만 되돌린다(감사 로그 ``log_access`` 가 저장마다 연다).
    before_flush 때의 판정을 그대로 믿으면 되돌려진 값으로 알리거나, 반대로 살아남은 값을
    놓친다. 그래서 마지막 flush 뒤 주문의 실측일·드래프트 여부로 한 번 더 본다.
    """
    order = entry.get("order")
    try:
        after = order_date_sync._dates_from_rows(getattr(order, "schedule_dates", []), "measurement")
        is_draft = is_erp_order_draft(order)
    except ObjectDeletedError:
        return None
    return _verdict(entry, get_today_kst().isoformat(), after, is_draft)


# --------------------------------------------------------------------------- #
# 예약(업무 트랜잭션 안) · 커밋 뒤 발송
# --------------------------------------------------------------------------- #
def _already_reserved(session: Any, dedupe_key: str) -> bool:
    return (
        session.query(DomainSideEffectOutbox.id)
        .filter(DomainSideEffectOutbox.dedupe_key == dedupe_key)
        .first()
        is not None
    )


def _reserve_rows(
    session: Any, order: Any, date: str, actor_user_id: Optional[int], source: str
) -> dict:
    """기준 이벤트 → outbox → 알림+팬아웃 → payload 보강(flush 만, commit 은 바깥 트랜잭션)."""
    event_row = OrderEvent(
        order_id=order.id,
        event_type=EVENT_TYPE,
        payload={"date": date, "source": source},
        created_by_user_id=actor_user_id,
    )
    session.add(event_row)
    session.flush()
    dedupe_key = build_dedupe_key(order.id, date)
    row = enqueue_side_effect(
        session,
        source_domain="ORDER_EVENT",
        source_id=event_row.id,
        effect_type=EFFECT_TYPE,
        payload={"order_id": int(order.id), "date": date, "notification_id": None},
        dedupe_key=dedupe_key,
        provider_idempotency_key=dedupe_key,
    )
    actor = session.get(User, actor_user_id) if actor_user_id else None
    added_by = str(getattr(actor, "name", "") or "").strip()
    notif = Notification(
        order_id=order.id,
        notification_type=NOTIFICATION_TYPE,
        target_type="TEAM",
        target_team=TARGET_TEAM,
        is_urgent=False,
        title=_title(order)[:200],
        message=_message(order, added_by),
        created_by_user_id=actor_user_id,
        created_by_name=added_by or None,
        created_at=now_utc_naive(),
    )
    session.add(notif)
    session.flush()
    states = fan_out_new_notification(session, notif, actor_user_id=actor_user_id)
    next_payload = dict(row.payload or {})
    next_payload["notification_id"] = int(notif.id)
    row.payload = next_payload
    flag_modified(row, "payload")
    session.flush()
    return {
        "notification_id": int(notif.id),
        "recipient_ids": sorted({int(st.user_id) for st in states}),
        "payload": build_measure_same_day_payload(
            order, notification_id=int(notif.id), added_by=added_by, added_at=notif.created_at
        ),
    }


def reserve_measure_same_day_alert(
    session: Any, order_id: int, date: str, actor_user_id: Optional[int], source: str
) -> Optional[dict]:
    """``before_commit``: 업무 트랜잭션 안 savepoint 에서 기준 이벤트·outbox·알림을 만든다.

    주문 저장과 **같은 커밋**으로 남으므로 "저장은 됐는데 알림 행이 없다"가 생기지 않는다.
    같은 날 이미 예약됐으면(멱등 키) 아무것도 만들지 않는다 — 동시 저장 경합으로 부분 고유
    인덱스가 막으면 savepoint 만 되돌리고 업무 트랜잭션은 그대로 커밋한다.

    Args:
        session: 커밋 중인 업무 세션.
        order_id: 주문 id.
        date: 오늘 날짜(``YYYY-MM-DD``).
        actor_user_id: 변경자 id(요청 밖이면 None).
        source: 쓰기 경로 힌트(Flask endpoint 또는 ``system``).

    Returns:
        커밋 뒤 발송 인자(``notification_id``·``recipient_ids``·``payload``). 없으면 None.
    """
    order = session.get(Order, int(order_id))
    if order is None:
        return None
    dedupe_key = build_dedupe_key(order.id, date)
    if _already_reserved(session, dedupe_key):
        logger.info("[MEAS_SAME_DAY] 같은 날 이미 예약됨 — 건너뜀(%s)", dedupe_key)
        return None
    session.info[_RESERVING] = True
    try:
        with session.begin_nested():
            return _reserve_rows(session, order, date, actor_user_id, source)
    except IntegrityError:
        logger.info("[MEAS_SAME_DAY] 동시 예약 경합 — 건너뜀(%s)", dedupe_key)
        return None
    finally:
        session.info.pop(_RESERVING, None)


def dispatch_measure_same_day_alert(
    notification_id: int, recipient_ids: list[int], payload: dict
) -> Optional[int]:
    """``after_commit``: 커밋된 알림의 푸시 enqueue·배지 무효화·화면 emit(단계마다 따로 삼킨다).

    추가한 본인도 영업이면 받는다(제외 로직 없음 — 스펙 §8-1).

    Args:
        notification_id: 커밋된 알림 id.
        recipient_ids: 팬아웃된 수신자 id.
        payload: 화면 확인창 payload(:func:`build_measure_same_day_payload`).

    Returns:
        notification_id.
    """
    s = _session_factory()
    try:
        push_sender.enqueue_push_for_notification(notification_id, db=s)
    except Exception:  # noqa: BLE001 - 알림 행은 이미 커밋됐다. 푸시만 실패.
        logger.exception("[MEAS_SAME_DAY] push enqueue 실패(id=%s)", notification_id)
    finally:
        s.close()

    try:
        from foms.api.notifications import invalidate_badge_cache_for_user_ids

        invalidate_badge_cache_for_user_ids(recipient_ids)
    except Exception:  # noqa: BLE001 - 배지는 TTL 로 곧 맞는다.
        logger.exception("[MEAS_SAME_DAY] 배지 캐시 무효화 실패(id=%s)", notification_id)

    try:
        if has_app_context() and recipient_ids:
            realtime_notifications.emit_erp_notification_to_users(recipient_ids, payload)
    except Exception:  # noqa: BLE001 - 화면 알림은 재조회 API 가 메운다.
        logger.exception("[MEAS_SAME_DAY] 화면 emit 실패(id=%s)", notification_id)
    return notification_id


# --------------------------------------------------------------------------- #
# 세션 이벤트 배선
# --------------------------------------------------------------------------- #
def _is_deleted(session: Any, order: Any) -> bool:
    if order in session.deleted:
        return True
    if getattr(order, "deleted_at", None):
        return True
    return str(getattr(order, "status", "") or "").upper() == "DELETED"


def _collect_pending(session: Any) -> None:
    """``before_commit``: 마지막 flush 결과로 판정을 확정하고, 같은 트랜잭션에 예약한다."""
    if session.info.get(_RESERVING) or session.in_nested_transaction():
        return  # savepoint 커밋 — 바깥 트랜잭션 커밋 때 한 번만 굳힌다.
    # before_commit 은 커밋이 하는 flush 보다 먼저 돈다. 방금 바뀐 실측일을 보려면 여기서
    # 한 번 flush 해야 한다(clean 세션이면 즉시 반환 — shipment_change 선례).
    session.flush()
    state = session.info.pop(_STATE, None)
    if not state:
        return
    targets: list[tuple[int, str]] = []
    for entry in state.values():
        order = entry.get("order")
        if order is None or order in session.deleted:
            continue
        date = _final_verdict(entry)
        order_id = getattr(order, "id", None)
        if not date or order_id is None or _is_deleted(session, order):
            continue
        targets.append((int(order_id), str(date)))
    if not targets:
        return
    actor_user_id, source = order_date_sync._resolve_event_actor_and_source()
    pending = session.info.setdefault(_PENDING, {})
    for order_id, date in targets:
        if order_id in pending:
            continue
        try:
            job = reserve_measure_same_day_alert(session, order_id, date, actor_user_id, source)
        except Exception:  # noqa: BLE001 - 알림 예약 실패로 주문 저장을 깨지 않는다.
            logger.exception("[MEAS_SAME_DAY] 예약 실패(order=%s)", order_id)
            continue
        if job is not None:
            pending[order_id] = job
    # 예약 flush 가 다시 채운 판정 상태는 이 커밋에서 이미 소비됐다.
    session.info.pop(_STATE, None)


def _dispatch_pending(session: Any) -> None:
    """``after_commit``: 굳힌 목록을 먼저 꺼낸 뒤 항목마다 발송한다(예외는 로그만)."""
    if session.info.get(_RESERVING) or session.in_nested_transaction():
        # savepoint 커밋에도 after_commit 이 온다(감사 로그 log_access 가 매 저장마다 연다).
        # 여기서 상태를 비우면 바깥 커밋이 판정을 잃는다.
        return
    pending = session.info.pop(_PENDING, None)
    session.info.pop(_STATE, None)
    if not pending:
        return
    for job in list(pending.values()):
        try:
            dispatch_measure_same_day_alert(**job)
        except Exception:  # noqa: BLE001 - 커밋된 요청을 500 으로 만들지 않는다.
            logger.exception("[MEAS_SAME_DAY] 커밋 뒤 발송 실패(id=%s)", job.get("notification_id"))


def register_measure_same_day_listener() -> None:
    """전역 ``Session`` 에 당일 실측 알림 리스너를 **1회** 등록한다.

    before_flush 쪽 입력은 :func:`foms.services.order_date_sync.register_date_sync_listener`
    가 모은다. 등록 지점이 갈리면 "판정은 나는데 알림만 안 오는" 반쪽 배선이 생기므로 그
    함수 끝에서 이 함수를 부른다.

    Returns:
        None.
    """
    global _LISTENERS_REGISTERED
    if _LISTENERS_REGISTERED:
        return
    _LISTENERS_REGISTERED = True

    @event.listens_for(Session, "before_commit")
    def _meas_same_day_before_commit(session):
        _collect_pending(session)

    @event.listens_for(Session, "after_commit")
    def _meas_same_day_after_commit(session):
        _dispatch_pending(session)

    @event.listens_for(Session, "after_soft_rollback")
    def _meas_same_day_after_soft_rollback(session, previous_transaction):
        _reset_after_rollback(session, previous_transaction)


def _reset_after_rollback(session: Any, previous_transaction: Any) -> None:
    """롤백된 트랜잭션의 판정은 무효다 — 다음 커밋으로 새어가면 안 된다.

    savepoint 롤백(바깥 트랜잭션은 계속)이면 상태를 그대로 둔다. 처음 값(origin)은 여전히
    유효하고, before_commit 이 그때의 주문 상태로 판정을 다시 계산한다(:func:`_final_verdict`).
    """
    if getattr(previous_transaction, "nested", False):
        return
    session.info.pop(_STATE, None)
    session.info.pop(_PENDING, None)
