"""AI 직원 실행 기록 — 남기기 · 마지막 한 번 · 최근 실패(설계서 2026-11-14-foms-graft 3.4 ``ai_agent_runs`` · 3.10).

- 새 길(물어보기 ERP 읽기 · 훑기)은 ``ai_agent_runs`` 에 한 줄 — 단계마다 도구 · 한 일 · 짧은 말 · 걸린 시간(코드 · 수만,
  손님 글 없음). :func:`record_run` 은 커밋하지 않는다(부르는 쪽).
- **상담 AI 는 새 줄을 쓰지 않는다** — 지금 차례 줄(``cs_agent_turns``)에서 단계를 엮어 보이고, 시간은 전체(``latency_ms``)만
  보인다(설계서 9절). 차례가 만든 할 일 제안(``source_kind = cs_turn``)이 있으면 그 단계를 더한다.
- 최근 실패: 상담 AI 는 실패한 차례(실패 코드 · 실패한 때 ``updated_at`` — ``(state, updated_at)`` 색인), 제안하는 직원은
  실행하지 못한 제안(할 일 · 주문 번호 · 실패 코드). 상담 AI 마지막 차례는 번호(기본 키) 내림차순 한 줄.
- 화면 글은 코드가 정한 말 · 숫자 · 날짜뿐이다. 시간은 한국 시간 글('MM-DD HH:MM').
- 단계마다 상태(:data:`STEP_STATES` — 끝남 · 건너뜀 · 걸림 · 승인 대기 · 실패)를 싣는다(점검 2차 w3-15 — 화면 아이콘이 상태를 따른다).
  쓰는 쪽이 ``state`` 를 넣었으면 그대로, 없으면 읽을 때 정한다(한 일이 '건너뜀'으로 시작 · 끝 코드 실패면 마지막 단계 실패).
- 상담 AI 차례에 그 차례가 근거로 남긴 키(:func:`foms.services.brain.usage_events.refs_of` — 접목판 '근거 줄' 관리 칸이 켜졌을
  때만 남는다)가 있으면 '손님 · 주문 찾기'(주문 키) · '회사 지식 찾기'(지식 키 — 모두 보기 범위 이름만) 단계를 보인다(w3-16).
  차례가 만든 제안이 아직 승인 전이면 끝에 '승인 대기'. 보낸 직원 이름('담당')은 ADMIN 에게만(R10-28 — 직원 번호는 ADMIN 만 본다).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select

from foms.persistence.graft.models import AiAgentRun, ErpActionProposal
from foms.services.ai_staff.registry import AGENTS, TOOLS, proposer
from foms.services.cs_agent.settings_field import MODEL_NAMES
from foms.services.datetime_kst import format_datetime_kst
from foms.services.brain.usage_events import refs_of
from foms.services.erp_actions.registry import ACTIONS, STATUS_FAILED, STATUS_OPEN
from models import CsAgentTurn, User

__all__ = [
    "FAILURE_LIMIT", "OUTCOME_LABELS", "STEP_STATES", "clean_steps", "latest_run", "recent_failures", "record_run",
]

FAILURE_LIMIT = 3
_TEXT_LIMIT, _MAX_STEPS = 80, 20
#: 단계 상태 — 끝남 · 건너뜀 · 걸림(검사에 걸림) · 승인 대기 · 실패.
STEP_DONE, STEP_SKIPPED, STEP_WARN, STEP_WAIT, STEP_FAILED = "done", "skipped", "warn", "wait", "failed"
STEP_STATES: tuple[str, ...] = (STEP_DONE, STEP_SKIPPED, STEP_WARN, STEP_WAIT, STEP_FAILED)
_SKIP_HEAD = "건너뜀"
_ORDER_PREFIX = "erp:order/"
_TURN_REF = "cs_turn"  # 상담 차례 근거 줄 · 제안의 ``source_kind``(foms.services.cs_agent.graft_step.SOURCE_KIND)
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
            row = {"tool": _short(step.get("tool"))[:40], "what": _short(step.get("what")),
                   "detail": _short(step.get("detail")), "ms": _ms(step.get("ms"))}
            if step.get("state") in STEP_STATES:  # 쓰는 쪽이 정한 상태(없으면 읽을 때 정한다 — :func:`_with_states`)
                row["state"] = step["state"]
            out.append(row)
    return out


def _with_states(steps: list[dict[str, Any]], outcome: Any) -> list[dict[str, Any]]:
    """단계마다 상태 — 넣어 둔 값 그대로, 없으면 한 일이 '건너뜀'으로 시작하면 건너뜀 · 아니면 끝남. 끝 코드가 실패면 마지막 단계 실패."""
    for step in steps:
        if step.get("state") not in STEP_STATES:
            step["state"] = STEP_SKIPPED if str(step.get("what") or "").startswith(_SKIP_HEAD) else STEP_DONE
    if steps and str(outcome or "") == "failed":
        steps[-1]["state"] = STEP_FAILED
    return steps


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


def _step(tool: str, what: str, detail: str, state: str = STEP_DONE) -> dict[str, Any]:
    return {"tool": tool, "what": what, "detail": detail, "ms": None, "state": state}


def _evidence_steps(session: Any, turn: CsAgentTurn) -> list[dict[str, Any]]:
    """그 차례가 근거로 남긴 키 → '손님 · 주문 찾기' · '회사 지식 찾기' 단계(남긴 것이 없으면 빈 목록 — 지어내지 않는다)."""
    keys = refs_of(session, _TURN_REF, turn.id)
    orders = [key[len(_ORDER_PREFIX):] for key in keys if key.startswith(_ORDER_PREFIX)]
    knowledge = [key for key in keys if not key.startswith("erp:")]
    out = []
    if orders:
        out.append(_step("erp.order.find", "손님 · 주문 찾기",
                         " · ".join(f"주문 #{number}" for number in orders[:3]) + " · 손님 정보 가림"))
    if knowledge:
        from foms.services.cs_agent.graft_step import brain_labels  # 무거운 꾸러미 — 상담 AI 자세히에서만 싣는다

        labels = list(brain_labels(session, knowledge).values())
        if labels:
            detail = labels[0] + (f" 외 {len(knowledge) - 1}개" if len(knowledge) > 1 else "")
        else:  # 이름을 보일 수 없는 항목(지금 판 아님 · 보기 범위 좁음)뿐 — 수만
            detail = f"지식 {len(knowledge)}개"
        out.append(_step("knowledge.search", "회사 지식 찾기", detail))
    return out


def _turn_steps(session: Any, turn: CsAgentTurn) -> list[dict[str, Any]]:
    """상담 차례 줄 → 단계(시간 없음 — 전체 시간만 있다) · 단계마다 상태."""
    steps = [_step("cs.thread.read", "손님 글 읽기", TOOLS["cs.thread.read"])]
    steps.extend(_evidence_steps(session, turn))
    failed = turn.state == "failed"
    if turn.model:
        steps.append(_step(MODEL_NAMES.get(turn.model, turn.model), "초안 쓰기",
                           "사람에게 넘김" if turn.handoff else ("못 씀" if failed else "초안 씀"),
                           STEP_FAILED if failed else (STEP_SKIPPED if turn.handoff else STEP_DONE)))
    elif failed:
        steps.append(_step("", "초안 쓰기", "못 씀", STEP_FAILED))
    if turn.check_codes is not None:
        codes = [str(code) for code in turn.check_codes] if isinstance(turn.check_codes, list) else []
        steps.append(_step("risk.check", "위험 검사", f"걸림 {len(codes)}개" if codes else "걸린 것 없음",
                           STEP_WARN if codes else STEP_DONE))
    made = session.execute(select(ErpActionProposal.action, ErpActionProposal.level, ErpActionProposal.status).where(
        ErpActionProposal.source_kind == _TURN_REF, ErpActionProposal.source_ref == str(turn.id))).all()
    for action, level, _status in made:
        spec = ACTIONS.get(action)
        steps.append(_step("actions.propose", "할 일 제안", f"{spec.label if spec else action} · 수준 {level}"))
    waiting = sum(1 for _action, _level, status in made if status == STATUS_OPEN)
    if waiting:
        steps.append(_step("inbox", "승인 대기", f"{waiting}개 · 승인 전에는 안 바뀌어요", STEP_WAIT))
    return steps


def _staff_name(session: Any, user_id: Any) -> Optional[str]:
    """보낸 직원 이름(번호가 없거나 사람을 못 찾으면 ``None``)."""
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        return None
    name = session.execute(select(User.name).where(User.id == user_id)).scalar_one_or_none()
    text = " ".join(str(name or "").split())[:20]
    return text or None


def _cs_latest(session: Any, show_staff: bool) -> Optional[dict[str, Any]]:
    turn = session.execute(select(CsAgentTurn).order_by(CsAgentTurn.id.desc()).limit(1)).scalars().first()
    if turn is None:
        return None
    steps = _turn_steps(session, turn)
    return {"at": _at(turn.created_at), "total_ms": _ms(turn.latency_ms), "per_step": False, "steps": steps,
            "outcome": _outcome(turn.state), "proposals": sum(1 for s in steps if s["tool"] == "actions.propose"),
            "who": _staff_name(session, turn.sent_by_user_id) if show_staff else None}


def latest_run(session: Any, agent: str, *, show_staff: bool = False) -> Optional[dict[str, Any]]:
    """마지막 실행 한 번 — ``{"at", "total_ms", "per_step", "steps", "outcome", "proposals", "who"}``. 없으면 ``None``.

    상담 AI 는 차례 줄에서 엮고(단계 시간 없음 · ``per_step`` 거짓), 그 밖은 ``ai_agent_runs`` 의 가장 새 줄. 단계마다 ``state``.
    ``who``(담당 — 상담 차례를 보낸 직원 이름)는 ``show_staff``(ADMIN)이고 값이 있을 때만, 그 밖은 ``None``.
    """
    if agent == "cs":
        return _cs_latest(session, show_staff)
    row = session.execute(select(AiAgentRun).where(AiAgentRun.agent == agent)
                          .order_by(AiAgentRun.started_at.desc(), AiAgentRun.id.desc()).limit(1)).scalars().first()
    if row is None:
        return None
    return {"at": _at(row.started_at), "total_ms": _ms(row.total_ms), "per_step": True,
            "steps": _with_states(clean_steps(row.steps or []), row.outcome), "outcome": _outcome(row.outcome),
            "proposals": int(row.proposals or 0), "who": None}


def recent_failures(session: Any, agent: str, now: datetime.datetime, days: int = 14,
                    limit: int = FAILURE_LIMIT) -> list[dict[str, Any]]:
    """최근 실패 ``[{"label", "code", "at", "href"}]`` — 새것 먼저 ``limit`` 개(지난 ``days`` 일).

    상담 AI 는 실패한 차례, 제안하는 직원은 실행하지 못한 제안. 그 밖 직원은 빈 목록.
    """
    since = now - datetime.timedelta(days=days)
    found: list[tuple[datetime.datetime, dict[str, Any]]] = []
    if agent == "cs":
        for turn in session.execute(select(CsAgentTurn.updated_at, CsAgentTurn.error_code).where(
                CsAgentTurn.state == "failed", CsAgentTurn.updated_at >= since)
                .order_by(CsAgentTurn.updated_at.desc()).limit(limit)):
            found.append((turn.updated_at, {"label": "초안을 못 씀", "code": turn.error_code or "",
                                            "at": _at(turn.updated_at), "href": None}))
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
