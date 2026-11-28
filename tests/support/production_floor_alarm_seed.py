"""생산 현장 알람 시험 준비물(설계서 2026-11-28 생산 현장 알람 §7) — 스위치 · 넣어 주는 시각 · 실시간/폰 가로채기 · 약속 1 · 2 모양.

이름은 모두 지어낸 값이다. 주문 · 계정 · 카드 누름은 ``production_part_claim_seed`` 그대로(진짜 표시 줄이 생긴다). 시각은 늘 넣어 준다
(:func:`switch_on` 이 알람 모듈의 시계를 바꾼다) — 벽시계에 기대는 시험을 만들지 않는다.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import event

from db import db_session, engine
from foms.services.production import floor_alarm
from foms.services.production.floor_alarm_text import LIKE_ESCAPE, LIKE_PATTERN, PREFIX
from models import Notification, NotificationUserState, Order
from tests.support.production_part_claim_seed import Person, Seed, make_order

SWITCH = "FOMS_PRODUCTION_FLOOR_ALARM"
#: 넣어 주는 시각 — UTC naive 2026-11-28 03:00 = 한국 시각 낮 12시, 오늘 = 11-28(토).
NOW = datetime.datetime(2026, 11, 28, 3, 0, 0)
TODAY = datetime.date(2026, 11, 28)


@dataclass
class Wire:
    """가로챈 배달 — 실시간 ``(받는 사람들, 값)`` · 폰 알림 줄 번호 · 종 숫자 캐시 비운 사람."""

    sent: list[tuple[list[int], dict[str, Any]]] = field(default_factory=list)
    pushed: list[int] = field(default_factory=list)
    badges: list[int] = field(default_factory=list)

    def to(self, uid: int) -> list[dict[str, Any]]:
        return [body for uids, body in self.sent if uid in uids]


def switch_on(monkeypatch, *, now: datetime.datetime = NOW, today: datetime.date = TODAY) -> dict[str, Any]:
    """스위치를 켜고 알람 모듈의 시계를 넣어 준다. 돌려준 dict 의 ``now`` 를 바꾸면 시각이 간다."""
    clock = {"now": now, "today": today}
    monkeypatch.setenv(SWITCH, "on")
    monkeypatch.setattr(floor_alarm, "_clock", lambda: (clock["now"], clock["today"]))
    return clock


def capture(monkeypatch) -> Wire:
    """실시간 · 폰 알림 · 종 숫자 캐시 비우기를 가로챈다(소켓 · 큐 없이 무엇이 나갔는지 본다)."""
    wire = Wire()
    monkeypatch.setattr(floor_alarm, "emit_erp_notification_to_users",
                        lambda uids, body=None: wire.sent.append((list(uids), dict(body or {}))) or len(list(uids)))
    monkeypatch.setattr(floor_alarm, "enqueue_push_for_notification",
                        lambda nid, db=None: wire.pushed.append(int(nid)) or {"enqueued": True})
    monkeypatch.setattr(floor_alarm, "_badge_hook", lambda uids: wire.badges.extend(int(u) for u in uids))
    return wire


def alarm_order(n: int = 2, *, customer: str = "정하늘", build: Optional[str] = "2026-11-30", **kw: Any) -> Seed:
    """생산 단계 가짜 주문 — 고객 이름 · 시공일(글의 "11/30 시공")을 넣는다. 납작 열 ``erp_construction_date`` 도 같이."""
    extra = {"parties": {"customer": {"name": customer}}, **(kw.pop("extra", None) or {})}
    if build:
        extra["schedule"] = {"construction": {"date": build}}
    seed = make_order(n, extra=extra, **kw)
    order = db_session.get(Order, seed.id)
    order.customer_name, order.erp_construction_date = customer, build
    db_session.commit()
    return seed


def alarms(uid: Optional[int] = None, *, order_id: Optional[int] = None) -> list[Notification]:
    """만들어진 생산 알람 줄(번호 순) — ``uid`` 를 주면 그 사람 것만."""
    db_session.expire_all()
    query = db_session.query(Notification).filter(Notification.notification_type.like(LIKE_PATTERN, escape=LIKE_ESCAPE))
    if uid is not None:
        query = query.filter(Notification.target_user_id == uid)
    if order_id is not None:
        query = query.filter(Notification.order_id == order_id)
    return query.order_by(Notification.id).all()


def kinds(uid: Optional[int] = None) -> list[str]:
    """알람 종류 이름에서 앞머리를 뗀 것(번호 순) — ``['NEW_GIVEN', 'STOP_TAKEN']``."""
    return [n.notification_type[len(PREFIX):] for n in alarms(uid)]


def state_of(notification_id: int) -> NotificationUserState:
    db_session.expire_all()
    return db_session.query(NotificationUserState).filter_by(notification_id=notification_id).one()


def ack(notification_id: int, at: datetime.datetime = NOW) -> None:
    """[확인]을 누른 것으로 만든다(확인 기록 API 가 쓰는 칸)."""
    state_of(notification_id).ack_at = at
    db_session.commit()


def press(order: Seed, j: int, part: str, action: str) -> SimpleNamespace:
    """표시 쓰기 요청 모양(``MarkRequest`` 가 싣는 칸)."""
    return SimpleNamespace(order_id=order.id, key=order.keys[j], part=part, action=action)


def who(person: Optional[Person], *, done: Optional[bool] = None) -> Optional[dict[str, Any]]:
    """약속 1 · 2 의 사람 한 칸 ``{user_id, name}``(+ ``done``)."""
    if person is None:
        return None
    return {"user_id": person.id, "name": person.name, **({} if done is None else {"done": done})}


def gave(order: Seed, j: int, part: str, *, by: Person, src: Optional[Person], to: Person) -> dict[str, Any]:
    """담당 바꾸기 쓰기 결과 모양(약속 1 ``gave`` — ``self`` = 누른 사람이 받음)."""
    return {"changed": True, "mark": {"holders": [who(to, done=False)]},
            "gave": {"order_id": order.id, "drawing_key": order.keys[j], "part": part, "by": who(by), "from": who(src),
                     "to": who(to), "self": by.id == to.id}}


def give(order: Seed, j: int, part: str, *, by: Person, src: Optional[Person], to: Person) -> None:
    """담당 바꾸기 한 번 — 커밋 전 적기 → 커밋 → 보내기(ⓑ 가 표시 쓰기 API 에 거는 두 줄과 같은 차례)."""
    floor_alarm.note_mark(db_session, by, press(order, j, part, "takeover"), gave(order, j, part, by=by, src=src, to=to))
    db_session.commit()
    floor_alarm.flush(db_session)


def fire(kind: str, order: Seed, actor: Any, **material: Any) -> None:
    """그 밖 사건 한 번 — 적기 → 커밋 → 보내기."""
    floor_alarm.note(db_session, kind, order.id, actor, **material)
    db_session.commit()
    floor_alarm.flush(db_session)


def count_queries(fn: Any) -> tuple[Any, list[str]]:
    """``fn`` 을 돌리며 나간 SQL 글 목록."""
    seen: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        return fn(), seen
    finally:
        event.remove(engine, "before_cursor_execute", _before)
