"""Automatic task policy helpers."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from foms.services.orders.erp_policy_data_access import (
    get_policy,
    get_stage,
    get_task_templates,
    recommend_owner_team,
)
from foms.services.error_logging import log_handled_exception


def _business_days_until(date_iso: str):
    """Lazy import to avoid eager business_calendar coupling at import time."""
    from foms.services.common.business_calendar import business_days_until

    return business_days_until(date_iso)


@dataclass(frozen=True)
class AutoTaskSpec:
    auto_key: str
    title: str
    owner_team: Optional[str]
    due_date: Optional[str]
    meta: Dict[str, Any]


def _parse_date(value: Any) -> Optional[datetime.date]:
    try:
        if not value:
            return None
        return datetime.date.fromisoformat(str(value))
    except Exception:
        return None


def build_auto_tasks(sd: Dict[str, Any], now: Optional[datetime.datetime] = None) -> List[AutoTaskSpec]:
    """structured_data 기반 자동 Task spec 목록을 만든다."""
    now_dt = now or datetime.datetime.now()
    out: List[AutoTaskSpec] = []
    sd = sd or {}

    policy = get_policy()
    rules = (policy.get("rules") or {}) if isinstance(policy.get("rules"), dict) else {}
    automation = (policy.get("automation") or {}) if isinstance(policy.get("automation"), dict) else {}
    enabled_keys = set(automation.get("enabled_auto_keys") or [])
    if automation.get("enable_auto_tasks") is False:
        enabled_keys = set()

    stage = get_stage(sd) or ""
    stage_updated_at = ((sd.get("workflow") or {}).get("stage_updated_at"))
    owner_team = ((sd.get("assignments") or {}).get("owner_team")) or None

    meas_date_s = (((sd.get("schedule") or {}).get("measurement") or {}).get("date"))
    cons_date_s = (((sd.get("schedule") or {}).get("construction") or {}).get("date"))
    meas_date = _parse_date(meas_date_s)
    cons_date = _parse_date(cons_date_s)

    urgent = bool((sd.get("flags") or {}).get("urgent"))
    if urgent and "AUTO_URGENT" in enabled_keys:
        out.append(
            AutoTaskSpec(
                auto_key="AUTO_URGENT",
                title="긴급 발주 팔로업",
                owner_team=owner_team or "CS",
                due_date=str(cons_date_s or meas_date_s or "") or None,
                meta={"auto_key": "AUTO_URGENT", "reason": (sd.get("flags") or {}).get("urgent_reason")},
            )
        )

    blueprint_hours = int(rules.get("blueprint_sla_hours", 48) or 48)
    if stage in ("DRAWING", "CONFIRM") and stage_updated_at and "AUTO_BLUEPRINT_48H" in enabled_keys:
        try:
            timestamp = datetime.datetime.fromisoformat(str(stage_updated_at))
            due_at = timestamp + datetime.timedelta(hours=blueprint_hours)
            out.append(
                AutoTaskSpec(
                    auto_key="AUTO_BLUEPRINT_48H",
                    title="도면 48시간 SLA",
                    owner_team=owner_team or "DRAWING",
                    due_date=due_at.date().isoformat(),
                    meta={"auto_key": "AUTO_BLUEPRINT_48H", "due_at": due_at.isoformat()},
                )
            )
        except Exception:
            log_handled_exception("policy task append")

    if meas_date:
        days_until = _business_days_until(meas_date.isoformat())
        threshold = int(rules.get("measurement_imminent_business_days", 4) or 4)
        if days_until is not None and 0 <= days_until <= threshold and "AUTO_MEASURE_D4" in enabled_keys:
            out.append(
                AutoTaskSpec(
                    auto_key="AUTO_MEASURE_D4",
                    title="실측 D-4 임박 체크",
                    owner_team=owner_team or "MEASURE",
                    due_date=meas_date.isoformat(),
                    meta={
                        "auto_key": "AUTO_MEASURE_D4",
                        "measurement_date": meas_date.isoformat(),
                        "d": days_until,
                    },
                )
            )

    if cons_date:
        days_until = _business_days_until(cons_date.isoformat())
        construction_threshold = int(rules.get("construction_imminent_business_days", 3) or 3)
        production_threshold = int(rules.get("production_imminent_business_days", 2) or 2)
        if days_until is not None and 0 <= days_until <= construction_threshold and "AUTO_CONSTRUCT_D3" in enabled_keys:
            out.append(
                AutoTaskSpec(
                    auto_key="AUTO_CONSTRUCT_D3",
                    title="시공 D-3 임박 체크",
                    owner_team="CONSTRUCTION",
                    due_date=cons_date.isoformat(),
                    meta={
                        "auto_key": "AUTO_CONSTRUCT_D3",
                        "construction_date": cons_date.isoformat(),
                        "d": days_until,
                    },
                )
            )
        if days_until is not None and 0 <= days_until <= production_threshold and "AUTO_PRODUCTION_D2" in enabled_keys:
            out.append(
                AutoTaskSpec(
                    auto_key="AUTO_PRODUCTION_D2",
                    title="생산 D-2 임박 체크",
                    owner_team="PRODUCTION",
                    due_date=cons_date.isoformat(),
                    meta={
                        "auto_key": "AUTO_PRODUCTION_D2",
                        "construction_date": cons_date.isoformat(),
                        "d": days_until,
                    },
                )
            )

    if automation.get("enable_stage_templates") is not False:
        out.extend(build_stage_template_tasks(sd, now=now_dt))

    return out


def _resolve_due_date(due: Dict[str, Any], sd: Dict[str, Any], now_dt: datetime.datetime) -> Optional[str]:
    if not isinstance(due, dict):
        return None
    due_type = due.get("type")
    if due_type == "measurement_date":
        base = _parse_date((((sd.get("schedule") or {}).get("measurement") or {}).get("date")))
        if not base:
            return None
        offset_business_days = due.get("offset_business_days")
        if offset_business_days is None:
            return base.isoformat()
        try:
            from foms.services.common.business_calendar import add_business_days

            return add_business_days(base, int(offset_business_days)).isoformat()
        except Exception:
            return base.isoformat()
    if due_type == "construction_date":
        base = _parse_date((((sd.get("schedule") or {}).get("construction") or {}).get("date")))
        if not base:
            return None
        offset_business_days = due.get("offset_business_days")
        if offset_business_days is None:
            return base.isoformat()
        try:
            from foms.services.common.business_calendar import add_business_days

            return add_business_days(base, int(offset_business_days)).isoformat()
        except Exception:
            return base.isoformat()
    if due_type == "blueprint_sla":
        workflow = sd.get("workflow") or {}
        raw_timestamp = workflow.get("stage_updated_at")
        if not raw_timestamp:
            return None
        try:
            timestamp = datetime.datetime.fromisoformat(str(raw_timestamp))
        except Exception:
            return None
        offset_hours = int(due.get("offset_hours", 48) or 48)
        return (timestamp + datetime.timedelta(hours=offset_hours)).date().isoformat()
    if due_type == "today":
        offset_business_days = due.get("offset_business_days")
        if offset_business_days is None:
            return now_dt.date().isoformat()
        try:
            from foms.services.common.business_calendar import add_business_days

            return add_business_days(now_dt.date(), int(offset_business_days)).isoformat()
        except Exception:
            return now_dt.date().isoformat()
    return None


def build_stage_template_tasks(sd: Dict[str, Any], now: Optional[datetime.datetime] = None) -> List[AutoTaskSpec]:
    """현재 stage용 템플릿 Task spec 목록을 계산한다."""
    now_dt = now or datetime.datetime.now()
    sd = sd or {}
    stage = get_stage(sd) or ""
    if not stage:
        return []

    template = get_task_templates()
    stages = (template.get("stages") or {}) if isinstance(template.get("stages"), dict) else {}
    items = stages.get(stage) or []
    if not isinstance(items, list):
        return []

    recommended_team = (sd.get("assignments") or {}).get("owner_team") or recommend_owner_team(sd)
    out: List[AutoTaskSpec] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (item.get("key") or "").strip()
        title = (item.get("title") or "").strip()
        if not key or not title:
            continue
        owner = item.get("owner_team") or recommended_team
        due_date = _resolve_due_date(item.get("due") or {}, sd, now_dt)
        auto_key = f"TEMPLATE_{stage}_{key}"
        out.append(
            AutoTaskSpec(
                auto_key=auto_key,
                title=title,
                owner_team=owner,
                due_date=due_date,
                meta={"auto_key": auto_key, "template_stage": stage, "template_key": key},
            )
        )
    return out


def get_required_task_keys_for_stage(stage: Optional[str]) -> List[str]:
    """주어진 단계의 필수 Task 템플릿 key 목록을 반환한다."""
    if not stage:
        return []

    template = get_task_templates()
    stages = (template.get("stages") or {}) if isinstance(template.get("stages"), dict) else {}
    items = stages.get(stage) or []
    if not isinstance(items, list):
        return []

    keys = []
    for item in items:
        if isinstance(item, dict):
            key = (item.get("key") or "").strip()
            if key:
                keys.append(key)
    return keys


__all__ = [
    "AutoTaskSpec",
    "_business_days_until",
    "_parse_date",
    "_resolve_due_date",
    "build_auto_tasks",
    "build_stage_template_tasks",
    "get_required_task_keys_for_stage",
]
