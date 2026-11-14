"""AI 직원 숫자 — 2주 승인율 · 제안 수 · 상담 초안 '그대로 보냄' · 시간 · 비용(설계서 2026-11-14-foms-graft 3.10).

- **2주 승인율**: (직원, 할 일)마다 지난 14일 결정 수 · 승인 수 · 비율 — 승인 대기 자세히와 **같은 함수**
  (:func:`foms.services.erp_actions.views.approval_rate`)를 다시 쓴다. 결정이 0 이면 ``pct`` 는 ``None``(화면 '—').
- **상담 초안**: '그대로 보냄'은 상담 AI 기록판과 같은 계산(:func:`foms.services.cs_agent.metrics.compute_metrics` — 브랜드를
  더한다). 시간은 차례 줄의 전체 시간(``latency_ms``) 평균.
- **비용**: 상담 AI 차례 줄의 ``cost_usd`` 합(지난 7일). 화면에는 ADMIN 에게만 보인다(가르는 것은 :mod:`.views`).
- 새 길(물어보기 · 훑기)은 실행 기록(``ai_agent_runs``)의 수 · 전체 시간 평균.
- 숫자만 — 직원 · 손님 이름 · 글은 읽지 않는다. 기간은 한국 날짜 기준.
- 차례 줄(``cs_agent_turns``)의 기간은 ``created_at`` 만으로 거르지 않는다(그 칸만의 색인이 없다) —
  :func:`turns_since` 가 ``(state, updated_at)`` 색인으로 먼저 좁힌다.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import ColumnElement, func, select

from foms.persistence.graft.models import AiAgentRun, ErpActionProposal
from foms.services.ai_staff.registry import AGENTS, proposer
from foms.services.cs_agent.metrics import compute_metrics
from foms.services.cs_agent.state import KST
from foms.services.cs_agent.turns import STATES as TURN_STATES
from foms.services.erp_actions.views import RATE_DAYS, approval_rate
from models import CsAgentTurn

__all__ = ["COST_DAYS", "RATE_DAYS", "approval_rates", "cs_cost", "cs_draft_stats", "proposal_counts", "run_stats",
           "turns_since"]

COST_DAYS = 7
_UTC = datetime.timezone.utc


def _since(now: datetime.datetime, days: int) -> datetime.datetime:
    """``days`` 일 앞 한국 자정(UTC naive) — 기간의 시작."""
    day = now.replace(tzinfo=_UTC).astimezone(KST).date() - datetime.timedelta(days=days)
    return datetime.datetime.combine(day, datetime.time(), tzinfo=KST).astimezone(_UTC).replace(tzinfo=None)


def turns_since(since: datetime.datetime) -> tuple[ColumnElement[bool], ...]:
    """``since`` 뒤 만든 차례 줄 조건 — ``(state, updated_at)`` 색인을 타는 꼴.

    상태는 검사 제약의 값 전부(:data:`foms.services.cs_agent.turns.STATES` — 빠지는 줄이 없다)이고 차례 줄은 늘
    ``updated_at >= created_at`` 이라, ``created_at >= since`` 만 건 것과 같은 줄이다.

    Args:
        since: 기간 시작(UTC naive).

    Returns:
        ``where`` 에 넣을 조건 셋.
    """
    return (CsAgentTurn.state.in_(TURN_STATES), CsAgentTurn.updated_at >= since, CsAgentTurn.created_at >= since)


def approval_rates(session: Any, now: datetime.datetime,
                   only: Optional[str] = None) -> dict[tuple[str, str], dict[str, Any]]:
    """제안을 만드는 (직원, 할 일)마다 지난 14일 승인율 ``{"days", "decided", "approved", "pct"}``.

    Args:
        session: DB 세션(읽기만).
        now: 지금(UTC naive).
        only: 이 직원 것만(자세히 한 장 — 없으면 모두). 할 일 하나에 질의 하나다.

    Returns:
        ``{(직원, 할 일): 승인율}`` — 직원 목록의 제안하는 할 일 전부(못 함 빼고).
    """
    return {(key, action): approval_rate(session, proposer(key), action, now)
            for key, agent in AGENTS.items() if only is None or key == only for action in agent.actions()}


def proposal_counts(session: Any, now: datetime.datetime, days: int = RATE_DAYS) -> dict[tuple[str, str], int]:
    """지난 ``days`` 일 만든 제안 수 ``{(직원, 할 일): n}`` — 질의 하나(제안자 · 할 일로 묶음)."""
    rows = session.execute(select(ErpActionProposal.proposed_by, ErpActionProposal.action,
                                  func.count(ErpActionProposal.id))
                           .where(ErpActionProposal.created_at >= now - datetime.timedelta(days=days))
                           .group_by(ErpActionProposal.proposed_by, ErpActionProposal.action)).all()
    out: dict[tuple[str, str], int] = {}
    for proposed_by, action, count in rows:
        key = str(proposed_by or "").split(":", 1)[-1]
        if key in AGENTS:
            out[(key, action)] = int(count)
    return out


def cs_draft_stats(session: Any, now: datetime.datetime, days: int = RATE_DAYS) -> dict[str, Any]:
    """상담 초안 — 지난 ``days`` 일 차례 수 · [보내기]로 보낸 수 · '그대로 보냄' 수 · 비율 · 전체 시간 평균(ms).

    Returns:
        ``{"days", "turns", "sent", "as_is", "pct", "avg_ms"}`` — 보낸 것이 없으면 ``pct`` 는 ``None``.
    """
    today = now.replace(tzinfo=_UTC).astimezone(KST).date()
    found = compute_metrics(session, start=today - datetime.timedelta(days=days), end=today + datetime.timedelta(days=1))
    turns = sum(m.turns for m in found.values())
    sent = sum(m.as_is.total for m in found.values())
    as_is = sum(m.as_is.hits for m in found.values())
    average = session.execute(select(func.avg(CsAgentTurn.latency_ms)).where(
        *turns_since(_since(now, days)), CsAgentTurn.latency_ms.isnot(None))).scalar()
    return {"days": days, "turns": turns, "sent": sent, "as_is": as_is,
            "pct": round(100 * as_is / sent) if sent else None,
            "avg_ms": int(round(float(average))) if average is not None else None}


def cs_cost(session: Any, now: datetime.datetime, days: int = COST_DAYS) -> Optional[Decimal]:
    """상담 AI 지난 ``days`` 일 비용(달러) 합 — 줄이 없으면 ``None``."""
    total = session.execute(select(func.sum(CsAgentTurn.cost_usd)).where(
        *turns_since(_since(now, days)), CsAgentTurn.cost_usd.isnot(None))).scalar()
    return Decimal(str(total)) if total is not None else None


def run_stats(session: Any, agent: str, now: datetime.datetime, days: int = RATE_DAYS) -> dict[str, Any]:
    """실행 기록(``ai_agent_runs``) 지난 ``days`` 일 — 수 · 전체 시간 평균(ms) · 만든 제안 수."""
    count, average, made = session.execute(
        select(func.count(AiAgentRun.id), func.avg(AiAgentRun.total_ms), func.sum(AiAgentRun.proposals))
        .where(AiAgentRun.agent == agent, AiAgentRun.started_at >= _since(now, days))).one()
    return {"days": days, "runs": int(count or 0),
            "avg_ms": int(round(float(average))) if average is not None else None, "proposals": int(made or 0)}
