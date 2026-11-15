"""AI 직원 화면 값 — 목록 · 자세히 · 여는 사람 판정(설계서 2026-11-14-foms-graft 3.10 · 5.2 · 9절, 판 ⑪).

- 여는 사람(:func:`staff_viewer`): 새 화면 스위치(``brain_ui``)가 켜진 사람 가운데 회사 지식 화면을 여는 ADMIN · MANAGER
  (``foms.web.brain._agents_open`` 과 같은 판정 — api 가 web 을 부를 수 없어 services 에 둔다). 그 밖은 ``None``(API 404).
- 비용 칸은 ADMIN 에게만 싣는다(MANAGER 답에는 열쇠가 없다). 수준 고치기 칸(``can_edit``)도 ADMIN 만.
- 목업과 다르게 그리는 것(9절): 모델 이름은 설정 값 그대로 · 상담 AI 의 주문 읽기는 '있음'(새로 붙음 아님) · 상담 AI 실행 기록은
  전체 시간만 · 운영 AI · 일정 AI 는 '시험 중 · 규칙'. 시공 팀 · 인원 글은 어디에도 없다(D211).
- 'AI 시험' 칸의 값은 T16 이 채운다(이 답에는 없다).
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from foms.services.ai_staff.levels import choices_of, editable, levels_version
from foms.services.ai_staff.metrics import (
    COST_DAYS, RATE_DAYS, approval_rates, cs_cost, cs_draft_stats, proposal_counts, run_stats,
)
from foms.services.ai_staff.registry import AGENTS, Agent, level_table
from foms.services.ai_staff.runs import latest_run, recent_failures
from foms.services.ai_staff.sweeps import RULES
from foms.services.brain.access import screen_viewer
from foms.services.brain.chat_settings import read_chat_settings
from foms.services.brain.scope import ROLE_MANAGER, Viewer
from foms.services.cs_agent.brain_prompt import PURPOSE_DRAFT
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.settings_field import MODEL_NAMES
from foms.services.erp_actions.registry import LEVEL_LABELS
from foms.services.graft_flags import enabled

__all__ = ["TRIAL_LABEL", "staff_detail", "staff_list", "staff_viewer"]

TRIAL_LABEL = "시험 중 · 규칙"
_ABOUT: dict[str, str] = {
    "cs": "채널톡 작은 창에서 손님 메시지를 읽고 근거 있는 답 초안을 써요. 직원이 보내기 · 고치기 · 버리기 가운데 골라요.",
    "drawing": "주 1회 도면 학습 요약을 읽고 주간 노트와 물어볼 것을 남겨요. 손님 정보는 읽지 않아요.",
    "ask": "직원 질문에 회사 지식과 주문 · 방문 읽기로 답해요. 읽기만 하고 바꾸지 않아요.",
    "ops": "하루 한 번 정해진 규칙으로 주문을 훑고 할 일 제안만 만들어요. 모델을 부르지 않아요.",
    "schedule": "협력사가 바란 시공일을 정해진 규칙으로 훑고 시공 잡기 제안만 만들어요. 모델을 부르지 않아요.",
}
_READS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "cs": (("lightbulb", "회사 지식", "상용구 · 정책 · 말투 규칙 · 배운 점"), ("chat", "상담 메시지", "가린 뒤 · 사진 포함"),
           ("cube", "주문 · 방문 읽기", "손님 이름 · 전화 · 주소는 가림 · 바꾸기는 못 해요")),
    "drawing": (("document", "도면 학습 요약", "손님 정보 없음"),),
    "ask": (("lightbulb", "회사 지식", "보는 사람의 보기 범위 안 항목만"),
            ("cube", "주문 · 방문 읽기", "손님 이름 · 전화 · 주소는 가림 · 바꾸기는 못 해요")),
    "ops": (("cube", "주문 칸", "단계 · 날짜 · 담당 · 알림톡 기록만 — 손님 글은 읽지 않아요"),),
    "schedule": (("calendar", "방문 일정", "협력사 희망 시공일 · 우리 시공일"),),
}
_READS_NOTE = {True: "모델을 부르지 않아요 — 정해진 규칙으로만 읽어요", False: "DB 를 직접 못 봐요 — 도구로만 읽어요"}
_FOOT = {True: "규칙이 만든 것은 제안뿐이에요. 사람이 승인해야 바뀌어요.",
         False: "손님 이름 · 전화 · 주소는 가린 채로 AI 에 가요. 바꾸기는 할 일 제안으로만 해요."}
_NOTES: dict[tuple[str, str], str] = {
    ("cs", "cs_draft"): "'그대로 보냄' 비율", ("cs", "erp_read"): "가린 채 읽기만", ("ask", "erp_read"): "가린 채 읽기만",
    ("cs", "send_measure_alimtalk"): "손님에게 나가는 글은 사람이 보내요 · 운영 AI 몫",
}


def staff_viewer(user: Any) -> Optional[Viewer]:
    """AI 직원 화면 · API 를 여는 사람의 Viewer — 새 화면 스위치 켬 + 회사 지식 화면을 여는 ADMIN · MANAGER. 아니면 ``None``."""
    if user is None or not enabled("brain_ui", user):
        return None
    viewer = screen_viewer(user)
    if viewer is None or not (viewer.is_admin or viewer.role == ROLE_MANAGER):
        return None
    return viewer


def _main_level(agent: Agent, levels: dict[str, Optional[int]]) -> int:
    """직원의 대표 수준 — 첫 할 일의 수준(못 함이면 0)."""
    return levels.get(agent.duties[0].key) or 0


def _tag(agent: Agent, levels: dict[str, Optional[int]]) -> dict[str, str]:
    if agent.trial:
        return {"text": "시험 중", "tone": "warning"}
    level = _main_level(agent, levels)
    return {"text": f"수준 {level}", "tone": "primary" if level else "success"}


def staff_list(session: Any, viewer: Viewer) -> dict[str, Any]:
    """왼쪽 목록 — 직원 다섯 ``[{"key", "label", "icon", "trial", "tag", "sub"}]`` + 수준 고치기 칸."""
    table = level_table(session)
    agents = [{"key": key, "label": agent.label, "icon": agent.icon, "trial": agent.trial, "tag": _tag(agent, table[key]),
               "sub": f"{'새로' if agent.trial else '있음'} · {agent.summary}"} for key, agent in AGENTS.items()]
    return {"agents": agents, "can_edit": viewer.is_admin}


def _model_label(session: Any, key: str) -> Optional[str]:
    """설정에 든 모델 이름(상담 AI 초안 · 물어보기) — 규칙 직원 · 도면 루틴은 ``None``."""
    if key == "cs":
        model = read_settings(session, log=False).model_for(PURPOSE_DRAFT)
    elif key == "ask":
        model = read_chat_settings(session).get("model")
    else:
        return None
    return MODEL_NAMES.get(model, str(model))


def _rule_note(key: str, action: str) -> str:
    rule = next((r for r in RULES.values() if r.agent == key and r.action == action), None)
    return f"규칙 {rule.key} — {rule.label}" if rule else ""


def _usage(session: Any, viewer: Viewer, key: str, now: datetime.datetime,
           cs_stats: Optional[dict[str, Any]]) -> dict[str, Any]:
    """시간 · 수 · (ADMIN 만) 비용 — ``{"days", "avg_ms", "count", "unit"}`` (+ ``"cost", "cost_days"``).

    ``cs_stats`` 는 자세히 한 장이 한 번 읽은 :func:`.metrics.cs_draft_stats`(상담 AI 만 — 그 밖은 ``None``)."""
    out: dict[str, Any] = {"days": RATE_DAYS, "avg_ms": None, "count": None, "unit": ""}
    if key == "cs" and cs_stats is not None:
        out.update(avg_ms=cs_stats["avg_ms"], count=cs_stats["turns"], unit="초안")
    elif key in ("ask", "ops", "schedule"):
        stats = run_stats(session, key, now)
        out.update(avg_ms=stats["avg_ms"], count=stats["runs"], unit="실행")
    if viewer.is_admin and key == "cs":  # 돈을 재는 길은 상담 AI 차례 줄뿐(규칙 직원은 모델을 부르지 않는다)
        cost = cs_cost(session, now)
        out.update(cost=f"${cost:,.2f}" if cost is not None else None, cost_days=COST_DAYS)
    return out


def _duties(session: Any, viewer: Viewer, key: str, agent: Agent, now: datetime.datetime,
            levels: dict[str, Optional[int]], cs_stats: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """할 일 줄 — 수준 · 고를 값 · 2주 승인율 · 건수 · 메모(수준 · 상담 초안 수는 자세히 한 장이 한 번 읽어 넘긴다)."""
    rates = approval_rates(session, now, only=key) if agent.actions() else {}
    counts = proposal_counts(session, now) if agent.actions() else {}
    rows = []
    for duty in agent.duties:
        level, rate, count = levels[duty.key], None, None
        if duty.is_action and level is not None:
            rate, count = rates.get((key, duty.key)), counts.get((key, duty.key), 0)
        elif duty.key == "cs_draft" and cs_stats is not None:
            rate = {"days": cs_stats["days"], "decided": cs_stats["sent"], "approved": cs_stats["as_is"],
                    "pct": cs_stats["pct"]}
            count = cs_stats["turns"]
        rows.append({
            "key": duty.key, "label": duty.label, "level": level,
            "level_label": "못 함" if level is None else LEVEL_LABELS[level],
            "tone": "danger" if level is None else ("primary" if level else "success"),
            "editable": viewer.is_admin and editable(duty),
            "choices": [{"value": n, "label": LEVEL_LABELS[n]} for n in choices_of(duty)] if viewer.is_admin else [],
            "rate": rate, "count": count, "note": _NOTES.get((key, duty.key)) or _rule_note(key, duty.key),
        })
    return rows


def staff_detail(session: Any, viewer: Viewer, key: Any, now: datetime.datetime) -> Optional[dict[str, Any]]:
    """직원 하나 자세히(판 ⑪ 가운데 · 오른쪽). 모르는 열쇠면 ``None``(API 404).

    Returns:
        ``{"key", "label", "icon", "trial", "model", "status", "about", "reads", "reads_note", "tools", "duties",
        "failures", "usage", "run", "foot", "can_edit", "levels_version"}``.
    """
    agent = AGENTS.get(key) if isinstance(key, str) else None
    if agent is None:
        return None
    levels = level_table(session)[agent.key]  # 수준 표 한 번 — 할 일 줄 · 판 번호가 같은 줄을 쓴다
    cs_stats = cs_draft_stats(session, now) if agent.key == "cs" else None
    main = _main_level(agent, levels)
    status = ({"text": TRIAL_LABEL, "tone": "warning"} if agent.trial
              else {"text": f"있음 · 수준 {LEVEL_LABELS[main]}", "tone": "success"})
    return {
        "key": agent.key, "label": agent.label, "icon": agent.icon, "trial": agent.trial,
        "model": _model_label(session, agent.key), "status": status, "about": _ABOUT[agent.key],
        "reads": [{"icon": icon, "label": label, "help": help_text} for icon, label, help_text in _READS[agent.key]],
        "reads_note": _READS_NOTE[agent.trial],
        "tools": [{"name": tool.name, "what": tool.what, "new": tool.new} for tool in agent.tools],
        "duties": _duties(session, viewer, agent.key, agent, now, levels, cs_stats),
        "failures": recent_failures(session, agent.key, now),
        "usage": _usage(session, viewer, agent.key, now, cs_stats),
        "run": latest_run(session, agent.key), "foot": _FOOT[agent.trial], "can_edit": viewer.is_admin,
        "levels_version": levels_version(session),
    }
