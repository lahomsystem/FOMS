"""수정 제작 고르기 — 다시 만들 도면 · 다시 할 공정(설계서 2026-11-28 흐름 셋 §2-2 · §2-3, 사장님 답 6 "다시 할 칸 고르기").

``POST /api/orders/<id>/production/rework`` 가 지금 문(반장 · 관리자 · 단계 · 도면 수정 중 · 보류)을 지난 뒤 여기를 두 번 부른다.

1. :func:`read_pick` — 몸의 ``keys``(도면이 1장 이상인 주문) 또는 ``steps``(도면이 0장인 주문)를 검사한다. 한 장도(한 칸도) 안 골랐으면
   400 ``REWORK_PICK_REQUIRED``(값을 안 싣는 옛 화면 사본 포함 — 다시 할 것이 없으면 [완료 취소]), 지금 도면이 아니면 409
   ``DRAWING_NOT_CURRENT``, 반장이 남의 공장 도면을 고르면 403 ``OTHER_FACTORY``, 모르는 공정 값은 400 ``BAD_REQUEST``. 쿼리 0 · 쓰기 0.
   관리자 뚫기 대상이 아니다(업무 문이 아니라 잘못된 요청).
2. :func:`apply_pick` — 같은 tx 에서 쓴다(주문 행은 부르는 쪽이 이미 잠갔다). ``sd`` 는 부르는 쪽 작업 사본이고 재대입 ·
   ``flag_modified`` 는 부르는 쪽이 지금처럼 한 번 한다.

도면이 있는 주문: **고른 도면만** 네 파트 표시를 '미정'으로(줄은 남긴다 — 사람 목록 · 바뀐 기록 칸만 비운다). 줄마다 이벤트
``PRODUCTION_PART_MARKED``(``action: 'rework'`` · ``from`` · ``to: 'NONE'`` · ``holders_before`` · ``by_name`` · ``rework_count`` — 바뀐 기록
글은 ``part_history`` 가 만든다). 공정 칸은 지금 동기화 규칙으로(넷 다 꺼짐 — ``via: part_marks`` · ``trigger: rework``), 공장 완료 표지는
고른 도면이 있는 공장만 지운다. 표시를 한 줄도 안 쓴 파트(손으로 켠 옛 칸 · 칸도 도면도 안 쓰고 완료된 주문)는 **안 고른 도면을 완료로
풀어 적는다** — 그 파트도 이제 도면으로 보므로(``part_progress.parts_in_use``) 안 풀면 안 고른 도면까지 미정이 된다.

도면이 없는 주문: **고른 칸만** 끈다. 안 고른 칸 가운데 꺼져 있던 것은 켠다(``via: 'rework'`` · 이름 없음 — 제작 완료된 주문이라 안 고른
공정은 끝난 것이다. 안 채우면 고른 칸 하나를 켜는 순간 "한 칸이라도 켜면 넷 다" 규칙이 안 고른 칸까지 요구한다).

``rework`` 는 기록용 낱말이다 — 도면 쓰기 API(``/api/production/part-marks``)가 받는 누름이 아니다.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import insert, update

from foms.services.datetime_kst import now_utc_naive, parse_datetime_utc
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_factory import sheet_factory
from foms.services.production import mark_crew as mc
from foms.services.production.factory_constants import DEFAULT_FACTORY
from foms.services.production.factory_marks import clear_factory_marks
from foms.services.production.factory_scope import OTHER_FACTORY, other_factory_message
from foms.services.production.part_access import can_write_sheet
from foms.services.production.part_constants import MARK_STATE_NONE, PRODUCTION_PART_KEYS
from foms.services.production.part_mark_notes import actor_name
from foms.services.production.part_mark_write import MarkWrite, after_views, plan_write
from foms.services.production.part_marks_query import order_marks
from foms.services.production.part_progress import cards_used, marks_by_part
from foms.services.production.part_steps_sync import STEP_EVENT, apply_part_step_changes, plan_part_step_changes, step_event_rows
from foms.services.production.step_expand import UNKNOWN_FINISHER, expand_hand_step
from foms.services.production.steps import (
    PRODUCTION_STEP_DEFS,
    PRODUCTION_STEP_KEYS,
    PRODUCTION_STEP_LABELS,
    REWORK_KEYS,
    REWORK_STEPS,
    set_production_step,
    step_done_map,
)
from models import OrderEvent, ProductionPartMark

REWORK_PICK_REQUIRED = "REWORK_PICK_REQUIRED"
PICK_DRAWINGS_MESSAGE = "다시 만들 도면을 골라 주세요. 화면을 새로 고친 뒤 [수정 제작]을 다시 눌러 주세요."
PICK_STEPS_MESSAGE = "다시 할 공정을 골라 주세요. 화면을 새로 고친 뒤 [수정 제작]을 다시 눌러 주세요."
BAD_STEP_MESSAGE = "공정 값이 올바르지 않아요."
DRAWING_NOT_CURRENT = "DRAWING_NOT_CURRENT"
#: 작업 시트용 글(도면 판의 같은 코드는 "[다시 받기]를 눌러 주세요." — 작업 시트에는 그 단추가 없다).
NOT_CURRENT_MESSAGE = "도면이 바뀌었어요. 화면을 다시 열어 주세요."
STARTED_MESSAGE = "수정 제작을 시작했어요."
#: 표시 이벤트 ``action`` · 공정 칸 ``via`` · 이벤트 ``trigger``.
ACTION_REWORK = "rework"
VIA_REWORK = "rework"
TRIGGER_REWORK = "rework"


class ReworkRefusal(Exception):
    """고른 것이 틀려 거절 — 수정 제작 API 의 지금 거절 꼴(``{success, code, message}`` — 화면이 ``message`` 를 그대로 보인다)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def body(self) -> dict[str, Any]:
        return {"success": False, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class ReworkPick:
    """검사를 마친 고른 것 — 도면(``entries`` = 지금 확정 도면 항목 · 도면 번호 순)이거나 공정(``steps`` · 정의 순서), 둘 중 하나만."""

    entries: tuple[dict[str, Any], ...] = ()
    numbers: tuple[int, ...] = ()
    factories: tuple[int, ...] = ()
    steps: tuple[str, ...] = ()

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(entry["key"] for entry in self.entries)

    def record(self) -> dict[str, list[str]]:
        """회차 기록(``production.rework``) · 감사에 더하는 칸 — ``{keys: […]}`` 또는 ``{steps: […]}``."""
        return {REWORK_KEYS: list(self.keys)} if self.entries else {REWORK_STEPS: list(self.steps)}

    def event_extra(self) -> dict[str, Any]:
        """이벤트 ``PRODUCTION_REWORK_STARTED`` payload 에 더하는 칸 — 도면이면 번호(``numbers``)도."""
        return {**self.record(), "numbers": list(self.numbers)} if self.entries else self.record()

    def alarm(self) -> dict[str, Any]:
        """알람 재료(``floor_alarm.note(…, 'rework', …)`` — 약속 4): ``drawing_keys`` 또는 ``steps`` + ``factories``."""
        if self.entries:
            return {"drawing_keys": list(self.keys), "factories": list(self.factories)}
        return {"steps": list(self.steps), "factories": list(self.factories)}

    def message(self) -> str:
        """끝난 뒤 알림 글 — "수정 제작을 시작했어요. 도면 2장을 다시 만들어요." · "… 조립 · 검수를 다시 해요."."""
        if self.entries:
            return f"{STARTED_MESSAGE} 도면 {len(self.entries)}장을 다시 만들어요."
        return f"{STARTED_MESSAGE} {_object_words([PRODUCTION_STEP_LABELS[key] for key in self.steps])} 다시 해요."


def _object_words(labels: list[str]) -> str:
    """"조립 · 검수를" — 마지막 낱말 받침에 맞춘 을/를."""
    text = " · ".join(labels)
    last = text[-1]
    final = (ord(last) - ord("가")) % 28 if "가" <= last <= "힣" else 1
    return f"{text}{'을' if final else '를'}"


def read_pick(user: Any, sd: Any, body: Any) -> ReworkPick:
    """몸의 고른 것을 검사한다 — 도면이 1장 이상인 주문은 ``keys`` 만, 0장인 주문은 ``steps`` 만 본다(다른 쪽은 보내도 안 읽는다).

    Args:
        user: 누른 사람(반장 · 관리자 — 부르는 쪽 문이 이미 봤다). 반장은 자기 공장 도면만 고른다.
        sd: 잠근 주문의 ``structured_data``(읽기만).
        body: 요청 몸.

    Raises:
        ReworkRefusal: 안 고름(400) · 모르는 공정(400) · 지금 도면이 아님(409) · 남의 공장 도면(403).
    """
    body = body if isinstance(body, dict) else {}
    files = resolve_final_drawing_files(sd if isinstance(sd, dict) else {})
    if not files:
        return _read_steps(body.get(REWORK_STEPS))
    raw = body.get(REWORK_KEYS)
    if not isinstance(raw, list) or not raw:
        raise ReworkRefusal(400, REWORK_PICK_REQUIRED, PICK_DRAWINGS_MESSAGE)
    current = {entry["key"] for entry in files}
    if any(not isinstance(key, str) or key not in current for key in raw):
        raise ReworkRefusal(409, DRAWING_NOT_CURRENT, NOT_CURRENT_MESSAGE)
    picked, seen = [], set()
    for number, entry in enumerate(files, 1):
        if entry["key"] not in raw or entry["key"] in seen:  # 같은 key 가 지금 도면에 두 번 있어도 줄은 key 마다 하나
            continue
        seen.add(entry["key"])
        factory = sheet_factory(sd, entry)
        if not can_write_sheet(user, factory):
            raise ReworkRefusal(403, OTHER_FACTORY, other_factory_message(factory))
        picked.append((number, entry, factory))
    return ReworkPick(entries=tuple(entry for _n, entry, _f in picked), numbers=tuple(n for n, _e, _f in picked),
                      factories=tuple(sorted({f for _n, _e, f in picked})))


def _read_steps(raw: Any) -> ReworkPick:
    if not isinstance(raw, list) or not raw:
        raise ReworkRefusal(400, REWORK_PICK_REQUIRED, PICK_STEPS_MESSAGE)
    if any(not isinstance(key, str) or key not in PRODUCTION_STEP_KEYS for key in raw):
        raise ReworkRefusal(400, "BAD_REQUEST", BAD_STEP_MESSAGE)
    return ReworkPick(steps=tuple(key for key, _label in PRODUCTION_STEP_DEFS if key in raw), factories=(DEFAULT_FACTORY,))


def apply_pick(db: Any, order: Any, sd: dict[str, Any], pick: ReworkPick, user: Any, *, count: int) -> None:
    """고른 것을 쓴다 — 표시 줄 · 이벤트는 여기서, 공정 칸 · 공장 완료 표지는 ``sd`` 에 제자리(부르는 쪽이 한 번 재대입).

    Args:
        db: 세션(같은 tx — 주문 행은 이미 잠겨 있다).
        order: 잠근 주문.
        sd: 부르는 쪽 작업 사본(``production`` 이 사전으로 있다).
        pick: :func:`read_pick` 결과.
        user: 누른 사람.
        count: 이번 수정 제작 횟수(표시 이벤트 ``rework_count``).
    """
    if pick.entries:
        _apply_drawings(db, order, sd, pick, user, count)
    else:
        _apply_steps(db, order, sd, pick, user)


def _apply_drawings(db: Any, order: Any, sd: dict[str, Any], pick: ReworkPick, user: Any, count: int) -> None:
    now = now_utc_naive()
    rows = order_marks(db, order.id)  # 네 파트 한 번
    writes = _settle_rest(db, order, sd, rows, set(pick.keys), user, now)
    by_part = marks_by_part(rows)
    undone: list[MarkWrite] = []
    for entry in pick.entries:
        for part in PRODUCTION_PART_KEYS:
            row = by_part.get(part, {}).get(entry["key"])
            if row is None or str(row.state or MARK_STATE_NONE) == MARK_STATE_NONE:
                continue  # 줄이 없거나 이미 미정 — 쓸 것이 없다(수정 제작 규칙이 그 파트를 도면으로 본다)
            write = plan_write(order, entry, row, part=part, target=MARK_STATE_NONE, user=user, action=ACTION_REWORK,
                               override=False, now=now)
            write.event["payload"].update(holders_before=_people_before(write.before), rework_count=count)
            undone.append(write)
    views = after_views(rows, writes + undone).get(int(order.id), [])
    # 공정 칸 — 지금 동기화 규칙 그대로(네 파트 모두 미완료 도면이 생겼으니 켜져 있던 칸이 모두 꺼진다)
    changes = plan_part_step_changes(sd, views, None, PRODUCTION_PART_KEYS)
    apply_part_step_changes(sd, changes, at_iso=datetime.datetime.now(datetime.timezone.utc).isoformat())
    events = [w.event for w in undone] + step_event_rows(order.id, changes, actor_user_id=user.id, trigger=TRIGGER_REWORK,
                                                         actor_name=actor_name(user))
    if undone:  # 표마다 한 번(고른 장 수와 무관)
        db.execute(update(ProductionPartMark), [{"id": w.row_id, **w.values} for w in undone])
    if events:
        db.execute(insert(OrderEvent), events)
    clear_factory_marks(sd, pick.factories)  # 고른 도면이 있는 공장만 — 안 고른 공장은 완료 그대로(한 공장 주문은 표지가 없다)


def _settle_rest(db: Any, order: Any, sd: dict[str, Any], rows: list[Any], picked: set[str], user: Any,
                 now: datetime.datetime) -> list[MarkWrite]:
    """표시를 한 줄도 안 쓴 파트의 **안 고른 도면**을 완료로 풀어 적는다(도면 수정 전달과 같은 길 — ``step_expand``, 파트마다 문 둘).

    손으로 켠 옛 칸 = 칸을 켠 사람 이름 · 칸 시각. 칸도 안 켠 파트(공정 칸 · 도면을 한 번도 안 쓰고 제작 완료된 주문) = 이름 없음 · 지금.
    표시를 쓴 파트의 안 고른 도면은 건드리지 않는다(있는 그대로).
    """
    used = cards_used(rows)
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    steps = {str(s.get("key")): s for s in production.get("steps") or [] if isinstance(s, dict)}
    writes: list[MarkWrite] = []
    for part in PRODUCTION_PART_KEYS:
        if part in used:
            continue
        step = steps.get(part) or {}
        hand = bool(step.get("done"))
        writes += expand_hand_step(db, order, sd, rows, part, exclude_keys=picked, user=user,
                                   done_by_name=str(step.get("by_name") or "").strip() if hand else "",
                                   done_at=(_naive_utc(step.get("at")) if hand else None) or now)
    return writes


def _naive_utc(raw: Any) -> Optional[datetime.datetime]:
    aware = parse_datetime_utc(raw) if raw else None
    return aware.replace(tzinfo=None) if aware is not None else None


def _people_before(before: Any) -> list[dict[str, Any]]:
    """미정으로 돌리기 전 작업한 사람들 ``[{uid, name, done}]``(표시 이벤트의 목록 꼴) — 사람 없는 완료 · 기본은 끝낸 사람 하나."""
    crew = [{"uid": m.get("uid"), "name": m.get("name"), "done": mc.is_done(m)} for m in before.crew]
    if crew or not before.done_by_name:
        return crew
    return [{"uid": before.done_by_user_id, "name": before.done_by_name, "done": True}]


def _apply_steps(db: Any, order: Any, sd: dict[str, Any], pick: ReworkPick, user: Any) -> None:
    now = now_utc_naive()
    at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    was = step_done_map(sd)
    name = actor_name(user)
    events: list[dict[str, Any]] = []
    for key, _label in PRODUCTION_STEP_DEFS:
        done = key not in pick.steps  # 고른 칸 = 끔 · 안 고른 칸 = 켜 둠(꺼져 있던 것은 이름 없이 채운다)
        if was.get(key, False) == done:
            continue
        set_production_step(sd, key, done, by_name=None, at_iso=at_iso, via=VIA_REWORK)
        payload = {"key": key, "done": done, "domain": "PRODUCTION_DOMAIN", "action": STEP_EVENT, "via": VIA_REWORK,
                   "trigger": TRIGGER_REWORK, **({UNKNOWN_FINISHER: True} if done else {"by_name": name})}
        events.append({"order_id": int(order.id), "event_type": STEP_EVENT, "payload": payload,
                       "created_by_user_id": user.id, "created_at": now})
    if events:
        db.execute(insert(OrderEvent), events)
    clear_factory_marks(sd)  # 도면이 없어 있는 공장도 없다 — 남은 옛 표지는 지금처럼 모두 지운다


__all__ = ["ACTION_REWORK", "BAD_STEP_MESSAGE", "DRAWING_NOT_CURRENT", "NOT_CURRENT_MESSAGE", "PICK_DRAWINGS_MESSAGE",
           "PICK_STEPS_MESSAGE", "REWORK_PICK_REQUIRED", "ReworkPick", "ReworkRefusal", "TRIGGER_REWORK", "VIA_REWORK",
           "apply_pick", "read_pick"]
