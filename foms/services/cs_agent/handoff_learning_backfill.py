"""쌓인 지식 한 번 잇기(되채우기 — 설계 글 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 7.3 · 사장님 11-26
'뻔한 것은 AI가 바로' · 11-27 "공정 단계만 여쭙게 하고 켜기").

사람 세션이 지식 전체를 읽어 만든 잇기 계획(저장소 밖 JSON — 관리자 스크립트 ``scripts/maintenance/brain_link_backfill.py``)을 밤
이어 붙이기(:mod:`.handoff_learning_link`)와 **같은 거르기 · 가름 · 넣는 길**로 넣는다. 규칙을 다시 쓰지 않고 그 모듈 함수를 그대로
부른다(규칙은 한 벌).

계획 꼴: ``{"links": [{"from": 키, "kind": 종류, "to": 키, "glyph": 참 · 거짓, "sure": "high" | "mid", "why": 한 줄}], "same": [...],
"clash": [...]}`` — ``same`` · ``clash`` 는 수만 센다(합치기는 늘 사장님). 계획의 ``glyph`` 는 믿지 않는다 — 코드가 다시 잰다.

줄마다(버리면 까닭 코드별로 센다):

1. **꼴** — 키 둘 · 종류(:data:`.handoff_learning_link_prompt.KINDS`) · 확신 · 근거 한 줄(:func:`why_reason` — 가림 · 한자 0).
   같은 (시작, 종류, 대상)이 다시 나오면 ``repeat``.
2. **시작 항목** — 지금 판이 살아 있나(없음 · 은퇴 · 기간 끝남은 ``source``).
3. **대상 거르기** — :func:`check_target`(모르는 키 · 은퇴 · 자기 자신 · 허용 짝 밖 · 이미 있는 잇기 · 열린 같은 안 · 사장님이
   거절했거나 'AI 가 배운 것'에서 지운 같은 잇기 · 링크 제약).
4. **가름** — **바로**: :func:`auto_block` 이 ``None``(종류 — 공정 단계 · 금액 · 수량 · 같이 안 됨은 늘 사장님 · 코드 글자 맞춤
   (:func:`glyph_matches`)이 그 대상을 가리키고 그 이름의 지식이 하나뿐 · 보기 범위 · 브랜드 · 사장님 결정 끝) · 계획 확신 ``high`` ·
   패널 '배운 것 바로 반영' 켬. 하나라도 빠지면 **올림**(열린 제안 — 승인 대기 ⑥ 규칙 잇기 칸, 금액 · 꼭 같이 · 같이 안 됨은 ② 한
   장씩 — :func:`foms.services.brain.inbox_bins.rule_link_change`). 올린 까닭은 처음 빠진 조건 코드로 센다(``ask_why``). 시작 유형은
   가리지 않는다(밤 붙이기는 배운 사실 · 정책 · 상황 · 제작 조건만 고른다 — 시작 유형별 수 ``by_source_type`` 로 보인다).
5. **넣기** — :func:`file_link` 그대로(만든 이 ``agent:cs_handoff_learning`` — 바로 넣은 것은 'AI 가 배운 것'에 뜨고 거기서 지운다).
   까닭 글은 ``쌓인 지식 잇기(되채우기) — <근거>``(밤 붙이기와 구별). 근거는 시작 항목 지금 판을 만든 제안의 근거
   (:func:`source_evidence`) — 서로 다른 사람 둘이 없으면(옮기기 · 사람이 만든 지식) 제안 길 근거 관문이 막는다(``brain_evidence``).

올림은 한 번에 ``max_ask`` 개까지(사장님 하루 몫) — 넘는 것은 넣지 않고 ``ask_left`` 로 센다(다음 실행이 넣는다). 멱등 — 다시
돌리면 들어간 잇기(``exists``) · 열린 같은 안(``open``)으로 빠진다.

**미리 돌려 보기**(``apply=False`` — 기본): 같은 일을 저장점 안에서 다 하고 되돌린다. 넣는 길이 안마다 부르는 커밋 · 되돌리기는
:class:`_Trial` 이 안쪽 저장점 풀기 · 되돌리기로 바꾼다 — 제안 길 관문 · 바로 반영까지 돌아 수가 넣을 때와 같다.

내는 것은 수 · 코드뿐(글 · 이름 · 금액 없음) — 버린 줄의 키는 ``show_dropped`` 일 때만.
"""

from __future__ import annotations

import datetime
from typing import Any, Collection, Mapping, Optional, Sequence

from foms.services.brain.constants import OP_LINK_ADD, STATUS_ACTIVE
from foms.services.brain.errors import BrainShapeError
from foms.services.brain.inbox_bins import BIN_CONTENT, BIN_RULES, rule_link_change
from foms.services.brain.proposals import Proposer
from foms.services.brain.store import current_object, kst_day
from foms.services.cs_agent import handoff_learning_link_prompt as lp
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.handoff_learning import auto_learn
from foms.services.cs_agent.handoff_learning_gates import AGENT
from foms.services.cs_agent.handoff_learning_link import (
    auto_block, check_target, file_link, glyph_matches, label_owners, source_evidence, why_reason,
)
from foms.services.cs_agent.settings import read_settings

__all__ = ["LANES", "MAX_ASK", "REASON_HEAD", "SURE", "plan_lines", "run_backfill"]

#: 한 번에 올리는 수 상한(사장님 하루 몫) · 제안 까닭 글 머리(밤 붙이기 :data:`.handoff_learning_link.REASON_HEAD` 와 구별).
MAX_ASK = 60
REASON_HEAD = "쌓인 지식 잇기(되채우기)"
SURE: tuple[str, ...] = ("high", "mid")
LANES: tuple[str, ...] = ("auto", "ask")
_PROPOSER = Proposer.agent_named(AGENT).name


class _Trial:
    """미리 돌려 보기 세션 — 넣는 길의 커밋은 안쪽 저장점 풀기, 되돌리기는 그 저장점까지만. 바깥 저장점은 끝(:meth:`close`)에
    트랜잭션째 되돌린다(쓰기 0). 나머지는 진짜 세션에 그대로 넘긴다."""

    def __init__(self, session: Any) -> None:
        self._session = session
        self._outer = session.begin_nested()  # 안쪽 저장점 풀기가 트랜잭션을 끝내지 않게(SQLite 는 첫 저장점이 곧 트랜잭션)
        self._point = session.begin_nested()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    def commit(self) -> None:
        self._point.commit()
        self._point = self._session.begin_nested()

    def rollback(self) -> None:
        self._point.rollback()
        self._point = self._session.begin_nested()

    def close(self) -> None:
        self._session.rollback()


def plan_lines(plans: Sequence[Any]) -> tuple[list[Any], dict[str, int]]:
    """계획 묶음들 → 잇기 줄(차례 그대로 이어 붙임) · 계획 수(묶음 · 줄 · 같은 내용 · 어긋남).

    Raises:
        BrainShapeError: 묶음이 JSON 객체가 아니거나 ``links`` 가 목록이 아니다(글은 싣지 않는다).
    """
    lines: list[Any] = []
    counts = {"files": 0, "links": 0, "same": 0, "clash": 0}
    for plan in plans:
        if not isinstance(plan, Mapping) or not isinstance(plan.get("links", []), list):
            raise BrainShapeError(["plan: links 목록이 있는 JSON 객체여야 한다"])
        links = plan.get("links") or []
        counts["files"] += 1
        counts["links"] += len(links)
        for name in ("same", "clash"):
            counts[name] += len(plan[name]) if isinstance(plan.get(name), list) else 0
        lines.extend(links)
    return lines, counts


def _shape(line: Any) -> tuple[Optional[str], Optional[tuple[str, str, str]], Optional[str], Optional[str]]:
    """꼴(모듈 설명 1) → (버린 까닭, (시작, 종류, 대상), 확신, 제안 까닭 글)."""
    if not isinstance(line, Mapping):
        return "form", None, None, None
    start, kind, to = (line[k].strip() if isinstance(line.get(k), str) else "" for k in ("from", "kind", "to"))
    if not start or not to or kind not in lp.KINDS or line.get("sure") not in SURE:
        return "form", None, None, None
    code, reason = why_reason(line.get("why"), REASON_HEAD)
    return code, (start, kind, to), str(line["sure"]), reason


def _alive(source: Any, today: datetime.date) -> bool:
    """시작 항목 지금 판이 살아 있나(은퇴 · 기간 끝남이 아님)."""
    return source is not None and source.status == STATUS_ACTIVE and (source.valid_to is None or source.valid_to >= today)


def _held(kind: str, source: Any, target: Any, *, sure: str, found: dict[str, bool], to: str, auto: Any) -> Optional[str]:
    """바로 넣는 조건(모듈 설명 4)에서 처음 빠진 것 — 다 맞으면 ``None``."""
    blocked = auto_block(kind, source, target, matched=to in found, unique=found.get(to, False))
    if blocked is not None:
        return blocked
    if sure != "high":
        return "mid"
    return "auto_off" if auto is None else None


class _Tally:
    """수 모음(글 · 이름 없음 — 키는 ``show_dropped`` 일 때 버린 줄만)."""

    def __init__(self, show_dropped: bool) -> None:
        self.show = show_dropped
        self.by_kind: dict[str, dict[str, int]] = {}
        self.by_source_type: dict[str, dict[str, int]] = {}
        self.ask_why: dict[str, int] = {}
        self.ask_bins = {BIN_RULES: 0, BIN_CONTENT: 0}
        self.dropped: dict[str, int] = {}
        self.dropped_keys: list[dict[str, Any]] = []
        self.glyph_fixed = {"plan_yes_code_no": 0, "plan_no_code_yes": 0}
        self.only_held = {"auto": 0, "ask": 0}
        self.ask_left = 0
        self.ends: dict[str, dict[str, int]] = {"from": {}, "to": {}}

    @property
    def asks(self) -> int:
        return sum(self.ask_bins.values())

    def drop(self, code: str, number: int, triple: Optional[tuple[str, str, str]]) -> None:
        self.dropped[code] = self.dropped.get(code, 0) + 1
        if self.show:
            keys = dict(zip(("from", "kind", "to"), triple)) if triple is not None else {}
            self.dropped_keys.append({"n": number, "code": code, **keys})

    def glyph(self, said: Any, found: bool) -> None:
        if said is True and not found:
            self.glyph_fixed["plan_yes_code_no"] += 1
        elif said is not True and found:
            self.glyph_fixed["plan_no_code_yes"] += 1

    def filed(self, code: str, number: int, triple: tuple[str, str, str], source: Any, held: Optional[str]) -> None:
        """넣는 길 결과 — 바로 · 올림(바로 반영이 막혀 열린 채 남은 것도 올림)이 아니면 버린 까닭."""
        if code not in ("auto", "proposed", "auto_blocked"):
            self.drop(code, number, triple)
            return
        start, kind, to = triple
        lane = "auto" if code == "auto" else "ask"
        for table, name in ((self.by_kind, kind), (self.by_source_type, source.item_type)):
            row = table.setdefault(name, {"auto": 0, "ask": 0})
            row[lane] += 1
        for end, key in (("from", start), ("to", to)):
            self.ends[end][key] = self.ends[end].get(key, 0) + 1
        if lane == "ask":
            why = "auto_blocked" if code == "auto_blocked" else str(held)
            self.ask_why[why] = self.ask_why.get(why, 0) + 1
            rules = rule_link_change(OP_LINK_ADD, kind, proposed_by=_PROPOSER, link_to=to)
            self.ask_bins[BIN_RULES if rules else BIN_CONTENT] += 1

    def summary(self) -> dict[str, Any]:
        totals = {lane: sum(row[lane] for row in self.by_kind.values()) for lane in LANES}
        out: dict[str, Any] = {
            "auto_total": totals["auto"], "ask_total": totals["ask"], "dropped_total": sum(self.dropped.values()),
            "by_kind": dict(sorted(self.by_kind.items())), "by_source_type": dict(sorted(self.by_source_type.items())),
            "ask_bins": self.ask_bins, "ask_why": dict(sorted(self.ask_why.items())), "ask_left": self.ask_left,
            "only_held": self.only_held, "dropped": dict(sorted(self.dropped.items())), "glyph_fixed": self.glyph_fixed,
            "most_on_one": {end: max(counts.values(), default=0) for end, counts in self.ends.items()},
        }
        if self.show:
            out["dropped_keys"] = self.dropped_keys
        return out


def _run(session: Any, picked: Sequence[Any], *, now: datetime.datetime, only: Optional[str], max_ask: int,
         tally: _Tally) -> None:
    """줄마다 꼴 → 시작 → 대상 거르기 → 가름 → 넣기(모듈 설명 1 ~ 5)."""
    today = kst_day(naive_utc(now))
    auto = auto_learn(session, read_settings(session, log=False))
    owners = label_owners(session, today)
    matches: dict[str, dict[str, bool]] = {}
    evidence: dict[str, list[str]] = {}
    seen: set[tuple[str, str, str]] = set()
    for number, line in enumerate(picked, start=1):
        code, triple, sure, reason = _shape(line)
        if code is None and triple in seen:
            code = "repeat"
        if code is not None or triple is None:
            tally.drop(code or "form", number, triple)
            continue
        seen.add(triple)
        start, kind, to = triple
        source = current_object(session, start)
        if not _alive(source, today):
            tally.drop("source", number, triple)
            continue
        code, target = check_target(session, source, kind, to, today)
        if code is not None:
            tally.drop(code, number, triple)
            continue
        if start not in matches:  # 계획의 glyph 는 믿지 않는다 — 시작 항목 글에서 코드가 다시 잰다
            matches[start] = glyph_matches(source.text, start, owners)
            evidence.update(source_evidence(session, [source]))
        tally.glyph(line.get("glyph"), to in matches[start])
        held = _held(kind, source, target, sure=str(sure), found=matches[start], to=to, auto=auto)
        lane = "auto" if held is None else "ask"
        if only is not None and lane != only:
            tally.only_held[lane] += 1
            continue
        if lane == "ask" and tally.asks >= max_ask:
            tally.ask_left += 1
            continue
        done = file_link(session, source, kind, to, reason=str(reason), evidence=evidence[start], auto=auto, now=now,
                         wanted_auto=held is None)
        tally.filed(done, number, triple, source, held)


def run_backfill(session: Any, plans: Sequence[Any], *, now: datetime.datetime, apply: bool = False,
                 only: Optional[str] = None, limit: Optional[int] = None, kinds: Optional[Collection[str]] = None,
                 max_ask: int = MAX_ASK, show_dropped: bool = False) -> dict[str, Any]:
    """잇기 계획을 넣는다(모듈 설명). ``apply`` 가 아니면 저장점 안에서 같은 일을 하고 되돌린다(쓰기 0).

    Args:
        plans: 읽은 계획 묶음들(차례대로 이어 붙인다).
        now: 지금 시각(시간대 있는 값).
        only: ``auto`` · ``ask`` 면 그쪽만 넣는다(다른 쪽은 ``only_held`` 로 센다).
        limit: 앞 N 줄만(``kinds`` 로 고른 뒤).
        kinds: 이 종류만(나머지는 ``kinds_skipped`` 로 센다).
        max_ask: 한 번에 올리는 수 상한 — 넘는 것은 ``ask_left``.
        show_dropped: 버린 줄의 차례 · 키 · 까닭을 싣는다(글 없음).

    Returns:
        수 · 코드만(모듈 설명).

    Raises:
        BrainShapeError: 계획 묶음 꼴 · ``only`` · ``limit`` · ``max_ask`` 값이 틀렸다.
    """
    problems = [*(["only: auto 또는 ask"] if only not in (None, *LANES) else []),
                *(["limit: 1 이상"] if limit is not None and limit < 1 else []),
                *(["max_ask: 0 이상"] if max_ask < 0 else [])]
    if problems:
        raise BrainShapeError(problems)
    lines, plan = plan_lines(plans)
    wanted = [line for line in lines if not kinds or (isinstance(line, Mapping) and line.get("kind") in kinds)]
    picked = wanted[:limit] if limit is not None else wanted
    tally = _Tally(show_dropped)
    work = session if apply else _Trial(session)
    try:
        _run(work, picked, now=now, only=only, max_ask=max_ask, tally=tally)
    finally:
        if not apply:
            work.close()
    return {"applied": bool(apply), "plan": plan, "kinds_skipped": len(lines) - len(wanted), "picked": len(picked),
            "max_ask": max_ask, **tally.summary()}
