"""생산 현장 알람 — 읽기 한 곳 · 받는 사람 문 · 알람 모양(설계서 2026-11-28 생산 현장 알람 §4-3 · §4-5 · §4-10).

* :class:`Reads` = ``flush`` 한 번의 읽기. 주문 · 사람 · 반장 · 표시 줄 · 앞 알람을 **한 번씩만** 읽어 둔다(같은 주문의 사건이 여럿이어도).
* :func:`can_receive` = 받는 사람 문(§4-5 의 2) — 켜진 계정 · 협력사 아님 · 켜진 프리랜서 아님 · 생산 쓰기 사람 가운데 파트 계정 · 반장.
  관리자는 담당을 받았을 때(``admin_ok``)만. 진짜 직원에게 잘못 퍼지지 않게 하는 한 곳이다.
* :func:`people` = **작업 중인 사람**(표시 줄 ``NEED`` 에서 자기 몫 완료가 없는 사람) · 자기 몫을 완료한 사람. 목록은 ``mark_crew.crew_of`` 하나.
* :class:`Alarm` · :class:`Plan` = 만들 알람 · 닫을 알람(규칙 :mod:`.floor_alarm_rules` 이 만들고 :mod:`.floor_alarm` 이 줄로 쓴다).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from foms.services.auth.freelancer_lists import is_list_freelancer
from foms.services.production import floor_alarm_text as T
from foms.services.production import mark_crew as mc
from foms.services.production.factory_constants import account_production_factory
from foms.services.production.part_access import VIEW_ADMIN, VIEW_PART, VIEW_SUB, part_view_mode
from foms.services.production.part_constants import MARK_STATE_NEED
from foms.services.production.part_marks_query import order_marks
from foms.services.production.write_access import can_write_production
from models import Notification, NotificationUserState, Order, User

#: 앞 알람을 읽는 기간(다시 받기와 같은 72시간 — 안 누른 알람을 닫으려면 그만큼 봐야 한다) · "이미 나갔던" 판정 기간 · 합치기 기간.
RECENT_HOURS = 72
SENT_HOURS = 24
MERGE_SECONDS = 60


@dataclass(frozen=True)
class Alarm:
    """만들 알람 하나 — 받는 사람 · 종류 · 글. ``render`` 가 있으면 60초 합치기 대상(번호를 넣어 글을 다시 짓는다)."""

    user_id: int
    ntype: str
    title: str
    message: str
    numbers: tuple[int, ...] = ()
    render: Optional[Callable[[tuple[int, ...]], tuple[str, str]]] = field(default=None, compare=False)


@dataclass
class Plan:
    """사건 하나의 결과 — 만들 알람 · 닫을 알람(``(알림 줄, 받는 사람 상태)``)."""

    alarms: list[Alarm] = field(default_factory=list)
    close: list[tuple[Any, Any]] = field(default_factory=list)


def can_receive(user: Any, *, admin_ok: bool = False) -> bool:
    """받는 사람 문(§4-5 의 2) — 진짜 직원에게 잘못 퍼지지 않게 하는 한 곳. 이미 읽은 사용자 행만 본다(쿼리 0)."""
    if user is None or getattr(user, "is_active", None) is not True or getattr(user, "partner_org_id", None) is not None:
        return False
    if not can_write_production(user) or is_list_freelancer(user):  # 생산 쓰기 사람은 프리랜서 설정을 읽지 않는다(영업팀만 읽는다)
        return False
    mode = part_view_mode(user)
    return mode in (VIEW_PART, VIEW_SUB) or (admin_ok and mode == VIEW_ADMIN)


def actor_factory(actor: Any) -> Optional[int]:
    """누른 사람의 공장 — 생산팀 계정이면 계정 공장, 관리자 · 다른 팀 · 모르는 사람은 None(주문 도면의 공장을 쓴다)."""
    if actor is None or getattr(actor, "role", None) == "ADMIN":
        return None
    return account_production_factory(actor)


class Reads:
    """``flush`` 한 번의 읽기 — 주문 · 사람 · 반장 · 표시 줄 · 앞 알람을 한 번씩만 읽어 둔다."""

    def __init__(self, db: Any, now: datetime.datetime, today: datetime.date) -> None:
        self.db, self.now, self.today = db, now, today
        self._orders: dict[int, Any] = {}
        self._users: dict[int, Any] = {}
        self._marks: dict[int, list[Any]] = {}
        self._recent: dict[int, list[tuple[Any, Any]]] = {}
        self._leads: Optional[list[Any]] = None

    def order(self, order_id: int) -> Any:
        if order_id not in self._orders:
            self._orders[order_id] = self.db.get(Order, order_id)
        return self._orders[order_id]

    def users(self, ids: Iterable[Any]) -> dict[int, Any]:
        """사람 행(없는 번호는 None) — 아직 안 읽은 번호만 한 번에 읽는다."""
        wanted = {int(i) for i in ids if isinstance(i, int) and not isinstance(i, bool)}
        missing = sorted(wanted - set(self._users))
        if missing:
            found = {int(u.id): u for u in self.db.query(User).filter(User.id.in_(missing)).all()}
            self._users.update({uid: found.get(uid) for uid in missing})
        return {uid: self._users[uid] for uid in wanted}

    def leads(self) -> list[Any]:
        """켜진 반장 계정(받는 사람 문을 지난 사람만)."""
        if self._leads is None:
            rows = self.db.query(User).filter(User.production_lead.is_(True), User.is_active.is_(True)).all()
            self._users.update({int(u.id): u for u in rows})
            self._leads = [u for u in rows if can_receive(u)]
        return self._leads

    def marks(self, order_id: int) -> list[Any]:
        if order_id not in self._marks:
            self._marks[order_id] = order_marks(self.db, order_id)
        return self._marks[order_id]

    def recent(self, order_id: int) -> list[tuple[Any, Any]]:
        """그 주문의 생산 알람 ``(알림 줄, 받는 사람 상태)`` — 72시간 안, 오래된 것부터."""
        if order_id not in self._recent:
            since = self.now - datetime.timedelta(hours=RECENT_HOURS)
            self._recent[order_id] = (
                self.db.query(Notification, NotificationUserState)
                .join(NotificationUserState, NotificationUserState.notification_id == Notification.id)
                .filter(Notification.order_id == order_id, Notification.created_at >= since,
                        Notification.notification_type.like(T.LIKE_PATTERN, escape=T.LIKE_ESCAPE))
                .order_by(Notification.id.asc()).all())
        return self._recent[order_id]

    def remember(self, order_id: int, notification: Any, state: Any) -> None:
        """방금 만든 알람을 이미 읽어 둔 앞 알람 목록에 더한다(같은 ``flush`` 의 다음 사건이 합치거나 닫을 수 있게). 아직 안 읽었으면
        그대로 둔다 — 나중에 읽을 때 방금 넣은 줄이 같이 온다."""
        if order_id in self._recent:
            self._recent[order_id].append((notification, state))


def is_open(state: Any) -> bool:
    """안 누르고(``ack_at`` 없음) 보관도 안 된 알람인지."""
    return state.ack_at is None and state.archived_at is None


def people(marks: Iterable[Any], key_numbers: dict[str, Any], *, done: bool, part: Optional[str] = None) -> dict[int, set[int]]:
    """그 도면들의 표시 줄에서 작업 중(``done`` 거짓) · 자기 몫 완료(참)인 사람 → 도면 번호들."""
    out: dict[int, set[int]] = {}
    for row in marks:
        key = getattr(row, "drawing_key", None)
        if key not in key_numbers or (part is not None and row.part != part):
            continue
        if not done and str(getattr(row, "state", "")) != MARK_STATE_NEED:
            continue
        for item in mc.crew_of(row):
            uid = item.get("uid")
            if uid is not None and mc.is_done(item) == done:
                out.setdefault(int(uid), set()).update(n for n in (key_numbers[key],) if n)
    return out
