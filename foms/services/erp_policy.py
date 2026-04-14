"""
ERP Policy canonical wrapper.

- public import path `foms.services.erp_policy`는 유지한다.
- 내부 구현은 `erp_policy_internal/*`로 분해한다.
"""

from __future__ import annotations

from foms.services.erp_policy_internal.constants import (
    DEFAULT_OWNER_TEAM_BY_STAGE,
    ORDER_SETTLEMENT_ALERT_TARGET_STATUSES,
    STAGE_LABELS,
    STAGE_NAME_TO_CODE,
    STAGE_SQL_FILTER_MAP,
    STAGES_REQUIRING_TEAM,
    _POLICY_PATH,
    _QUEST_TEMPLATES_PATH,
    _TEMPLATES_PATH,
)
from foms.services.erp_policy_internal.data_access import (
    _CACHE,
    _get_mtime,
    _safe_read_json,
    get_policy,
    get_quest_templates,
    get_stage,
    get_task_templates,
    recommend_owner_team,
)
from foms.services.erp_policy_internal.permissions import (
    can_modify_by_team_policy,
    can_modify_domain,
    get_assignee_ids,
)
from foms.services.erp_policy_internal.quests import (
    check_quest_approvals_complete,
    create_quest_from_template,
    get_next_stage_for_completed_quest,
    get_quest_template_for_stage,
    get_required_approval_teams_for_stage,
)
from foms.services.erp_policy_internal.tasks import (
    AutoTaskSpec,
    _business_days_until,
    _parse_date,
    _resolve_due_date,
    build_auto_tasks,
    build_stage_template_tasks,
    get_required_task_keys_for_stage,
)

__all__ = [
    "ORDER_SETTLEMENT_ALERT_TARGET_STATUSES",
    "STAGE_LABELS",
    "DEFAULT_OWNER_TEAM_BY_STAGE",
    "STAGE_NAME_TO_CODE",
    "STAGE_SQL_FILTER_MAP",
    "STAGES_REQUIRING_TEAM",
    "get_policy",
    "get_task_templates",
    "get_stage",
    "recommend_owner_team",
    "AutoTaskSpec",
    "build_auto_tasks",
    "build_stage_template_tasks",
    "get_required_task_keys_for_stage",
    "get_quest_templates",
    "get_quest_template_for_stage",
    "get_required_approval_teams_for_stage",
    "get_next_stage_for_completed_quest",
    "check_quest_approvals_complete",
    "create_quest_from_template",
    "get_assignee_ids",
    "can_modify_domain",
    "can_modify_by_team_policy",
]
