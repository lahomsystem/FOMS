"""담당 바꾸기에서 받을 수 있는 사람 — 판정 한 곳 · 한 사람 읽기 · 고르기 창 목록(설계서 2026-11-28 흐름 셋 §1-2 · §1-3 · §1-5).

반장 · 관리자가 남이 작업 중인 도면을 다른 사람에게 줄 때(``POST /api/production/part-marks`` 의 ``takeover`` + ``to_user_id``)
쓰기(:mod:`~foms.services.production.part_mark_write`)와 고르기 창 목록(``GET …/part-marks/receivers``)이 같은 판정을 본다 — 목록에
있는데 서버가 막거나, 목록에 없는데 서버가 받지 않게.

* **받을 수 있는 사람** = 그 도면을 지금 [<파트> 시작]할 수 있는 파트 계정: 켜진 계정 · 협력사 아님 · 보기 전용(VIEWER) 아님 · 계정
  파트 목록에 그 파트가 있음(반장이 그 파트도 가졌으면 든다) · 그 도면의 공장 계정. 판정은 :mod:`part_access` 의 함수만 쓴다
  (역할 · 팀을 여기서 따로 견주지 않는다). 누른 사람 '나'는 이 판정과 따로 늘 받을 수 있다(쓰기의 지금 길 — 파트 문 · 공장 문).
* **쿼리**: 한 사람 읽기 = 1(남에게 줄 때만 — 주문 잠금 아래에서 한 번 읽은 값으로 판정한다, 사용자 행은 잠그지 않는다). 목록 = 2
  (주문 ⟕ 그 도면 · 그 파트 표시 줄 한 번 + 켜진 직원 한 번 — 팀 별칭 때문에 파이썬에서 거른다).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import and_

from foms.services.production import mark_crew as mc
from foms.services.production.part_access import can_write_sheet, part_account_parts
from foms.services.production.part_mark_notes import actor_name
from models import Order, ProductionPartMark, User

#: 사람 없는 줄의 바뀔 줄 앞쪽 낱말("담당 미정 → 담당 오재단").
NO_HOLDER_WORD = "미정"


def can_receive(user: Any, part: str, factory: Any) -> bool:
    """이 사람이 그 파트 · 그 공장 도면을 넘겨받을 수 있는지(쿼리 0 — 이미 읽은 행).

    Args:
        user: 받는 사람 행(없는 계정이면 None).
        part: 파트 key.
        factory: 그 도면의 공장(1 · 2 · None = 1공장).

    Returns:
        켜진 파트 계정이고 그 파트를 가졌고 그 공장 도면을 쓸 수 있으면 True.
    """
    return user is not None and part in part_account_parts(user) and can_write_sheet(user, factory)


def receiver(db: Any, uid: Any) -> Optional[User]:
    """받는 사람 한 줄(쿼리 1 — 없는 계정이면 None). 세션에 이미 든 행이어도 다시 읽는다(그사이 꺼진 계정을 놓치지 않게)."""
    return db.query(User).filter(User.id == uid).populate_existing().one_or_none()


def order_and_mark(db: Any, order_id: int, key: str, part: str) -> tuple[Optional[Order], Optional[ProductionPartMark]]:
    """주문 한 줄 + 그 도면 · 그 파트 표시 줄(없으면 None) — 쿼리 1(읽기 전용 · 잠금 없음)."""
    hit = (db.query(Order, ProductionPartMark)
           .outerjoin(ProductionPartMark, and_(ProductionPartMark.order_id == Order.id,
                                               ProductionPartMark.drawing_key == key, ProductionPartMark.part == part))
           .filter(Order.id == order_id).first())
    return (hit[0], hit[1]) if hit is not None else (None, None)


def _seat(crew: list[dict[str, Any]], seat_uid: Any) -> Optional[dict[str, Any]]:
    """자리를 내줄 사람 — 고른 사람, 안 골랐으면 아직 작업 중인 사람이 하나일 때만(쓰기 판정 ``_pick_target`` 과 같은 규칙)."""
    if seat_uid is not None:
        return mc.find(crew, seat_uid)
    if len(crew) == 1:
        return crew[0]
    pending = [m for m in crew if not mc.is_done(m)]
    return pending[0] if len(pending) == 1 else None


def swap_line(crew: list[dict[str, Any]], seat_uid: Any, name: str) -> str:
    """고르기 창의 바뀔 줄 "담당 김재단 · 오재단 → 담당 박반장 · 오재단"(이름 줄은 둘까지 + "외 n" — :func:`~mark_crew.name_line`)."""
    seat = _seat(crew, seat_uid)
    after = [name if m is seat else m.get("name") for m in crew] if seat is not None else [name]
    before = mc.name_line(mc.names(crew)) or NO_HOLDER_WORD
    return f"담당 {before} → 담당 {mc.name_line(str(n or '') for n in after)}"


def list_people(db: Any, viewer: Any, part: str, factory: Any, row: Any, seat_uid: Any = None) -> list[dict[str, Any]]:
    """고르기 창 "누구에게 줄까요?"의 사람들 — 맨 앞 '나', 그다음 이름 순(쿼리 1).

    Args:
        db: 세션.
        viewer: 누른 사람(반장 · 관리자 — 문은 부르는 쪽이 본다).
        part: 파트 key.
        factory: 그 도면의 공장.
        row: 그 도면 · 그 파트 표시 줄(없으면 None) — 이미 작업 중이거나 자기 몫을 완료한 사람은 뺀다.
        seat_uid: 자리를 내줄 사람(여럿이 같이 작업 중일 때 고른 사람 — 바뀔 줄 글에만 쓴다).

    Returns:
        ``[{user_id, name, me, line}]`` — ``name`` = 단추 글(같은 이름이 둘이면 "김재단 (kim2)"), ``line`` = 고르면 보일 바뀔 줄.
    """
    crew = mc.crew_of(row)
    inside = {m.get("uid") for m in crew}
    me = getattr(viewer, "id", None)
    staff = db.query(User).filter(User.is_active.is_(True), User.partner_org_id.is_(None)).all()
    others = sorted((u for u in staff if u.id != me and u.id not in inside and can_receive(u, part, factory)),
                    key=lambda u: (actor_name(u) or "", u.id))
    names = [actor_name(u) or "" for u in others]
    mine = actor_name(viewer) or ""
    people = [] if me in inside else [{"user_id": me, "name": mine, "me": True, "line": swap_line(crew, seat_uid, mine)}]
    for user, name in zip(others, names):
        label = f"{name} ({user.username})" if names.count(name) > 1 else name
        people.append({"user_id": user.id, "name": label, "me": False, "line": swap_line(crew, seat_uid, name)})
    return people


__all__ = ["NO_HOLDER_WORD", "can_receive", "list_people", "order_and_mark", "receiver", "swap_line"]
