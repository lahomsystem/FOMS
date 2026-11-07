"""FCOMM-01 3단계 겹 3: 프리랜서 목록 강제 거르기 — "내 주문" = 연결 표 하나.

켜진 프리랜서(:func:`is_list_freelancer`)에게 "내 주문"은 ``order_freelancer_links`` 에 (주문, 나) 줄이
있는 주문**뿐**이다(설계서 §6.1). 직원의 "내 담당" 판정(담당 이름 · 퀘스트 담당 이름 · 시공자 이름 ·
``sales_assignee_user_ids`` · 도면 담당 id)은 프리랜서에게 쓰지 않는다 — 이름이 같은 남의 주문이 끼고,
담당에서 빠진 뒤에도 보이기 때문이다(검수 원장 A9).

부르는 곳은 두 군데뿐이다. 화면마다 따로 부르지 않는다.

- :func:`foms.services.erp_permissions.build_mine_sql_filter` → :func:`freelancer_mine_sql_filter`
- :func:`foms.services.erp_permissions.is_order_related_to_user` → :func:`freelancer_order_related`

목록이 "내 것만"을 끌 수 없게 하는 강제 켜짐은 :mod:`foms.services.common.erp_mine_filter` 가 한다
(시공팀 선례와 같은 자리). 직접 만든 주문(초안 포함)은 연결 표의 ``CREATOR`` 줄이 덮는다.

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.1 · §6.3 겹 3
시험: tests/security/test_freelancer_lists.py
"""
from __future__ import annotations

from typing import Any, Optional

from flask import g, has_app_context, has_request_context
from sqlalchemy import select

from db import db_session, get_db
from foms.services.auth.freelancer_scope import could_be_freelancer
from foms.services.sales_commission.settings import is_freelancer
from models import Order, OrderFreelancerLink

#: 요청 안에서 한 번만 읽는 "내 주문 번호" 묶음(``{user_id: frozenset}``). 요청이 끝나면 버려진다.
_G_IDS_ATTR = "_fcomm_list_order_ids"


def _session() -> Any:
    """앱 문맥이면 요청 세션, 밖이면 전역 세션(스크립트 · 시험 직접 호출)."""
    return get_db() if has_app_context() else db_session


def _int_id(obj: Any) -> Optional[int]:
    try:
        return int(getattr(obj, "id", None))
    except (TypeError, ValueError):
        return None


def is_list_freelancer(user: Any) -> bool:
    """켜진 프리랜서인지 — 직원 · 영업팀 계정이 아니면 설정을 읽지 않는다(요청 안에서는 한 번만 읽는다)."""
    if not could_be_freelancer(user):
        return False
    return is_freelancer(_session(), user)


def current_user_is_list_freelancer() -> bool:
    """지금 요청의 로그인 사용자가 켜진 프리랜서인지. 요청 밖이면 False."""
    if not has_request_context():
        return False
    return is_list_freelancer(getattr(g, "current_user", None))


def freelancer_mine_sql_filter(user: Any) -> list[Any]:
    """프리랜서의 "내 주문" SQL 조건 목록(``build_mine_sql_filter`` 와 같은 꼴 — OR 로 묶을 조건 목록).

    조건은 하나다: ``orders.id IN (SELECT order_id FROM order_freelancer_links WHERE user_id = 나)``.
    EXISTS 와 같은 집합이고, 바깥 주문 표를 참조하지 않아 ``mine_membership_clause`` 가 별칭으로 옮겨도
    그대로 맞는다.
    """
    uid = _int_id(user)
    linked = select(OrderFreelancerLink.order_id).where(OrderFreelancerLink.user_id == (uid if uid is not None else -1))
    return [Order.id.in_(linked)]


def freelancer_order_ids(user: Any) -> frozenset[int]:
    """연결 표의 내 주문 번호(쿼리 1번 — 요청 안에서는 사용자마다 한 번만 읽는다).

    캐시는 요청 안에서만 둔다(앱 문맥만 있는 긴 작업에 낡은 답을 남기지 않는다). 그래서 담당에서 빠지면
    다음 요청부터 안 보인다. 목록 화면 루프(실측 요약 API 등)가 주문마다 물어도 쿼리는 한 번이다.
    """
    uid = _int_id(user)
    if uid is None:
        return frozenset()
    cache: Optional[dict[int, frozenset[int]]] = None
    if has_request_context():
        cache = getattr(g, _G_IDS_ATTR, None)
        if cache is None:
            cache = {}
            setattr(g, _G_IDS_ATTR, cache)
        if uid in cache:
            return cache[uid]
    rows = _session().query(OrderFreelancerLink.order_id).filter(OrderFreelancerLink.user_id == uid).all()
    ids = frozenset(int(row[0]) for row in rows if row[0] is not None)
    if cache is not None:
        cache[uid] = ids
    return ids


def freelancer_order_related(user: Any, order: Any) -> bool:
    """주문 하나가 프리랜서의 "내 주문"인지(파이썬 판정 — ``is_order_related_to_user`` 의 프리랜서 갈래)."""
    order_id = _int_id(order)
    return order_id is not None and order_id in freelancer_order_ids(user)


__all__ = [
    "current_user_is_list_freelancer",
    "freelancer_mine_sql_filter",
    "freelancer_order_ids",
    "freelancer_order_related",
    "is_list_freelancer",
]
