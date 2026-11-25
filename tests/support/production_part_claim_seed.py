"""생산 파트 카드 시험 준비물 — 가짜 계정 · 생산 주문 · 카드 누름(설계서 2026-11-23 self-claim P1 시험이 같이 쓴다).

이름은 모두 지어낸 값이다. 주문은 생산 단계 ERP 주문 + 확정 도면 n장(``drawing_current_files``, 시트 신원 있음)이고,
``run=True`` 면 지금 생산 회차(제작 중), ``False`` 면 제작대기(첫 카드가 제작을 시작한다 — §4-8).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from itertools import count
from typing import Any

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import Order, OrderEvent, ProductionPartMark, ProductionRun, User

ONE = "/api/production/part-marks"
BULK = "/api/production/part-marks/basic"
HISTORY = "/api/production/part-history"
_seq = count(1)


@dataclass(frozen=True)
class Person:
    """시드 사용자의 값만(요청 끝에 세션이 닫혀 ORM 객체는 떨어진다)."""

    id: int
    username: str
    role: str
    name: str


def make_user(name: str, *, team: str | None = "PRODUCTION", role: str = "STAFF", part: str | None = None,
              partner_org_id: int | None = None, lead: bool | None = None) -> Person:
    """가짜 계정 하나(파트 계정이면 ``part``, 반장이면 ``lead=True`` — 설계서 2026-11-23 '승인 때 고친 것' 5)."""
    user = User(username=f"sc_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part, partner_org_id=partner_org_id, production_lead=lead)
    db_session.add(user)
    db_session.commit()
    return Person(user.id, user.username, user.role, name)


def login(client, user: Person) -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


@dataclass(frozen=True)
class Seed:
    """시드 주문의 id · 장 key 들."""

    id: int
    keys: tuple[str, ...]


def make_order(n: int = 3, *, steps_done: tuple[str, ...] = (), run: bool = True, by_name: str = "박반장",
               extra: dict[str, Any] | None = None) -> Seed:
    """생산 단계 가짜 주문 — 확정 도면 ``n`` 장 · 공정 칸(``steps_done`` 은 손으로 켠 칸, ``via`` 없는 옛 칸)."""
    prefix = f"c{next(_seq)}"
    files = [{"key": f"{prefix}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"{prefix}-s{j}"} for j in range(n)]
    steps = [{"key": k, "label": k, "done": k in steps_done, "at": None, "by_name": by_name if k in steps_done else None}
             for k in ("cut", "edge", "assemble", "inspect")]
    sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": "가짜고객"}},
          "drawing_current_files": files, "production": {"steps": steps}, **(extra or {})}
    order = Order(received_date=get_today_kst().isoformat(), customer_name="가짜고객", phone="010-0000-0000",
                  address="가짜시", product="가짜장", status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                  structured_data=sd)
    db_session.add(order)
    db_session.commit()
    if run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        db_session.commit()
    return Seed(order.id, tuple(f["key"] for f in files))


def fresh(oid: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, oid)


def patch_sd(oid: int, **production: Any) -> None:
    """주문 ``structured_data.production`` 칸을 고친다(보류 등 — deepcopy → 재대입 → flag_modified)."""
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["production"].update(production)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def step(oid: int, key: str) -> dict:
    return next(s for s in fresh(oid).structured_data["production"]["steps"] if s["key"] == key)


def row(oid: int, key: str, part: str) -> ProductionPartMark | None:
    db_session.expire_all()
    return db_session.query(ProductionPartMark).filter_by(order_id=oid, drawing_key=key, part=part).one_or_none()


def events(oid: int, event_type: str) -> list[OrderEvent]:
    db_session.expire_all()
    return db_session.query(OrderEvent).filter_by(order_id=oid, event_type=event_type).order_by(OrderEvent.id).all()


def current_runs(oid: int) -> int:
    db_session.expire_all()
    return db_session.query(ProductionRun).filter_by(order_id=oid, is_current=True).count()


def mark(client, order: Seed, j: int, part: str, action: str, seen: str, **extra: Any):
    """카드 한 장 누름(``extra`` = ``seen_by`` 등)."""
    body = {"order_id": order.id, "drawing_key": order.keys[j], "part": part, "action": action, "seen": seen, **extra}
    return client.post(ONE, json=body)


def finish(client, order: Seed, j: int, part: str):
    """맡기 → 완료(재단이면 맡기 → 완료 그대로). 두 번째 응답을 돌려준다."""
    assert mark(client, order, j, part, "take", "none").status_code == 200
    return mark(client, order, j, part, "done", "need")


def code(resp) -> str | None:
    return (resp.get_json().get("data") or {}).get("code")


def check_step(client, oid: int, key: str, done: bool):
    return client.post(f"/api/orders/{oid}/production/steps", json={"key": key, "done": done})
