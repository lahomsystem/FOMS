"""FCOMM-01 3단계 겹 2: 프리랜서 주문 단위 판정 — "이 주문이 내 주문인가".

설계서 §6.1: "내 주문" = ``order_freelancer_links`` 에 (주문, 나) 줄이 있다(관계는 무엇이든 — 대표 담당 ·
다른 담당 · 발주사 · 직접 등록). 이것 하나만 쓴다 — 퀘스트 담당 이름 · 시공자 이름 · ``sales_assignee_user_ids``
같은 다른 이름 판정은 프리랜서에게 쓰지 않는다(검수 원장 A9).

예외 하나: **내가 만든 아직 초안인 주문**. ERP 새 주문 화면은 초안 주문 행을 먼저 만들고(``status='DRAFT'``)
그 번호로 자동 저장 · 첨부 올리기 · 등록(structured PUT)을 한다. 연결 훅이 초안을 만들 때 ``CREATOR`` 줄을
붙이지만, 훅은 실패해도 저장을 막지 않으므로(``link_hook._before_flush``) 그 줄이 없을 수 있다 — 그러면
본인이 쓰던 초안이 등록 도중 404 가 된다. 그래서 초안을 만든 기록(``ORDER_DRAFT_CREATED`` 이벤트의 작성자)이
나이고 그 주문이 아직 초안이면 본인 것으로 본다. 등록(승격)된 뒤에는 연결 표만 본다.

마법사 초안 표(``order_drafts.user_id``)는 근거로 쓰지 **않는다** — 그 표의 ``order_id`` 는 클라이언트가 PUT
본문으로 넣는 값이라(:mod:`foms.api.erp_order_draft`), 근거로 삼으면 남의 주문 번호를 적어 넣는 것만으로 그
주문이 열린다. 세션의 ``erp_draft_order_id`` 도 쓰지 않는다(브라우저 토큰으로 남의 초안에 묶일 수 있다).

판정은 쿼리 한 번(``EXISTS`` 두 개를 ``OR``)이고, 요청 안에서는 ``g`` 에 (사람, 주문) → 결과를 둔다. 문지기 ·
파일 관문 · 핸들러가 같은 요청에서 같은 주문을 여러 번 물어도 쿼리는 한 번이다. 요청이 끝나면 버려지므로 담당에서
빠지면 **다음 요청부터** 안 보인다.

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.1 · §6.3 겹 2 · §6.5
시험: tests/security/test_freelancer_order_scope.py
"""
from __future__ import annotations

from typing import Any, Optional

from flask import g, has_request_context
from sqlalchemy import exists, or_, select

from db import db_session
from models import Order, OrderEvent, OrderFreelancerLink

#: 초안 주문을 처음 만든 기록(``foms.api.erp_orders_structured.ORDER_DRAFT_CREATED_EVENT`` 와 같은 값).
DRAFT_CREATED_EVENT = "ORDER_DRAFT_CREATED"
#: 아직 등록 전인 초안 주문의 ``status``.
DRAFT_STATUS = "DRAFT"
#: 요청 안 캐시 ``{(user_id, order_id): bool}``.
_G_CACHE_ATTR = "_fcomm_order_access"


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _request_cache() -> Optional[dict[tuple[int, int], bool]]:
    """요청 안이면 캐시 dict, 밖(워커 · 스크립트)이면 None — 앱 문맥만 있는 긴 작업에 낡은 답을 남기지 않는다."""
    if not has_request_context():
        return None
    cache = getattr(g, _G_CACHE_ATTR, None)
    if cache is None:
        cache = {}
        setattr(g, _G_CACHE_ATTR, cache)
    return cache


def _access_query(db: Any, user_id: int, order_id: int) -> bool:
    """연결 줄 또는 "내가 만든 초안" 이 있는가(쿼리 1번, 둘 다 order_id 인덱스를 탄다)."""
    linked = exists().where(
        OrderFreelancerLink.order_id == order_id,
        OrderFreelancerLink.user_id == user_id,
    )
    own_draft = exists(
        select(OrderEvent.id)
        .join(Order, Order.id == OrderEvent.order_id)
        .where(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == DRAFT_CREATED_EVENT,
            OrderEvent.created_by_user_id == user_id,
            Order.status == DRAFT_STATUS,
        )
    )
    return bool(db.query(or_(linked, own_draft)).scalar())


def freelancer_can_access_order(db: Any, user: Any, order_id: Any) -> bool:
    """프리랜서 ``user`` 가 주문 ``order_id`` 를 볼 수 있는가(연결 줄 또는 내가 만든 초안).

    프리랜서인지는 부르는 쪽이 이미 판정했다고 본다(문지기 · ``user_can_read_order``). 없는 주문 번호도
    거짓이다 — 남의 주문과 같은 답이라 존재 여부가 새지 않는다.

    Args:
        db: SQLAlchemy 세션.
        user: 판정할 계정(``id`` 를 읽는다). None 이면 거짓.
        order_id: 주문 번호(정수로 바꿀 수 없으면 거짓).

    Returns:
        볼 수 있으면 True.
    """
    uid = _int_or_none(getattr(user, "id", None)) if user is not None else None
    oid = _int_or_none(order_id)
    if uid is None or oid is None or oid <= 0:
        return False
    cache = _request_cache()
    key = (uid, oid)
    if cache is not None and key in cache:
        return cache[key]
    allowed = _access_query(db, uid, oid)
    if cache is not None:
        cache[key] = allowed
    return allowed


def freelancer_can_read_order(user: Any, order: Any) -> bool:
    """``user_can_read_order`` 의 프리랜서 분기 — 주문 객체로 판정한다(없거나 id 가 없으면 거짓)."""
    if order is None:
        return False
    return freelancer_can_access_order(db_session, user, getattr(order, "id", None))


__all__ = [
    "DRAFT_CREATED_EVENT",
    "DRAFT_STATUS",
    "freelancer_can_access_order",
    "freelancer_can_read_order",
]
