"""JSON-backed policy/template loading helpers."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from foms.services.orders.erp_policy_constants import (
    DEFAULT_OWNER_TEAM_BY_STAGE,
    _POLICY_PATH,
    _QUEST_TEMPLATES_PATH,
    _TEMPLATES_PATH,
)


_CACHE: Dict[str, Any] = {
    "policy_mtime": None,
    "policy": None,
    "tpl_mtime": None,
    "templates": None,
    "quest_tpl_mtime": None,
    "quest_templates": None,
}


def _safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file) or {}
    except Exception:
        return None


def _get_mtime(path: str):
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


def get_policy() -> Dict[str, Any]:
    """정책 JSON 로드(+ 캐시). 파일이 없거나 깨져도 기본값으로 동작."""
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
    merged.update(
        {
            key: value
            for key, value in loaded.items()
            if key in ("version", "rules", "teams", "automation") and value is not None
        }
    )
    if isinstance(default.get("rules"), dict) and isinstance(loaded.get("rules"), dict):
        merged["rules"] = {**default["rules"], **loaded["rules"]}
    if isinstance(default.get("teams"), dict) and isinstance(loaded.get("teams"), dict):
        merged["teams"] = {**default["teams"], **loaded["teams"]}
    if isinstance((default.get("teams") or {}).get("default_owner_team_by_stage"), dict) and isinstance(
        ((loaded.get("teams") or {}).get("default_owner_team_by_stage")),
        dict,
    ):
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
    """Stage task template JSON 로드(+ 캐시)."""
    mtime = _get_mtime(_TEMPLATES_PATH)
    if _CACHE.get("templates") is not None and _CACHE.get("tpl_mtime") == mtime:
        return _CACHE["templates"]
    default = {"version": 1, "stages": {}}
    loaded = _safe_read_json(_TEMPLATES_PATH) or {}
    merged = default
    merged.update({key: value for key, value in loaded.items() if key in ("version", "stages") and value is not None})
    if isinstance(default.get("stages"), dict) and isinstance(loaded.get("stages"), dict):
        merged["stages"] = {**default["stages"], **loaded["stages"]}
    _CACHE["tpl_mtime"] = mtime
    _CACHE["templates"] = merged
    return merged


def get_quest_templates() -> Dict[str, Any]:
    """Quest 템플릿 로드(+ 캐시)."""
    mtime = _get_mtime(_QUEST_TEMPLATES_PATH)
    if _CACHE.get("quest_templates") is not None and _CACHE.get("quest_tpl_mtime") == mtime:
        return _CACHE["quest_templates"]

    default = {"version": 1, "stages": {}}
    loaded = _safe_read_json(_QUEST_TEMPLATES_PATH) or {}
    merged = default
    merged.update({key: value for key, value in loaded.items() if key in ("version", "stages") and value is not None})
    if isinstance(default.get("stages"), dict) and isinstance(loaded.get("stages"), dict):
        merged["stages"] = {**default["stages"], **loaded["stages"]}

    _CACHE["quest_tpl_mtime"] = mtime
    _CACHE["quest_templates"] = merged
    return merged


def get_stage(sd: Dict[str, Any]) -> Optional[str]:
    """Return workflow stage from structured_data."""
    try:
        return ((sd or {}).get("workflow") or {}).get("stage")
    except Exception:
        return None


def recommend_owner_team(sd: Dict[str, Any]) -> Optional[str]:
    """저장/강제 변경 없이 stage 기반 추천 오너팀만 계산한다."""
    stage = get_stage(sd or {})
    if not stage:
        return None
    policy = get_policy()
    stage_map = ((policy.get("teams") or {}).get("default_owner_team_by_stage")) or DEFAULT_OWNER_TEAM_BY_STAGE
    if isinstance(stage_map, dict):
        return stage_map.get(stage)
    return DEFAULT_OWNER_TEAM_BY_STAGE.get(stage)


__all__ = [
    "_CACHE",
    "_get_mtime",
    "_safe_read_json",
    "get_policy",
    "get_quest_templates",
    "get_stage",
    "get_task_templates",
    "recommend_owner_team",
]
