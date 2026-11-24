"""2공장 생산 쪽 시험 준비물(설계서 2026-11-23 §4-13 · §4-14, 3단계 ⑤ ⑥) — 공장 계정 · 섞인 주문 · 공장 완료 표지.

이름은 모두 지어낸 값이다. 주문은 :func:`tests.support.production_part_claim_seed.make_order` 그대로(시트 신원 있음)에 장의 공장
``drawing_factory.sheets`` 를 더한다(공장 지정 API 가 쓰는 꼴과 같다). 시공일은 비어 있어 첫 화면 '시공일 없음' 장(``day=none``)에 선다.
"""
from __future__ import annotations

import copy
from typing import Any, Iterable, Optional

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Order, ProductionPartMark, User
from tests.support.production_part_claim_seed import Person, Seed, make_order, make_user

TABLET = {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}
PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
HOME_NONE = "/erp/production/home?day=none"


def factory_user(name: str, *, factory: int = 1, part: Optional[str] = None, lead: Optional[bool] = None,
                 role: str = "STAFF", team: Optional[str] = "PRODUCTION") -> Person:
    """공장 계정 하나 — 2공장이면 ``users.production_factory = 2``(1공장은 비움 = 지금과 같다)."""
    person = make_user(name, team=team, role=role, part=part, lead=lead)
    if factory == 2:
        user = db_session.get(User, person.id)
        user.production_factory = 2
        db_session.commit()
    return person


def mixed_order(n: int = 5, *, f2: Iterable[int] = (3, 4), steps_done: tuple[str, ...] = (), run: bool = True,
                extra: Optional[dict[str, Any]] = None) -> Seed:
    """섞인 주문 — 장 ``f2`` 번째(0부터)가 2공장, 나머지 1공장. ``f2`` 가 비면 한 공장 주문."""
    seed = make_order(n, steps_done=steps_done, run=run, extra=extra)
    f2 = tuple(f2)
    if f2:
        order = db_session.get(Order, seed.id)
        sd = copy.deepcopy(order.structured_data)
        sd["drawing_factory"] = {"sheets": {sd["drawing_current_files"][j]["sheet_id"]: 2 for j in f2}, "files": {},
                                 "at": "2026-11-24T00:00:00+00:00", "by_name": "오가람"}
        order.structured_data = sd
        flag_modified(order, "structured_data")
        db_session.commit()
    return seed


def set_factory_done(oid: int, factory: int, keys: Iterable[str], by_name: str = "강검수") -> None:
    """공장 완료 표지를 직접 심는다(``production.factory_done`` — 공장 완료 API 가 쓰는 꼴)."""
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    done = dict((sd.get("production") or {}).get("factory_done") or {})
    done[str(factory)] = {"keys": list(keys), "at": "2026-11-24T07:10:00+00:00", "by_name": by_name, "by_user_id": None}
    sd.setdefault("production", {})["factory_done"] = done
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def put_mark(seed: Seed, j: int, part: str, state: str, who: Person) -> None:
    """표시 줄 하나를 직접 심는다(맡음 · 완료 · 기본)."""
    finished = state in ("DONE", "BASIC")
    db_session.add(ProductionPartMark(
        order_id=seed.id, drawing_key=seed.keys[j], part=part, state=state,
        picked_by_user_id=None if state == "BASIC" else who.id, picked_by_name=None if state == "BASIC" else who.name,
        done_by_user_id=who.id if finished else None, done_by_name=who.name if finished else None,
        updated_by_user_id=who.id))
    db_session.commit()


def set_cookies(client, cookies: dict[str, str]) -> None:
    for key in ("foms_ptr", "foms_vw", "foms_scr"):
        client.delete_cookie(key, domain="localhost")
    for key, value in cookies.items():
        client.set_cookie(key, value, domain="localhost")
