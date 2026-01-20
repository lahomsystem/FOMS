"""
ERP Policy (룰/정책) 모듈

- 이후 수정 용이하게 "룰 정의"를 한 곳에 모아둔다.
- DB/Flask에 의존하지 않는 순수 함수 중심으로 구성한다.
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from business_calendar import business_days_until


# -----------------------------
# Stage / Team
# -----------------------------

STAGE_LABELS: Dict[str, str] = {
    "RECEIVED": "주문접수",
    "HAPPYCALL": "해피콜(CS)",
    "MEASURE": "실측",
    "DRAWING": "도면",
    "CONFIRM": "고객컨펌",
    "PRODUCTION": "생산",
    "CONSTRUCTION": "시공",
}


DEFAULT_OWNER_TEAM_BY_STAGE: Dict[str, str] = {
    "RECEIVED": "SALES",
    "HAPPYCALL": "CS",
    "MEASURE": "MEASURE",
    "DRAWING": "DRAWING",
    "CONFIRM": "DRAWING",
    "PRODUCTION": "PRODUCTION",
    "CONSTRUCTION": "CONSTRUCTION",
}

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_POLICY_PATH = os.path.join(_DATA_DIR, "erp_policy.json")
_TEMPLATES_PATH = os.path.join(_DATA_DIR, "erp_task_templates.json")

_CACHE: Dict[str, Any] = {
    "policy_mtime": None,
    "policy": None,
    "tpl_mtime": None,
    "templates": None,
}


def _safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return None


def _get_mtime(path: str):
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


def get_policy() -> Dict[str, Any]:
    """
    정책 JSON 로드(+ 캐시). 파일이 없거나 깨져도 기본값으로 동작.
    """
    mtime = _get_mtime(_POLICY_PATH)
    if _CACHE.get("policy") is not None and _CACHE.get("policy_mtime") == mtime:
        return _CACHE["policy"]

    default = {
        "version": 1,
        "rules": {
            "blueprint_sla_hours": 48,
            "measurement_imminent_business_days": 4,
            "construction_imminent_business_days": 3,
            "production_imminent_business_days": 2,
        },
        "teams": {"default_owner_team_by_stage": DEFAULT_OWNER_TEAM_BY_STAGE},
        "automation": {
            "enable_auto_tasks": True,
            "enable_stage_templates": True,
            "enabled_auto_keys": [
                "AUTO_URGENT",
                "AUTO_BLUEPRINT_48H",
                "AUTO_MEASURE_D4",
                "AUTO_CONSTRUCT_D3",
                "AUTO_PRODUCTION_D2",
            ],
        },
    }

    loaded = _safe_read_json(_POLICY_PATH) or {}
    merged = default
    # shallow merge + nested merges we care about
    merged.update({k: v for k, v in loaded.items() if k in ("version", "rules", "teams", "automation") and v is not None})
    if isinstance(default.get("rules"), dict) and isinstance(loaded.get("rules"), dict):
        merged["rules"] = {**default["rules"], **loaded["rules"]}
    if isinstance(default.get("teams"), dict) and isinstance(loaded.get("teams"), dict):
        merged["teams"] = {**default["teams"], **loaded["teams"]}
    if isinstance((default.get("teams") or {}).get("default_owner_team_by_stage"), dict) and isinstance(((loaded.get("teams") or {}).get("default_owner_team_by_stage")), dict):
        merged["teams"]["default_owner_team_by_stage"] = {
            **default["teams"]["default_owner_team_by_stage"],
            **loaded["teams"]["default_owner_team_by_stage"],
        }
    if isinstance(default.get("automation"), dict) and isinstance(loaded.get("automation"), dict):
        merged["automation"] = {**default["automation"], **loaded["automation"]}

    _CACHE["policy_mtime"] = mtime
    _CACHE["policy"] = merged
    return merged


def get_task_templates() -> Dict[str, Any]:
    mtime = _get_mtime(_TEMPLATES_PATH)
    if _CACHE.get("templates") is not None and _CACHE.get("tpl_mtime") == mtime:
        return _CACHE["templates"]
    default = {"version": 1, "stages": {}}
    loaded = _safe_read_json(_TEMPLATES_PATH) or {}
    merged = default
    merged.update({k: v for k, v in loaded.items() if k in ("version", "stages") and v is not None})
    if isinstance(default.get("stages"), dict) and isinstance(loaded.get("stages"), dict):
        merged["stages"] = {**default["stages"], **loaded["stages"]}
    _CACHE["tpl_mtime"] = mtime
    _CACHE["templates"] = merged
    return merged


def get_stage(sd: Dict[str, Any]) -> Optional[str]:
    try:
        return ((sd or {}).get("workflow") or {}).get("stage")
    except Exception:
        return None


def recommend_owner_team(sd: Dict[str, Any]) -> Optional[str]:
    """
    저장/강제 변경 없이, "추천 오너팀"만 계산.
    - 기본은 stage 기반, 없으면 None
    """
    st = get_stage(sd or {})
    if not st:
        return None
    policy = get_policy()
    stage_map = ((policy.get("teams") or {}).get("default_owner_team_by_stage")) or DEFAULT_OWNER_TEAM_BY_STAGE
    if isinstance(stage_map, dict):
        return stage_map.get(st)
    return DEFAULT_OWNER_TEAM_BY_STAGE.get(st)


# -----------------------------
# Auto Task Policy
# -----------------------------

@dataclass(frozen=True)
class AutoTaskSpec:
    auto_key: str
    title: str
    owner_team: Optional[str]
    due_date: Optional[str]  # YYYY-MM-DD
    meta: Dict[str, Any]


def _parse_date(s: Any) -> Optional[datetime.date]:
    try:
        if not s:
            return None
        return datetime.date.fromisoformat(str(s))
    except Exception:
        return None


def build_auto_tasks(sd: Dict[str, Any], now: Optional[datetime.datetime] = None) -> List[AutoTaskSpec]:
    """
    structured_data 기반으로 생성/업데이트해야 할 자동 Task 목록을 만든다.
    - 여기서는 "무엇을 만들지"만 결정하고, DB upsert는 다른 모듈이 수행한다.
    """
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

    # urgent
    urgent = bool((sd.get("flags") or {}).get("urgent"))
    if urgent and "AUTO_URGENT" in enabled_keys:
        out.append(AutoTaskSpec(
            auto_key="AUTO_URGENT",
            title="긴급 발주 팔로업",
            owner_team=owner_team or "CS",
            due_date=str(cons_date_s or meas_date_s or "") or None,
            meta={"auto_key": "AUTO_URGENT", "reason": (sd.get("flags") or {}).get("urgent_reason")},
        ))

    # blueprint 48h
    blueprint_hours = int(rules.get("blueprint_sla_hours", 48) or 48)
    if stage in ("DRAWING", "CONFIRM") and stage_updated_at and "AUTO_BLUEPRINT_48H" in enabled_keys:
        try:
            ts = datetime.datetime.fromisoformat(str(stage_updated_at))
            due_at = ts + datetime.timedelta(hours=blueprint_hours)
            out.append(AutoTaskSpec(
                auto_key="AUTO_BLUEPRINT_48H",
                title="도면 48시간 SLA",
                owner_team=owner_team or "DRAWING",
                due_date=due_at.date().isoformat(),
                meta={"auto_key": "AUTO_BLUEPRINT_48H", "due_at": due_at.isoformat()},
            ))
        except Exception:
            pass

    # measurement D-4
    if meas_date:
        d = business_days_until(meas_date.isoformat())
        threshold = int(rules.get("measurement_imminent_business_days", 4) or 4)
        if d is not None and 0 <= d <= threshold and "AUTO_MEASURE_D4" in enabled_keys:
            out.append(AutoTaskSpec(
                auto_key="AUTO_MEASURE_D4",
                title="실측 D-4 임박 체크",
                owner_team=owner_team or "MEASURE",
                due_date=meas_date.isoformat(),
                meta={"auto_key": "AUTO_MEASURE_D4", "measurement_date": meas_date.isoformat(), "d": d},
            ))

    # construction D-3 and production D-2 (based on construction date)
    if cons_date:
        d = business_days_until(cons_date.isoformat())
        th3 = int(rules.get("construction_imminent_business_days", 3) or 3)
        th2 = int(rules.get("production_imminent_business_days", 2) or 2)
        if d is not None and 0 <= d <= th3 and "AUTO_CONSTRUCT_D3" in enabled_keys:
            out.append(AutoTaskSpec(
                auto_key="AUTO_CONSTRUCT_D3",
                title="시공 D-3 임박 체크",
                owner_team="CONSTRUCTION",
                due_date=cons_date.isoformat(),
                meta={"auto_key": "AUTO_CONSTRUCT_D3", "construction_date": cons_date.isoformat(), "d": d},
            ))
        if d is not None and 0 <= d <= th2 and "AUTO_PRODUCTION_D2" in enabled_keys:
            out.append(AutoTaskSpec(
                auto_key="AUTO_PRODUCTION_D2",
                title="생산 D-2 임박 체크",
                owner_team="PRODUCTION",
                due_date=cons_date.isoformat(),
                meta={"auto_key": "AUTO_PRODUCTION_D2", "construction_date": cons_date.isoformat(), "d": d},
            ))

    # stage templates (optional)
    if automation.get("enable_stage_templates") is not False:
        out.extend(build_stage_template_tasks(sd, now=now_dt))

    return out


def _resolve_due_date(due: Dict[str, Any], sd: Dict[str, Any], now_dt: datetime.datetime) -> Optional[str]:
    if not isinstance(due, dict):
        return None
    typ = due.get("type")
    if typ == "measurement_date":
        base = _parse_date((((sd.get("schedule") or {}).get("measurement") or {}).get("date")))
        if not base:
            return None
        off_bd = due.get("offset_business_days")
        if off_bd is None:
            return base.isoformat()
        try:
            from business_calendar import add_business_days
            return add_business_days(base, int(off_bd)).isoformat()
        except Exception:
            return base.isoformat()
    if typ == "construction_date":
        base = _parse_date((((sd.get("schedule") or {}).get("construction") or {}).get("date")))
        if not base:
            return None
        off_bd = due.get("offset_business_days")
        if off_bd is None:
            return base.isoformat()
        try:
            from business_calendar import add_business_days
            return add_business_days(base, int(off_bd)).isoformat()
        except Exception:
            return base.isoformat()
    if typ == "blueprint_sla":
        # stage_updated_at 기준 offset_hours 적용(기본 48)
        wf = (sd.get("workflow") or {})
        ts_raw = wf.get("stage_updated_at")
        if not ts_raw:
            return None
        try:
            ts = datetime.datetime.fromisoformat(str(ts_raw))
        except Exception:
            return None
        off_h = int(due.get("offset_hours", 48) or 48)
        return (ts + datetime.timedelta(hours=off_h)).date().isoformat()
    if typ == "today":
        off_bd = due.get("offset_business_days")
        if off_bd is None:
            return now_dt.date().isoformat()
        try:
            from business_calendar import add_business_days
            return add_business_days(now_dt.date(), int(off_bd)).isoformat()
        except Exception:
            return now_dt.date().isoformat()
    return None


def build_stage_template_tasks(sd: Dict[str, Any], now: Optional[datetime.datetime] = None) -> List[AutoTaskSpec]:
    now_dt = now or datetime.datetime.now()
    sd = sd or {}
    stage = get_stage(sd) or ""
    if not stage:
        return []

    tpl = get_task_templates()
    stages = (tpl.get("stages") or {}) if isinstance(tpl.get("stages"), dict) else {}
    items = stages.get(stage) or []
    if not isinstance(items, list):
        return []

    # owner_team fallback: 정책 추천 -> stage 기본
    rec_team = (sd.get("assignments") or {}).get("owner_team") or recommend_owner_team(sd)

    out: List[AutoTaskSpec] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        key = (it.get("key") or "").strip()
        title = (it.get("title") or "").strip()
        if not key or not title:
            continue
        owner = (it.get("owner_team") or rec_team)
        due = _resolve_due_date(it.get("due") or {}, sd, now_dt)
        auto_key = f"TEMPLATE_{stage}_{key}"
        out.append(AutoTaskSpec(
            auto_key=auto_key,
            title=title,
            owner_team=owner,
            due_date=due,
            meta={"auto_key": auto_key, "template_stage": stage, "template_key": key},
        ))
    return out

