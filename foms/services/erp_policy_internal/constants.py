"""Constants and repo-root data paths for ERP policy."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List


STAGE_LABELS: Dict[str, str] = {
    "RECEIVED": "주문접수",
    "MEASURE": "실측",
    "DRAWING": "도면",
    "CONFIRM": "고객컨펌",
    "PRODUCTION": "생산",
    "CONSTRUCTION": "시공",
    "CS": "CS",
    "COMPLETED": "완료",
    "AS": "AS처리",
    "AS_RECEIVED": "AS접수",
    "AS_COMPLETED": "AS완료",
}


DEFAULT_OWNER_TEAM_BY_STAGE: Dict[str, str] = {
    "RECEIVED": "CS",
    "MEASURE": "SALES",
    "DRAWING": "DRAWING",
    "CONFIRM": "SALES",
    "PRODUCTION": "PRODUCTION",
    "CONSTRUCTION": "CONSTRUCTION",
    "CS": "CS",
    "COMPLETED": "CS",
    "AS": "CS",
    "AS_RECEIVED": "CS",
    "AS_COMPLETED": "CS",
}


STAGE_NAME_TO_CODE: Dict[str, str] = {
    "주문접수": "RECEIVED",
    "실측": "MEASURE",
    "도면": "DRAWING",
    "고객컨펌": "CONFIRM",
    "생산": "PRODUCTION",
    "시공": "CONSTRUCTION",
    "CS": "CS",
    "완료": "COMPLETED",
    "AS처리": "AS",
    "AS접수": "AS_RECEIVED",
    "AS완료": "AS_COMPLETED",
}


STAGE_SQL_FILTER_MAP: Dict[str, List[str]] = {
    "주문접수": ['"주문접수"', '"RECEIVED"'],
    "실측": ['"실측"', '"MEASURE"'],
    "도면": ['"도면"', '"DRAWING"'],
    "고객컨펌": ['"고객컨펌"', '"CONFIRM"'],
    "생산": ['"생산"', '"PRODUCTION"'],
    "시공": ['"시공"', '"CONSTRUCTION"'],
    "CS": ['"CS"'],
    "완료": ['"완료"', '"COMPLETED"', '"AS완료"', '"AS_COMPLETED"'],
    "AS처리": ['"AS접수"', '"AS처리"', '"AS_RECEIVED"', '"AS"'],
}


STAGES_REQUIRING_TEAM: Dict[str, List[str]] = {
    "CS": ['"주문접수"', '"RECEIVED"', '"CS"', '"완료"', '"COMPLETED"', '"AS접수"', '"AS처리"', '"AS_RECEIVED"', '"AS"', '"실측"', '"MEASURE"', '"고객컨펌"', '"CONFIRM"'],
    "SALES": ['"실측"', '"MEASURE"', '"고객컨펌"', '"CONFIRM"'],
    "MEASURE": ['"실측"', '"MEASURE"'],
    "DRAWING": [],
    "PRODUCTION": ['"생산"', '"PRODUCTION"'],
    "CONSTRUCTION": [],
}


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DATA_DIR = _REPO_ROOT / "data"
_POLICY_PATH = str(_DATA_DIR / "erp_policy.json")
_TEMPLATES_PATH = str(_DATA_DIR / "erp_task_templates.json")
_QUEST_TEMPLATES_PATH = str(_DATA_DIR / "erp_quest_templates.json")


__all__ = [
    "DEFAULT_OWNER_TEAM_BY_STAGE",
    "STAGE_LABELS",
    "STAGE_NAME_TO_CODE",
    "STAGE_SQL_FILTER_MAP",
    "STAGES_REQUIRING_TEAM",
    "_POLICY_PATH",
    "_QUEST_TEMPLATES_PATH",
    "_TEMPLATES_PATH",
]
