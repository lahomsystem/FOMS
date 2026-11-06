"""FCOMM-01 3단계 겹 4 · J8: 켜진 프리랜서가 스스로 수수료 주인 · 이름을 바꾸는 길과, 열어 준 일의 범위를 막는다.

* 발주사(``parties.orderer.name``) — 수수료 주인 · 거래구분(라홈 · 하우드 · 개인영업)을 정한다(``calc.resolve_owner``).
  이미 등록된 주문에서 프리랜서가 발주사를 바꾸는 저장은 거부한다(라홈↔하우드, 프리랜서 이름으로/에서 — 검토 원장 A13).
  등록 때 고르는 것은 허용한다: 초안(``meta.draft`` · status ``DRAFT``)을 등록하는 저장도 같은 PUT 이라 초안이면 통과.
  프리랜서가 쓸 수 있는 다른 쓰기 길은 발주사를 이미 있는 주문에 쓰지 않는다 — 자동 저장은 초안만,
  마법사 등록은 새 주문만 만들고, 칸 하나 고치기(PATCH)는 문지기 허용 목록 밖이다.
* 담당자 뱃지(``parties.manager.name`` · ``names``) — "내 주문"(연결 표) · 수수료 대표를 정한다(사용자 결정 D21).
  등록된 주문에서 명단(사람 · 순서)을 바꾸는 저장은 거부한다 — structured PUT(발주사와 같은 한 줄)과 실측 판 칸
  고치기(``erp_measurement.api_erp_measurement_update``) 두 길. 초안 · 첫 등록은 된다.
* 이름(``User.name``) — 내 정보 화면에서 이름을 바꿀 수 없다(검토 원장 A1). 같은 폼의 비밀번호 바꾸기는 된다.
* 열어 준 일의 범위(D22 · D23): 채널톡 PUSH 는 영발 · 실측만, 퀘스트 승인은 실측 단계(도면으로 넘기기)만.

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §1.2 J8 · §6.3 겹 4 · §6.5, 사용자 결정 D21~D23
시험: tests/security/test_freelancer_edit_guards.py · tests/security/test_freelancer_decisions.py
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from flask import flash, g, jsonify, request, session

from foms.services.audit_writer import record_access_denied
from foms.services.auth.freelancer_scope import could_be_freelancer, is_freelancer_user
from foms.services.erp_order_flags import is_erp_draft_structured_data, is_erp_order_draft
from foms.services.orders.confirm_drawing_gate import normalize_stage_code
from foms.services.orders.manager_names import order_manager_names
from foms.services.sales_commission.names import normalize_name

ORDERER_LOCKED_MSG = "등록된 주문의 발주사는 CS 나 회계팀이 바꿔요."
MANAGER_LOCKED_MSG = "등록된 주문의 담당자는 CS 가 바꿔요."
PROFILE_NAME_LOCKED_MSG = "이름은 관리자에게 바꿔 달라고 해 주세요."
PUSH_KIND_LOCKED_MSG = "프리랜서 계정은 영발 PUSH · 실측 PUSH 만 보낼 수 있어요."
QUEST_STAGE_LOCKED_MSG = "프리랜서 계정은 실측을 마치고 도면으로 넘기는 승인만 할 수 있어요."

#: 프리랜서가 보낼 수 있는 채널톡 PUSH 종류(D22 — 영발 · 실측). 발주 · AS · 도면방은 직원 몫.
FREELANCER_PUSH_KINDS: frozenset[str] = frozenset({"measurement", "measure_room"})
#: 프리랜서가 승인할 수 있는 단계(D23 — 실측 끝 · 도면으로 넘기기).
FREELANCER_QUEST_STAGES: frozenset[str] = frozenset({"MEASURE"})

#: "이 저장은 발주사 · 담당자를 건드리지 않는다" 표식(저장이 옛 값을 그대로 남기는 경우).
_UNCHANGED = object()


def _incoming_party(structured_data: Any, role: str) -> Any:
    """이 저장이 ``parties.<role>`` 자리에 싣는 값. 저장이 옛 값을 남기면 :data:`_UNCHANGED`.

    structured PUT 의 합치기 규칙(``_preserve_operational_structured_state`` 의 ``parties`` 깊은 합치기)을 따른다:
    ``parties`` · ``<role>`` 중 하나라도 없거나 ``parties`` 가 비어 있으면 옛 값이 남고, ``parties`` 가 사전이 아니면
    통째로 바뀌어 그 자리가 사라진다(None).
    """
    if not isinstance(structured_data, dict) or "parties" not in structured_data:
        return _UNCHANGED
    parties = structured_data.get("parties")
    if parties in (None, ""):
        return _UNCHANGED
    if not isinstance(parties, dict):
        return None
    if role not in parties:
        return _UNCHANGED
    return parties.get(role)


def _incoming_orderer_name(structured_data: Any) -> Any:
    """이 저장이 끝난 뒤 남을 발주사 이름. 저장이 옛 값을 남기면 :data:`_UNCHANGED`(사전이 아닌 값은 이름 없음)."""
    orderer = _incoming_party(structured_data, "orderer")
    if orderer is _UNCHANGED:
        return _UNCHANGED
    if not isinstance(orderer, dict):
        return ""
    if "name" not in orderer:
        return _UNCHANGED
    return orderer.get("name")


def _stored_party(order: Any, role: str) -> Any:
    sd = getattr(order, "structured_data", None)
    parties = sd.get("parties") if isinstance(sd, dict) else None
    return parties.get(role) if isinstance(parties, dict) else None


def _stored_orderer_name(order: Any) -> Any:
    orderer = _stored_party(order, "orderer")
    return orderer.get("name") if isinstance(orderer, dict) else None


def _merge(old: Any, incoming: Any) -> Any:
    """PUT 의 ``_merge_preserving_missing`` 과 같은 깊은 합치기(둘 다 사전일 때만 칸별로, 아니면 들어온 값)."""
    if not isinstance(old, dict) or not isinstance(incoming, dict):
        return copy.deepcopy(incoming)
    merged = copy.deepcopy(old)
    for key, value in incoming.items():
        merged[key] = _merge(merged.get(key), value) if isinstance(merged.get(key), dict) else copy.deepcopy(value)
    return merged


def _saved_manager_names(manager: Any) -> list[str]:
    """저장 직전 정리(``normalize_manager_party`` — 대표가 비면 명단도 비운다)를 거친 뒤 남을 담당자 명단."""
    if isinstance(manager, dict) and not str(manager.get("name") or "").strip():
        return []
    return order_manager_names({"parties": {"manager": manager}})


def _stored_manager_names(order: Any) -> list[str]:
    """지금 저장된 담당자 명단(sd 에 없으면 ``orders.manager_name`` — 화면이 보여 주는 것과 같다)."""
    return order_manager_names(getattr(order, "structured_data", None), getattr(order, "manager_name", None))


def _names_key(names: list[str]) -> list[str]:
    """견줄 꼴 — 수수료 판정과 같은 이름 정리, 순서는 그대로(대표가 바뀌는 것도 바꾼 것이다)."""
    return [normalize_name(name) for name in names]


def _orderer_changed(order: Any, structured_data: Any) -> bool:
    incoming = _incoming_orderer_name(structured_data)
    return incoming is not _UNCHANGED and normalize_name(incoming) != normalize_name(_stored_orderer_name(order))


def _managers_changed(order: Any, structured_data: Any) -> bool:
    incoming = _incoming_party(structured_data, "manager")
    if incoming is _UNCHANGED:
        return False
    after = _saved_manager_names(_merge(_stored_party(order, "manager"), incoming))
    return _names_key(after) != _names_key(_stored_manager_names(order))


def _is_draft(order: Any) -> bool:
    """아직 등록 전 초안인지 — 등록 저장(``_finalize_draft_state``)과 같은 판정."""
    return is_erp_order_draft(order) or is_erp_draft_structured_data(getattr(order, "structured_data", None))


def _deny(message: str, reason: str, note: str, order_id: Optional[int] = None) -> tuple[Any, int]:
    """거부 감사 1줄 + 403 응답."""
    detail: dict[str, Any] = {"endpoint": request.endpoint, "reason": f"FREELANCER_{reason}"}
    if order_id is not None:
        detail["order_id"] = order_id
    record_access_denied(
        note,
        user_id=session.get("user_id"),
        ip=request.remote_addr,
        endpoint=request.endpoint,
        action=f"freelancer:{reason}",
        structured_action="ACCESS_DENIED",
        detail=detail,
    )
    return jsonify({"success": False, "data": None, "error": message}), 403


def freelancer_party_change_denial(order: Any, structured_data: Any) -> Optional[tuple[Any, int]]:
    """structured PUT 직전 판정 — 켜진 프리랜서가 등록된 주문의 발주사 또는 담당자 명단을 바꾸면 403, 아니면 None.

    이름은 수수료 판정과 같은 정리(:func:`normalize_name`)로 견준다 — 띄어쓰기만 다른 것은 바꾼 것이 아니다.
    담당자는 저장 뒤 남을 명단(PUT 합치기 · 저장 직전 정리를 그대로 따라 한 것)과 지금 명단을 사람 · 순서까지 견준다.

    Args:
        order: 저장할 주문(잠그기 전 읽은 행).
        structured_data: 요청 본문의 ``structured_data``.

    Returns:
        ``({'success': False, 'data': None, 'error': ...}, 403)`` 또는 None.
    """
    user = getattr(g, "current_user", None)
    if not could_be_freelancer(user) or _is_draft(order):
        return None
    orderer_changed = _orderer_changed(order, structured_data)
    if not orderer_changed and not _managers_changed(order, structured_data):
        return None
    if not is_freelancer_user(user):
        return None
    order_id = int(getattr(order, "id", 0) or 0)
    if orderer_changed:
        return _deny(ORDERER_LOCKED_MSG, "ORDERER_LOCKED", f"프리랜서 발주사 변경 거부(주문 {order_id})", order_id)
    return _deny(MANAGER_LOCKED_MSG, "MANAGER_LOCKED", f"프리랜서 담당자 변경 거부(주문 {order_id})", order_id)


#: structured PUT 의 호출 자리(``foms/api/erp_orders_structured.py``)가 쓰는 이름 — 발주사 · 담당자를 함께 본다(D21).
freelancer_orderer_change_denial = freelancer_party_change_denial


def freelancer_manager_change_denial(order: Any, new_names: list[str]) -> Optional[tuple[Any, int]]:
    """실측 판 담당자 칸 저장 직전 판정 — 켜진 프리랜서가 등록된 주문의 담당자 명단을 바꾸면 403, 아니면 None.

    Args:
        order: 저장할 주문.
        new_names: 저장 뒤 남을 명단(핸들러가 ``normalize_name_list`` 로 만든 것, 대표가 맨 앞).

    Returns:
        403 응답 또는 None.
    """
    user = getattr(g, "current_user", None)
    if not could_be_freelancer(user) or _is_draft(order):
        return None
    if _names_key(list(new_names or [])) == _names_key(_stored_manager_names(order)) or not is_freelancer_user(user):
        return None
    order_id = int(getattr(order, "id", 0) or 0)
    return _deny(MANAGER_LOCKED_MSG, "MANAGER_LOCKED", f"프리랜서 담당자 변경 거부(주문 {order_id})", order_id)


def freelancer_push_kind_denial(payload: Any) -> Optional[tuple[Any, int]]:
    """채널톡 수동 PUSH 직전 — 켜진 프리랜서는 영발 · 실측 PUSH 만(D22). 아니면 403, 맞으면 None.

    종류는 핸들러(``run_manual_push``)와 같이 읽는다 — 비었으면 ``measurement``.
    """
    user = getattr(g, "current_user", None)
    kind = (payload.get("push_kind") if isinstance(payload, dict) else None) or "measurement"
    allowed = isinstance(kind, str) and kind in FREELANCER_PUSH_KINDS  # 글자가 아닌 값(목록 등)은 거부
    if not could_be_freelancer(user) or allowed or not is_freelancer_user(user):
        return None
    return _deny(PUSH_KIND_LOCKED_MSG, "PUSH_KIND_LOCKED", f"프리랜서 PUSH 종류 거부({str(kind)[:40]})")


def freelancer_quest_stage_denial(stage_code: Any) -> Optional[tuple[Any, int]]:
    """퀘스트 승인 직전 — 켜진 프리랜서는 실측 단계 승인(도면으로 넘기기)만(D23). 아니면 403, 맞으면 None."""
    user = getattr(g, "current_user", None)
    stage = normalize_stage_code(stage_code)
    if not could_be_freelancer(user) or stage in FREELANCER_QUEST_STAGES or not is_freelancer_user(user):
        return None
    return _deny(QUEST_STAGE_LOCKED_MSG, "QUEST_STAGE_LOCKED", f"프리랜서 퀘스트 승인 단계 거부({stage[:40]})")


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
    "FREELANCER_PUSH_KINDS",
    "FREELANCER_QUEST_STAGES",
    "MANAGER_LOCKED_MSG",
    "ORDERER_LOCKED_MSG",
    "PROFILE_NAME_LOCKED_MSG",
    "PUSH_KIND_LOCKED_MSG",
    "QUEST_STAGE_LOCKED_MSG",
    "freelancer_manager_change_denial",
    "freelancer_orderer_change_denial",
    "freelancer_party_change_denial",
    "freelancer_profile_name",
    "freelancer_push_kind_denial",
    "freelancer_quest_stage_denial",
]
