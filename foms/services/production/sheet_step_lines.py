"""작업 시트 공정 보기 줄 — 도면이 있는 주문의 공정 칸 넷(사장님 2026-11-27 "도면이 주, 작업 시트는 보기").

사장님 결정(질문 창 설명 그대로): "작업 시트의 공정 칸은 누르는 칸이 아니라 '재단 2/3 · 김재단 작업 중', '엣지 미정' 같은 진행
표시가 되고, 누르면 그 주문의 도면 화면으로 갑니다. … 도면이 아예 없는 주문만 지금처럼 칸을 누릅니다."

**순수 계산 · 쿼리 0** — 작업 시트 뷰(``production_sheet_view``)가 이미 읽은 표시 줄을 넘긴다. 낱말은 이미 화면에 있는 것만:

* 세부 기록(사장님 2026-11-27 둘째 말 "여기서 공정에 세부기록 남겨(어떤 인원이 작업 중인지 등)"): 사람 이름 + 때. 작업 중 = 먼저 시작한
  사람부터 · 시작한 때는 맨 먼저 시작한 사람 것("김재단 11/27 09:30부터 작업 중" — 반장 고르기 창 제목 "박엣지 08:10부터 작업 중" 꼴),
  완료 = 마지막에 완료한 사람부터 · 때는 마지막 완료("재단 완료 · 김재단 11/27 10:32" — 옛 칸 옆 글 "도면 2/2 완료 · 김재단 11/24 15:02" 꼴).
  여러 명이면 도면 카드 이름 줄(:func:`~foms.services.production.mark_crew.name_line` — 둘까지 이름, 나머지 "외 n"). 때 글 = PC 도면 목록 창과
  같은 :func:`~foms.services.production.pc_sheet.stamp`("M/D HH:MM", KST).
* 줄 글: 모두 완료 "재단 완료 · 김재단 11/27 10:32" · 일부 완료 "재단 2/3 완료 · 김재단 11/27 09:30부터 작업 중"(아무도 안 하면
  "재단 2/3 완료 · 미정") · 아무도 완료 안 함 "재단 김재단 11/27 09:30부터 작업 중" · "엣지 미정". 재단 [기본] 장이 있으면 카드 낱말 "기본" +
  장 수("재단 완료 · 기본 2장 · 김재단 11/27 10:32"), 담당이 바뀐 장이 있으면 끝에 " · 바뀜 n"(옛 칸 옆 글과 같은 꼬리). 손으로 켜 둔 옛 칸은 도면 카드 글 "재단 완료 · 박반장" + 때 + " · 작업 시트에서 완료"
  (:func:`~foms.services.production.part_card_state.hand_cell` · PC 도면 목록 창 작은 글).
* 색 뜻 = 도면 카드와 같다: 완료 초록(``ok``) · 작업 중 남색(``run``) · 미정 호박(``miss`` — 작업 시트 "n장 미완료" 글과 같은 색).
* 줄이 길면 글 칸 안에서 두 줄로 내려간다(말줄임 없음 — sheet.css ``.fpp-note``).

도면 0장 주문은 None — 지금 체크 칸 그대로.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from foms.services.production import mark_crew as mc
from foms.services.production.part_card_state import hand_cell
from foms.services.production.part_constants import (
    BASIC_ALLOWED_PARTS,
    MARK_STATE_BASIC,
    MARK_STATE_DONE,
    MARK_STATE_NEED,
    PRODUCTION_PART_KEYS,
    PRODUCTION_PART_LABELS,
    basic_word,
)
from foms.services.production.part_holders import HOLDER_NONE
from foms.services.production.part_progress import current_keys, marks_by_part, part_progress, per_sheet_only
from foms.services.production.pc_sheet import stamp

#: 손으로 켜 둔 옛 칸의 꼬리 — 도면 카드 · PC 도면 목록 창이 같은 칸에 쓰는 작은 글.
HAND_NOTE = "작업 시트에서 완료"
TONE_OK, TONE_RUN, TONE_MISS = "ok", "run", "miss"
_FLOOR = datetime.datetime.min


def _people(rows: list[Any], *, done: bool) -> tuple[list[str], Any]:
    """(이름 차례, 때) — 완료 = 늦게 완료한 사람부터 · 마지막 완료 때, 작업 중 = 먼저 시작한 사람부터 · 맨 먼저 시작한 때.
    같이 작업한 줄은 사람마다(목록 ``crew``), 목록이 없으면 줄의 요약 칸(완료한 사람 · 맡은 사람)."""
    pairs: list[tuple[Any, str]] = []
    for row in rows:
        crew = mc.crew_of(row)
        if done:
            got = [(mc.from_iso(m.get("done_at")), str(m.get("done_name") or "").strip()) for m in crew if mc.is_done(m)]
            got = got or [(getattr(row, "done_at", None), str(getattr(row, "done_by_name", None) or "").strip())]
        else:
            got = [(mc.from_iso(m.get("at")), str(m.get("name") or "").strip()) for m in crew if not mc.is_done(m)]
            got = got or [(getattr(row, "picked_at", None), str(getattr(row, "picked_by_name", None) or "").strip())]
        pairs += [(at, name) for at, name in got if name]
    pairs.sort(key=lambda p: p[0] or _FLOOR, reverse=done)
    names: list[str] = []
    for _at, name in pairs:
        if name not in names:
            names.append(name)
    return names, (pairs[0][0] if pairs else None)


def _who(names: list[str], at: Any, tail: str = "") -> str:
    """이름 줄 + 때 — "김재단 11/27 10:32" · "김재단 · 오재단 외 1 11/27 09:30부터 작업 중"."""
    when = stamp(at)
    return " ".join(p for p in (mc.name_line(names), f"{when}{tail}" if when else tail.strip()) if p)


def _line(part: str, text: str, tone: str, *, done: bool, hand: bool = False) -> dict[str, Any]:
    label = PRODUCTION_PART_LABELS[part]
    return {"key": part, "label": label, "text": text, "rest": text[len(label) + 1:], "tone": tone, "done": done, "hand": hand}


def idle_line(part: str) -> dict[str, Any]:
    """아무도 손 안 댄 파트 "엣지 미정" — 손 체크 칸을 끈 뒤 그 자리에 보일 줄도 이것(카드를 안 쓴 파트라 남는 것이 없다)."""
    return _line(part, f"{PRODUCTION_PART_LABELS[part]} {HOLDER_NONE}", TONE_MISS, done=False)


def step_line(sd: Any, marks: list[Any], part: str, today: datetime.date) -> dict[str, Any]:
    """파트 하나의 보기 줄.

    Returns:
        ``{key, label, text, rest, tone, done, hand[, off]}`` — ``text`` = 줄 글 전부("재단 2/3 완료 · 김재단 11/27 09:30부터 작업 중"), ``rest`` = 이름 칸
        뒤 글(화면은 이름 칸 · 뒤 글 둘로 그린다), ``hand`` = 손으로 켜 둔 옛 칸(반장 · 관리자에게 끄는 길이 남는다), ``off`` = 그 칸을
        끈 뒤의 줄(:func:`idle_line`).
    """
    label = PRODUCTION_PART_LABELS[part]
    hand = hand_cell(sd, marks, part)
    if hand is not None:  # 끈 뒤 그 자리 줄(``off``)도 함께 — 화면이 끄기 응답 뒤 요청 없이 바꿔 보인다
        when = stamp(_step_at(sd, part))
        text = f"{hand['text']}{f' {when}' if when else ''} · {HAND_NOTE}"
        return {**_line(part, text, TONE_OK, done=True, hand=True), "off": idle_line(part)}
    progress = part_progress(sd, marks, part)
    rows = [r for k, r in marks_by_part(marks).get(part, {}).items() if k in set(current_keys(sd))]
    finished = [r for r in rows if str(getattr(r, "state", "")) == MARK_STATE_DONE]
    held = [r for r in rows if str(getattr(r, "state", "")) == MARK_STATE_NEED]
    basic = sum(1 for r in rows if part in BASIC_ALLOWED_PARTS and str(getattr(r, "state", "")) == MARK_STATE_BASIC)
    extra = [f"{basic_word(part)} {basic}장"] if basic else []  # 재단 "기본 2장" · 조립 "조립 없음 2장"
    handed = sum(1 for r in rows if getattr(r, "handed_from_name", None))
    tail = [f"바뀜 {handed}"] if handed else []  # 담당이 바뀐 장 — 옛 칸 옆 글("… · 바뀜 1")과 같은 꼬리
    if progress["done"]:
        names, at = _people(finished, done=True)
        who = _who(names, at)
        return _line(part, " · ".join([f"{label} 완료", *extra, *([who] if who else []), *tail]), TONE_OK, done=True)
    head = f"{label} {progress['done_n']}/{progress['total_n']} 완료" if progress["done_n"] else label
    if held:
        names, at = _people(held, done=False)
        who = _who(names or ["다른 사람"], at, "부터 작업 중") if at else _who(names or ["다른 사람"], None, " 작업 중")
        if not progress["done_n"]:
            return _line(part, " · ".join([f"{head} {who}", *tail]), TONE_RUN, done=False)
        return _line(part, " · ".join([head, *extra, who, *tail]), TONE_RUN, done=False)
    if not progress["done_n"]:
        return idle_line(part)
    return _line(part, " · ".join([head, *extra, HOLDER_NONE, *tail]), TONE_MISS, done=False)


def _step_at(sd: Any, part: str) -> Any:
    production = sd.get("production") if isinstance(sd, dict) else None
    for step in (production or {}).get("steps") or [] if isinstance(production, dict) else []:
        if isinstance(step, dict) and step.get("key") == part:
            return step.get("at")
    return None


def sheet_step_lines(sd: Any, marks: list[Any], today: datetime.date) -> Optional[dict[str, dict[str, Any]]]:
    """작업 시트 공정 칸 넷의 보기 줄(파트 → 줄) — 도면이 있는 주문만(공정 API 켜기 거절 ``STEP_PER_SHEET`` 와 같은 한 판정
    :func:`~foms.services.production.part_progress.per_sheet_only`). 도면 0장 주문은 None(지금 체크 칸)."""
    if not per_sheet_only(sd):
        return None
    marks = list(marks)
    return {part: step_line(sd, marks, part, today) for part in PRODUCTION_PART_KEYS}


__all__ = ["HAND_NOTE", "TONE_MISS", "TONE_OK", "TONE_RUN", "idle_line", "sheet_step_lines", "step_line"]
