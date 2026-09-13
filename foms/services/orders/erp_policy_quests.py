"""Quest template and approval helpers."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE
from foms.services.orders.erp_policy_data_access import get_quest_templates


def get_quest_template_for_stage(stage: Optional[str]) -> Optional[Dict[str, Any]]:
    """주어진 단계의 Quest 템플릿을 반환한다."""
    if not stage:
        return None
    stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
    template = get_quest_templates()
    stages = (template.get("stages") or {}) if isinstance(template.get("stages"), dict) else {}
    return stages.get(stage_code)


def get_required_approval_teams_for_stage(stage: Optional[str]) -> List[str]:
    """주어진 단계의 필수 승인 팀 목록을 반환한다."""
    quest_template = get_quest_template_for_stage(stage)
    if not quest_template:
        return []
    required_approvals = quest_template.get("required_approvals")
    if isinstance(required_approvals, list):
        return [str(team) for team in required_approvals if team]
    return []


def get_next_stage_for_completed_quest(stage: Optional[str]) -> Optional[str]:
    """현재 단계 Quest 완료 후 다음 단계를 반환한다."""
    quest_template = get_quest_template_for_stage(stage)
    if not quest_template:
        return None
    next_stage = quest_template.get("next_stage")
    return str(next_stage) if next_stage else None


def check_quest_approvals_complete(sd: Dict[str, Any], stage: Optional[str]) -> tuple[bool, List[str]]:
    """현재 단계 Quest의 필수 승인 완료 여부를 반환한다."""
    if not stage:
        return (False, [])

    quests = sd.get("quests") or []
    if not isinstance(quests, list):
        return (False, [])

    stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
    current_quest = None
    for quest in quests:
        if isinstance(quest, dict):
            quest_stage = quest.get("stage")
            if quest_stage == stage or quest_stage == stage_code:
                current_quest = quest
                break

    if not current_quest:
        required_teams = get_required_approval_teams_for_stage(stage)
        return (False, required_teams)

    required_teams = current_quest.get("required_approvals")
    if not required_teams or not isinstance(required_teams, list):
        required_teams = get_required_approval_teams_for_stage(stage)
    if not required_teams:
        return (True, [])

    team_approvals = current_quest.get("team_approvals") or {}
    if not isinstance(team_approvals, dict):
        return (False, required_teams)

    quest_status = current_quest.get("status", "OPEN")
    if quest_status == "OPEN":
        all_unapproved = True
        for team in required_teams:
            team_key = str(team)
            approval = team_approvals.get(team_key) or team_approvals.get(team)
            if approval is not None:
                if isinstance(approval, dict):
                    if approval.get("approved", False):
                        all_unapproved = False
                        break
                elif bool(approval):
                    all_unapproved = False
                    break
        if all_unapproved:
            return (False, required_teams)

    missing_teams = []
    for team in required_teams:
        team_key = str(team)
        approval = team_approvals.get(team_key) or team_approvals.get(team)
        if approval is None:
            missing_teams.append(team)
        elif isinstance(approval, dict):
            if not approval.get("approved", False):
                missing_teams.append(team)
        elif not bool(approval):
            missing_teams.append(team)

    return (len(missing_teams) == 0, missing_teams)


#: 발주사 라홈 주문에서 **주관 팀**을 CS 로 바꾸는 단계(표시·배정 축).
#: 승인 축(누가 누를 수 있는가)은 여기서 좁히지 않는다 — 2026-09-13 정정 참조.
LAHOM_CS_OWNER_STAGES = ("실측", "MEASURE", "고객컨펌", "CONFIRM")


def resolve_required_approval_teams(
    stage: Optional[str],
    quest: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """이 단계를 **누가 승인할 수 있는가** — 화면·서버·감사가 함께 쓰는 SSOT.

    2026-09-13 정정. 그 전에는 이 판정이 세 곳(quest 생성·화면 표시·감사)에 각자 라홈
    분기를 갖고 흩어져 있었고, 두 가지가 동시에 틀려 있었다.

    1. **업무 규칙이 달랐다.** 실측·고객컨펌의 주관 팀은 CS 와 영업 **둘 다**다
       (사용자 확인 2026-09-13: CS 는 자가실측, 영업은 방문 실측). 그런데 템플릿 기본값은
       ``["SALES"]`` 라 CS 가 자가실측을 못 눌렀고, 라홈 분기는 ``["CS"]`` 로 덮어써서
       영업이 방문실측을 못 눌렀다. 양쪽이 서로 다른 한 팀을 배제하고 있었다.
       (운영 신고: 영업팀이 라홈 주문 실측 완료를 누르자 403 — 실측 단계 라홈 344건이
       그 상태였다.)
    2. **화면과 서버가 다른 잣대를 썼다.** 서버는 ``required_approvals`` 로 판정하는데
       화면은 그걸 안 보고 ``can_edit_erp``/도메인 권한으로만 판정해, **서버가 거부할
       버튼을 화면이 내밀었다.**

    라홈 주문의 ``owner_team=CS`` 는 그대로다 — "누가 주관하는가"(표시·배정)와
    "누가 승인할 수 있는가"는 다른 축이고, 이 함수는 승인 축만 답한다.

    저장값 취급: quest 에 이미 실린 ``required_approvals`` 가 정책보다 **좁으면 정책을
    쓴다**. 옛 규칙으로 저장된 quest(``["CS"]`` 84건)를 마이그레이션 없이 오늘 바로 풀기
    위해서다. 저장값이 정책과 같거나 더 넓으면 그대로 존중한다(수동으로 넓힌 경우 보존).

    Args:
        stage: 단계(한글명 또는 영문 코드).
        quest: 저장된 quest dict(없으면 정책만 본다).

    Returns:
        승인 가능한 팀 코드 목록(정규화 전 원본 코드).
    """
    policy = [str(t) for t in (get_required_approval_teams_for_stage(stage) or []) if t]
    raw = quest.get("required_approvals") if isinstance(quest, dict) else None
    saved = [str(t) for t in (raw or []) if t]
    if not saved:
        return policy
    if not policy:
        return saved
    # 저장값이 정책의 진부분집합이면 옛 규칙으로 좁혀진 것 — 정책이 이긴다.
    if set(saved) < set(policy):
        return policy
    return saved


def create_quest_from_template(
    stage: Optional[str],
    owner_person: Optional[str] = None,
    structured_data: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """템플릿 기반으로 Quest 객체를 생성한다."""
    if not stage:
        return None

    quest_template = get_quest_template_for_stage(stage)
    if not quest_template:
        return None

    now = datetime.datetime.now()
    required_teams = quest_template.get("required_approvals") or []
    owner_team = quest_template.get("owner_team") or ""

    # 라홈 발주사는 **주관 팀**만 CS 로 바꾼다(표시·배정). 승인 축은 안 좁힌다 —
    # 실측·고객컨펌은 CS·영업 둘 다 누른다(:func:`resolve_required_approval_teams`).
    if stage in LAHOM_CS_OWNER_STAGES and structured_data:
        orderer_name = (((structured_data.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
        if orderer_name and "라홈" in orderer_name:
            owner_team = "CS"

    assignee_based_stages = ["실측", "MEASURE", "도면", "DRAWING", "고객컨펌", "CONFIRM"]
    is_assignee_based = stage in assignee_based_stages

    quest = {
        "stage": stage,
        "title": quest_template.get("title") or "",
        "description": quest_template.get("description") or "",
        "owner_team": owner_team,
        "owner_person": owner_person or "",
        "status": "OPEN",
        "required_approvals": required_teams,
        "team_approvals": {},
        "approval_mode": "assignee" if is_assignee_based else "team",
        "assignee_approval": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    if not is_assignee_based:
        for team in required_teams:
            if team:
                quest["team_approvals"][str(team)] = {
                    "approved": False,
                    "approved_by": None,
                    "approved_at": None,
                }
    else:
        quest["assignee_approval"] = {
            "approved": False,
            "approved_by": None,
            "approved_by_name": None,
            "approved_at": None,
        }

    return quest


__all__ = [
    "check_quest_approvals_complete",
    "create_quest_from_template",
    "get_next_stage_for_completed_quest",
    "get_quest_template_for_stage",
    "get_required_approval_teams_for_stage",
]
