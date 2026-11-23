"""상담 AI 평가 — ⑪ 'AI 시험' 칸 값(설계서 2026-11-14-foms-graft 3.10 · 3.15 · D209). ``GET /api/ai-staff/cs`` 의 ``evals``.

저장은 :mod:`.evals`(설정 · 묶음 · 결과 줄), 돌리기는 :mod:`.evals_run`. 이 모듈은 읽기만 한다(500줄 상한으로 나눴다).

- 줄 셋: '지난 상담'(보내도 되는 답 비율 — 분모는 본 수 − 옳은 넘김, 지난번 비율 · 기준 — 0 이면 기준 없음 —
  설계서 2026-11-22-ai-eval-meaning-judge 2.5 · 2026-11-23-brain-learning-upgrade 4.2) · '위험 문장'(근거 없는 약속 수 · 기준 0) ·
  '능력 질문'(온톨로지 화면과 같은 재료 점수 — 돈 0, 보는 사람의 보기 범위). 숫자를 낸 마지막 시험(끝남 · 상한 · 시간 상한 · 도는
  중)으로 그린다.
- 옛 결과 줄(``judge`` 칸 없음 — '같은 뜻인가' 자, ``partial`` 칸 · ``same`` · ``partial`` · ``different`` 코드)은 옛 글
  "AI 답이 직원 답과 같은 뜻 N%" 그대로 그린다. 새 줄(:data:`.evals.JUDGE_VERSION`)은 "보내도 되는 답 N%". '지난번'은 같은 자로
  돈 시험끼리만 견준다.
- 사장님 채점(:mod:`.evals_marks`)이 있으면 지난 상담 줄 글 끝에 한 구절 — 채점 수, 모이면(:mod:`.evals_calibrate`) 안 되는 답을
  잡은 비율 · 되는 답을 통과시킨 비율 · 사장님 기준으로 바로잡은 초안 통과율(오차 폭), 넘김은 사장님 답이 '늘 사람 몫' 분류와
  같은 수.
- 틀린 차례(차례 번호 · 까닭 코드 · 화면 말 — 글 없음) · 마지막 시험 줄(때 · 상태 · 까닭 말 · 모델 · 진행 · ADMIN 만 쓴 돈).
- ADMIN 만: 돌릴 수 있음 · 막힌 까닭(돈 상한 0 · 묶음 0) · 설정 값. MANAGER 답에는 돈 열쇠가 없다.
- 꼬리표 · 막대 색 갈래는 success · primary · warning · danger 뿐(무채색 없음).
- 보이는 시험이 아직 도는 중(줄 섬 · 도는 중 — 오래 소식 없는 줄은 빼고)이면 줄 꼬리표는 판정 없이 '도는 중'(점검 2차 w3-13 —
  17/40 에서 '통과'를 보이지 않는다). 막대 · 결과 글(본 수)은 지금까지 값 그대로.
"""

from __future__ import annotations

import datetime
from typing import Any, Mapping, Optional

from foms.services.ai_staff import evals_marks as marks
from foms.services.ai_staff.evals import (
    ACTIVE, CAP_STOPPED, DONE, FAILED, JUDGE_VERSION, MESSAGES, NOT_READY, QUEUED, RUNNING, SCORED, SET_PAST, SET_RISK,
    STALE, TIME_STOPPED, UNSUPPORTED, is_stale, latest_results, naive_utc, parse_money, read_eval_settings,
)
from foms.services.ai_staff.evals_calibrate import calibrate
from foms.services.brain.ontology_view import ontology_summary
from foms.services.brain.scope import Viewer
from foms.services.cs_agent.checks import REASONS
from foms.services.cs_agent.settings_field import MODEL_NAMES
from foms.services.datetime_kst import format_datetime_kst, get_today_kst

__all__ = ["CODE_LABELS", "STATUS_LABELS", "STOP_LABELS", "eval_view"]

SHOWN_FAILURES = 5
STATUS_LABELS: dict[str, str] = {
    QUEUED: "줄 서는 중", RUNNING: "도는 중", DONE: "끝남", CAP_STOPPED: "상한에서 멈춤", TIME_STOPPED: "시간 상한에서 멈춤",
    NOT_READY: "준비 안 됨", FAILED: "실패", STALE: "멈춘 채 끝남",
}
SET_LABELS = {SET_PAST: "지난 상담", SET_RISK: "위험 문장"}
RUNNING_VERDICT = ("도는 중", "primary")
#: 틀린 까닭 코드 → 화면 말(검사 코드는 :data:`foms.services.cs_agent.checks.REASONS` 의 말).
CODE_LABELS: dict[str, str] = {
    "direct": "직원 답과 많이 다름", "edited": "직원이 고쳐 보냈을 답", "different": "직원 답과 뜻이 다름",
    "partial": "맞지만 중요한 안내가 빠짐", "fail_conflict": "직원 답과 사실이 어긋남", "fail_promise": "근거 없이 약속함",
    "fail_unanswered": "물은 것에 답하지 않음",
    "judge_unknown": "판정을 못 받음", "handoff": "사람에게 넘김", "refused": "답하지 않음",
    UNSUPPORTED: "근거 없는 약속", "mask_leak": "가림 검사에 걸림", "bad_request": "재료 꼴이 틀림",
    "timeout": "모델 답을 못 받음", "rate_limited": "모델 답을 못 받음", "api_error": "모델 답을 못 받음",
    "bad_response": "모델 답을 못 받음",
}
#: 멈춘 까닭 코드 → 화면 말(모르는 코드는 말 없이 상태만).
STOP_LABELS: dict[str, str] = {
    "no_cap": "돈 상한이 0", "no_api_key": "두뇌 열쇠 없음", "sdk_debug_logging": "본문 디버그 로그가 켜짐",
    "no_knowledge": "승인 지식 없음", "brand_not_enabled": "브랜드 꺼짐", "brand_mismatch": "지식 브랜드 다름",
    "api_auth": "열쇠 거절", "spend_record_invalid": "돈 줄 꼴이 틀림", "daily_cap_reached": "한 번 상한",
    "api_spend_limit": "콘솔 돈 상한", "queue_unavailable": "줄이 없음",
}


def _part(run: Optional[Mapping[str, Any]], kind: str) -> dict[str, int]:
    """결과 줄의 묶음 수 칸(정수만)."""
    part = run.get(kind) if run is not None and isinstance(run.get(kind), dict) else {}
    return {key: int(value) for key, value in part.items() if isinstance(value, int) and not isinstance(value, bool)}


def _pct(numerator: int, denominator: int) -> Optional[int]:
    """비율(%, 반올림) — 분모 0 이면 ``None``."""
    return round(numerator * 100 / denominator) if denominator else None


def _row(key: str, label: str, pct: Optional[int], text: str, verdict: tuple[str, str]) -> dict[str, Any]:
    """화면 줄 하나 — 막대 비율(없으면 ``None``) · 결과 글 · 꼬리표(글 · 색 갈래 — 무채색 없음)."""
    return {"key": key, "label": label, "pct": pct, "text": text, "verdict": {"text": verdict[0], "tone": verdict[1]}}


def _past_pct(run: Optional[Mapping[str, Any]]) -> Optional[int]:
    """'지난 상담' 통과 비율 = 통과 ÷ (본 수 − 옳은 넘김). 옳은 넘김 칸이 없는 옛 줄은 0 으로 본다."""
    part = _part(run, SET_PAST)
    return _pct(part.get("passed", 0), part.get("done", 0) - part.get("right_handoff", 0))


def _judge_of(run: Optional[Mapping[str, Any]]) -> int:
    """그 시험의 판정 자의 판(칸이 없는 옛 줄은 1 — '같은 뜻인가')."""
    judge = run.get("judge") if run is not None else None
    return judge if isinstance(judge, int) and not isinstance(judge, bool) else 1


def _p(share: Optional[float]) -> int:
    return round((share or 0.0) * 100)


def _marks_phrase(session: Any, shown: Optional[Mapping[str, Any]]) -> str:
    """사장님 채점 한 구절(모듈 설명) — 채점이 없으면 빈 글."""
    pairs, (handed, agreed) = marks.graded_pairs(session)
    run_id = shown.get("id") if shown is not None else None
    seen = (marks.observed(session, run_id) if isinstance(run_id, int) and _judge_of(shown) == JUDGE_VERSION
            else (0, 0))
    cal = calibrate(pairs, seen)
    parts = [f"사장님 채점 {cal.graded}개"] if cal.graded else []
    if cal.ready:
        parts.append(f"안 되는 답 {_p(cal.caught)}% 잡음 · 되는 답 {_p(cal.passed_ok)}% 통과")
        if cal.corrected is not None:
            spread = f"({_p(cal.low)}~{_p(cal.high)}%)" if cal.low is not None else ""
            parts.append(f"사장님 기준 초안 통과 {_p(cal.corrected)}%{spread}")
        elif seen[0]:
            parts.append("채점이 사장님과 너무 달라 바로잡지 못해요")
    if handed:
        parts.append(f"넘김 {handed}개 가운데 {agreed}개 사장님과 같음")
    return " · ".join(parts)


def _past_row(run: Optional[Mapping[str, Any]], live: bool = False,
              previous: Optional[Mapping[str, Any]] = None, graded: str = "") -> dict[str, Any]:
    """'지난 상담' 줄 — 통과 비율(차례 · 옳은 넘김 · 지난번) · 기준(0 이면 기준 없음) · 사장님 채점 구절(``graded``).
    ``live`` 면(도는 중) 판정 대신 '도는 중'."""
    part = _part(run, SET_PAST)
    total, done, right = part.get("total", 0), part.get("done", 0), part.get("right_handoff", 0)
    if run is None:
        return _row(SET_PAST, "지난 상담", None, "아직 돌리지 않았어요.", ("아직", "warning"))
    if total == 0:
        return _row(SET_PAST, "지난 상담 0개", None, "시험용으로 떼어 둔 상담이 없어요 — 묶음 0", ("묶음 0", "warning"))
    pct, target = _past_pct(run), int(run.get("target_pct") or 0)
    tail = f" · {graded}" if graded else ""
    if pct is None:
        text = f"견줄 차례가 아직 없어요 (옳은 넘김 {right})" if done else "아직 한 차례도 못 봤어요."
        return _row(SET_PAST, f"지난 상담 {total}개", None, text + tail, ("아직", "warning"))
    before = _past_pct(previous) if _judge_of(previous) == _judge_of(run) else None  # 같은 자끼리만 견준다
    head = "보내도 되는 답" if _judge_of(run) == JUDGE_VERSION else "AI 답이 직원 답과 같은 뜻"
    text = (f"{head} {pct}% ({done - right}차례 · 옳은 넘김 {right}"
            + (f" · 지난번 {before}%)" if before is not None else ")"))
    text += f" · 기준 {target}%" if target else ""
    text += f" · {done}/{total}개 봄" if done < total else ""
    verdict = (("통과", "success") if pct >= target else ("기준 밑", "danger")) if target else (f"{pct}%", "primary")
    return _row(SET_PAST, f"지난 상담 {total}개", pct, text + tail, RUNNING_VERDICT if live else verdict)


def _risk_row(run: Optional[Mapping[str, Any]], live: bool = False) -> dict[str, Any]:
    """'위험 문장' 줄 — 검사를 지나고도 근거 없는 약속을 담은 수(기준 0). ``live`` 면(도는 중) 판정 대신 '도는 중'."""
    part = _part(run, SET_RISK)
    total, done, bad = part.get("total", 0), part.get("done", 0), part.get("bad", 0)
    if run is None:
        return _row(SET_RISK, "위험 문장", None, "아직 돌리지 않았어요.", ("아직", "warning"))
    if total == 0:
        return _row(SET_RISK, "위험 문장 0개", None, "검사에 걸린 적 있는 차례가 없어요 — 묶음 0", ("묶음 0", "warning"))
    if done == 0:
        return _row(SET_RISK, f"위험 문장 {total}개", None, "아직 한 차례도 못 봤어요.", ("아직", "warning"))
    text = f"근거 없는 약속 {bad} · 기준 0" + (f" · {done}/{total}개 봄" if done < total else "")
    verdict = ("통과", "success") if bad == 0 else (f"{bad}건", "danger")
    return _row(SET_RISK, f"위험 문장 {total}개", _pct(done - bad, done), text, RUNNING_VERDICT if live else verdict)


def _cq_row(session: Any, viewer: Viewer, erp: bool) -> dict[str, Any]:
    """'능력 질문' 줄 — 온톨로지 화면과 같은 재료 점수(돈 0 · 보는 사람의 보기 범위)."""
    cq = ontology_summary(session, viewer, today=get_today_kst(), erp=erp)["cq"]
    covered, total = int(cq["covered"]), int(cq["total"])
    text = (f"회사 지식만 {cq['covered_before']} · 주문 읽기 더하면 {covered}" if "covered_before" in cq
            else f"회사 지식만 {covered}")
    return _row("cq", f"능력 질문 {total}개", _pct(covered, total), text,
                (f"{covered} / {total}", "success" if total and covered == total else "warning"))


def _failures(run: Optional[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """틀린 차례 — 새 것부터 :data:`SHOWN_FAILURES` 개(차례 번호 · 까닭 코드 · 화면 말, 글 없음)."""
    items = run.get("failures") if run is not None and isinstance(run.get("failures"), list) else []
    out = []
    for item in reversed(items[-SHOWN_FAILURES:]):
        if isinstance(item, dict) and item.get("set") in SET_LABELS and isinstance(item.get("turn"), int):
            code = str(item.get("code") or "")
            out.append({"label": f"{SET_LABELS[item['set']]} · 차례 #{item['turn']}", "code": code,
                        "reason": CODE_LABELS.get(code) or REASONS.get(code) or code})
    return out


def _status_of(run: Mapping[str, Any], at: datetime.datetime) -> str:
    """보이는 상태 — 오래 소식 없는 줄 섬 · 도는 중은 '멈춘 채 끝남'."""
    status = str(run.get("status") or "")
    return STALE if status in ACTIVE and is_stale(run, at) else status


def _last(run: Optional[Mapping[str, Any]], at: datetime.datetime, admin: bool) -> Optional[dict[str, Any]]:
    """마지막으로 돌린 때 · 상태 · 모델 · 묶음 진행 · (ADMIN 만) 쓴 돈."""
    if run is None:
        return None
    status = _status_of(run, at)
    past, risk = _part(run, SET_PAST), _part(run, SET_RISK)
    code = run.get("code") if isinstance(run.get("code"), str) else None
    out = {"at": format_datetime_kst(run.get("started_at"), "%m-%d %H:%M"), "status": status,
           "status_label": STATUS_LABELS.get(status, status), "code": code, "reason": STOP_LABELS.get(code or ""),
           "model": MODEL_NAMES.get(run.get("model"), run.get("model")),
           "progress": f"지난 상담 {past.get('done', 0)}/{past.get('total', 0)} · "
                       f"위험 문장 {risk.get('done', 0)}/{risk.get('total', 0)}"}
    if admin:
        cost = parse_money(run.get("cost_usd", "0"))
        out["cost"] = f"${cost:,.2f}" if cost is not None else None
    return out


def eval_view(session: Any, viewer: Viewer, *, now: datetime.datetime, erp: bool) -> dict[str, Any]:
    """⑪ 'AI 시험' 칸 값 — ``GET /api/ai-staff/cs`` 의 ``evals``.

    Returns:
        ``{"rows": [지난 상담, 위험 문장, 능력 질문], "failures", "last", "running"}`` + ADMIN 만
        ``{"can_run", "blocked", "settings"}``(돈 상한 · 묶음 크기 · 기준). MANAGER 답에는 돈 열쇠가 없다.
    """
    at = naive_utc(now)
    runs = latest_results(session)
    latest = runs[0] if runs else None
    scored = [run for run in runs if run.get("status") in SCORED]
    shown, previous = (scored + [None, None])[:2]
    running = latest is not None and _status_of(latest, at) in ACTIVE
    live = shown is not None and _status_of(shown, at) in ACTIVE  # 보이는 숫자가 아직 끝나지 않은 시험 것
    rows = [_past_row(shown, live, previous, _marks_phrase(session, shown)), _risk_row(shown, live),
            _cq_row(session, viewer, erp)]
    out: dict[str, Any] = {"rows": rows, "failures": _failures(shown), "last": _last(latest, at, viewer.is_admin),
                           "running": running}
    if viewer.is_admin:
        settings = read_eval_settings(session)
        blocked = ("EVAL_NO_CAP" if settings.cap_usd <= 0 else
                   "EVAL_NO_SIZE" if settings.past_size + settings.risk_size <= 0 else None)
        out.update(can_run=True, settings=settings.as_dict(),
                   blocked={"code": blocked, "message": MESSAGES[blocked]} if blocked else None)
    return out
