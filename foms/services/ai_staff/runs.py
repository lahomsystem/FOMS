"""AI 직원 실행 기록 — 남기기 · 마지막 한 번 · 최근 실패(설계서 2026-11-14-foms-graft 3.4 ``ai_agent_runs`` · 3.10).

- 새 길(물어보기 ERP 읽기 · 훑기)은 ``ai_agent_runs`` 에 한 줄 — 단계마다 도구 · 한 일 · 짧은 말 · 걸린 시간(코드 · 수만,
  손님 글 없음). :func:`record_run` 은 커밋하지 않는다(부르는 쪽).
- **상담 AI 는 새 줄을 쓰지 않는다** — 지금 차례 줄(``cs_agent_turns``)에서 단계를 엮어 보이고, 시간은 전체(``latency_ms``)만
  보인다(설계서 9절). 차례가 만든 할 일 제안(``source_kind = cs_turn``)이 있으면 그 단계를 더한다.
- 최근 실패: 상담 AI 는 실패한 차례(실패 코드), 제안하는 직원은 실행하지 못한 제안(할 일 · 주문 번호 · 실패 코드).
- 화면 글은 코드가 정한 말 · 숫자 · 날짜뿐이다. 시간은 한국 시간 글('MM-DD HH:MM').
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select

from foms.persistence.graft.models import AiAgentRun, ErpActionProposal
from foms.services.ai_staff.registry import AGENTS, TOOLS, proposer
from foms.services.cs_agent.settings_field import MODEL_NAMES
from foms.services.datetime_kst import format_datetime_kst
from foms.services.erp_actions.registry import ACTIONS, STATUS_FAILED
from models import CsAgentTurn

__all__ = ["FAILURE_LIMIT", "OUTCOME_LABELS", "clean_steps", "latest_run", "recent_failures", "record_run"]

FAILURE_LIMIT = 3
_TEXT_LIMIT, _MAX_STEPS = 80, 20
#: 끝 코드 → 화면 말(모르는 코드는 '끝남').
OUTCOME_LABELS: dict[str, str] = {
    "done": "끝남", "answered": "답함", "level_zero": "수준 0 — 제안을 만들지 않음",
    "posted": "초안을 메모로 올림", "stored": "초안을 저장만 함", "skipped": "건너뜀", "failed": "실패",
    "superseded": "지난 초안(손님이 더 씀)", "staff_replied": "직원이 먼저 답함", "claimed": "쓰는 중", "posting": "올리는 중",
}


def _short(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split())[:_TEXT_LIMIT]


def _ms(value: Any) -> Optional[int]:
    return max(0, int(value)) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def clean_steps(steps: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """단계 목록 다듬기 — ``{"tool", "what", "detail", "ms"}`` 스무 개까지 · 글은 한 줄 80자 · 시간은 0 이상 정수."""
    out: list[dict[str, Any]] = []
    for step in list(steps)[:_MAX_STEPS]:
        if isinstance(step, Mapping):
            out.append({"tool": _short(step.get("tool"))[:40], "what": _short(step.get("what")),
                        "detail": _short(step.get("detail")), "ms": _ms(step.get("ms"))})
    return out


def record_run(session: Any, agent: str, steps: Iterable[Mapping[str, Any]], *, started_at: datetime.datetime,
               total_ms: Optional[int], source_kind: Optional[str] = None, source_ref: Optional[str] = None,
               outcome: str = "done", proposals: int = 0) -> AiAgentRun:
    """실행 기록 한 줄을 더한다(flush 해 번호를 채운다 — 커밋은 부르는 쪽).

    Args:
        session: DB 세션.
        agent: 직원 열쇠(:data:`.registry.AGENTS`).
        steps: 단계 ``[{"tool", "what", "detail", "ms"}]``(코드 · 수만).
        started_at: 시작(UTC naive). total_ms: 전체 걸린 시간. source_kind · source_ref: 무엇 때문에(예 ``sweep``).
        outcome: 끝 코드(:data:`OUTCOME_LABELS`). proposals: 만든 제안 수.

    Returns:
        새 줄.

    Raises:
        ValueError: 모르는 직원(부르는 쪽 코드 실수).
    """
    if agent not in AGENTS:
        raise ValueError("agent")
    row = AiAgentRun(agent=agent, started_at=started_at, total_ms=_ms(total_ms), source_kind=source_kind,
                     source_ref=source_ref, steps=clean_steps(steps), outcome=str(outcome)[:24],
                     proposals=max(0, int(proposals)))
    session.add(row)
    session.flush()
    return row


def _at(value: Optional[datetime.datetime]) -> Optional[str]:
    return format_datetime_kst(value, "%m-%d %H:%M") if value else None


def _outcome(code: Any) -> str:
    return OUTCOME_LABELS.get(str(code or ""), "끝남")


def _turn_steps(session: Any, turn: CsAgentTurn) -> list[dict[str, Any]]:
    """상담 차례 줄 → 단계(시간 없음 — 전체 시간만 있다)."""
    steps = [{"tool": "cs.thread.read", "what": "손님 글 읽기", "detail": TOOLS["cs.thread.read"], "ms": None}]
    if turn.model:
        steps.append({"tool": MODEL_NAMES.get(turn.model, turn.model), "what": "초안 쓰기",
                      "detail": "사람에게 넘김" if turn.handoff else "초안 씀", "ms": None})
    if turn.check_codes is not None:
        codes = [str(code) for code in turn.check_codes] if isinstance(turn.check_codes, list) else []
        steps.append({"tool": "risk.check", "what": "위험 검사",
                      "detail": f"걸림 {len(codes)}개" if codes else "걸린 것 없음", "ms": None})
    made = session.execute(select(ErpActionProposal.action, ErpActionProposal.level).where(
        ErpActionProposal.source_kind == "cs_turn", ErpActionProposal.source_ref == str(turn.id))).all()
    for action, level in made:
        spec = ACTIONS.get(action)
        steps.append({"tool": "actions.propose", "what": "할 일 제안",
                      "detail": f"{spec.label if spec else action} · 수준 {level}", "ms": None})
    return steps


def _cs_latest(session: Any) -> Optional[dict[str, Any]]:
    turn = session.execute(select(CsAgentTurn).order_by(CsAgentTurn.created_at.desc(), CsAgentTurn.id.desc())
                           .limit(1)).scalars().first()
    if turn is None:
        return None
    steps = _turn_steps(session, turn)
    return {"at": _at(turn.created_at), "total_ms": _ms(turn.latency_ms), "per_step": False, "steps": steps,
            "outcome": _outcome(turn.state), "proposals": sum(1 for s in steps if s["tool"] == "actions.propose")}


def latest_run(session: Any, agent: str) -> Optional[dict[str, Any]]:
    """마지막 실행 한 번 — ``{"at", "total_ms", "per_step", "steps", "outcome", "proposals"}``. 없으면 ``None``.

    상담 AI 는 차례 줄에서 엮고(단계 시간 없음 · ``per_step`` 거짓), 그 밖은 ``ai_agent_runs`` 의 가장 새 줄.
    """
    if agent == "cs":
        return _cs_latest(session)
    row = session.execute(select(AiAgentRun).where(AiAgentRun.agent == agent)
                          .order_by(AiAgentRun.started_at.desc(), AiAgentRun.id.desc()).limit(1)).scalars().first()
    if row is None:
        return None
    return {"at": _at(row.started_at), "total_ms": _ms(row.total_ms), "per_step": True,
            "steps": clean_steps(row.steps or []), "outcome": _outcome(row.outcome), "proposals": int(row.proposals or 0)}


def recent_failures(session: Any, agent: str, now: datetime.datetime, days: int = 14,
                    limit: int = FAILURE_LIMIT) -> list[dict[str, Any]]:
    """최근 실패 ``[{"label", "code", "at", "href"}]`` — 새것 먼저 ``limit`` 개(지난 ``days`` 일).

    상담 AI 는 실패한 차례, 제안하는 직원은 실행하지 못한 제안. 그 밖 직원은 빈 목록.
    """
    since = now - datetime.timedelta(days=days)
    found: list[tuple[datetime.datetime, dict[str, Any]]] = []
    if agent == "cs":
        for turn in session.execute(select(CsAgentTurn.created_at, CsAgentTurn.error_code).where(
                CsAgentTurn.state == "failed", CsAgentTurn.created_at >= since)
                .order_by(CsAgentTurn.created_at.desc()).limit(limit)):
            found.append((turn.created_at, {"label": "초안을 못 씀", "code": turn.error_code or "", "at": _at(turn.created_at),
                                            "href": None}))
    if AGENTS[agent].actions():
        for row in session.execute(select(ErpActionProposal).where(
                ErpActionProposal.proposed_by == proposer(agent), ErpActionProposal.status == STATUS_FAILED,
                ErpActionProposal.created_at >= since).order_by(ErpActionProposal.created_at.desc()).limit(limit)
                ).scalars():
            spec = ACTIONS.get(row.action)
            when = row.decided_at or row.created_at
            found.append((when, {"label": f"{spec.label if spec else row.action} — #{row.order_id}",
                                 "code": row.error_code or "", "at": _at(when),
                                 "href": f"/erp/orders/{row.order_id}" if row.order_id else None}))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _when, item in found[:limit]]
