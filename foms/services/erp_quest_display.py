"""ERP quest display SSOT — resolve current quest and approval UI fields."""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

from foms.services.erp_display import normalize_manager_name
from foms.services.erp_policy import (
    STAGE_LABELS,
    STAGE_NAME_TO_CODE,
    can_modify_domain,
    create_quest_from_template,
    get_quest_template_for_stage,
    get_required_approval_teams_for_stage,
)

__all__ = [
    "ACTIVE_QUEST_STATUSES",
    "resolve_current_quest",
    "build_current_quest_payload",
    "resolve_order_role_assignees",
    "assignee_user_ids_from_sd",
    "load_assignee_user_map",
    "load_assignee_user_map_batch",
]

ACTIVE_QUEST_STATUSES = frozenset({"OPEN", "IN_PROGRESS"})


def _stage_aliases(stage: str, stage_code: str) -> set[str]:
    """Collect label/code aliases for matching quest.stage values."""
    stage_label_from_code = STAGE_LABELS.get(stage_code, stage)
    possible = {stage, stage_code, stage_label_from_code}
    if stage in STAGE_NAME_TO_CODE:
        possible.add(STAGE_NAME_TO_CODE[stage])
    if stage_code in STAGE_LABELS:
        possible.add(STAGE_LABELS[stage_code])
    return possible


def resolve_current_quest(
    sd: dict[str, Any],
    stage: str | None,
    stage_code: str | None,
) -> dict[str, Any] | None:
    """Resolve the active quest for display (display-only synthesis allowed).

    Args:
        sd: Order structured_data.
        stage: Human-readable stage label from ``_erp_get_stage``.
        stage_code: Normalized stage code.

    Returns:
        Quest dict for UI, or None when quest UI should be hidden.
    """
    if not stage or not stage_code:
        return None
    if stage_code in ("CONSTRUCTION", "DRAWING"):
        return None

    quests = sd.get("quests") or []
    possible_stages = _stage_aliases(stage, stage_code)
    matching = [
        q for q in quests if isinstance(q, dict) and q.get("stage") in possible_stages
    ]
    if matching:
        active = [
            q
            for q in matching
            if str(q.get("status", "OPEN")).upper() in ACTIVE_QUEST_STATUSES
        ]
        if not active:
            return None
        sort_key = lambda x: (x.get("created_at") or x.get("updated_at") or "1970-01-01T00:00:00",)
        active.sort(key=sort_key, reverse=True)
        return active[0]

    quest_tpl = get_quest_template_for_stage(stage)
    if not quest_tpl:
        return None
    temp_quest = create_quest_from_template(stage, None, sd)
    if temp_quest:
        return temp_quest
    team_approvals_template = {
        str(team): {"approved": False, "approved_by": None, "approved_at": None}
        for team in quest_tpl.get("required_approvals", []) or []
        if team
    }
    return {
        "stage": stage,
        "title": quest_tpl.get("title", ""),
        "description": quest_tpl.get("description", ""),
        "owner_team": quest_tpl.get("owner_team", ""),
        "status": "OPEN",
        "team_approvals": team_approvals_template,
    }


def _apply_lahom_cs_override(current_quest: dict[str, Any], sd: dict[str, Any], stage: str) -> list[str]:
    """Apply 라홈 orderer CS team override to quest + required teams."""
    required_teams = list(get_required_approval_teams_for_stage(stage))
    if stage in ("실측", "MEASURE", "고객컨펌", "CONFIRM"):
        orderer_name = (((sd.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
        if orderer_name and "라홈" in orderer_name:
            current_quest["owner_team"] = "CS"
            required_teams = ["CS"]
            existing_cs = current_quest.get("team_approvals", {}).get("CS", {})
            approved = (
                existing_cs.get("approved", False)
                if isinstance(existing_cs, dict)
                else bool(existing_cs)
            )
            current_quest["team_approvals"] = {
                "CS": {
                    "approved": approved,
                    "approved_by": existing_cs.get("approved_by") if isinstance(existing_cs, dict) else None,
                    "approved_at": existing_cs.get("approved_at") if isinstance(existing_cs, dict) else None,
                }
            }
    return required_teams


def _compute_approval_state(
    current_quest: dict[str, Any],
    stage: str,
    sd: dict[str, Any],
) -> tuple[bool, list[str], dict[str, bool], list[str]]:
    """Return all_approved, missing_teams, team_approvals, required_teams."""
    quest_status = str(current_quest.get("status", "OPEN")).upper()
    approval_mode = current_quest.get("approval_mode") or (
        "assignee" if stage in ("실측", "MEASURE", "도면", "DRAWING", "고객컨펌", "CONFIRM") else "team"
    )
    required_teams = _apply_lahom_cs_override(current_quest, sd, stage)
    team_approvals_raw = current_quest.get("team_approvals") or {}

    if approval_mode == "assignee":
        assignee = current_quest.get("assignee_approval") or {}
        approved = bool(assignee.get("approved")) or quest_status == "COMPLETED"
        return approved, [], {}, required_teams

    missing_teams: list[str] = []
    team_approvals: dict[str, bool] = {}
    all_approved = False

    if quest_status == "OPEN":
        missing_teams = required_teams.copy() if required_teams else []
        team_approvals = {team: False for team in required_teams}
    elif quest_status == "COMPLETED":
        team_approvals = {team: True for team in required_teams}
        all_approved = True
    else:
        if not required_teams:
            all_approved = quest_status == "COMPLETED"
        else:
            for team in required_teams:
                ad = team_approvals_raw.get(str(team)) or team_approvals_raw.get(team)
                team_approvals[team] = (
                    ad.get("approved", False)
                    if isinstance(ad, dict)
                    else bool(ad) if ad is not None else False
                )
            missing_teams = [t for t in required_teams if not team_approvals.get(t, False)]
            all_approved = len(missing_teams) == 0

    return all_approved, missing_teams, team_approvals, required_teams


def _assignee_display_names(
    sd: dict[str, Any],
    stage_code: str,
    current_quest: dict[str, Any],
    order: Any,
    user_map: dict[int, str],
) -> list[str]:
    """Resolve assignee display names for assignee-approval quests."""
    assignments = sd.get("assignments") or {}
    user_ids: list[int] = []
    if stage_code in ("MEASURE", "CONFIRM"):
        user_ids = assignments.get("sales_assignee_user_ids") or []
    elif stage_code == "DRAWING":
        user_ids = assignments.get("drawing_assignee_user_ids") or []
        if not user_ids:
            for a in (assignments.get("drawing_assignees") or []) + (sd.get("drawing_assignees") or []):
                if isinstance(a, dict) and a.get("id"):
                    user_ids.append(a["id"])
    user_ids = [int(uid) for uid in user_ids if isinstance(uid, (int, str)) and str(uid).isdigit()]
    names: list[str] = []
    if user_ids:
        for uid in user_ids:
            mapped = user_map.get(uid)
            if isinstance(mapped, str) and mapped:
                names.append(mapped)
    elif stage_code in ("MEASURE", "CONFIRM"):
        mgr = (
            ((sd.get("parties") or {}).get("manager") or {}).get("name")
            or getattr(order, "manager_name", None)
            or current_quest.get("owner_person")
            or ""
        )
        if str(mgr).strip():
            names = [str(mgr).strip()]
    return names


def _join_display_names(names: list[str]) -> str:
    """담당자 표시명 목록을 UI용 단일 문자열로 합친다."""
    cleaned = [str(name).strip() for name in names if str(name or "").strip()]
    return ", ".join(cleaned) if cleaned else "-"


def resolve_order_role_assignees(
    sd: dict[str, Any],
    order: Any = None,
    user_map: dict[int, str] | None = None,
) -> dict[str, str]:
    """실측/도면/시공 담당 표시명을 structured_data에서 해석한다.

    Args:
        sd: Order.structured_data
        order: Order ORM(실측 담당 manager fallback용, 선택)
        user_map: user_id → 표시명 (sales/drawing assignee id 해석용)

    Returns:
        measurement_assignee, drawing_assignee, construction_assignee 키를 가진 dict
    """
    user_map = user_map or {}
    assignments = sd.get("assignments") or {}
    shipment = sd.get("shipment") or {}
    parties = sd.get("parties") or {}

    sales_ids: list[int] = []
    for raw in assignments.get("sales_assignee_user_ids") or []:
        if isinstance(raw, int):
            sales_ids.append(raw)
        elif isinstance(raw, str) and raw.isdigit():
            sales_ids.append(int(raw))
    measurement_names = [user_map[uid] for uid in sales_ids if uid in user_map]
    if not measurement_names:
        raw_manager = ((parties.get("manager") or {}).get("name"))
        if raw_manager is None and order is not None:
            raw_manager = getattr(order, "manager_name", None)
        try:
            manager_uid = int(raw_manager)  # type: ignore[arg-type]
            if manager_uid in user_map:
                measurement_names = [user_map[manager_uid]]
        except (TypeError, ValueError):
            pass
    if not measurement_names:
        resolved = normalize_manager_name(
            ((parties.get("manager") or {}).get("name")),
            getattr(order, "manager_name", None) if order is not None else "",
        )
        if str(resolved or "").strip() and str(resolved).strip() != "-":
            measurement_names = [str(resolved).strip()]

    drawing_names: list[str] = []
    drawing_ids: list[int] = []
    for assignee in sd.get("drawing_assignees") or []:
        if isinstance(assignee, dict):
            name = str(assignee.get("name") or "").strip()
            if name:
                drawing_names.append(name)
            elif assignee.get("id") is not None:
                try:
                    drawing_ids.append(int(assignee["id"]))
                except (TypeError, ValueError):
                    pass
    for raw in assignments.get("drawing_assignee_user_ids") or []:
        if isinstance(raw, int):
            drawing_ids.append(raw)
        elif isinstance(raw, str) and raw.isdigit():
            drawing_ids.append(int(raw))
    if not drawing_names and drawing_ids:
        drawing_names = [user_map[uid] for uid in dict.fromkeys(drawing_ids) if uid in user_map]
    if not drawing_names:
        drawing_manager = str(shipment.get("drawing_manager") or "").strip()
        if drawing_manager:
            drawing_names = [drawing_manager]
        else:
            for raw in shipment.get("drawing_managers") or []:
                name = str(raw or "").strip()
                if name:
                    drawing_names.append(name)

    construction_names: list[str] = []
    for raw in shipment.get("construction_workers") or []:
        if isinstance(raw, str):
            name = raw.strip()
        elif isinstance(raw, dict):
            name = str(raw.get("name") or "").strip()
        else:
            name = str(raw or "").strip()
        if name and name not in construction_names:
            construction_names.append(name)
    if not construction_names:
        legacy_worker = shipment.get("construction_worker")
        if isinstance(legacy_worker, str) and legacy_worker.strip():
            construction_names = [legacy_worker.strip()]

    return {
        "measurement_assignee": _join_display_names(measurement_names),
        "drawing_assignee": _join_display_names(drawing_names),
        "construction_assignee": _join_display_names(construction_names),
    }


def _compute_can_assignee_approve(
    current_user: Any,
    order: Any,
    sd: dict[str, Any],
    stage_code: str,
    current_quest: dict[str, Any],
) -> bool:
    """Whether current_user may approve an assignee-mode quest."""
    if not current_user or not current_quest:
        return False
    approval_mode = current_quest.get("approval_mode") or (
        "assignee" if stage_code in ("MEASURE", "DRAWING", "CONFIRM") else "team"
    )
    if approval_mode != "assignee":
        return False

    domain = (
        "DRAWING_DOMAIN"
        if stage_code == "DRAWING"
        else ("SALES_DOMAIN" if stage_code in ("MEASURE", "CONFIRM") else None)
    )
    if not domain:
        return False

    can_assignee = can_modify_domain(current_user, order, domain, False, None)
    if can_assignee:
        return True

    if domain != "SALES_DOMAIN":
        return False

    assignments = sd.get("assignments") or {}
    user_ids = assignments.get("sales_assignee_user_ids") or []
    user_ids = [int(uid) for uid in user_ids if isinstance(uid, (int, str)) and str(uid).isdigit()]
    if user_ids:
        return False

    manager_names: set[str] = set()
    for src in [
        ((sd.get("parties") or {}).get("manager") or {}).get("name"),
        getattr(order, "manager_name", None),
        current_quest.get("owner_person"),
    ]:
        if str(src or "").strip():
            manager_names.add(str(src).strip().lower())
    un = (getattr(current_user, "name", None) or "").strip().lower()
    uu = (getattr(current_user, "username", None) or "").strip().lower()
    return un in manager_names or uu in manager_names


def build_current_quest_payload(
    *,
    sd: dict[str, Any],
    stage: str | None,
    stage_code: str | None,
    order: Any,
    current_user: Any = None,
    user_map: dict[int, str] | None = None,
) -> dict[str, Any] | None:
    """Build template-ready current_quest payload for queue/detail views."""
    current_quest = resolve_current_quest(sd, stage, stage_code)
    if not current_quest:
        return None
    current_quest = copy.deepcopy(current_quest)

    stage_key = stage if isinstance(stage, str) else ""
    stage_code_key = stage_code or STAGE_NAME_TO_CODE.get(stage_key, stage_key)
    all_approved, missing_teams, team_approvals, required_teams = _compute_approval_state(
        current_quest, stage_key, sd
    )
    approval_mode = current_quest.get("approval_mode") or (
        "assignee" if stage_code_key in ("MEASURE", "DRAWING", "CONFIRM") else "team"
    )
    assignee_display_names = (
        _assignee_display_names(sd, stage_code_key, current_quest, order, user_map or {})
        if approval_mode == "assignee"
        else []
    )
    can_assignee_approve = _compute_can_assignee_approve(
        current_user, order, sd, stage_code_key, current_quest
    )

    return {
        "title": current_quest.get("title", ""),
        "description": current_quest.get("description", ""),
        "owner_team": current_quest.get("owner_team", ""),
        "status": current_quest.get("status", "OPEN"),
        "all_approved": all_approved,
        "missing_teams": missing_teams,
        "required_approvals": required_teams,
        "team_approvals": team_approvals,
        "approval_mode": approval_mode,
        "assignee_approval": current_quest.get("assignee_approval") or {},
        "assignee_display_names": assignee_display_names,
        "can_assignee_approve": can_assignee_approve,
    }


def assignee_user_ids_from_sd(sd: dict[str, Any]) -> set[int]:
    """structured_data가 참조하는 담당자 user id 집합(영업/도면 배정)."""
    assignments = sd.get("assignments") or {}
    user_ids: set[int] = set()
    for raw in assignments.get("sales_assignee_user_ids") or []:
        if isinstance(raw, int):
            user_ids.add(raw)
        elif isinstance(raw, str) and raw.isdigit():
            user_ids.add(int(raw))
    for raw in assignments.get("drawing_assignee_user_ids") or []:
        if isinstance(raw, int):
            user_ids.add(raw)
        elif isinstance(raw, str) and raw.isdigit():
            user_ids.add(int(raw))
    for a in (assignments.get("drawing_assignees") or []) + (sd.get("drawing_assignees") or []):
        if isinstance(a, dict) and a.get("id"):
            try:
                user_ids.add(int(a["id"]))
            except (TypeError, ValueError):
                pass
    manager_raw = ((sd.get("parties") or {}).get("manager") or {}).get("name")
    if isinstance(manager_raw, int):
        user_ids.add(manager_raw)
    elif isinstance(manager_raw, str) and manager_raw.isdigit():
        user_ids.add(int(manager_raw))
    return user_ids


def _user_id_name_map(db, user_ids: set[int]) -> dict[int, str]:
    """user id 집합 → 표시명 map (1회 in_ 조회)."""
    if not user_ids:
        return {}
    try:
        from models import User

        rows = db.query(User).filter(User.id.in_(user_ids)).all()
    except Exception as exc:
        logger.warning("load_assignee_user_map failed: %s", exc)
        return {}
    out: dict[int, str] = {}
    for u in rows:
        uid = getattr(u, "id", None)
        name = getattr(u, "name", None)
        if isinstance(uid, int) and isinstance(name, str) and name:
            out[uid] = name
    return out


def load_assignee_user_map(db, sd: dict[str, Any]) -> dict[int, str]:
    """Load user id → display name map for assignee ids referenced in structured_data."""
    return _user_id_name_map(db, assignee_user_ids_from_sd(sd))


def load_assignee_user_map_batch(db, sds: list[dict[str, Any]]) -> dict[int, str]:
    """여러 structured_data의 담당자 id를 합집합으로 1회 조회(모바일 큐 N+1 제거).

    id로 키된 map이므로 각 주문은 자신이 참조하는 id만 조회하던 결과와 동일하게 동작한다.
    """
    all_ids: set[int] = set()
    for sd in sds:
        all_ids |= assignee_user_ids_from_sd(sd or {})
    return _user_id_name_map(db, all_ids)
