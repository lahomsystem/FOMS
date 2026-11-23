"""도면 마감 알림 — WORKER 1분 알림 루프의 한 단계(설계서 ``docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md`` §9).

마감 날 아침 · 저녁 칸, 마감이 지난 뒤 일하는 날 아침 칸에 아직 안 내려온 주문의 도면 담당 · 영업 쪽에게 벨 + 폰 알림을 만든다.
때 · 대상 · 글 · 받는 사람은 읽기만 하는 :mod:`.drawing_deadline_plan`, 여기는 스위치 · 한 번만 · 기록 · 작업 시트 줄.

- 스위치(§9-8): :data:`ENABLED_ENV` 가 참일 때만 돈다 — 꺼지면 쿼리 0 · 안 보냄(처음 끔). :data:`ONLY_USERS_ENV` 가 있으면
  그 사람만 받고 나머지는 '건너뜀' 수만 남긴다. 값은 있는데 번호가 하나도 없으면 **아무에게도** 안 보낸다(잘못 적은 값이
  전원 발송이 되지 않게).
- 한 번만(§9-6): SystemSetting :data:`STATE_KEY` 한 줄을 ``with_for_update`` 로 잠근 같은 트랜잭션에서 알림 줄을 만든다(WORKER 가
  둘이어도 열쇠마다 한 번). 값 = ``{'sent': {열쇠: {'at': KST 시각, 'to': [이름], 'skipped': 수}}}``, :data:`KEEP_DAYS` 일 지난 열쇠는
  지운다. 새 표 · 마이그레이션 · 주문 JSONB 쓰기 없음.
- 커밋 · 배달(배지 · 실시간 · 폰)은 부르는 쪽(``scripts/maintenance/run_notification_escalation.py``)이 한다 — 서비스가 api 층을
  거꾸로 부르지 않는다.
"""

from __future__ import annotations

import copy
import datetime
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm.attributes import flag_modified

from foms.services.common.business_calendar import is_business_day
from foms.services.datetime_kst import now_kst, to_utc_naive
from foms.services.feature_flags import env_bool, env_id_list
from foms.services.notifications.drawing_deadline_plan import (
    KIND_EVENING,
    SLOT_HOURS,
    DueAlert,
    PeopleCache,
    alert_text,
    due_alerts,
    recipients_for,
    slot_of,
    still_waiting,
    to_kst,
    user_names,
)
from foms.services.notifications.drawing_deadline_push import GENERIC_TITLE, NOTIFICATION_TYPE
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.production.drawing_arrival import day_md
from models import Notification, SystemSetting

_LOGGER = logging.getLogger("drawing_deadline_alert")

ENABLED_ENV = "FOMS_DRAWING_DEADLINE_ALERT_ENABLED"
ONLY_USERS_ENV = "FOMS_DRAWING_DEADLINE_ALERT_ONLY_USERS"
STATE_KEY = "drawing_deadline_alert_state"
#: 보낸 열쇠를 남겨 두는 날 수(지난 열쇠는 지운다).
KEEP_DAYS = 14
#: 창이 끝난 칸을 이 프로세스가 이미 확인했는가(``(날, 칸)``) — 창 밖 바퀴는 칸마다 한 번만 읽고 그 뒤 쿼리 0.
_MISSED_CHECKED: Set[Tuple[str, str]] = set()
#: 이 프로세스가 **커밋된 기록 줄에서 읽어** 이미 보냈다고 아는 오늘 열쇠(``{'day': 'YYYY-MM-DD', 'keys': set()}``).
#: 오늘 대상 열쇠는 모두 오늘 날짜를 품는다(마감 날 = 오늘 · 늦음 = 그날)라 날이 바뀌면 비운다. 자기가 방금 만든 열쇠는
#: 넣지 않는다(커밋이 실패하면 거짓 기억이 된다) — 그래서 창 안 바퀴는 보낼 것이 없으면 후보 1개만 읽는다(§8 표).
_KNOWN_SENT: Dict[str, Any] = {"day": "", "keys": set()}


def alert_enabled() -> bool:
    """스위치 :data:`ENABLED_ENV` 가 켜졌나(기본 끔)."""
    return env_bool(ENABLED_ENV, False)


def only_user_ids() -> Optional[Set[int]]:
    """받는 사람 허용 목록 — 값이 없으면 None(모두), 값이 있으면 그 번호들(번호가 없으면 빈 집합 = 아무도 안 받음)."""
    if not (os.getenv(ONLY_USERS_ENV, "") or "").strip():
        return None
    return env_id_list(ONLY_USERS_ENV)


def _empty_result(enabled: bool) -> Dict[str, Any]:
    return {"enabled": enabled, "slot": None, "checked": 0, "due": 0, "sent": 0, "notifications": 0,
            "skipped": 0, "missed_slot": 0, "created_notification_ids": [], "recipient_user_ids": [],
            "title": GENERIC_TITLE}


def _sent_map(row: Optional[SystemSetting]) -> Dict[str, Any]:
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    sent = value.get("sent")
    return dict(sent) if isinstance(sent, dict) else {}


def read_sent(db: Any) -> Dict[str, Any]:
    """보낸 기록(잠그지 않음, PK 읽기 1개) — 미리 보기 · 작업 시트 · 창 놓침 확인이 쓴다."""
    return _sent_map(db.get(SystemSetting, STATE_KEY))


def _known_sent(today: datetime.date) -> Set[str]:
    """오늘 이미 보냈다고 아는 열쇠(날이 바뀌면 비운다)."""
    if _KNOWN_SENT["day"] != today.isoformat():
        _KNOWN_SENT["day"], _KNOWN_SENT["keys"] = today.isoformat(), set()
    return _KNOWN_SENT["keys"]


def _remember(today: datetime.date, sent: Dict[str, Any]) -> None:
    """커밋된 기록에서 읽은 오늘 열쇠를 기억한다."""
    mark = f":{today.isoformat()}:"
    _known_sent(today).update(k for k in sent if mark in k)


def run_drawing_deadline_alerts(db: Any, *, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """알림 루프 한 바퀴의 도면 마감 단계(커밋은 부르는 쪽).

    쿼리: 스위치 끔 · 영업일 아님 0, 창 밖 0(창이 끝난 칸마다 프로세스에서 한 번만 놓침 확인), 창 안 후보 1
    (+ 보낼 것이 있으면 기록 읽기 · 잠금 · 다시 보기 · 사람 · 쓰기).

    Args:
        db: 세션.
        now: 기준 시각(시간대 있는 값, 시험은 KST 로 넣는다 — CI 는 UTC). 없으면 ``now_kst()``.

    Returns:
        ``{enabled, slot, checked, due, sent, notifications, skipped, missed_slot, created_notification_ids,
        recipient_user_ids, title}``.
    """
    if not alert_enabled():
        return _empty_result(False)
    result = _empty_result(True)
    now_k = to_kst(now or now_kst())
    today = now_k.date()
    if not is_business_day(today):
        return result
    slot = slot_of(now_k)
    if slot is None:
        result["missed_slot"] = check_missed_slots(db, now_k)
        return result
    result["slot"] = slot
    result["checked"], dues = due_alerts(db, today, slot)
    pending = [d for d in dues if d.key not in _known_sent(today)]
    if pending:
        sent = read_sent(db)
        _remember(today, sent)
        pending = [d for d in pending if d.key not in sent]
    result["due"] = len(pending)
    if not pending:
        return result
    row = _lock_state_row(db)
    locked = _sent_map(row)
    _remember(today, locked)  # 잠금 뒤 읽은 값 = 다른 WORKER 가 커밋한 것까지(자기 쓰기는 아직 없다)
    pending = still_waiting(db, [d for d in pending if d.key not in locked])
    if pending:
        _send(db, pending, now_k, row, locked, result)
    return result


def _lock_state_row(db: Any) -> Optional[SystemSetting]:
    """기록 줄을 ``FOR UPDATE`` 로 잠가 새로 읽는다(다른 WORKER 가 커밋할 때까지 기다린다 — 그 뒤 그쪽 열쇠가 보인다)."""
    return db.get(SystemSetting, STATE_KEY, populate_existing=True, with_for_update=True)


def _send(db: Any, pending: List[DueAlert], now_k: datetime.datetime, row: Optional[SystemSetting],
          sent: Dict[str, Any], result: Dict[str, Any]) -> None:
    """잠근 같은 트랜잭션에서 사람마다 알림 줄 + 기록. 허용 목록은 줄을 만들기 **전에** 거른다."""
    allow = only_user_ids()
    cache = PeopleCache(db)
    plans = []
    for due in pending:
        everyone = recipients_for(db, due, cache)["all"]
        targets = sorted(everyone if allow is None else everyone & allow)
        plans.append((due, targets, len(everyone) - len(targets)))
    names = user_names(db, {uid for _d, targets, _s in plans for uid in targets})
    created_at = to_utc_naive(now_k)
    recipients: Set[int] = set()
    titles: Set[str] = set()
    for due, targets, skipped in plans:
        title, body = alert_text(due, now_k.date())
        titles.add(title)
        for uid in targets:
            note = Notification(order_id=due.order_id, notification_type=NOTIFICATION_TYPE, target_type="USER",
                                target_user_id=uid, is_urgent=False, title=title, message=body, is_read=False,
                                created_by_name="FOMS", created_at=created_at)
            db.add(note)
            db.flush()
            recipients.update(int(s.user_id) for s in fan_out_new_notification(db, note, actor_user_id=None))
            result["created_notification_ids"].append(note.id)
        sent[due.key] = {"at": now_k.isoformat(timespec="minutes"), "to": [names[uid] for uid in targets],
                         "skipped": skipped}
        result["skipped"] += skipped
    _write_state(db, row, sent, now_k.date())
    result["sent"] = len(plans)
    result["notifications"] = len(result["created_notification_ids"])
    result["recipient_user_ids"] = sorted(recipients)
    result["title"] = titles.pop() if len(titles) == 1 else GENERIC_TITLE


def _write_state(db: Any, row: Optional[SystemSetting], sent: Dict[str, Any], today: datetime.date) -> None:
    """기록 줄에 쓴다 — :data:`KEEP_DAYS` 일 지난 열쇠는 지운다(``at`` 의 날 기준)."""
    floor = (today - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    kept = {k: v for k, v in sent.items() if isinstance(v, dict) and str(v.get("at") or "")[:10] >= floor}
    if row is None:
        row = SystemSetting(setting_key=STATE_KEY, description="도면 마감 알림 — 보낸 열쇠 · 때 · 받은 사람", version=1)
        db.add(row)
    value = copy.deepcopy(row.setting_value) if isinstance(row.setting_value, dict) else {}
    value["sent"] = kept
    row.setting_value = value
    flag_modified(row, "setting_value")
    db.flush()


def check_missed_slots(db: Any, now_k: datetime.datetime) -> int:
    """창이 끝났는데 대상이 있었고 그 칸 기록이 없으면 WARN ``missed_slot`` 한 줄(§9-8). 칸마다 프로세스에서 한 번만 읽는다.

    Args:
        db: 세션(읽기만).
        now_k: KST 시각(창 밖 · 영업일).

    Returns:
        기록 없이 놓친 알림 수(창이 아직 안 끝났거나 이미 본 칸이면 0, 쿼리 0).
    """
    today = now_k.date().isoformat()
    for seen in [s for s in _MISSED_CHECKED if s[0] != today]:
        _MISSED_CHECKED.discard(seen)
    todo = [slot for slot, (_start, end) in SLOT_HOURS.items()
            if now_k.hour >= end and (today, slot) not in _MISSED_CHECKED]
    missed = 0
    sent: Optional[Dict[str, Any]] = None
    for slot in todo:
        _MISSED_CHECKED.add((today, slot))
        _checked, dues = due_alerts(db, now_k.date(), slot)
        dues = [d for d in dues if d.key not in _known_sent(now_k.date())]
        if not dues:
            continue
        if sent is None:
            sent = read_sent(db)
            _remember(now_k.date(), sent)
        keys = [d.key for d in dues if d.key not in sent]
        if keys:
            _LOGGER.warning("[drawing-deadline-alert] missed_slot day=%s slot=%s orders=%d", today, slot, len(keys))
            missed += len(keys)
    return missed


def reset_process_memory() -> None:
    """시험용 — 이 프로세스의 기억(창 놓침 확인 · 보낸 줄 아는 열쇠)을 비운다."""
    _MISSED_CHECKED.clear()
    _KNOWN_SENT["day"], _KNOWN_SENT["keys"] = "", set()


def _when_label(key: str, at_text: str) -> Optional[Tuple[datetime.date, str]]:
    """기록 한 줄 → (날, '아침 8:02' · '저녁 6:01'). 못 읽으면 None."""
    try:
        at = to_kst(datetime.datetime.fromisoformat(str(at_text)))
    except ValueError:
        return None
    if key.endswith(f":{KIND_EVENING}"):
        hour = at.hour - 12 if at.hour > 12 else at.hour
        return at.date(), f"저녁 {hour}:{at.minute:02d}"
    return at.date(), f"아침 {at.hour}:{at.minute:02d}"


def format_alert_line(sent: Dict[str, Any], order_id: int) -> str:
    """작업 시트 '알림 보냄' 줄(§5-7) — 실제로 누군가에게 보낸 것만, 날마다 묶어 때 순서로.

    Args:
        sent: 기록 값 ``sent``(:func:`read_sent`).
        order_id: 주문 번호.

    Returns:
        ``'알림 보냄 11/23 (월) 아침 8:02 · 저녁 6:01 · 11/24 (화) 아침 8:01'`` 또는 빈 글(보낸 것이 없으면).
    """
    prefix = f"{int(order_id)}:"
    picked = []
    for key, value in sent.items():
        if not key.startswith(prefix) or not isinstance(value, dict) or not value.get("to"):
            continue
        when = _when_label(key, value.get("at"))
        if when is not None:
            picked.append((str(value.get("at")), when))
    if not picked:
        return ""
    parts: List[str] = []
    last_day: Optional[datetime.date] = None
    for _at, (day, label) in sorted(picked):
        parts.append(label if day == last_day else f"{day_md(day)} {label}")
        last_day = day
    return "알림 보냄 " + " · ".join(parts)


def sheet_alert_line(db: Any, order_id: int) -> str:
    """작업 시트용 — 스위치가 켜졌을 때만 기록 줄을 읽는다(PK 읽기 1개, 꺼지면 쿼리 0 · 빈 글)."""
    if not alert_enabled():
        return ""
    return format_alert_line(read_sent(db), order_id)


__all__ = [
    "ENABLED_ENV",
    "KEEP_DAYS",
    "NOTIFICATION_TYPE",
    "ONLY_USERS_ENV",
    "STATE_KEY",
    "alert_enabled",
    "check_missed_slots",
    "format_alert_line",
    "only_user_ids",
    "read_sent",
    "reset_process_memory",
    "run_drawing_deadline_alerts",
    "sheet_alert_line",
]
