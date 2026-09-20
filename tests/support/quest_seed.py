"""테스트용 quest 시드 헬퍼 — 생산 시작 게이트가 CONFIRM quest 를 요구하게 된 뒤(2026-09-20 F2)
CONFIRM 주문으로 ``production/start`` 를 부르는 테스트가 공통으로 쓰는 quest dict 를 만든다.

모양은 ``create_quest_from_template`` 의 assignee 모드 결과와 같다(필수 팀 CS·SALES).
"""
from __future__ import annotations

from typing import Any

CONFIRM_REQUIRED_TEAMS = ["CS", "SALES"]


def confirm_quest_completed(
    *,
    stage: str = "CONFIRM",
    approved_by: int = 12,
    approved_by_name: str = "담당",
    approved_at: str = "2026-09-16T10:00:00",
    **overrides: Any,
) -> dict:
    """담당자 승인이 끝나 COMPLETED 인 고객 컨펌 quest(assignee 모드).

    ``stage`` 에 한글 저장형 ``'고객컨펌'`` 을 넣으면 별칭 매칭 경로를 검증할 수 있다.
    ``overrides`` 는 마지막에 얹어 아무 키나 덮어쓴다.
    """
    quest = {
        "stage": stage,
        "title": "고객 컨펌",
        "status": "COMPLETED",
        "approval_mode": "assignee",
        "required_approvals": list(CONFIRM_REQUIRED_TEAMS),
        "team_approvals": {},
        "assignee_approval": {
            "approved": True,
            "approved_by": approved_by,
            "approved_by_name": approved_by_name,
            "approved_at": approved_at,
        },
        "completed_at": approved_at,
    }
    quest.update(overrides)
    return quest


def confirm_quest_open(*, stage: str = "CONFIRM", **overrides: Any) -> dict:
    """아직 담당자 승인이 없는 OPEN 고객 컨펌 quest(assignee 모드)."""
    quest = {
        "stage": stage,
        "title": "고객 컨펌",
        "status": "OPEN",
        "approval_mode": "assignee",
        "required_approvals": list(CONFIRM_REQUIRED_TEAMS),
        "team_approvals": {},
        "assignee_approval": {
            "approved": False,
            "approved_by": None,
            "approved_by_name": None,
            "approved_at": None,
        },
    }
    quest.update(overrides)
    return quest
