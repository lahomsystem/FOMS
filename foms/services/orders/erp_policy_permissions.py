"""ERP domain permission helpers."""

from __future__ import annotations

from typing import List, Optional

from foms.services.orders.erp_policy_constants import DEFAULT_OWNER_TEAM_BY_STAGE


def get_assignee_ids(order, domain: str) -> List[int]:
    """주문의 특정 도메인에 대한 담당자 user_id 목록을 반환한다."""
    if not order or not order.structured_data:
        return []

    assignments = order.structured_data.get("assignments") or {}

    def _normalize_ids(values):
        out = []
        for value in values or []:
            try:
                out.append(int(value))
            except (TypeError, ValueError):
                continue
        return out

    if domain == "SALES_DOMAIN":
        return _normalize_ids(assignments.get("sales_assignee_user_ids") or [])
    if domain == "DRAWING_DOMAIN":
        ids = _normalize_ids(assignments.get("drawing_assignee_user_ids"))
        if ids:
            return ids
        legacy = assignments.get("drawing_assignees") or order.structured_data.get("drawing_assignees") or []
        legacy_ids = []
        for assignee in legacy:
            if not isinstance(assignee, dict):
                continue
            user_id = assignee.get("user_id", assignee.get("id"))
            try:
                legacy_ids.append(int(user_id))
            except (TypeError, ValueError):
                continue
        return legacy_ids
    return []


def can_modify_domain(
    user,
    order,
    domain: str,
    emergency_override: bool = False,
    override_reason: Optional[str] = None,
) -> bool:
    """사용자가 주문의 특정 도메인을 수정할 수 있는지 검사한다."""
    if not user:
        return False
    if user.role == "ADMIN":
        return True
    if domain in ("SALES_DOMAIN", "DRAWING_DOMAIN"):
        allowed_ids = get_assignee_ids(order, domain)
        if user.id in allowed_ids:
            return True
        if user.role == "MANAGER" and emergency_override and override_reason:
            return True
        return False
    return can_modify_by_team_policy(user, order, domain, emergency_override, override_reason)


def can_modify_by_team_policy(
    user,
    order,
    domain: str,
    emergency_override: bool = False,
    override_reason: Optional[str] = None,
) -> bool:
    """팀 기반 권한 검사 (PRODUCTION, CONSTRUCTION, CS, AS 등)."""
    if not user or not order:
        return False
    if user.role == "MANAGER" and emergency_override and override_reason:
        return True
    if not order.structured_data or not order.structured_data.get("workflow"):
        return False

    current_stage = order.structured_data["workflow"].get("stage")
    if not current_stage:
        return False
    owner_team = DEFAULT_OWNER_TEAM_BY_STAGE.get(current_stage)
    if not owner_team:
        return False
    return user.team == owner_team


def is_drawing_workbench_participant(user, order) -> bool:
    """도면 담당자(지정), 도면팀(DRAWING) 소속, 또는 관리자."""
    if not user or not order:
        return False
    if user.role == "ADMIN":
        return True
    try:
        uid = int(user.id)
    except (TypeError, ValueError):
        return False
    if uid in get_assignee_ids(order, "DRAWING_DOMAIN"):
        return True
    if (getattr(user, "team", None) or "").strip() == "DRAWING":
        return True
    return False


def can_transfer_drawing(user, order) -> bool:
    """도면 전달(첫 전달·수정본 전달·마법사 전달 대기) 권한 술어 — 화면과 서버가 함께 쓴다.

    ADMIN 또는 지정 도면 담당만 참이다. 도면 담당이 한 명도 없으면 누구도 참이 아니다
    (서버가 담당 미지정 400 으로 막는다). 도면팀 소속만으로는 전달할 수 없다(M14-a).
    MANAGER 의 사유 있는 긴급 오버라이드는 서버 ``perform_drawing_transfer`` 에만 있다 —
    화면 버튼은 켜지 않는다.
    """
    if not user or not order:
        return False
    assignee_ids = get_assignee_ids(order, "DRAWING_DOMAIN")
    if not assignee_ids:
        return False
    if getattr(user, "role", None) == "ADMIN":
        return True
    try:
        uid = int(user.id)
    except (TypeError, ValueError):
        return False
    return uid in assignee_ids


def has_pending_unchecked_drawing_revision_requests(structured_data: object) -> bool:
    """REQUEST_REVISION 이벤트 중 review_check.checked가 아직 False인 항목이 있으면 True."""
    if not isinstance(structured_data, dict):
        return False
    for h in structured_data.get("drawing_transfer_history") or []:
        if not isinstance(h, dict) or h.get("action") != "REQUEST_REVISION":
            continue
        review = h.get("review_check") if isinstance(h.get("review_check"), dict) else {}
        if not bool(review.get("checked")):
            return True
    return False


__all__ = [
    "can_modify_by_team_policy",
    "can_transfer_drawing",
    "can_modify_domain",
    "get_assignee_ids",
    "is_drawing_workbench_participant",
    "has_pending_unchecked_drawing_revision_requests",
]
