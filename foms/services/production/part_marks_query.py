"""생산 파트 표시 줄 · 생산 회차 읽기 — 완료 판정 · 공정 API · 작업 시트 · 카드 쓰기가 같이 쓰는 쿼리 한 곳.

표시 줄 읽기는 모두 유일 제약 ``uq_production_part_marks_order_key_part``(앞머리 ``order_id``)를 탄다. 주문이 여럿이면
``order_id IN (…)`` 한 번(주문 수와 무관 — N+1 없음). 판정 자체는 :mod:`foms.services.production.part_progress`(쿼리 0)다.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import object_session

from models import ProductionPartMark, ProductionRun


def order_marks(db: Any, order_id: int) -> list[ProductionPartMark]:
    """한 주문의 표시 줄 전부(네 파트 · 옛 판 key 포함) — 쿼리 1.

    Args:
        db: 세션.
        order_id: 주문 id.

    Returns:
        ``ProductionPartMark`` 줄 목록.
    """
    return db.query(ProductionPartMark).filter(ProductionPartMark.order_id == int(order_id)).all()


def attached_order_marks(order: Any) -> list[ProductionPartMark]:
    """주문이 붙은 세션으로 그 주문 표시 줄을 읽는다 — 세션을 따로 받지 않는 판정 함수(일반 단계 쓰기 문지기)용.

    아직 저장 안 된 주문(``id`` 없음)은 줄이 있을 수 없어 빈 목록이다.

    Raises:
        RuntimeError: 저장된 주문인데 세션에서 떨어져 표시 줄을 못 읽을 때(카드 판정을 조용히 건너뛰지 않는다).
    """
    if getattr(order, "id", None) is None:
        return []
    session = object_session(order)
    if session is None:
        raise RuntimeError(f"order {order.id} is detached — cannot read production part marks")
    return order_marks(session, order.id)


def marks_by_order(db: Any, order_ids: Iterable[int]) -> dict[int, list[ProductionPartMark]]:
    """주문들의 표시 줄 — 주문 → 줄 목록. 쿼리 1(주문이 없으면 0). 표시 줄이 없는 주문은 빈 목록.

    Args:
        db: 세션.
        order_ids: 주문 id 들.

    Returns:
        ``{order_id: [줄…]}`` — 넘긴 id 모두가 열쇠로 있다.
    """
    ids = sorted({int(i) for i in order_ids})
    out: dict[int, list[ProductionPartMark]] = {i: [] for i in ids}
    if not ids:
        return out
    for row in db.query(ProductionPartMark).filter(ProductionPartMark.order_id.in_(ids)).all():
        out.setdefault(int(row.order_id), []).append(row)
    return out


def orders_with_current_run(db: Any, order_ids: Iterable[int]) -> set[int]:
    """그중 지금 생산 회차(``is_current``)가 있는 주문 id — 쿼리 1(주문이 없으면 0).

    회차가 없는 생산 단계 주문 = 제작대기(첫 카드를 맡으면 제작이 저절로 시작된다, §4-8).
    """
    ids = sorted({int(i) for i in order_ids})
    if not ids:
        return set()
    rows = (db.query(ProductionRun.order_id)
            .filter(ProductionRun.order_id.in_(ids), ProductionRun.is_current.is_(True)).all())
    return {int(order_id) for (order_id,) in rows}


def my_old_claims(db: Any, user_id: int, part: str, order_ids: Iterable[int], before: Any) -> list[ProductionPartMark]:
    """밤 넘긴 내 담당(아침 칩, 설계서 2026-11-23 §4-9) — 그 주문들에서 내가 맡은 NEED 줄 중 맡은 때가 ``before`` 전. 쿼리 1.

    Args:
        db: 세션.
        user_id: 나.
        part: 내 파트.
        order_ids: 첫 화면 생산 주문 id 들(없으면 쿼리 0).
        before: 오늘 KST 0시(UTC naive).

    Returns:
        ``ProductionPartMark`` 줄 목록(지금 장인지는 부르는 쪽이 거른다).
    """
    ids = sorted({int(i) for i in order_ids})
    if not ids:
        return []
    return (db.query(ProductionPartMark)
            .filter(ProductionPartMark.order_id.in_(ids), ProductionPartMark.part == part,
                    ProductionPartMark.state == "NEED", ProductionPartMark.picked_by_user_id == int(user_id),
                    ProductionPartMark.picked_at < before)
            .all())
