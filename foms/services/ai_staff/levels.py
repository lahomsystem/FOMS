"""AI 직원 수준 표 고치기 — ADMIN 만(설계서 2026-11-14-foms-graft 3.10).

- 수준 표는 ``SystemSetting`` 열쇠 :data:`.registry.SETTINGS_KEY` — ``{"<직원>": {"<할 일>": 0 ~ 2}}``. 읽기는
  :func:`.registry.level_of` · :func:`.registry.level_table` 한 곳이고, 이 모듈은 화면 값(:func:`levels_view`)과 고치기
  (:func:`save_levels`)만 한다.
- 고칠 수 있는 칸 = 그 직원의 **할 일 목록 이름인 할 일**(제안을 만드는 일)이고 처음 수준이 '못 함'이 아닌 것. 값은
  0 ~ min(할 일 ``level_cap``, 2) 정수. 3 · 상한 넘음 · 참거짓 · 글자 · 모르는 직원 · 모르는 할 일 · 직원만의 일은 거절한다.
- 고치는 사람은 켜진 내부 ADMIN 뿐(:class:`LevelError` ``LEVEL_FORBIDDEN`` — API 는 없는 것과 같은 404).
- 고치면 감사 줄 ``AI_STAFF_LEVELS_SAVED`` 한 줄(직원 · 할 일 · 앞 값 · 뒤 값 — 숫자와 열쇠만). 커밋은 부르는 쪽.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.ai_staff.registry import AGENTS, SETTINGS_KEY, Agent, Duty, level_table
from foms.services.audit_writer import normalize_security_detail
from foms.services.brain.scope import viewer_of
from foms.services.erp_actions.registry import ACTIONS, LEVEL_LABELS, MAX_LEVEL
from models import SecurityLog, SystemSetting

__all__ = ["AUDIT_LEVELS_SAVED", "LevelError", "choices_of", "editable", "levels_view", "save_levels"]

AUDIT_LEVELS_SAVED = "AI_STAFF_LEVELS_SAVED"
#: 실패 코드 → 화면 말(받은 값은 싣지 않는다).
MESSAGES: dict[str, str] = {
    "LEVEL_FORBIDDEN": "찾을 수 없습니다.",
    "LEVEL_SHAPE": "수준 값이 맞지 않아요 — 다시 골라 주세요.",
}


class LevelError(Exception):
    """수준 고치기 거절 — ``code`` 는 :data:`MESSAGES` 열쇠, ``fields`` 는 틀린 칸 이름(``직원.할 일``)."""

    def __init__(self, code: str, fields: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code, self.fields = code, tuple(fields)

    @property
    def message(self) -> str:
        """화면 말."""
        return MESSAGES[self.code]


def editable(duty: Duty) -> bool:
    """수준 표로 바꿀 수 있는 할 일인가 — 할 일 목록 이름이고 '못 함'이 아님."""
    return duty.is_action and duty.level is not None


def choices_of(duty: Duty) -> tuple[int, ...]:
    """고를 수 있는 수준 — 0 ~ min(할 일 상한, 2). 바꿀 수 없는 할 일은 빈 묶음."""
    if not editable(duty):
        return ()
    return tuple(range(0, min(ACTIONS[duty.key].level_cap, MAX_LEVEL) + 1))


def _row(session: Any, *, lock: bool) -> Optional[SystemSetting]:
    """수준 표 줄(``lock`` 이면 ``FOR UPDATE``) — 없으면 ``None``."""
    query = session.query(SystemSetting).filter(SystemSetting.setting_key == SETTINGS_KEY)
    return (query.populate_existing().with_for_update() if lock else query).first()


def levels_view(session: Any) -> dict[str, Any]:
    """화면 값 — 판 번호 · 직원마다 할 일 ``[{"action", "label", "level", "level_label", "editable", "choices"}]``.

    Args:
        session: DB 세션(수준 표 한 줄만 읽는다).

    Returns:
        ``{"version": n(표가 없으면 0), "agents": {"<직원>": [할 일 줄 …]}}`` — '못 함'은 ``level`` ``None`` · '못 함'.
    """
    table, row = level_table(session), _row(session, lock=False)
    agents: dict[str, list[dict[str, Any]]] = {}
    for key, agent in AGENTS.items():
        agents[key] = [{"action": duty.key, "label": duty.label, "level": table[key][duty.key],
                        "level_label": "못 함" if table[key][duty.key] is None else LEVEL_LABELS[table[key][duty.key]],
                        "editable": editable(duty),
                        "choices": [{"value": n, "label": LEVEL_LABELS[n]} for n in choices_of(duty)]}
                       for duty in agent.duties]
    return {"version": int(row.version or 0) if row is not None else 0, "agents": agents}


def _value_ok(duty: Duty, value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value in choices_of(duty)


def _parse(body: Any) -> dict[tuple[str, str], int]:
    """본문 ``{"levels": {"<직원>": {"<할 일>": n}}}`` → ``{(직원, 할 일): n}``. 틀린 칸이 하나라도 있으면 거절."""
    levels = body.get("levels") if isinstance(body, Mapping) else None
    if not isinstance(levels, Mapping) or not levels:
        raise LevelError("LEVEL_SHAPE", ("levels",))
    out: dict[tuple[str, str], int] = {}
    problems: list[str] = []
    for agent_key, duties in levels.items():
        agent: Optional[Agent] = AGENTS.get(agent_key) if isinstance(agent_key, str) else None
        if agent is None or not isinstance(duties, Mapping) or not duties:
            problems.append(str(agent_key)[:20])
            continue
        for action, value in duties.items():
            duty = agent.duty(action) if isinstance(action, str) else None
            if duty is None or not _value_ok(duty, value):
                problems.append(f"{agent.key}.{str(action)[:40]}")
            else:
                out[(agent.key, duty.key)] = value
    if problems:
        raise LevelError("LEVEL_SHAPE", tuple(problems))
    return out


def _audit(session: Any, actor_id: int, changes: dict[str, list[Optional[int]]]) -> None:
    """감사 한 줄 — 열쇠와 앞뒤 수만."""
    session.add(SecurityLog(
        user_id=actor_id, action=AUDIT_LEVELS_SAVED, target_type="system_setting", target_id=None,
        message=f"AI 직원 수준 고침 {len(changes)}칸", detail=normalize_security_detail({"changes": changes})))


def save_levels(session: Any, actor: Any, body: Any) -> dict[str, Any]:
    """수준 표를 고친다(ADMIN 만 — 커밋은 부르는 쪽).

    Args:
        session: DB 세션.
        actor: 로그인 사용자(켜진 내부 ADMIN 이어야 한다).
        body: ``{"levels": {"<직원>": {"<할 일>": 0 ~ 2}}}`` — 적은 칸만 바꾸고 나머지는 그대로 둔다.

    Returns:
        고친 뒤 :func:`levels_view` 값.

    Raises:
        LevelError: ``LEVEL_FORBIDDEN``(ADMIN 아님) · ``LEVEL_SHAPE``(모르는 직원 · 할 일 · 직원만의 일 · 못 함 · 상한 넘음 ·
            3 · 정수 아님).
    """
    viewer = viewer_of(actor)
    if not viewer.is_admin or viewer.user_id is None:
        raise LevelError("LEVEL_FORBIDDEN")
    wanted = _parse(body)
    before = level_table(session)
    row = _row(session, lock=True)
    if row is None:
        row = SystemSetting(setting_key=SETTINGS_KEY, setting_value={})
        session.add(row)
    stored = copy.deepcopy(row.setting_value) if isinstance(row.setting_value, dict) else {}
    changes: dict[str, list[Optional[int]]] = {}
    for (agent_key, action), value in wanted.items():
        cell = stored.get(agent_key) if isinstance(stored.get(agent_key), dict) else {}
        cell[action] = value
        stored[agent_key] = cell
        if before[agent_key][action] != value:
            changes[f"{agent_key}.{action}"] = [before[agent_key][action], value]
    row.setting_value = stored
    flag_modified(row, "setting_value")
    if changes:
        row.version = int(row.version or 0) + 1
        _audit(session, viewer.user_id, changes)
    session.flush()
    return levels_view(session)
