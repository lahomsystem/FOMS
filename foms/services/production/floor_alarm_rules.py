"""생산 현장 알람 — 누가 · 무엇을 받나(설계서 2026-11-28 생산 현장 알람 §4-3 받는 사람 · §4-5 받는 사람 문 · §2-2 까닭이 풀리면 닫기).

적어 둔 사건 하나(:func:`plan`) → 만들 알람(:class:`Alarm`) · 닫을 알람. 읽기는 :class:`Reads` 가 한 번의 ``flush`` 안에서 주문 · 사람 ·
표시 줄 · 앞 알람을 **한 번씩만** 읽어 준다(§4-10). 줄을 만들고 보내는 일은 :mod:`foms.services.production.floor_alarm` 몫이다.

* **작업 중인 사람** = 지금 확정 도면의 표시 줄(``NEED``)에서 자기 몫 완료가 없는 사람(:func:`~.floor_alarm_reads.people`). 옛 도면 key 줄은
  이력이라 세지 않는다(도면이 새 도면으로 바뀐 사건만 옛 key 줄을 본다).
* **받는 사람 문**(:func:`~.floor_alarm_reads.can_receive`) 을 지난 사람만 받는다. 관리자는 담당을 받았을 때(``given``)만. 누른 사람 본인은 늘
  뺀다. 팀 · 역할 · 전체 길은 없다 — 늘 사람 지정.
* **닫기** = 안 누른 알람의 까닭이 사라지면 보관(``archived_at``)으로 닫는다 — 지금 막힌 도면을 아직 작업 중인 사람의 것은 남긴다.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Iterable, Optional

from foms.services.orders.drawing_factory import present_factories
from foms.services.orders.drawing_fix import blocked, blocked_entries
from foms.services.orders.drawing_fix_requests import find_request
from foms.services.orders.order_mutation_policy import normalize_team
from foms.services.orders.state_axes import read_main_stage
from foms.services.production import floor_alarm_text as T
from foms.services.production.factory_constants import DEFAULT_FACTORY, account_production_factory
from foms.services.production.floor_alarm_reads import (
    MERGE_SECONDS,
    RECENT_HOURS,
    SENT_HOURS,
    Alarm,
    Plan,
    Reads,
    actor_factory,
    can_receive,
    is_open,
    people,
)
from foms.services.production.part_constants import PRODUCTION_PART_LABELS
from foms.services.production.part_progress import current_keys
from foms.services.production.ship_dates import due_day, kind_word, order_ship_dates
from foms.services.production.steps import step_done_map

#: 시공일 임박 띠(#12) — 바뀐 뒤 출고일이 오늘부터 이 날 수 안일 때만.
DATE_NEAR_DAYS = 2
STAGE_PRODUCTION = "PRODUCTION"


class _Case:
    """사건 하나를 푸는 자리 — 주문 · 재료 · 누른 사람과 알람 더하기 · 닫기."""

    def __init__(self, reads: Reads, note: dict[str, Any], order: Any) -> None:
        self.reads, self.note, self.order = reads, note, order
        self._wanted: list[tuple[Alarm, bool]] = []  # (알람, 관리자도 받는지) — 받는 사람 문은 끝에 한 번에 본다(사람 읽기 1)
        self.sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        self.m: dict[str, Any] = note.get("m") or {}
        self.actor_id, self.actor_name = note.get("by"), str(note.get("by_name") or "")
        self.plan = Plan()
        self.numbers = {key: no for no, key in enumerate(current_keys(self.sd), 1)}
        customer = ((self.sd.get("parties") or {}).get("customer") or {}).get("name") or getattr(order, "customer_name", "")
        ship = order_ship_dates(order)
        due = due_day((day for day, _kind in ship), reads.today)
        self._customer = str(customer or "").strip()
        self._when = f"{due.month}/{due.day} {kind_word(ship[0][1])}" if due is not None else ""

    def scene(self, numbers: Iterable[Any] = (), part: str = "") -> T.Scene:
        found = tuple(sorted({int(n) for n in numbers if isinstance(n, int)}))
        return T.Scene(customer=self._customer, when=self._when, numbers=found, actor=self.actor_name, part=part)

    @property
    def marks(self) -> list[Any]:
        return self.reads.marks(int(self.order.id))

    def _actor(self) -> Any:
        return self.reads.users([self.actor_id]).get(self.actor_id) if isinstance(self.actor_id, int) else None

    @property
    def by_drawing_team(self) -> bool:
        """누른 사람이 도면팀인지 — 적을 때 본 팀이 있으면 그 값(쿼리 0), 없으면(이름만 받은 자리) 사람을 읽는다."""
        team = self.note["by_team"] if "by_team" in self.note else getattr(self._actor(), "team", None)
        return normalize_team(team) == "DRAWING"

    def material_keys(self) -> dict[str, Any]:
        """재료의 도면(``drawing_keys`` 또는 ``numbers``) → ``{key: 번호}``(지금 도면에 없는 key 는 번호 None)."""
        keys = [str(k) for k in self.m.get("drawing_keys") or [] if k]
        if not keys and isinstance(self.m.get("numbers"), (list, tuple)):
            by_no = {no: key for key, no in self.numbers.items()}
            keys = [by_no[n] for n in self.m["numbers"] if n in by_no]
        return {key: self.numbers.get(key) for key in keys}

    def add(self, uid: Any, ntype: str, text: tuple[str, str], *, numbers: Iterable[int] = (), admin_ok: bool = False,
            render: Optional[Callable[[tuple[int, ...]], tuple[str, str]]] = None) -> None:
        """알람 후보 하나를 더한다(본인 · 같은 종류 겹침은 뺀다) — 받는 사람 문은 :meth:`finish` 가 본다."""
        again = any(a.user_id == uid and a.ntype == ntype for a, _ok in self._wanted)
        if isinstance(uid, int) and not isinstance(uid, bool) and uid != self.actor_id and not again:
            self._wanted.append((Alarm(uid, ntype, text[0], text[1], tuple(sorted(set(numbers))), render), admin_ok))

    def finish(self) -> Plan:
        """후보의 사람들을 한 번에 읽어 받는 사람 문을 지난 알람만 남긴다."""
        users = self.reads.users(a.user_id for a, _ok in self._wanted)
        self.plan.alarms = [a for a, admin_ok in self._wanted if can_receive(users.get(a.user_id), admin_ok=admin_ok)]
        return self.plan

    def sent(self, ntype: str, *, open_only: bool = False, hours: int = SENT_HOURS) -> dict[int, list[tuple[Any, Any]]]:
        """그 종류 알람이 이 주문으로 나갔던 사람 → 줄들(``open_only`` = 안 누른 것만 · 72시간 안)."""
        since = self.reads.now - datetime.timedelta(hours=RECENT_HOURS if open_only else hours)
        out: dict[int, list[tuple[Any, Any]]] = {}
        for notif, state in self.reads.recent(int(self.order.id)):
            if notif.notification_type == ntype and notif.created_at >= since and (not open_only or is_open(state)):
                out.setdefault(int(state.user_id), []).append((notif, state))
        return out

    def close(self, rows: Iterable[tuple[Any, Any]]) -> None:
        self.plan.close.extend(row for row in rows if row not in self.plan.close)

    def blocked_keys(self) -> dict[str, Any]:
        """지금(쓰기 뒤) 막힌 도면 ``{key: 번호}`` — 주문 통째면 전부(도면 판 막힘과 같은 판정)."""
        block = blocked(self.sd)
        return dict(self.numbers) if block.whole else {row["key"]: row["no"] for row in blocked_entries(self.sd, block=block)}

    def close_stale_revising(self) -> set[int]:
        """안 누른 '도면 수정 중' 멈춤 알람 가운데 까닭이 사라진 것(지금 막힌 도면을 작업 중이지 않은 사람 것)을 닫는다."""
        pending = self.sent(T.STOP_REVISING, open_only=True)
        if not pending:
            return set()
        still = people(self.marks, self.blocked_keys(), done=False)
        gone = {uid for uid in pending if uid not in still}
        self.close(row for uid in gone for row in pending[uid])
        return gone

    def close_given(self, uid: Any, part: str) -> None:
        """받은 사람이 그 파트 도면에서 다 빠졌으면 안 누른 '새 일' 알람을 닫는다(띠 없음 — §2-2)."""
        label = PRODUCTION_PART_LABELS.get(part, part)
        mine = [row for row in self.sent(T.NEW_GIVEN, open_only=True).get(uid, []) if f" {label} 담당을 " in (row[0].title or "")]
        if mine and uid not in people(self.marks, self.numbers, done=False, part=part):
            self.close(mine)

    def lead_ids(self, factories: Iterable[Any]) -> list[int]:
        wanted = {f for f in factories if f} or {DEFAULT_FACTORY}
        return [int(u.id) for u in self.reads.leads() if (account_production_factory(u) or DEFAULT_FACTORY) in wanted]

    def factories(self) -> tuple[int, ...]:
        """재료의 공장(``factories`` · ``factory``) → 없으면 누른 생산팀 계정의 공장 → 주문 도면이 있는 공장 → 1공장."""
        given = self.m.get("factories") or ([self.m["factory"]] if self.m.get("factory") else [])
        if given:
            return tuple(given)
        own = self.note["by_factory"] if "by_factory" in self.note else actor_factory(self._actor())
        return (own,) if own else (present_factories(self.sd) or (DEFAULT_FACTORY,))


def _given(c: _Case) -> None:
    key, part = str(c.m.get("drawing_key") or ""), str(c.m.get("part") or "")
    for uid in c.m.get("to") or []:
        c.add(uid, T.NEW_GIVEN, T.given(c.scene([c.numbers.get(key)], part)), numbers=[n for n in (c.numbers.get(key),) if n],
              admin_ok=True, render=lambda nums: T.given(c.scene(nums, part)))


def _taken(c: _Case) -> None:
    key, part = str(c.m.get("drawing_key") or ""), str(c.m.get("part") or "")
    to_name, self_take = str(c.m.get("to_name") or ""), bool(c.m.get("self"))

    def render(nums: Iterable[int]) -> tuple[str, str]:
        return T.taken(c.scene(nums, part), to_name=to_name, self_take=self_take)

    for uid in c.m.get("to") or []:
        c.add(uid, T.STOP_TAKEN, render([c.numbers.get(key)]), numbers=[n for n in (c.numbers.get(key),) if n], render=render)
        c.close_given(uid, part)


def _mark_notice(ntype: str, text: Callable[[T.Scene], tuple[str, str]]) -> Callable[[_Case], None]:
    def run(c: _Case) -> None:
        key, part = str(c.m.get("drawing_key") or ""), str(c.m.get("part") or "")
        for uid in c.m.get("to") or []:
            c.add(uid, ntype, text(c.scene([c.numbers.get(key)], part)))
            if ntype == T.NOTICE_START_CANCELLED:
                c.close_given(uid, part)
    return run


def _drawing_replaced(c: _Case) -> None:
    given = c.m.get("numbers") if isinstance(c.m.get("numbers"), dict) else {}
    keys = {str(k): given.get(k) for k in c.m.get("drawing_keys") or []}
    working, finished = people(c.marks, keys, done=False), people(c.marks, keys, done=True)
    waited = c.sent(T.STOP_REVISING)
    asked = {c.m.get("request_user_id")} | {(find_request(c.sd, rid) or {}).get("by_user_id") for rid in c.m.get("request_ids") or []}
    every = [n for n in keys.values() if n]
    gone = c.close_stale_revising()
    here = people(c.marks, c.numbers, done=False) if gone else {}  # 멈춤이 닫히는 사람 가운데 아직 이 주문을 작업 중인 사람(통째 막힘이 풀림)
    for uid in asked | {u for u in working if u in waited} | {u for u in gone if u in here}:  # #16 — 이미 멈춰 있던 일 · 요청한 사람
        mine = working.get(uid) or finished.get(uid) or (None if uid in asked else here.get(uid))  # 요청한 사람은 바뀐 도면 번호
        c.add(uid, T.NOTICE_FIX_APPLIED, T.fix_applied(c.scene(mine or every)))
    for uid, nums in working.items():  # #5
        if uid not in asked and uid not in waited:
            c.add(uid, T.STOP_DRAWING, T.stop_drawing(c.scene(nums), drawing_team=c.by_drawing_team), numbers=nums)
    for uid, nums in finished.items():  # #6
        if uid not in asked and uid not in working:
            c.add(uid, T.NOTICE_DRAWING, T.notice_drawing(c.scene(nums)))


def _drawing_revising(c: _Case) -> None:
    now_blocked, picked = c.blocked_keys(), c.material_keys()
    keys = {k: n for k, n in now_blocked.items() if k in picked} if picked else now_blocked
    pending = c.sent(T.STOP_REVISING, open_only=True)
    for uid, nums in people(c.marks, keys, done=False).items():
        if uid not in pending:
            c.add(uid, T.STOP_REVISING, T.stop_revising(c.scene(nums), drawing_team=c.by_drawing_team), numbers=nums)


def _fix_stopped(c: _Case) -> None:
    working = people(c.marks, c.material_keys() or c.numbers, done=False)
    for uid in c.close_stale_revising():  # #20 — 안 누른 멈춤 알람이 닫힐 때만
        c.add(uid, T.NOTICE_UNBLOCKED, T.unblocked(c.scene(working.get(uid) or c.material_keys().values())))


def _fix_rejected(c: _Case) -> None:
    keys = c.material_keys()
    working, waited = people(c.marks, keys, done=False), c.sent(T.STOP_REVISING)
    c.close_stale_revising()
    for uid in {c.m.get("request_user_id")} | {u for u in working if u in waited}:
        c.add(uid, T.NOTICE_FIX_REJECTED, T.fix_rejected(c.scene(keys.values()), reason=str(c.m.get("reason") or "")))


def _workers_stop(ntype: str, text: Callable[[_Case, Iterable[int]], tuple[str, str]], *, picked: bool = False) -> Callable[[_Case], None]:
    def run(c: _Case) -> None:
        for uid, nums in people(c.marks, c.material_keys() if picked else c.numbers, done=False).items():
            c.add(uid, ntype, text(c, nums), numbers=nums)
    return run


def _hold_released(c: _Case) -> None:
    pending = c.sent(T.STOP_HOLD, open_only=True)
    for rows in pending.values():
        c.close(rows)
    for uid in set(c.sent(T.STOP_HOLD)) | set(pending):  # 보류 멈춤이 나갔던 사람(24시간 안) + 안 누른 채 닫히는 사람
        c.add(uid, T.NOTICE_HOLD_RELEASED, T.hold_released(c.scene()))


def _date_changed(c: _Case) -> None:
    today = c.reads.today
    near = any(0 <= (day - today).days <= DATE_NEAR_DAYS for day, _kind in order_ship_dates(c.order))
    if read_main_stage(c.order) != STAGE_PRODUCTION or not near or T.pulled_forward(c.m.get("detail"), today) is False:
        return
    left = [part for part, done in step_done_map(c.sd).items() if not done]
    for uid in c.lead_ids(present_factories(c.sd)):
        c.add(uid, T.NOTICE_DATE, T.date_changed(c.scene(), detail=str(c.m.get("detail") or ""), left_parts=left))


def _defect(c: _Case) -> None:
    for uid in c.lead_ids(c.factories()):
        c.add(uid, T.NOTICE_DEFECT, T.defect(c.scene(), label=str(c.m.get("label") or "")))


def _rework(c: _Case) -> None:
    sheets = len({k for k in c.m.get("drawing_keys") or [] if k})
    for uid in c.lead_ids(c.factories()):
        c.add(uid, T.NOTICE_REWORK, T.rework(c.scene(), sheets=sheets, steps=c.m.get("steps") or ()))


_RULES: dict[str, Callable[[_Case], None]] = {
    "given": _given,
    "taken": _taken,
    "start_cancelled": _mark_notice(T.NOTICE_START_CANCELLED, T.start_cancelled),
    "done_cancelled": _mark_notice(T.NOTICE_DONE_CANCELLED, T.done_cancelled),
    "drawing_replaced": _drawing_replaced,
    "drawing_revising": _drawing_revising,
    "fix_stopped": _fix_stopped,
    "fix_rejected": _fix_rejected,
    "hold": _workers_stop(T.STOP_HOLD, lambda c, _n: T.stop_hold(c.scene(), reason=str(c.m.get("reason") or ""))),
    "hold_released": _hold_released,
    "cancelled": _workers_stop(T.STOP_CANCELLED, lambda c, _n: T.stop_cancelled(c.scene())),
    "item_cancelled": _workers_stop(T.STOP_CANCELLED, lambda c, _n: T.stop_cancelled(c.scene(), item=True)),
    "factory_moved": _workers_stop(
        T.STOP_FACTORY, lambda c, nums: T.stop_factory(c.scene(nums), factory=c.m.get("to_factory")), picked=True),
    "date_changed": _date_changed,
    "defect": _defect,
    "rework": _rework,
}
KINDS: tuple[str, ...] = tuple(_RULES)


def plan(reads: Reads, note: dict[str, Any]) -> Plan:
    """적어 둔 사건 하나 → 만들 알람 · 닫을 알람. 주문이 없거나 ERP 주문이 아니면 빈 것."""
    rule = _RULES.get(str(note.get("kind") or ""))
    order = reads.order(int(note["order_id"])) if rule is not None else None
    if order is None or not getattr(order, "is_erp_order", False):
        return Plan()
    case = _Case(reads, note, order)
    rule(case)
    return case.finish()


__all__ = ["DATE_NEAR_DAYS", "KINDS", "MERGE_SECONDS", "Alarm", "Plan", "Reads", "actor_factory", "can_receive", "plan"]
