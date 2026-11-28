"""생산 현장 알람 거는 함수(설계서 2026-11-28 생산 현장 알람 §4 · §6-2 약속 3 · 흐름 셋 §4-3 약속 3).

쓰기 자리들은 이 모듈의 함수만 부른다. 이름 · 인자는 약속이라 바꾸지 않는다.

* ``note_mark`` · ``note`` 는 **커밋 전** — 세션 주머니(``db.info['floor_alarm']``)에 적기만 한다(쿼리 0).
* ``flush`` 는 **커밋 바로 뒤** — 적어 둔 것을 읽어 알림 줄을 만들고(자기 커밋) 실시간 · 폰 알림을 보낸 뒤 주머니를 비운다.
  알람을 만들다 실패해도 본 쓰기는 이미 커밋돼 있고, 실패는 기록만 한다.
* 되감은 길에서는 ``flush`` 를 부르지 않는다. 그래도 남지 않게, 진짜 되감기(``after_rollback``)가 일어나면 주머니를 비운다.
* 넷 다 예외를 밖으로 내지 않고, 스위치(:data:`SWITCH_ENV` — 기본 꺼짐)가 꺼져 있으면 바로 돌아온다(줄 0 · 쿼리 0).

알림 줄은 지금 긴급 알림과 같은 표를 쓴다(새 표 · 새 칸 없음): ``notifications``(사람 지정 ``target_type='USER'``) +
``notification_user_states`` + ``notification_events``. 누가 무엇을 받는지는 :mod:`.floor_alarm_rules`, 글은 :mod:`.floor_alarm_text`.
윗사람 올림(5분 · 10분)에서는 ``escalation`` 이 이 종류를 늘 뺀다. 배지 캐시 비우기는 api 층 함수라 여기서 부르지 못한다 —
다시 받기 API 모듈(``foms/api/production/alarms.py``)이 :func:`set_badge_hook` 으로 꽂는다.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.feature_flags import env_bool
from foms.services.notifications.push_sender import enqueue_push_for_notification
from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
from foms.services.production import floor_alarm_rules as rules
from foms.services.production import floor_alarm_text as T
from models import (
    Notification,
    NotificationEvent,
    NotificationEventType,
    NotificationRecipientSource,
    NotificationUserState,
)

logger = logging.getLogger(__name__)

SWITCH_ENV = "FOMS_PRODUCTION_FLOOR_ALARM"
POCKET = "floor_alarm"
_badge_hook: Optional[Callable[[Iterable[int]], None]] = None


def set_badge_hook(hook: Optional[Callable[[Iterable[int]], None]]) -> None:
    """받는 사람 종 숫자 캐시를 비우는 함수를 꽂는다(api 층이 앱을 만들 때 한 번)."""
    global _badge_hook
    _badge_hook = hook


def enabled() -> bool:
    """알람 스위치가 켜졌는지 — 읽는 곳은 여기 하나(환경 변수 ``FOMS_PRODUCTION_FLOOR_ALARM``, 없거나 ``off`` = 꺼짐).

    Returns:
        켜졌으면 True.
    """
    return env_bool(SWITCH_ENV, False)


def _clock() -> tuple[Any, Any]:
    """(지금 UTC naive, 오늘 KST) — 시험은 이 함수를 바꿔 시각을 넣는다."""
    return now_utc_naive(), get_today_kst()


def _who(actor: Any) -> tuple[Optional[int], str]:
    """누른 사람 → (id, 이름). 사용자 객체 · ``{'id', 'name'}`` · None 을 받는다."""
    if isinstance(actor, dict):
        uid, name = actor.get("id", actor.get("user_id")), actor.get("name")
    else:
        uid, name = getattr(actor, "id", None), getattr(actor, "name", None) or getattr(actor, "username", None)
    return (uid if isinstance(uid, int) and not isinstance(uid, bool) else None), str(name or "").strip()


def _put(db: Any, kind: str, order_id: Any, actor: Any, material: dict[str, Any]) -> None:
    uid, name = _who(actor)
    entry = {"kind": kind, "order_id": int(order_id), "by": uid, "by_name": name, "m": material}
    if actor is not None and not isinstance(actor, dict) and hasattr(actor, "team"):  # 이미 읽은 사용자 행 — 글 · 공장 판정에 쓴다(쿼리 0)
        entry.update(by_team=getattr(actor, "team", None), by_factory=rules.actor_factory(actor))
    db.info.setdefault(POCKET, []).append(entry)


def _ids(people: Any, *, done: Optional[bool] = None) -> list[int]:
    """사람 목록(``[{user_id, name, done}]``)의 번호 — ``done`` 을 주면 그 몫 상태인 사람만."""
    return [h["user_id"] for h in people or []
            if isinstance(h, dict) and isinstance(h.get("user_id"), int) and (done is None or bool(h.get("done")) == done)]


def mark_events(actor_id: Any, action: str, data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """표시 쓰기 결과 → 사건들(순수 — 약속 1 ``gave`` · 약속 2 ``holders_before`` 를 읽는다).

    Returns:
        ``[(kind, 재료)]`` — ``given``(받은 사람) · ``taken``(원래 담당) · ``start_cancelled``(남이 뺀 사람) · ``done_cancelled``
        (남이 완료를 취소한 사람). 누른 사람 본인은 여기서 뺀다.
    """
    out: list[tuple[str, dict[str, Any]]] = []
    gave = data.get("gave") if isinstance(data.get("gave"), dict) else None
    if gave:
        to, src = gave.get("to") or {}, gave.get("from") or {}
        if not gave.get("self") and isinstance(to.get("user_id"), int):
            out.append(("given", {"to": [to["user_id"]]}))
        if isinstance(src.get("user_id"), int):
            out.append(("taken", {"to": [src["user_id"]], "self": bool(gave.get("self")), "to_name": str(to.get("name") or "")}))
        return out
    before = data.get("holders_before")
    after = (data.get("mark") or {}).get("holders") if isinstance(data.get("mark"), dict) else None
    if action in ("remove", "release"):
        gone = [uid for uid in _ids(before, done=False) if uid not in _ids(after) and uid != actor_id]
        out += [("start_cancelled", {"to": gone})] if gone else []
    if action == "undo":
        undone = [uid for uid in _ids(before, done=True) if uid not in _ids(after, done=True) and uid != actor_id]
        out += [("done_cancelled", {"to": undone})] if undone else []
    return out


def note_mark(db: Any, actor: Any, req: Any, data: Any) -> None:
    """표시 쓰기 전용 — ``mark_one`` 결과를 받은 바로 뒤, **커밋 전**에 부른다.

    세션 주머니에 적기만 한다(쿼리 0 · 예외 없음). 약속 1(``gave``) · 2(``holders_before``)를 읽는다.

    Args:
        db: 그 요청의 DB 세션.
        actor: 누른 사람.
        req: 표시 쓰기 요청.
        data: ``mark_one`` 결과.
    """
    try:
        if not enabled() or not isinstance(data, dict) or not data.get("changed"):
            return
        gave = data.get("gave") if isinstance(data.get("gave"), dict) else {}
        where = {"drawing_key": gave.get("drawing_key") or getattr(req, "key", None), "part": gave.get("part") or getattr(req, "part", None)}
        order_id = gave.get("order_id") or getattr(req, "order_id", None)
        for kind, material in mark_events(_who(actor)[0], str(getattr(req, "action", "") or ""), data):
            _put(db, kind, order_id, gave.get("by") or actor, {**where, **material})
    except Exception:  # noqa: BLE001 - 알람 적기가 표시 쓰기를 깨면 안 된다(기록만)
        logger.warning("[floor-alarm] note_mark failed", exc_info=True)


def note(db: Any, kind: str, order_id: Any, actor: Any, **material: Any) -> None:
    """그 밖 쓰기 자리 — **커밋 전**에 부른다. 세션 주머니에 적기만 한다(쿼리 0 · 예외 없음).

    Args:
        db: 그 요청의 DB 세션.
        kind: 알람 종류(약속 4 — ``hold`` · ``defect`` · ``rework`` · ``drawing_replaced`` …).
        order_id: 주문 id.
        actor: 한 사람(사용자 객체 또는 ``{'id', 'name'}``).
        **material: 종류마다의 재료(약속 4 — ``reason`` · ``drawing_keys`` · ``detail`` …).
    """
    try:
        if enabled() and kind in rules.KINDS:
            _put(db, kind, order_id, actor, material)
    except Exception:  # noqa: BLE001 - 알람 적기가 본 쓰기를 깨면 안 된다(기록만)
        logger.warning("[floor-alarm] note failed kind=%s", kind, exc_info=True)


def replaced_material(old_files: Any, new_files: Any, fix_result: Any = None) -> dict[str, Any]:
    """도면 바로 반영 재료 — 새 목록에서 빠진 옛 key 와 그 번호(옛 자리), 이번에 닫힌 공장 수정 요청 번호(순수)."""
    kept = {str((f or {}).get("key") or "") for f in new_files or [] if isinstance(f, dict)}
    numbers = {str(f.get("key")): no for no, f in enumerate(old_files or [], 1)
               if isinstance(f, dict) and f.get("key") and str(f.get("key")) not in kept}
    closed = (fix_result or {}).get("closed_requests") if isinstance(fix_result, dict) else None
    return {"drawing_keys": list(numbers), "numbers": numbers, "request_ids": list(closed or [])}


def payload(notification: Any) -> dict[str, Any]:
    """실시간 값 · 다시 받기 한 줄(약속 6 · 7) — 긴급은 지금 긴급 값과 같은 칸, 띠는 ``floor_notice``."""
    urgent = bool(notification.is_urgent)
    out = {"urgent": urgent, "notification_id": int(notification.id), "notification_type": notification.notification_type,
           "title": notification.title or "", "message": notification.message or "",
           "order_id": int(notification.order_id) if notification.order_id else None,
           "created_by_name": notification.created_by_name or ""}
    return out if urgent else {**out, "floor_notice": True}


class Outbox:
    """커밋 뒤 보낼 것 — 알람 값(새 줄인지) · 닫은 알람 번호."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, dict[str, Any], bool]] = []
        self.closed: dict[int, list[int]] = {}


def _merge_target(reads: rules.Reads, order_id: Any, actor_id: Any, alarm: rules.Alarm) -> Any:
    """60초 안 · 같은 주문 · 같은 종류 · 같은 준 사람 · 같은 받는 사람 · 안 누른 알람(제목 앞머리가 같은 것) — 없으면 None."""
    if alarm.render is None or order_id is None:
        return None
    head = T.merge_head(alarm.title)
    for notif, state in reversed(reads.recent(int(order_id))):
        if (notif.notification_type == alarm.ntype and state.user_id == alarm.user_id and state.ack_at is None
                and state.archived_at is None and notif.created_by_user_id == actor_id and T.merge_head(notif.title) == head
                and (reads.now - notif.created_at).total_seconds() <= rules.MERGE_SECONDS):
            return notif
    return None


def save(db: Any, reads: rules.Reads, plan: rules.Plan, out: Outbox, *, order_id: Any = None, actor_id: Any = None,
         actor_name: str = "") -> None:
    """알람 줄(알림 · 받는 사람 상태 · 이벤트)을 세션에 만든다 — 커밋은 부르는 쪽. 합칠 수 있으면 앞 줄의 글만 고친다."""
    for alarm in plan.alarms:
        merged = _merge_target(reads, order_id, actor_id, alarm)
        if merged is not None:
            numbers = tuple(sorted(set(T.numbers_in(merged.message)) | set(alarm.numbers)))
            merged.title, merged.message = alarm.render(numbers)
            out.sent.append((alarm.user_id, payload(merged), False))
            continue
        notif = Notification(
            order_id=order_id, notification_type=alarm.ntype, target_type="USER", target_user_id=alarm.user_id,
            is_urgent=T.is_urgent_type(alarm.ntype), title=alarm.title, message=alarm.message,
            created_by_user_id=actor_id, created_by_name=actor_name or None, is_read=False, created_at=reads.now)
        db.add(notif)
        db.flush()
        state = NotificationUserState(notification_id=notif.id, user_id=alarm.user_id,
                                      recipient_source=NotificationRecipientSource.TARGET_USER, created_at=reads.now)
        db.add(state)
        db.flush()
        db.add(NotificationEvent(notification_id=notif.id, user_state_id=state.id, actor_user_id=actor_id,
                                 recipient_user_id=alarm.user_id, event_type=NotificationEventType.CREATED))
        if order_id is not None:
            reads.remember(int(order_id), notif, state)
        out.sent.append((alarm.user_id, payload(notif), True))
    for notif, state in plan.close:
        if state.archived_at is None:
            state.archived_at = reads.now
            db.add(NotificationEvent(notification_id=notif.id, user_state_id=state.id, recipient_user_id=state.user_id,
                                     event_type=NotificationEventType.ARCHIVE, metadata_json={"floor_closed": True}))
            out.closed.setdefault(int(state.user_id), []).append(int(notif.id))


def deliver(db: Any, out: Outbox) -> None:
    """커밋 뒤 — 종 숫자 캐시 비우기 · 개인 방 실시간 · 긴급 새 줄의 폰 알림. 한 건이 실패해도 나머지는 보낸다."""
    people = sorted({uid for uid, _body, _new in out.sent} | set(out.closed))
    steps: list[Callable[[], Any]] = []
    if people and _badge_hook is not None:
        steps.append(lambda: _badge_hook(people))
    for uid, body, new in out.sent:
        steps.append(lambda uid=uid, body=body: emit_erp_notification_to_users([uid], body))
        if new and body["urgent"]:  # 띠는 폰 알림을 걸지 않는다(§4-1)
            steps.append(lambda body=body: enqueue_push_for_notification(body["notification_id"], db=db))
    for uid, ids in out.closed.items():
        steps.append(lambda uid=uid, ids=ids: emit_erp_notification_to_users(
            [uid], {"urgent": False, "floor_closed": True, "notification_ids": ids}))
    for step in steps:
        try:
            step()
        except Exception:  # noqa: BLE001 - 배달 실패는 기록만(줄은 남아 다시 받기가 살린다)
            logger.warning("[floor-alarm] delivery step failed", exc_info=True)


def flush(db: Any) -> None:
    """**커밋 바로 뒤**에 부른다 — 적어 둔 것을 알람 줄로 만들어 보내고 주머니를 비운다(자기 커밋 · 예외 없음).

    되감은 길에서는 부르지 않는다.

    Args:
        db: 그 요청의 DB 세션.
    """
    try:
        notes = db.info.pop(POCKET, None)
        if not notes or not enabled():
            return
        now, today = _clock()
        reads, out = rules.Reads(db, now, today), Outbox()
        reads.users({uid for n in notes for uid in (n.get("m") or {}).get("to") or []})  # 사람 지정 받는 사람을 한 번에
        for item in notes:
            save(db, reads, rules.plan(reads, item), out, order_id=item["order_id"], actor_id=item.get("by"),
                 actor_name=item.get("by_name") or "")
        if not out.sent and not out.closed:
            return
        db.commit()
    except Exception:  # noqa: BLE001 - 본 쓰기는 이미 커밋됐다. 알람 실패는 되감고 기록만
        logger.exception("[floor-alarm] flush failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("[floor-alarm] rollback after failed flush also failed", exc_info=True)
        return
    deliver(db, out)


@event.listens_for(Session, "after_rollback")
def _drop_pocket_on_rollback(session: Any) -> None:
    """진짜 되감기가 일어나면 적어 둔 것을 버린다(되감긴 쓰기의 알람이 다음 ``flush`` 에 실려 나가지 않게)."""
    session.info.pop(POCKET, None)


__all__ = ["POCKET", "SWITCH_ENV", "Outbox", "deliver", "enabled", "flush", "mark_events", "note", "note_mark", "payload",
           "replaced_material", "save", "set_badge_hook"]
