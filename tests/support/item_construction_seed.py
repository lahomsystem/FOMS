"""제품마다 '시공 끝'(2단계) 문지기 시험의 자료 · 로그인 도우미.

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md``. 자료 셋을 같은 꼴로 만든다.

* ``partial``  — 화장대(11/05)는 '시공 끝', 부엌가구(주문 날짜를 물려받아 11/17)는 남았다(부분 시공 중).
* ``plain``    — 제품 칸 날짜도 '시공 끝'도 없다(나눠 시공 아님 — 대조군).
* ``all_done`` — 두 제품 모두 '시공 끝'(대조군).
"""
from __future__ import annotations

import itertools

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders import item_construction_done as icd
from models import Order, User

UID_A = "aaaaaaaa-0000-4000-8000-0000000000a1"
UID_B = "bbbbbbbb-0000-4000-8000-0000000000b2"
BLOCKED = "11/17 부엌가구 시공이 남아 있어요"
FLAG = "FOMS_ITEM_CONSTRUCTION_DONE_ENABLED"

_seq = itertools.count(1)


def mark(day: str = "2026-11-05") -> dict:
    """방문으로 찍은 '시공 끝' 기록 하나."""
    return {"date": day, "at": f"{day}T17:40:00+09:00", "by_user_id": None, "by_name": "시공팀",
            "source": icd.SOURCE_VISIT, "attempt_id": None}


def seed_sd(stage: str, kind: str) -> dict:
    """``kind``: partial(부분 시공 중) · plain(나눠 시공 아님) · all_done(다 끝남)."""
    items = [{"uid": UID_A, "product_name": "화장대"}, {"uid": UID_B, "product_name": "부엌가구"}]
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": "가짜고객"}},
          "schedule": {"construction": {"date": "2026-11-05, 2026-11-17"}}, "items": items}
    if kind != "plain":
        items[0]["construction_date"] = "2026-11-05"   # 부엌가구는 주문 날짜를 물려받아 11/17 까지
        sd[icd.DONE_KEY] = {UID_A: mark()}
        if kind == "all_done":
            sd[icd.DONE_KEY][UID_B] = mark("2026-11-17")
    return sd


def seed_order(stage: str = "CONSTRUCTION", kind: str = "partial", *, status: str | None = None,
               hold: bool = False, regional: bool = False) -> int:
    """ERP 주문 한 건(``hold=True`` 면 보류 — 상태 쓰기가 엔진 밖 옛 길로 간다, ``regional`` 은 지방 주문)."""
    sd = seed_sd(stage, kind)
    if hold:
        sd["workflow"]["hold"] = {"active": True, "held_at": "2026-11-10T00:00:00", "reason": "시험"}
    order = Order(received_date="2026-11-01", customer_name="가짜고객", phone="010-0000-0000",
                  address="가짜시 가짜로 1", product="가짜장", status=status or stage, is_erp_order=True,
                  erp_stage_code=stage, structured_data=sd, is_regional=regional)
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def seed_user(role: str = "ADMIN", team: str | None = "CS") -> User:
    n = next(_seq)
    user = User(username=f"items_gate_{n}", password=generate_password_hash("pw"), role=role, team=team,
                name=f"가짜관리자{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def login(client, role: str = "ADMIN", team: str | None = "CS") -> User:
    user = seed_user(role, team)
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return user


def saved(order_id: int) -> tuple[str, str, dict]:
    """(상태 글, 단계, '시공 끝' 기록) — 세션을 비우고 다시 읽는다."""
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    sd = order.structured_data or {}
    return order.status, (sd.get("workflow") or {}).get("stage"), sd.get(icd.DONE_KEY) or {}


def flashes(client) -> list[str]:
    with client.session_transaction() as sess:
        return [msg for _cat, msg in sess.get("_flashes", [])]
