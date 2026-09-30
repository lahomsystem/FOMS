"""팀 코드 → 화면 팀 이름 정본."""

from __future__ import annotations

__all__ = ["TEAM_LABELS", "team_label"]

TEAM_LABELS: dict[str, str] = {
    "CS": "CS팀",
    "SALES": "영업팀",
    "MEASURE": "실측팀",
    "DRAWING": "도면팀",
    "PRODUCTION": "생산팀",
    "CONSTRUCTION": "시공팀",
    "SHIPMENT": "출고팀",
}


def team_label(code: object) -> str:
    key = str(code or "").strip()
    return TEAM_LABELS.get(key, key)
