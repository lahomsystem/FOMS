"""관리자 강제 진행(``admin_override``) 판정·기록 정본 (ADMIN-OVERRIDE-01).

세 가지 "override" 가 이름만 닮았고 축이 전부 다르다. 섞으면 MANAGER 가 업무 게이트를
뚫는 길이 열리므로 이 표대로만 쓴다.

* ``emergency_override`` — **권한 소유 축**. MANAGER 가 도메인·팀 소유를 넘는다
  (``foms/services/orders/erp_policy_permissions.py:62,78``,
  ``quest_approve_authz.py:242-248``). ADMIN·MANAGER 둘 다 쓰고, 의미·시그니처를 그대로 둔다.
* ``admin_override`` — **업무 게이트 축**. 단계 전제·퀘스트·보류·증빙·완료 경로를 사람
  판단으로 넘는다(이 모듈). ADMIN 전용, 사유 필수.
* 엔진 ``execute_transition(emergency_override=)`` — command ``from_values`` 멤버십 완화
  (``foms/services/orders/order_transition_service.py:359-367``). 라우트에 노출하지 않는다.
  라우트는 ``admin_override`` 를 받아 **엔진 호출 시에만** 그 값을 번역해 넘긴다.

셋은 서로를 함의하지 않는다. 한 요청에 둘이 같이 올 수 있고, ``admin_override`` 가
``emergency_override`` 를 켜지 않는다(켜면 MANAGER 가 업무 게이트를 뚫는 길이 생긴다).

**권한 축만 푼다.** If-Match(mutation_version) 충돌·잠금 아래 ``expected_from`` 재확인·
``to_values`` 위반·``confirm != true``·빈 사유·동일 단계·일괄 상한·삭제된 주문은 정합 축이라
관리자도 뚫지 못한다. 정합을 뚫으면 동시 편집이 조용히 서로를 덮는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from flask import jsonify
from sqlalchemy.exc import SQLAlchemyError

from foms.services.audit_writer import normalize_security_detail
from models import OrderEvent, SecurityLog

#: 뚫기에 성공했을 때만 남기는 주문 이벤트 종류(실패한 시도는 SecurityLog 만).
ADMIN_OVERRIDE_EVENT = "ADMIN_OVERRIDE_USED"

logger = logging.getLogger(__name__)

#: 뚫기 시도가 거부됐을 때 남기는 감사 action 태그.
ADMIN_OVERRIDE_DENIED_ACTION = "ADMIN_OVERRIDE_DENIED"

# 게이트 코드(화면 재시도 화이트리스트·타임라인 한글 표와 1:1).
GATE_OVERRIDE_BLOCK = "OVERRIDE_BLOCK"
GATE_USE_CS_COMPLETE = "USE_CS_COMPLETE"
GATE_INVALID_STAGE = "INVALID_STAGE"
GATE_QUEST_INCOMPLETE = "QUEST_INCOMPLETE"
GATE_HOLD_ACTIVE = "HOLD_ACTIVE"
GATE_AS_ACTIVE = "AS_ACTIVE"
GATE_COMMAND_REQUIRED = "COMMAND_REQUIRED"
GATE_DRAWING_STATUS = "DRAWING_STATUS"
GATE_EVIDENCE_MISSING = "EVIDENCE_MISSING"
GATE_OVERRIDE_TARGET = "OVERRIDE_TARGET"

GATE_CODES: tuple[str, ...] = (
    GATE_OVERRIDE_BLOCK,
    GATE_USE_CS_COMPLETE,
    GATE_INVALID_STAGE,
    GATE_QUEST_INCOMPLETE,
    GATE_HOLD_ACTIVE,
    GATE_AS_ACTIVE,
    GATE_COMMAND_REQUIRED,
    GATE_DRAWING_STATUS,
    GATE_EVIDENCE_MISSING,
    GATE_OVERRIDE_TARGET,
)

#: 뚫기 축 이름(이벤트 payload 의 ``axis``).
AXIS_VALUES: tuple[str, ...] = (
    "MAIN", "AS", "DELETE", "QUEST", "DRAWING", "HOLD", "CONSTRUCTION",
)

ADMIN_ONLY_MESSAGE = "관리자만 검사를 건너뛸 수 있습니다."
REASON_REQUIRED_MESSAGE = "검사를 건너뛰려면 사유가 필요합니다."
SHAPE_MESSAGE = (
    "주문별 관리자 강제 진행은 받지 않습니다. "
    "요청 본문 맨 위에 admin_override 와 사유를 한 번만 넣으세요."
)


@dataclass(frozen=True)
class AdminOverride:
    """뚫기가 성립한 요청 1건의 사람 판단 기록(사유와 행위자)."""

    reason: str
    actor_id: int
    actor_name: str
    actor_role: str


def _role_of(user: Any) -> str:
    """사용자 role 을 대문자 문자열로 읽는다(없으면 빈 문자열)."""
    return str(getattr(user, "role", "") or "").strip().upper()


def _reason_of(payload: Any) -> str:
    """본문에서 사유를 읽는다 — ``override_reason`` 우선, 없으면 ``reason``.

    강제 단계 변경 라우트는 ``reason`` 이 이미 필수 필드라, 사용자가 같은 사유를 두 번
    적지 않도록 같은 본문의 ``reason`` 을 뒤이어 읽는다.
    """
    if not isinstance(payload, Mapping):
        return ""
    raw = payload.get("override_reason")
    if raw is None or not str(raw).strip():
        raw = payload.get("reason")
    return str(raw or "").strip()


def _flag_of(payload: Any) -> Any:
    """본문의 ``admin_override`` 원값(없으면 None)."""
    if not isinstance(payload, Mapping):
        return None
    return payload.get("admin_override")


def _error(code: str, message: str, status: int):
    """표준 거부 응답. ``error`` 와 ``message`` 를 둘 다 싣는다.

    강제 단계 변경 라우트는 ``error`` 키를, 상태·게이트 라우트는 ``message`` 키를 읽는다 —
    한쪽만 실으면 화면이 빈 오류를 띄운다.
    """
    return (
        jsonify({"success": False, "code": code, "message": message, "error": message}),
        status,
    )


def resolve_admin_override(user: Any, payload: Any) -> Optional[AdminOverride]:
    """요청이 관리자 강제 진행으로 성립하는지 판정한다.

    ``admin_override`` 가 정확히 ``True`` 이고 role 이 ADMIN 이고 사유가 비어 있지 않을
    때만 객체를 돌려준다. ``emergency_override`` 만 실은 요청은 다른 축이라 None 이다.

    Args:
        user: 요청 사용자(User ORM 또는 role/id/name 속성을 가진 객체).
        payload: 요청 본문 매핑.

    Returns:
        성립하면 :class:`AdminOverride`, 아니면 None.
    """
    if _flag_of(payload) is not True:
        return None
    if _role_of(user) != "ADMIN":
        return None
    reason = _reason_of(payload)
    if not reason:
        return None
    try:
        actor_id = int(getattr(user, "id", 0) or 0)
    except (TypeError, ValueError):
        actor_id = 0
    return AdminOverride(
        reason=reason,
        actor_id=actor_id,
        actor_name=str(getattr(user, "name", "") or getattr(user, "username", "") or ""),
        actor_role="ADMIN",
    )


def admin_override_error(user: Any, payload: Any):
    """뚫기 요청의 모양·권한·사유를 검사한다(업무 게이트보다 **먼저** 돈다).

    비관리자가 게이트 코드 대신 정확한 오답(403)을 받게 하려고 순서를 고정한다.

    Args:
        user: 요청 사용자.
        payload: 요청 본문 매핑.

    Returns:
        거부 응답 ``(json, status)`` — 400 ``ADMIN_OVERRIDE_SHAPE`` / 403 ``ADMIN_ONLY`` /
        422 ``REASON_REQUIRED``. 뚫기 요청이 아니거나 문제가 없으면 None.
    """
    flag = _flag_of(payload)
    if isinstance(flag, (dict, list, tuple)):
        return _error("ADMIN_OVERRIDE_SHAPE", SHAPE_MESSAGE, 400)
    if flag is not True:
        return None
    if _role_of(user) != "ADMIN":
        return _error("ADMIN_ONLY", ADMIN_ONLY_MESSAGE, 403)
    if not _reason_of(payload):
        return _error("REASON_REQUIRED", REASON_REQUIRED_MESSAGE, 422)
    return None


def _normalize_gates(gates: Optional[Sequence[Any]]) -> list[str]:
    """건너뛴 게이트 코드를 중복 없는 문자열 목록으로 고른다(항상 1개 이상).

    호출부가 빈 목록을 주면 ``UNSPECIFIED`` 한 칸을 남긴다 — 어떤 검사를 건너뛰었는지
    모르는 채로 기록이 통째로 비는 것보다, 모른다고 적힌 편이 낫다.
    """
    out: list[str] = []
    for raw in gates or ():
        code = str(raw or "").strip()
        if code and code not in out:
            out.append(code)
    return out or ["UNSPECIFIED"]


def record_admin_override_event(
    db: Any,
    order: Any,
    *,
    override: AdminOverride,
    gates: Optional[Sequence[Any]],
    route: str,
    axis: str,
    from_value: Any = "",
    to_value: Any = "",
    bulk: bool = False,
) -> None:
    """뚫기에 **성공한** 주문 1건에 ``ADMIN_OVERRIDE_USED`` 이벤트와 감사행을 남긴다.

    커밋하지 않는다 — 호출부의 transaction 에 함께 실린다. 기존 전이 이벤트
    (``STAGE_CHANGED``·``CS_COMPLETED``·``AS_REGISTERED``·``ORDER_SOFT_DELETED``·
    ``STAGE_OVERRIDE``)는 그대로 남는다.

    Args:
        db: 활성 DB 세션.
        order: 대상 주문.
        override: 성립한 뚫기 판정.
        gates: 이 요청이 실제로 건너뛴 게이트 코드 전부(1개 이상).
        route: 라우트 이름(``blueprint.endpoint``).
        axis: 움직인 축(``MAIN``·``AS``·``DELETE``·``QUEST``·``DRAWING``·``HOLD``·
            ``CONSTRUCTION``). 축이 움직이지 않는 게이트면 from/to 는 빈 문자열이다.
        from_value: 이전 축 값(없으면 빈 문자열).
        to_value: 이후 축 값(없으면 빈 문자열).
        bulk: 일괄 요청이면 True.
    """
    codes = _normalize_gates(gates)
    order_id = int(getattr(order, "id", 0) or 0)
    payload = {
        "gate": codes[0],
        "gates": codes,
        "route": str(route or ""),
        "axis": str(axis or ""),
        "from": str(from_value or ""),
        "to": str(to_value or ""),
        "reason": override.reason,
        "actor": {
            "id": override.actor_id,
            "name": override.actor_name,
            "role": override.actor_role,
        },
        "bulk": bool(bulk),
    }
    db.add(
        OrderEvent(
            order_id=order_id,
            event_type=ADMIN_OVERRIDE_EVENT,
            payload=payload,
            created_by_user_id=override.actor_id or None,
        )
    )
    # 감사행은 호출부의 commit 에 함께 실린다(업무 변경이 되감기면 감사도 함께 되감긴다).
    # 감사 헬퍼(web 계층)는 services 에서 부르지 않는다 — 레이어 방향 계약.
    db.add(
        SecurityLog(
            user_id=override.actor_id or None,
            message=(
                f"주문 #{order_id} 관리자 강제 진행(건너뛴 검사: {', '.join(codes)}) "
                f"— {route} ({override.reason})"
            ),
            action=ADMIN_OVERRIDE_EVENT,
            target_type="order",
            target_id=order_id,
            detail=normalize_security_detail(payload),
        )
    )


def log_admin_override_denied(
    db: Any, *, order_id: Any, gate: str, route: str, user: Any
) -> None:
    """거부된 뚫기 시도를 감사 원장(SecurityLog)에만 남긴다.

    주문 이벤트는 남기지 않는다 — 일어나지 않은 일을 주문 이력에 적으면 안 된다.

    Args:
        db: 활성 DB 세션.
        order_id: 대상 order id(없으면 None).
        gate: 거부 사유 코드(``ADMIN_ONLY``·``REASON_REQUIRED`` 또는 게이트 코드).
        route: 라우트 이름.
        user: 시도한 사용자.
    """
    try:
        target_id = int(order_id) if order_id is not None else None
    except (TypeError, ValueError):
        target_id = None
    db.add(
        SecurityLog(
            user_id=getattr(user, "id", None),
            message=f"주문 #{target_id} 관리자 강제 진행 거부({gate}) — {route}",
            action=ADMIN_OVERRIDE_DENIED_ACTION,
            target_type="order",
            target_id=target_id,
            detail=normalize_security_detail({
                "gate": str(gate or ""),
                "route": str(route or ""),
                "actor_role": _role_of(user),
            }),
        )
    )
    try:
        # 거부 응답 뒤에는 커밋할 업무 변경이 없다 — 감사행을 여기서 직접 남긴다.
        db.commit()
    except SQLAlchemyError:
        # 감사 한 줄 때문에 거부 응답을 못 돌려주면 안 된다 — 스택은 남기고 되감는다.
        logger.warning("관리자 강제 진행 거부 감사행 기록 실패", exc_info=True)
        db.rollback()


__all__ = [
    "ADMIN_ONLY_MESSAGE",
    "ADMIN_OVERRIDE_DENIED_ACTION",
    "ADMIN_OVERRIDE_EVENT",
    "AXIS_VALUES",
    "AdminOverride",
    "GATE_CODES",
    "REASON_REQUIRED_MESSAGE",
    "SHAPE_MESSAGE",
    "admin_override_error",
    "log_admin_override_denied",
    "record_admin_override_event",
    "resolve_admin_override",
]
