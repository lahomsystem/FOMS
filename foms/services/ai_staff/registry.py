"""AI 직원 목록 — 다섯(설계서 2026-11-14-foms-graft 3.10). 선언 + 수준 읽기 한 곳.

- :data:`AGENTS` — 열쇠 · 화면 이름 · 아이콘 class · 쓰는 도구 · 할 일과 처음 수준. 할 일 열쇠가 할 일 목록
  (:data:`foms.services.erp_actions.registry.ACTIONS`)의 이름이면 그 직원이 만들 수 있는 제안이고, 아니면 그 직원만의 일(상담 답
  초안 · 읽기 · 주간 노트)이다. 처음 수준 ``None`` 은 '못 함'(그 직원은 그 할 일을 하지 않는다).
- 수준: 0 읽기만(**제안을 만들지 않음**) · 1 초안 · 2 제안. 3 은 없다. 처음 수준은 할 일의 ``level_cap`` 을 넘지 않는다(시험).
- 수준 표는 ``SystemSetting`` 열쇠 :data:`SETTINGS_KEY` — ``{"<직원>": {"<할 일>": 0 ~ 2}}``. 읽기는 :func:`level_of` ·
  :func:`level_table` 한 곳이고, 표가 없거나 그 칸 꼴이 틀리면(정수 아님 · 상한 넘음 · 3) 처음 값이다. 고치기는 :mod:`.levels`(T10).
  직원만의 일은 수준 표로 바꾸지 않는다(처음 값 그대로).
- 제안 줄의 ``proposed_by`` 는 ``'agent:<열쇠>'``(:func:`proposer` · :func:`agent_of`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from foms.services.erp_actions.registry import ACTIONS, MAX_LEVEL
from models import SystemSetting

__all__ = [
    "AGENTS", "Agent", "Duty", "PROPOSER_PREFIX", "SETTINGS_KEY", "TOOLS", "Tool", "agent_of", "level_of",
    "level_table", "proposer",
]

SETTINGS_KEY = "ai_staff_levels"
PROPOSER_PREFIX = "agent:"
#: 도구 이름 → 화면 말(실행 기록 ``ai_agent_runs.steps[].tool`` 도 이 이름을 쓴다).
TOOLS: dict[str, str] = {
    "knowledge.search": "회사 지식 찾기",
    "cs.thread.read": "상담 읽기(가린 뒤)",
    "erp.order.find": "주문 · 방문 읽기",
    "risk.check": "위험 문장 검사",
    "actions.propose": "할 일 제안 → 승인 대기",
    "mask.apply": "가림",
    "erp.order.get": "주문 읽기",
    "erp.visit.list": "방문 읽기",
    "erp.order.list": "주문 훑기",
    "drawing.digest": "학습 요약 읽기(손님 정보 없음)",
}


@dataclass(frozen=True)
class Tool:
    """쓰는 도구 하나 — 이름(:data:`TOOLS`) · 판 1 에 새로 붙었나."""

    name: str
    new: bool = False

    @property
    def what(self) -> str:
        """도구 화면 말."""
        return TOOLS[self.name]


@dataclass(frozen=True)
class Duty:
    """할 일 하나 — 열쇠(할 일 목록 이름 또는 직원만의 일) · 화면 이름 · 처음 수준(``None`` = 못 함)."""

    key: str
    label: str
    level: Optional[int]

    @property
    def is_action(self) -> bool:
        """할 일 목록(ERP 할 일)의 이름인가 — 참이면 제안을 만드는 일."""
        return self.key in ACTIONS


@dataclass(frozen=True)
class Agent:
    """AI 직원 하나."""

    key: str
    label: str
    icon: str  # 디자인 시스템 아이콘 class('i-…')
    trial: bool  # 판 1 에 새로 붙어 시험 중인가(규칙 훑기 — 모델을 부르지 않는다)
    summary: str
    tools: tuple[Tool, ...]
    duties: tuple[Duty, ...]

    @property
    def status_label(self) -> str:
        """지금 있는지 · 시험 중인지 화면 말."""
        return "새로 · 시험 중" if self.trial else "있음"

    def duty(self, key: str) -> Optional[Duty]:
        """열쇠 → 할 일(없으면 ``None``)."""
        return next((duty for duty in self.duties if duty.key == key), None)

    def actions(self) -> tuple[str, ...]:
        """이 직원이 제안할 수 있는 할 일 이름(못 함 · 직원만의 일 빼고)."""
        return tuple(duty.key for duty in self.duties if duty.is_action and duty.level is not None)


AGENTS: dict[str, Agent] = {agent.key: agent for agent in (
    Agent("cs", "상담 AI", "i-chat", False, "채널톡 작은 창 초안",
          (Tool("knowledge.search"), Tool("cs.thread.read"), Tool("erp.order.find"), Tool("risk.check"),
           Tool("actions.propose", new=True)),
          (Duty("cs_draft", "상담 답 초안", 1), Duty("erp_read", "주문 · 방문 읽기", 0),
           Duty("move_construction", "방문 옮기기 제안", 2), Duty("register_as", "AS 접수 제안", 2),
           Duty("add_construction_note", "시공 메모 더하기 제안", 2), Duty("send_measure_alimtalk", "알림톡 보내기", None))),
    Agent("drawing", "도면 AI 팀원", "i-document", False, "주 1회 루틴",
          (Tool("drawing.digest"),),
          (Duty("weekly_note", "주간 노트 · 물어볼 것", 1),)),
    Agent("ask", "지식 물어보기", "i-lightbulb", False, "읽기만",
          (Tool("mask.apply"), Tool("knowledge.search"), Tool("erp.order.get", new=True),
           Tool("erp.visit.list", new=True)),
          (Duty("ask_answer", "물어보기 답", 0), Duty("erp_read", "주문 · 방문 읽기", 0))),
    Agent("ops", "운영 AI", "i-predictive-analysis", True, "아침 훑기 · 제안만",
          (Tool("erp.order.list", new=True), Tool("actions.propose", new=True)),
          (Duty("send_measure_alimtalk", "알림톡 보내기(실측 예약)", 1), Duty("assign_draftsman", "도면 담당 맡기기(바로가기)", 1))),
    Agent("schedule", "일정 AI", "i-calendar", True, "협력사 희망 시공일 · 제안만",
          (Tool("erp.visit.list", new=True), Tool("actions.propose", new=True)),
          (Duty("schedule_construction", "시공 잡기", 2),)),
)}


def proposer(key: str) -> str:
    """직원 열쇠 → 제안 줄 ``proposed_by`` 값(``'agent:<열쇠>'``).

    Raises:
        ValueError: 목록에 없는 열쇠.
    """
    if key not in AGENTS:
        raise ValueError("agent")
    return f"{PROPOSER_PREFIX}{key}"


def agent_of(proposed_by: Any) -> Optional[Agent]:
    """제안 줄 ``proposed_by`` → 직원(사람 · 모르는 값이면 ``None``)."""
    if not isinstance(proposed_by, str) or not proposed_by.startswith(PROPOSER_PREFIX):
        return None
    return AGENTS.get(proposed_by[len(PROPOSER_PREFIX):])


def _stored(session: Any) -> dict[str, Any]:
    """수준 표 값(줄이 없거나 dict 가 아니면 빈 dict)."""
    row = session.get(SystemSetting, SETTINGS_KEY)
    value = row.setting_value if row is not None else None
    return value if isinstance(value, dict) else {}


def _effective(duty: Duty, stored: Any) -> Optional[int]:
    """할 일 하나의 지금 수준 — 수준 표 칸이 0 ~ min(상한, 2) 정수면 그 값, 아니면 처음 값(못 함은 ``None``)."""
    spec = ACTIONS.get(duty.key)
    if duty.level is None or spec is None:
        return duty.level
    value = stored.get(duty.key) if isinstance(stored, dict) else None
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= min(spec.level_cap, MAX_LEVEL):
        return value
    return duty.level


def level_table(session: Any) -> dict[str, dict[str, Optional[int]]]:
    """직원 → 할 일 → 지금 수준(못 함은 ``None``) — 수준 표를 한 번만 읽는다(화면 · 훑기용)."""
    stored = _stored(session)
    return {key: {duty.key: _effective(duty, stored.get(key)) for duty in agent.duties}
            for key, agent in AGENTS.items()}


def level_of(session: Any, agent: str, action: str) -> int:
    """직원 · 할 일의 지금 수준(0 ~ 2). 모르는 직원 · 그 직원에게 없는 할 일 · 못 함은 0(제안을 만들지 않음).

    Args:
        session: DB 세션(``SystemSetting`` 한 줄만 읽는다).
        agent: 직원 열쇠(:data:`AGENTS`).
        action: 할 일 열쇠(보통 할 일 목록 이름).

    Returns:
        수준 — 0 이면 그 직원은 그 할 일 제안을 만들지 않는다.
    """
    staff = AGENTS.get(agent)
    duty = staff.duty(action) if staff is not None else None
    if duty is None:
        return 0
    level = _effective(duty, _stored(session).get(agent))
    return level if level is not None else 0
