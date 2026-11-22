"""넘김 학습 넣기 — 우리 쪽 관문(:mod:`.handoff_learning_gates`) → 놓을 자리 판정(:mod:`.handoff_learning_place`) → 제안 길
(사장님 2026-11-22 '배우기를 지금 고쳐' · 설계서 ``docs/specs/2026-11-22-cs-learning-placement_SPEC.md`` 2.2).

그대로 두는 것: 꼴 · 가림 · 근거 · 숫자 관문, 사장님이 거절 · 지운 말 다시 안 넣기, **서로 다른 손님 둘 이상의 다른 말은 바로
고침**(D267 — 막히면 그 항목 엇갈림 카드), 두뇌의 고치기(``update``) 안(공용 부딪침 관문 — 막히면 그 항목 엇갈림 카드).

그 밖의 안(새로 만들기 · 바로 고치지 못한 다른 말)은 같음 · 겹침 관문(글자 비슷함 — 판정자를 부르지 않는다) 뒤 놓을 자리
판정자에게 한 번 묻고 답대로 한다(다른 말은 두뇌가 짚은 항목이 지금 없으면 ``target``):

- ``same`` · ``decided`` · ``not_rule`` → 넣지 않는다(``same`` · ``decided_before`` · ``not_rule``).
- ``adds`` → 그 항목 글 끝에 더한 문장만 붙여 고친다(새 항목 없음 — ``placed_added``). 대상이 고칠 수 있는 항목(라홈 사실 · 정책
  · 글 전체가 보임)이고 붙인 글이 :data:`.handoff_learning_gates.MAX_TEXT` 자 안이고 붙일 문장이 가림 · 한자 · 숫자 관문을 지날
  때만 — 아니면 ``new`` 처럼 넣는다.
- ``new`` → 새 지식(사실 · 정책 — ``placed_new``). 숫자는 근거 직원 답 · 회사 지식에 있어야 한다(다른 말은 여기서 처음 본다 —
  아니면 ``numbers``).
- ``contradicts`` → 그 항목 엇갈림 카드(``conflict_card``) — 글 첫 줄에 어긋나는 두 구절(:data:`.handoff_learning_gates.CLASH_HEAD`).
- 판정자를 못 부름 · 꼴이 틀린 답 → 넣지도 카드로 올리지도 않는다(``place_unavailable`` · ``place_unknown``).

판정으로 넣는 안(새 지식 · 더함)은 공용 부딪침 관문에 막히지 않는다(같은 일을 판정자가 했다 — 결과는 적힌다). 다른 말이 새 지식 ·
더함 · 바로 고침이 되어 바로 반영되면 같은 말을 모아 둔 앞 엇갈림 카드는 '합쳐짐'으로 닫는다. 넣은 안마다 커밋한다.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Optional, Sequence

from foms.services.brain.apply import AutoLearn
from foms.services.brain.constants import CHANGE_OPEN, STATUS_ACTIVE
from foms.services.brain.errors import BrainError as BrainStoreError
from foms.services.brain.errors import BrainGateError
from foms.services.brain.gates import FAIL, text_gates
from foms.services.brain.proposals import Proposer
from foms.services.brain.store import current_object
from foms.services.cs_agent.case_memory import text_similarity
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.handoff_learning_gates import (
    AGENT, CARD_PREFIX, CLASH_HEAD, DUP_SIMILARITY, MAX_FILED, MAX_TEXT, SAME_SIMILARITY, _card_rows, _check, _duplicate,
    _filer, _fix_text, _numbers_ok, _replies, _sources, _store_code, _try_card, apply_now, close_cards, seen_proposals,
)
from foms.services.cs_agent.handoff_learning_place import (
    ADDS, CONTRADICTS, DECIDED, NOT_RULE, SAME, UNAVAILABLE, UNKNOWN, Placement, place,
)
from foms.services.cs_agent.handoff_learning_prompt import DIFFERS, REASON_WORDS, updatable, whole_shown

__all__ = ["DROPPED", "file_proposals"]

#: 넣지 않는 판정 답 → 까닭 코드.
DROPPED: dict[str, str] = {SAME: "same", DECIDED: "decided_before", NOT_RULE: "not_rule",
                           UNAVAILABLE: "place_unavailable", UNKNOWN: "place_unknown"}
SKIP = ("conflict",)  # 판정으로 넣는 안 — 공용 부딪침 관문은 결과만 적는다(같은 일을 판정자가 했다)

Placed = tuple[Optional[str], Optional[Callable[[], Any]], list[int], Optional[str]]


def _similar_cards(session: Any, text: str) -> list[int]:
    """같은 말을 담은 열린 엇갈림 카드 id — 다른 말이 지식이 되면 합쳐 닫는다."""
    return [row[0] for row in _card_rows(session) if text_similarity(text, row[3]) >= DUP_SIMILARITY]


def _adds(session: Any, raw: dict[str, Any], card: dict[str, Any], verdict: Placement, *, known: str,
          replies: dict[str, list[str]], approved: Sequence[str]) -> Optional[tuple[Optional[str], Any]]:
    """``adds`` — 붙일 수 있으면 (막힌 까닭, 고치기 넣는 함수), 붙일 수 없으면(모듈 설명) ``None``(새 지식으로)."""
    target = current_object(session, verdict.target)
    if target is None or not updatable(target) or not whole_shown(target):
        return None
    joined = f"{(target.text or '').rstrip()} {verdict.added}"
    allowed = f"{known}\n{target.text or ''}"  # 지금 그 항목 글의 숫자는 이미 지식이다
    gates = text_gates([verdict.added], "")
    if len(joined) > MAX_TEXT or FAIL in (gates["mask"], gates["hanja"]) or not _numbers_ok([verdict.added], allowed, replies):
        return None
    common = card["common"]
    reason = common["reason"].replace("넘긴 상담 배우기 · ", "넘긴 상담 배우기 · 지금 지식에 더함 · ", 1)[:500]
    return _filer(session, {**raw, "op": "update", "key": target.item_key}, **{
        **card, "text": joined, "common": {**common, "reason": reason, "known": f"{common['known']}\n{target.text or ''}"}},
        approved=approved, skip_gates=SKIP)


def _placed(session: Any, raw: dict[str, Any], card: dict[str, Any], *, replies: dict[str, list[str]], known: str,
            approved: Sequence[str], cfg: Any, client: Any) -> Placed:
    """놓을 자리 판정(모듈 설명) → (막힌 까닭 코드, 넣는 함수, 넣으면 닫을 앞 카드 id, 넣으면 셀 이름)."""
    title, text, now = card["title"], card["text"], card["now"]
    differs = raw.get("op") == DIFFERS
    pointed = raw["key"].strip() if differs and isinstance(raw.get("key"), str) else ""
    if differs:
        target = current_object(session, pointed) if pointed else None
        if target is None or target.status != STATUS_ACTIVE:  # 두뇌가 짚은 항목이 없다 — 무엇과 다른지 모르는 안은 넣지 않는다
            return "target", None, [], None
    # 다른 말은 겹침을 엇갈림 카드를 빼고 본다(카드에 담긴 말이 지식이 되면 그 카드를 합쳐 닫는다)
    seen = [s for s in card["seen"] if not str(s[1] or "").startswith(CARD_PREFIX)] if differs else card["seen"]
    if any(text_similarity(text, one) >= SAME_SIMILARITY for one in approved):
        return "same", None, [], None
    dup = _duplicate(text, seen)
    if dup is not None:
        return dup, None, [], None
    verdict = place(session, key=pointed or None, title=title, text=text, cfg=cfg, now=now, client=client)
    session.commit()  # 판정자 부르기가 연 트랜잭션을 닫는다
    if verdict.verdict in DROPPED:
        return DROPPED[verdict.verdict], None, [], None
    if verdict.verdict == CONTRADICTS:
        clash = f"{CLASH_HEAD}회사 지식 「{verdict.clash[0]}」 ↔ 직원 「{verdict.clash[1]}」"
        return _try_card(session, verdict.target, {**card, "clash": clash}), None, [], None
    merged = _similar_cards(session, text) if differs else []
    if verdict.verdict == ADDS:
        added = _adds(session, raw, {**card, "seen": seen}, verdict, known=known, replies=replies, approved=approved)
        if added is not None:
            return added[0], added[1], merged, "placed_added"
    if not _numbers_ok([title, text], known, replies):  # 다른 말은 숫자 관문을 여기서 처음 본다(새로 만들기는 이미 지났다)
        return "numbers", None, [], None
    code, make = _filer(session, {**raw, "op": "create"}, **{**card, "seen": seen}, approved=approved, skip_gates=SKIP)
    return code, make, merged, "placed_new"


def file_proposals(session: Any, raw: Sequence[dict[str, Any]], cases: Sequence[dict[str, Any]], *,
                   now: datetime.datetime, known: str, approved: Sequence[str],
                   auto: Optional[AutoLearn] = None, cfg: Any = None, client: Any = None) -> dict[str, int]:
    """관문(우리 쪽) → 놓을 자리 판정 → 제안 길. 넣은 수(``filed``) · 바로 반영한 수(``applied``) · 엇갈림 카드 수(``conflict_card``)
    · 바로 고침(``differs_fixed`` — 바로 반영한 것만) · 판정으로 넣은 새 지식(``placed_new``) · 더함(``placed_added``)과 막힌
    까닭별 수. 넣은 안마다 커밋한다.

    Args:
        cases: 이번에 두뇌에 보낸 사례(차례 id · 상담 id · 가린 직원 답 · 넘긴 까닭).
        known: 숫자 허용 글(회사 지식 반영 · 확정 + 상담 승인 지식).
        approved: 반영된 지식 글(같음 관문).
        auto: 바로 반영(:mod:`.handoff_learning_gates` 설명 — 없으면 승인 대기로만).
        cfg · client: 놓을 자리 판정자(학습 돈 줄 · 패널 설정 — 끼운 판정자도 ``cfg`` 도 없으면 ``place_unavailable``).
    """
    by_id = {case["turn_id"]: case for case in cases}
    seen = seen_proposals(session)
    session.commit()
    counts: dict[str, int] = {"filed": 0}
    for number, item in enumerate(raw[:MAX_FILED * 2], start=1):
        code, title, text, why, ids = _check(item, by_id, known)
        make, merged, done, fix = None, [], None, False
        if code is None and counts["filed"] >= MAX_FILED:
            code = "cap"
        if code is None:
            reasons = sorted({REASON_WORDS.get(by_id[i]["reason"], "그 밖") for i in ids})
            chats = len({by_id[i]["chat_id"] for i in ids})
            reason = f"넘긴 상담 배우기 · 근거 상담 {chats}곳 · 넘긴 까닭 {' · '.join(reasons)} — {why}"[:500]
            allowed = "\n".join([known, *(by_id[i]["reply"] or "" for i in ids)])
            common = dict(reason=reason, proposer=Proposer.agent_named(AGENT), evidence=_sources(ids, by_id),
                          now=naive_utc(now), known=allowed)
            card = dict(title=title, text=text, number=number, common=common, now=now, seen=seen)
            if item.get("op") == "update":  # 두뇌가 고를 항목을 골랐다 — 예전 그대로(공용 부딪침 관문)
                code, make = _filer(session, item, title=title, text=text, number=number, common=common, now=now,
                                    seen=seen, approved=approved)
            else:
                if item.get("op") == DIFFERS:
                    wanted = item.get("key").strip() if isinstance(item.get("key"), str) else ""
                    fixed, merged, customers = _fix_text(session, item, wanted, {str(by_id[i]["chat_id"]) for i in ids})
                    if _duplicate(text, seen) == "rejected_before":  # 사장님이 거절 · 지운 말 — 손님이 둘이어도 다시 안 고친다
                        code, fixed, merged = "rejected_before", None, []
                    elif fixed is not None:  # 서로 다른 손님 둘 이상 — 그 항목을 바로 고친다(D267)
                        why_fix = f"넘긴 상담 배우기 · 지금 지식과 다른 직원 답 · 서로 다른 손님 {customers}곳 — {why}"[:500]
                        code, make = _filer(session, {**item, "op": "update"}, title=title, text=fixed, number=number,
                                            common={**common, "reason": why_fix}, now=now, seen=seen,
                                            approved=approved, skip_gates=SKIP)
                        fix, done = make is not None, "differs_fixed"
                if make is None and code not in ("same", "rejected_before"):  # 놓을 자리 판정(모듈 설명)
                    code, make, same, done = _placed(session, item, card, replies=_replies(ids, by_id), known=known,
                                                     approved=approved, cfg=cfg, client=client)
                    merged = sorted({*merged, *same}) if make is not None else []
        if make is not None:
            try:
                change = make()
                session.commit()
                seen = [(CHANGE_OPEN, None, title, text), *seen]  # 한 번에 비슷한 안 둘이 들어가지 않게
                extra = "applied" if auto is not None else None
                extra = apply_now(session, change, auto, now) or extra
                if extra == "applied":  # 같은 말을 모아 둔 앞 카드는 이 고침 · 새 지식 · 더함에 합쳐졌다
                    close_cards(session, merged, now)
                if done is not None and (extra == "applied" or done != "differs_fixed"):
                    counts[done] = counts.get(done, 0) + 1
                session.commit()
                if extra:  # 넣은 수(filed)와 따로 센다 — 바로 반영함 · 반영이 막혀 승인 대기에 남음
                    counts[extra] = counts.get(extra, 0) + 1
            except BrainGateError as exc:
                session.rollback()
                code = _store_code(exc)
                if set(exc.failed) == {"conflict"} and exc.unavailable:
                    code = "judge_unavailable"  # 아무도 판정하지 않았다 — '다른 말' 카드로 올리지 않는다
                elif set(exc.failed) == {"conflict"} or fix:  # 두뇌의 고치기가 부딪침에 · 바로 고침이 관문에 막혔다 — 카드로
                    code = _try_card(session, str(item.get("key") or "").strip() or None, card, fallback=code)
            except BrainStoreError as exc:  # 글 관문 · 근거 · 거절 · 대상 · 꼴 — 넣지 않고 센다
                session.rollback()
                code = _store_code(exc)
                if fix:  # 바로 고침이 막혔다 — 카드로
                    code = _try_card(session, str(item.get("key") or "").strip() or None, card, fallback=code)
        if code == "conflict_card":
            seen = [(CHANGE_OPEN, None, title, text), *seen]
        counts[code or "filed"] = counts.get(code or "filed", 0) + 1
    return counts
