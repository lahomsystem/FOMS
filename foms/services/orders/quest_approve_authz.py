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
    "actor_teams_for",
    "approvable_teams_for",
    "authorize_quest_approve",
    "display_team_axes",
    "find_stage_quest",
    "quest_approve_allowed",
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


def actor_teams_for(
    user,
    order,
    stage_code: str,
    quest: dict | None,
    required_teams: list[str] | None = None,
    *,
    construction_assignee_ids=None,
) -> list[str]:
    """현재 사용자가 승인 주체로 설 수 있는 팀 목록(승인 여부는 보지 않는다).

    라우트 게이트(:func:`authorize_quest_approve`)와 화면(재전이 버튼·팀 버튼)이 같은 답을
    내도록 판정을 이 한 함수에 모았다. ADMIN 은 필수 팀 전부, 승인 role 밖(VIEWER 등)은 빈
    목록 — 데코레이터 403 과 같은 답이다.

    Args:
        user: 현재 사용자(role/team/id).
        order: 대상 주문(시그니처 고정용 — 시공 배정은 ``construction_assignee_ids`` 로 받는다).
        stage_code: 현재 단계 영문 코드.
        quest: 현 단계 quest(required_approvals 근거). 없으면 정책 기본값.
        required_teams: 이미 계산한 필수 팀이 있으면 그대로 쓴다.
        construction_assignee_ids: 시공 단계의 active 배정 user id 목록(있으면 배정만 통과).

    Returns:
        승인 주체로 설 수 있는 팀 코드 목록.
    """
    role = (getattr(user, "role", None) or "").strip()
    if not user or role not in QUEST_APPROVE_ROLES:
        return []
    teams = (
        [normalize_team(t) for t in required_teams if t]
        if required_teams
        else required_teams_for_stage(quest, stage_code)
    )
    actor_team = normalize_team(getattr(user, "team", None))
    if stage_code == "CONSTRUCTION":
        if role.upper() == "ADMIN":
            return ["CONSTRUCTION"]
        if construction_assignee_ids:
            uid = _int_or_none(getattr(user, "id", None))
            return ["CONSTRUCTION"] if uid is not None and uid in construction_assignee_ids else []
        return ["CONSTRUCTION"] if team_has_capability(actor_team, ("CS", "SALES", "CONSTRUCTION")) else []
    if role.upper() == "ADMIN":
        return list(teams)
    return [t for t in teams if team_has_capability(actor_team, [t])]


def quest_approve_allowed(
    user,
    order,
    stage_code: str,
    quest: dict | None,
    required_teams: list[str] | None = None,
    *,
    construction_assignee_ids=None,
) -> bool:
    """현재 사용자가 이 단계 승인 API 에서 200 을 받는가(권한 축만)."""
    return bool(
        actor_teams_for(
            user, order, stage_code, quest, required_teams,
            construction_assignee_ids=construction_assignee_ids,
        )
    )


def approvable_teams_for(
    user,
    order,
    stage_code: str,
    quest: dict | None,
    required_teams: list[str] | None = None,
    *,
    construction_assignee_ids=None,
) -> list[str]:
    """팀 모드에서 아직 승인 안 된 팀 중 현재 사용자가 눌러 200 을 받을 팀. assignee 모드면 빈 목록."""
    quest = quest or {}
    if quest.get("approval_mode", "team") == "assignee":
        return []
    approvals = quest.get("team_approvals") or {}

    def _approved(team: str) -> bool:
        record = approvals.get(str(team)) or approvals.get(team)
        return bool(record.get("approved")) if isinstance(record, dict) else bool(record)

    return [
        t
        for t in actor_teams_for(
            user, order, stage_code, quest, required_teams,
            construction_assignee_ids=construction_assignee_ids,
        )
        if not _approved(t)
    ]


def display_team_axes(
    user,
    order,
    stage_code: str,
    quest: dict,
    required_teams: list[str],
    *,
    approval_mode: str,
    cta: dict,
) -> tuple[list[str], bool]:
    """화면용 두 축 — ``(approvable_teams, can_retransition)``.

    * ``approvable_teams``: 팀 모드에서만. 완료(is_done) quest 는 빈 목록. 저장되지 않은 합성
      quest 는 RECEIVED·CS 에서만 계산한다 — 생산·완료·AS 는 보드 명령이 실제 액션이고
      PRODUCTION quest 는 만들지 않는다는 규칙을 지킨다.
    * ``can_retransition``: 완료 quest 인데 단계가 아직 안 넘어간 막다른 길에서, 서버 재전이
      게이트(권한 + stage_advance_target + command 아님)와 같은 답.
    """
    is_done = bool(quest.get("is_done"))
    is_synth = bool(quest.get("is_synthesized"))
    if is_done or approval_mode != "team" or (is_synth and stage_code not in ("RECEIVED", "CS")):
        approvable: list[str] = []
    else:
        approvable = approvable_teams_for(user, order, stage_code, quest, required_teams)
    can_retransition = bool(
        is_done
        and cta.get("advances_stage")
        and not cta.get("command_required")
        and user is not None
        and quest_approve_allowed(user, order, stage_code, quest, required_teams)
    )
    return approvable, can_retransition


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

    # 시공: ASSIGNMENT-00 user-ID row 기반(JSONB 이름 미사용). 판정은 actor_teams_for 가 한다.
    if stage_code == "CONSTRUCTION":
        assigned = active_assignee_ids(db, order.id, "CONSTRUCTION")
        if quest_approve_allowed(
            user, order, stage_code, current_quest, construction_assignee_ids=assigned
        ):
            return (True, 200, "")
        if assigned:
            return (False, 403, "이 주문에 배정된 시공 담당자만 승인할 수 있습니다.")
        # 배정 0(backfill 미완) → 팀 capability 폴백(lock-out 방지)까지 실패한 경우.
        return (False, 403, "시공 승인 권한이 없는 팀입니다.")

    # 일반: actor team = 현 단계 필수 승인 팀(dynamic). 화면과 같은 술어를 쓴다.
    if quest_approve_allowed(user, order, stage_code, current_quest):
        return (True, 200, "")
    return (False, 403, "현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)")
