"""Quest template and approval helpers."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from .constants import STAGE_NAME_TO_CODE
from .data_access import get_quest_templates


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

    if stage in ("실측", "MEASURE", "고객컨펌", "CONFIRM") and structured_data:
        orderer_name = (((structured_data.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
        if orderer_name and "라홈" in orderer_name:
            owner_team = "CS"
            required_teams = ["CS"]

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
