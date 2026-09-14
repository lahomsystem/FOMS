"""AUTH-QUEST-01 권한 술어 SSOT — quest approve 라우트와 화면이 같은 함수를 쓴다.

``foms/api/quest.py`` 안에만 있던 판정을 옮겨 왔다. 화면(실측 대시보드 도면 전달 CTA)이
서버보다 넓은 버튼을 내밀지 않도록, 노출 잣대와 라우트 게이트가 **같은 함수**를 부른다.
로직은 라우트 원본 그대로다(순수 리팩터).
"""

from __future__ import annotations

from foms.services.orders.erp_policy_constants import DEFAULT_OWNER_TEAM_BY_STAGE
from foms.services.orders.erp_policy_quests import resolve_required_approval_teams
from foms.services.orders.assignment import active_assignee_ids
from foms.services.orders.order_mutation_policy import normalize_team, team_has_capability

__all__ = [
    "QUEST_APPROVE_ROLES",
    "authorize_quest_approve",
    "find_stage_quest",
    "required_teams_for_stage",
]


# 라우트 데코레이터 ``@role_required(['ADMIN','MANAGER','STAFF'])`` 의 문자열 집합.
# ``role_required`` 는 ``user.role not in roles`` 로 **대소문자 정규화 없이** 비교한다
# (foms/web/auth/routes.py). 화면 판정도 정확히 같은 방식(원문 in 튜플)으로 해야 답이 같다.
QUEST_APPROVE_ROLES: tuple[str, ...] = ("ADMIN", "MANAGER", "STAFF")


def _int_or_none(value):
    """int 변환 실패 시 None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def find_stage_quest(
    sd: dict | None, stage_name: str, stage_code: str
) -> tuple[dict | None, int]:
    """현 단계 quest 와 그 인덱스. 없으면 ``(None, -1)``.

    매칭 규칙은 라우트 원본 그대로 — ``quests`` 리스트를 순회하며
    ``isinstance(q, dict) and q.get("stage") in (stage_name, stage_code)``.

    Args:
        sd: 주문 structured_data dict.
        stage_name: 현재 단계 한글 이름.
        stage_code: 현재 단계 영문 코드.

    Returns:
        (quest dict 또는 None, 인덱스 또는 -1) 튜플.
    """
    quests = (sd or {}).get("quests") or []
    for i, q in enumerate(quests):
        if isinstance(q, dict):
            quest_stage = q.get("stage")
            if quest_stage == stage_name or quest_stage == stage_code:
                return q, i
    return None, -1


def required_teams_for_stage(current_quest: dict | None, stage_code: str) -> list[str]:
    """현 단계의 dynamic 필수 승인 팀(정규화). quest.required_approvals 우선, 없으면 기본 owner team.

    Args:
        current_quest: 현재 단계 quest dict (QUEST-BACKFILL 정규화된 required_approvals).
        stage_code: 현재 단계 영문 코드.

    Returns:
        정규화된 팀 코드 목록.
    """

    # 저장값을 그대로 믿지 않는다 — 옛 규칙으로 좁게 저장된 quest 를 SSOT 가 정책으로
    # 덮는다(2026-09-13: 라홈 실측이 ["CS"] 로 저장돼 영업이 못 누르던 것).
    teams = [normalize_team(t) for t in resolve_required_approval_teams(stage_code, current_quest) if t]
    if not teams:
        default = DEFAULT_OWNER_TEAM_BY_STAGE.get(stage_code)
        if default:
            teams = [normalize_team(default)]
    return [t for t in teams if t]


def authorize_quest_approve(
    db, user, order, stage_code: str, current_quest: dict | None, *,
    emergency_override: bool = False,
    override_reason: str = "",
) -> tuple[bool, int, str]:
    """quest approve 권한 게이트 (AUTH-QUEST-01). 권한만 판정 — 상태 전이·기록은 하지 않는다.

    §5.2: actor team = 현 단계 필수 승인 팀; 시공은 ASSIGNMENT-00 user-ID row 기반;
    관리자 override 는 사유 필수(감사). DRAWING/CONFIRM 의 command-required 거부는 caller 가
    앞단에서 처리한다.

    Args:
        db: DB 세션(construction assignment 조회용).
        user: 승인 주체(role/team/id).
        order: 대상 주문.
        stage_code: 현재 단계 영문 코드.
        current_quest: 현재 단계 quest(required_approvals dynamic 팀 근거).
        emergency_override: 관리자 오버라이드 요청 여부.
        override_reason: 오버라이드 사유(오버라이드 시 필수).

    Returns:
        (allowed, status, message) 튜플. 허용이면 ``(True, 200, "")``.
    """
    role = (getattr(user, "role", None) or "").strip().upper()
    actor_team = normalize_team(getattr(user, "team", None))

    # 관리자 오버라이드: 사유 필수(감사). role/team 불일치를 override_reason 으로만 뚫는다.
    if emergency_override:
        if role not in ("ADMIN", "MANAGER"):
            return (False, 403, "긴급 오버라이드는 관리자만 가능합니다.")
        if not override_reason:
            return (False, 422, "오버라이드 승인은 사유(override_reason)가 필수입니다.")
        return (True, 200, "")

    # ADMIN 정상 command 통과(§2.1 role bypass).
    if role == "ADMIN":
        return (True, 200, "")

    # 시공: ASSIGNMENT-00 user-ID row 기반(JSONB 이름 미사용).
    if stage_code == "CONSTRUCTION":
        assigned = active_assignee_ids(db, order.id, "CONSTRUCTION")
        if assigned:
            uid = _int_or_none(getattr(user, "id", None))
            if uid is not None and uid in assigned:
                return (True, 200, "")
            return (False, 403, "이 주문에 배정된 시공 담당자만 승인할 수 있습니다.")
        # 배정 0(backfill 미완) → 팀 capability 폴백(lock-out 방지).
        if team_has_capability(actor_team, ("CS", "SALES", "CONSTRUCTION")):
            return (True, 200, "")
        return (False, 403, "시공 승인 권한이 없는 팀입니다.")

    # 일반: actor team = 현 단계 필수 승인 팀(dynamic).
    required_teams = required_teams_for_stage(current_quest, stage_code)
    if required_teams and team_has_capability(actor_team, required_teams):
        return (True, 200, "")
    return (False, 403, "현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)")
