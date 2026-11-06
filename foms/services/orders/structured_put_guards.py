"""structured PUT 이 사용자 · DB 판정으로 되돌리는 칸 두 가지(FCOMM-01 T18 반증 재검수 R1 · R4).

순수 규칙은 :mod:`foms.services.orders.structured_form_projection` 에 있고, 여기에는 "지금 사용자"와 DB 가 있어야
정할 수 있는 판정만 둔다. 둘 다 거부(4xx)가 아니라 **조용히 옛 값으로 두기**다 — 폼은 이 칸을 렌더하지 않거나
페이지를 연 순간의 값을 되실어 보낼 뿐이라, 거부로 만들면 정상 저장까지 막힌다.

* 결제 확인 칸(``payment.*_confirmed`` · ``_at`` · ``_by`` · ``_by_user_id`` · 잔금 수단): 결제 확인 API 만 쓴다.
  예외는 초안의 첫 등록 — 새 주문 화면은 저장 전에 확인을 누르고 첫 등록에 싣는다. 그때도 누가 · 언제는 서버가
  찍고, 결제 확인을 못 하는 사람(문지기가 결제 확인 API 를 막는 켜진 프리랜서)의 값은 받지 않는다.
* AS 기준 일정 링크(``schedule.as_visit.schedule_link``): 지금 사용자가 읽을 수 없는 주문을 가리키게 바꾸면 옛 값으로
  둔다. 그대로 두면 편집 화면 · 모바일 상세의 AS 배너가 그 주문의 고객명 · 시공일(없는 번호면 존재 여부)을 보여 줬다.

스펙: docs/plans/2026-11-06-freelancer-commission-review-ledger.md ④ R1 · R4
시험: tests/security/test_freelancer_redteam_regressions.py
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from sqlalchemy.orm import load_only

from foms.services.auth.freelancer_scope import is_freelancer_request_allowed, is_freelancer_user
from foms.services.orders.as_schedule_link import LINK_PATH, read_link
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.orders.structured_form_projection import lock_payment_confirmation
from models import Order

logger = logging.getLogger(__name__)

#: 결제 확인 API endpoint — 이 endpoint 를 부를 수 있는 사람만 첫 등록에서 결제 확인을 싣는다.
PAYMENT_CONFIRM_ENDPOINT = "erp_orders_structured.api_payment_confirm"


def can_confirm_payment(user: Any) -> bool:
    """결제 확인 API 를 부를 수 있는 사람인가 — 켜진 프리랜서는 문지기 허용 목록을 따른다."""
    if user is None:
        return False
    if is_freelancer_user(user):
        return is_freelancer_request_allowed(PAYMENT_CONFIRM_ENDPOINT, "POST")
    return True


def guard_payment_confirmation(old_sd: dict, structured_data: dict, *, draft: bool, user: Any,
                               actor_name: str, now_iso: str) -> list[str]:
    """결제 확인 칸을 서버 소유로 다룬다(in-place) — 규칙은 ``lock_payment_confirmation``.

    Args:
        old_sd: 저장 전 서버 structured_data.
        structured_data: 저장할 projection 대상 dict.
        draft: 이 저장이 초안의 첫 등록인가.
        user: 지금 사용자.
        actor_name: 첫 등록 때 ``*_confirmed_by`` 에 찍을 이름.
        now_iso: 첫 등록 때 ``*_confirmed_at`` 에 찍을 시각(naive UTC ISO).

    Returns:
        폼 값이 무시된 ``payment.*`` 경로 목록.
    """
    actor: Optional[tuple] = None
    if draft and can_confirm_payment(user):
        actor = (getattr(user, "id", None), actor_name, now_iso)
    return lock_payment_confirmation(old_sd, structured_data, draft=draft, actor=actor)


def _ref_order_id(link: Any) -> Optional[int]:
    ref = link.get("ref_order_id") if isinstance(link, dict) else None
    return ref if isinstance(ref, int) and not isinstance(ref, bool) else None


def can_read_ref_order(db: Any, user: Any, ref_id: Optional[int]) -> bool:
    """기준 주문 ``ref_id`` 를 ``user`` 가 읽을 수 있나(없는 번호는 ``user_can_read_order(user, None)`` 판정)."""
    if ref_id is None:
        return False
    # 판정이 읽는 칸(id · partner_org_id)만 — 기준 주문의 structured_data(JSONB)는 읽지 않는다.
    ref_order = (db.query(Order).options(load_only(Order.id, Order.partner_org_id))
                 .filter(Order.id == ref_id).first())
    return user_can_read_order(user, ref_order)


def guard_schedule_link_ref(db: Any, old_sd: dict, structured_data: dict, user: Any) -> bool:
    """폼이 바꾼 AS 기준 일정 링크가 읽을 수 없는 주문을 가리키면 옛 링크로 되돌린다(in-place).

    링크를 그대로 두거나 지우는 저장은 건드리지 않는다. 링크 정본은 전용 API(``api_as_schedule_link``)다.

    Returns:
        되돌렸으면 True.
    """
    new_link = read_link(structured_data) if isinstance(structured_data, dict) else None
    old_link = read_link(old_sd) if isinstance(old_sd, dict) else None
    if new_link is None or new_link == old_link:
        return False
    ref_id = _ref_order_id(new_link)
    if can_read_ref_order(db, user, ref_id):
        return False
    as_visit = structured_data["schedule"]["as_visit"]
    if old_link is not None:
        as_visit[LINK_PATH[-1]] = copy.deepcopy(old_link)
    else:
        as_visit.pop(LINK_PATH[-1], None)
    logger.warning("[T18-R1] ignored schedule_link to unreadable order ref=%s user=%s",
                   new_link.get("ref_order_id"), getattr(user, "id", None))
    return True


__all__ = [
    "PAYMENT_CONFIRM_ENDPOINT",
    "can_confirm_payment",
    "can_read_ref_order",
    "guard_payment_confirmation",
    "guard_schedule_link_ref",
]
