"""지식 물어보기 평가 — 마지막 점수 한 줄(설계서 2026-11-14-foms-graft 3.10 'AI 시험' — "물어보기 평가 묶음의 마지막 점수(있을 때)").

점검 2차 w3-20: 물어보기 평가(``scripts/maintenance/brain_chat_eval.py``)는 점수를 찍기만 해서 AI 직원 화면 '지식 물어보기'의 'AI 시험'
칸이 늘 비어 있었다. 실행기가 돌 때마다 :func:`record_ask_eval` 로 마지막 점수 한 줄을 남기고, 화면은 :func:`ask_eval_view` 로 읽는다.

- 저장: ``SystemSetting`` 열쇠 :data:`ASK_EVAL_KEY` 한 줄(덮어쓴다 — 마지막 한 번만). 때(UTC) · 방식(찾기만 · 답까지) · 수(답할 질문 ·
  맞힘 · 지식에 없는 질문 · '모름' 맞힘 · 근거 없는 답) · 통과. **질문 글 · 답 글 · 틀린 질문 번호는 남기지 않는다.**
- 읽기 꼴은 상담 AI 'AI 시험' 칸(:func:`foms.services.ai_staff.evals_view.eval_view`)과 같다 — ``rows`` · ``failures`` · ``last`` ·
  ``running`` (+ 아직 없으면 ``note``). 꼬리표 색 갈래는 success · danger(무채색 없음). 기준은 판 1 완료 기준(맞힘 80% · 근거 없는
  답 0 · 지식에 없는 질문 모두 '모름' — :data:`foms.services.brain.eval_set.PASS_RATE`).
"""

from __future__ import annotations

import datetime
from typing import Any, Mapping, Optional

from foms.services.brain.eval_set import PASS_RATE
from foms.services.datetime_kst import format_datetime_kst
from models import SystemSetting

__all__ = ["ASK_EVAL_KEY", "MODES", "ask_eval_view", "read_ask_eval", "record_ask_eval"]

ASK_EVAL_KEY = "ai_staff_ask_eval_last"
MODES: dict[str, str] = {"retrieval": "찾기만(돈 0)", "answer": "답까지"}
_COUNTS = ("answerable", "hit", "unanswerable", "unknown_ok", "unsupported")
_DESCRIPTION = "AI 직원 '지식 물어보기' 마지막 평가 점수(수만 — 질문 · 답 글 없음, brain_chat_eval.py 가 남김)"
NO_RUN_NOTE = "아직 물어보기 평가를 돌리지 않았어요."


def _count(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def record_ask_eval(session: Any, score: Mapping[str, Any], *, mode: str, now: datetime.datetime) -> dict[str, Any]:
    """마지막 점수 한 줄을 남긴다(덮어씀 · 커밋은 부르는 쪽).

    Args:
        session: DB 세션.
        score: :meth:`foms.services.brain.eval_set.EvalScore.as_dict` — 수 칸만 읽는다(``misses`` 는 버린다).
        mode: ``retrieval``(찾기만) · ``answer``(답까지).
        now: 돌린 때(UTC naive).

    Returns:
        남긴 값.

    Raises:
        ValueError: 모르는 방식 · 수 칸이 0 이상 정수가 아님 · 맞힘이 답할 질문보다 많음(부르는 쪽 실수).
    """
    if mode not in MODES:
        raise ValueError("mode")
    counts = {name: _count(score.get(name)) for name in _COUNTS}
    if any(value is None for value in counts.values()) or counts["hit"] > counts["answerable"] \
            or counts["unknown_ok"] > counts["unanswerable"]:
        raise ValueError("score")
    value = {"at": now.replace(microsecond=0).isoformat(), "mode": mode, **counts, "passed": score.get("passed") is True}
    row = session.get(SystemSetting, ASK_EVAL_KEY)
    if row is None:
        session.add(SystemSetting(setting_key=ASK_EVAL_KEY, setting_value=value, description=_DESCRIPTION))
    else:
        row.setting_value = value
    return value


def read_ask_eval(session: Any) -> Optional[dict[str, Any]]:
    """남긴 점수(없거나 꼴이 틀리면 ``None``)."""
    row = session.get(SystemSetting, ASK_EVAL_KEY)
    value = row.setting_value if row is not None else None
    if not isinstance(value, dict) or value.get("mode") not in MODES:
        return None
    if any(_count(value.get(name)) is None for name in _COUNTS):
        return None
    return value


def ask_eval_view(session: Any) -> dict[str, Any]:
    """'지식 물어보기'의 'AI 시험' 칸 — 줄 하나(맞힘 비율 · 근거 없는 답 · '모름' 맞힘 · 통과/기준 밑) · 마지막 시험 줄."""
    value = read_ask_eval(session)
    if value is None:
        return {"rows": [], "failures": [], "last": None, "running": False, "note": NO_RUN_NOTE}
    answerable, hit = value["answerable"], value["hit"]
    unanswerable, unknown_ok, unsupported = value["unanswerable"], value["unknown_ok"], value["unsupported"]
    pct = round(hit * 100 / answerable) if answerable else None
    text = " · ".join(part for part in (
        f"맞힘 {pct}% · 기준 {round(PASS_RATE * 100)}%" if pct is not None else "답할 질문 0개",
        f"근거 없는 답 {unsupported} · 기준 0",
        f"지식에 없는 질문 '모름' {unknown_ok}/{unanswerable}" if unanswerable else "") if part)
    verdict = {"text": "통과", "tone": "success"} if value["passed"] else {"text": "기준 밑", "tone": "danger"}
    row = {"key": "ask", "label": f"물어보기 평가 {answerable + unanswerable}개", "pct": pct, "text": text,
           "verdict": verdict}
    last = {"at": format_datetime_kst(value.get("at"), "%m-%d %H:%M"), "status": value["mode"],
            "status_label": MODES[value["mode"]], "code": None, "reason": None, "model": None,
            "progress": ""}
    return {"rows": [row], "failures": [], "last": last, "running": False, "note": ""}
