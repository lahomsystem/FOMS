"""FCOMM-01 3단계 겹 4 · J8: 켜진 프리랜서가 스스로 수수료 주인 · 이름을 바꾸는 길을 막는다.

* 발주사(``parties.orderer.name``) — 수수료 주인 · 거래구분(라홈 · 하우드 · 개인영업)을 정한다(``calc.resolve_owner``).
  이미 등록된 주문에서 프리랜서가 발주사를 바꾸는 저장은 거부한다(라홈↔하우드, 프리랜서 이름으로/에서 — 검토 원장 A13).
  등록 때 고르는 것은 허용한다: 초안(``meta.draft`` · status ``DRAFT``)을 등록하는 저장도 같은 PUT 이라 초안이면 통과.
  프리랜서가 쓸 수 있는 다른 쓰기 길은 발주사를 이미 있는 주문에 쓰지 않는다 — 자동 저장은 초안만,
  마법사 등록은 새 주문만 만들고, 칸 하나 고치기(PATCH)는 문지기 허용 목록 밖이다.
* 이름(``User.name``) — 내 정보 화면에서 이름을 바꿀 수 없다(검토 원장 A1). 같은 폼의 비밀번호 바꾸기는 된다.

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §1.2 J8 · §6.3 겹 4 · §6.5
시험: tests/security/test_freelancer_edit_guards.py
"""
from __future__ import annotations

from typing import Any, Optional

from flask import flash, g, jsonify, request, session

from foms.services.audit_writer import record_access_denied
from foms.services.auth.freelancer_scope import could_be_freelancer, is_freelancer_user
from foms.services.erp_order_flags import is_erp_draft_structured_data, is_erp_order_draft
from foms.services.sales_commission.names import normalize_name

ORDERER_LOCKED_MSG = "등록된 주문의 발주사는 CS 나 회계팀이 바꿔요."
PROFILE_NAME_LOCKED_MSG = "이름은 관리자에게 바꿔 달라고 해 주세요."

#: "이 저장은 발주사를 건드리지 않는다" 표식(저장이 옛 값을 그대로 남기는 경우).
_UNCHANGED = object()


def _incoming_orderer_name(structured_data: Any) -> Any:
    """이 저장이 끝난 뒤 남을 발주사 이름. 저장이 옛 값을 남기면 :data:`_UNCHANGED`.

    structured PUT 의 합치기 규칙(``_preserve_operational_structured_state`` 의 ``parties`` 깊은 합치기)을 따른다:
    ``parties`` · ``orderer`` · ``name`` 중 하나라도 없거나 ``parties`` 가 비어 있으면 옛 값이 남고, 사전이 아닌
    값이 오면 통째로 바뀌어 이름이 사라진다.
    """
    if not isinstance(structured_data, dict) or "parties" not in structured_data:
        return _UNCHANGED
    parties = structured_data.get("parties")
    if parties in (None, ""):
        return _UNCHANGED
    if not isinstance(parties, dict):
        return ""
    if "orderer" not in parties:
        return _UNCHANGED
    orderer = parties.get("orderer")
    if not isinstance(orderer, dict):
        return ""
    if "name" not in orderer:
        return _UNCHANGED
    return orderer.get("name")


def _stored_orderer_name(order: Any) -> Any:
    sd = getattr(order, "structured_data", None)
    parties = sd.get("parties") if isinstance(sd, dict) else None
    orderer = parties.get("orderer") if isinstance(parties, dict) else None
    return orderer.get("name") if isinstance(orderer, dict) else None


def _is_draft(order: Any) -> bool:
    """아직 등록 전 초안인지 — 등록 저장(``_finalize_draft_state``)과 같은 판정."""
    return is_erp_order_draft(order) or is_erp_draft_structured_data(getattr(order, "structured_data", None))


def freelancer_orderer_change_denial(order: Any, structured_data: Any) -> Optional[tuple[Any, int]]:
    """structured PUT 직전 판정 — 켜진 프리랜서가 등록된 주문의 발주사를 바꾸면 403 응답, 아니면 None.

    이름은 수수료 판정과 같은 정리(:func:`normalize_name`)로 견준다 — 띄어쓰기만 다른 것은 바꾼 것이 아니다.
    직원 · 영업팀 계정이 아니면 설정을 읽지 않는다.

    Args:
        order: 저장할 주문(잠그기 전 읽은 행).
        structured_data: 요청 본문의 ``structured_data``.

    Returns:
        ``({'success': False, 'data': None, 'error': ...}, 403)`` 또는 None.
    """
    user = getattr(g, "current_user", None)
    if not could_be_freelancer(user) or _is_draft(order):
        return None
    incoming = _incoming_orderer_name(structured_data)
    if incoming is _UNCHANGED or normalize_name(incoming) == normalize_name(_stored_orderer_name(order)):
        return None
    if not is_freelancer_user(user):
        return None
    order_id = int(getattr(order, "id", 0) or 0)
    record_access_denied(
        f"프리랜서 발주사 변경 거부(주문 {order_id})",
        user_id=session.get("user_id"),
        ip=request.remote_addr,
        endpoint=request.endpoint,
        action="freelancer:ORDERER_LOCKED",
        structured_action="ACCESS_DENIED",
        detail={"endpoint": request.endpoint, "reason": "FREELANCER_ORDERER_LOCKED", "order_id": order_id},
    )
    return jsonify({"success": False, "data": None, "error": ORDERER_LOCKED_MSG}), 403


def freelancer_profile_name(user: Any, posted_name: Optional[str]) -> Optional[str]:
    """내 정보 저장에 쓸 이름 — 켜진 프리랜서면 언제나 지금 이름(바꾸려 했으면 안내 한 줄), 아니면 보낸 이름.

    Args:
        user: 저장할 사용자 행.
        posted_name: 폼이 보낸 이름.

    Returns:
        ``user.name`` 에 넣을 이름.
    """
    if not is_freelancer_user(user):
        return posted_name
    current = getattr(user, "name", None)
    if (posted_name or "").strip() and (posted_name or "").strip() != (current or "").strip():
        flash(PROFILE_NAME_LOCKED_MSG, "warning")
    return current


__all__ = [
    "ORDERER_LOCKED_MSG",
    "PROFILE_NAME_LOCKED_MSG",
    "freelancer_orderer_change_denial",
    "freelancer_profile_name",
]
