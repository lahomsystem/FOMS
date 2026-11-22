"""넘김 학습 넣기 — 우리 쪽 관문(:mod:`.handoff_learning_gates`) → 놓을 자리 판정(:mod:`.handoff_learning_place`) → 되풀이
문턱(:mod:`.handoff_learning_held`) → 제안 길(사장님 2026-11-22 '배우기를 지금 고쳐' · 11-23 '여러 번 나온 것만 바로 반영' · 설계서
``docs/specs/2026-11-22-cs-learning-placement_SPEC.md`` 2.2 · ``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 2.1 · 3절).

그대로 두는 것: 꼴 · 가림 · 근거 · 숫자 관문, 사장님이 거절 · 지운 말 다시 안 넣기, **서로 다른 손님 둘 이상의 다른 말은 바로
고침**(D267 — 막히면 그 항목 엇갈림 카드).

그 밖의 안(새로 만들기 · 두뇌의 고치기 · 바로 고치지 못한 다른 말)은 같음 · 겹침 관문(글자 비슷함 — 판정자를 부르지 않는다) 뒤 놓을
자리 판정자에게 한 번 묻고 답대로 한다. 고치기 · 다른 말은 두뇌가 짚은 항목을 대상으로 묻고, 그 항목이 지금 없으면 ``target``.
**고치기 안도 판정을 거친다**(11-23 2.1 — 공용 부딪침 관문으로 보내던 옛 길이 첫 밤 카드 19장 가운데 13장을 '지금 글 + 덧붙인 문장'
으로 올렸다). 고치기 글은 지금 글을 품으니 같음 관문은 짚은 항목 글과 똑같을 때만 같음으로 본다.

고치기 글이 짚은 항목의 지금 글을 그대로 품으면 그 글을 통째로 새 항목 · 기다리는 말로 쓰지 않고 판정자가 고른 더한 문장만 쓴다.

- ``same`` · ``decided`` · ``not_rule`` → 넣지 않는다(``same`` · ``decided_before`` · ``not_rule``).
- ``adds`` → 그 항목 글 끝에 더한 문장만 붙여 고친다(새 항목 없음 — ``placed_added``). 대상이 고칠 수 있는 항목(라홈 사실 · 정책
  · 글 전체가 보임)이고 붙인 글이 :data:`.handoff_learning_gates.MAX_TEXT` 자 안이고 붙일 문장이 가림 · 한자 · 숫자 관문을 지날
  때만 — 아니면 ``new`` 처럼 넣는다.
- ``new`` → 새 지식(사실 · 정책 — ``placed_new``). 숫자는 근거 직원 답 · 회사 지식에 있어야 한다(다른 말은 여기서 처음 본다 —
  아니면 ``numbers``).
- ``contradicts`` → 그 항목 엇갈림 카드(``conflict_card``) — 글 첫 줄에 어긋나는 두 구절(:data:`.handoff_learning_gates.CLASH_HEAD`).
  근거가 한 상담이어도 올린다(바로 반영이 아니라 사장님이 고른다).
- ``repeat`` → 아래 되풀이 문턱.
- 판정자를 못 부름 · 꼴이 틀린 답 → 넣지도 카드로 올리지도 않는다(``place_unavailable`` · ``place_unknown``).

**되풀이 문턱(사장님 11-23)**: ``adds`` · ``new`` 는 근거가 서로 다른 상담 :data:`.handoff_learning_held.MIN_CHATS` 곳 이상일 때만
넣는다(다른 말은 두뇌가 같은 말이라고 고른 앞 엇갈림 카드의 상담도 센다). 한 상담뿐이면 지식에도 카드에도 넣지 않고 '기다리는 말'로
모은다(``held`` — 숫자 관문은 지나야 한다). 판정자에게는 가까운 기다리는 말을 회사 지식과 따로 보이고, ``repeat``(그 기다리는 말과
같은 말)이면 근거를 합친다 — 합친 상담이 두 곳 이상이면 기다리는 말 없이 지금 지식 기준으로 놓을 자리를 한 번 더 묻고 그 답대로
넣는다(새 지식 · 더함이면 ``promoted``, 같음 · 이미 정함 · 규칙 아님이면 기다리는 말을 버리고 그 코드로 센다, 부딪침이면 카드). 같은
상담의 되풀이는 근거만 더하고 기다린다(``held``). 바로 반영이 켜져 있든 꺼져 있든 같다. 넣기 처음에 60일 동안 다시 안 나온
기다리는 말을 버린다.

판정으로 넣는 안(새 지식 · 더함)은 공용 부딪침 관문에 막히지 않는다(같은 일을 판정자가 했다 — 결과는 적힌다). 다른 말 · 고치기가 새
지식 · 더함 · 바로 고침이 되어 바로 반영되면 같은 말을 모아 둔 앞 엇갈림 카드는 '합쳐짐'으로 닫는다. 넣은 안마다 커밋한다. 바로
반영한 항목은 넣기 끝에 그 항목만 뜻 찾기 벡터를 넣는다(:func:`foms.services.brain.embed_sources.embed_items` — 같은 밤 뒤 바퀴가
뜻으로 찾게. 꺼짐 · 상한 · 실패면 넣지 않고 배우기는 계속 — 코드만 적는다).
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
from typing import Any, Callable, Optional, Sequence

from sqlalchemy.exc import SQLAlchemyError

from foms.services.brain.apply import AutoLearn
from foms.services.brain.chat_settings import read_chat_settings
from foms.services.brain.constants import CHANGE_OPEN, STATUS_ACTIVE
from foms.services.brain.embed_sources import embed_items
from foms.services.brain.embeddings import EmbedUnavailable
from foms.services.brain.errors import BrainError as BrainStoreError
from foms.services.brain.gates import FAIL, text_gates
from foms.services.brain.proposals import Proposer
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning_held as held
from foms.services.cs_agent.case_memory import text_similarity
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.handoff_learning_gates import (
    AGENT, CARD_PREFIX, CLASH_HEAD, DUP_SIMILARITY, MAX_FILED, MAX_TEXT, SAME_SIMILARITY, _card_rows, _check, _duplicate,
    _filer, _fix_text, _numbers_ok, _replies, _sources, _store_code, _try_card, apply_now, close_cards, seen_proposals,
)
from foms.services.cs_agent.handoff_learning_place import (
    ADDS, CONTRADICTS, DECIDED, NOT_RULE, REPEAT, SAME, UNAVAILABLE, UNKNOWN, Placement, learned_vector, place,
)
from foms.services.cs_agent.handoff_learning_prompt import DIFFERS, REASON_WORDS, updatable, whole_shown
from foms.services.cs_agent.send import SEND_BRAND

logger = logging.getLogger(__name__)

__all__ = ["DROPPED", "Said", "file_proposals"]

#: 넣지 않는 판정 답 → 까닭 코드.
DROPPED: dict[str, str] = {SAME: "same", DECIDED: "decided_before", NOT_RULE: "not_rule",
                           UNAVAILABLE: "place_unavailable", UNKNOWN: "place_unknown"}
SKIP = ("conflict",)  # 판정으로 넣는 안 — 공용 부딪침 관문은 결과만 적는다(같은 일을 판정자가 했다)
UPDATE = "update"
POINTING = (DIFFERS, UPDATE)  # 두뇌가 짚은 항목을 대상으로 판정하는 동작
_GONE = (SAME, DECIDED, NOT_RULE)  # 다시 물은 답이 이것이면 기다리는 말을 버린다

#: (막힌 까닭 코드, 넣는 함수, 넣으면 닫을 앞 카드 id, 넣으면 셀 이름, 넣으면 올림으로 적을 기다리는 말 번호).
Placed = tuple[Optional[str], Optional[Callable[[], Any]], list[int], Optional[str], Optional[int]]


@dataclasses.dataclass(frozen=True)
class Said:
    """안의 근거 — 차례 id · 상담 id · 넘긴 까닭 말 · 두뇌가 적은 까닭 · 같은 말을 들은 서로 다른 손님 수(다른 말은 두뇌가 같은
    말이라고 고른 앞 엇갈림 카드의 상담도 센다 — 되풀이 문턱이 본다)."""

    ids: tuple[int, ...]
    chats: frozenset[str]
    reasons: tuple[str, ...]
    why: str
    heard: int


def _reason(chats: int, said: Said, *, waited: bool = False) -> str:
    """제안 까닭 글(500자 안) — 근거 상담 수 · 넘긴 까닭 · 두뇌가 적은 까닭(``waited`` = 기다리던 말을 올림)."""
    more = " · 기다리던 말" if waited else ""
    return f"넘긴 상담 배우기 · 근거 상담 {chats}곳{more} · 넘긴 까닭 {' · '.join(said.reasons)} — {said.why}"[:500]


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
    return _filer(session, {**raw, "op": UPDATE, "key": target.item_key}, **{
        **card, "text": joined, "common": {**common, "reason": reason, "known": f"{common['known']}\n{target.text or ''}"}},
        approved=approved, skip_gates=SKIP)


def _settle(session: Any, verdict: Placement, said: Said, *, raw: dict[str, Any], card: dict[str, Any],
            replies: dict[str, list[str]], known: str, approved: Sequence[str], pointing: bool,
            vector: Optional[list[float]], wraps: bool = False, done_as: Optional[str] = None) -> Placed:
    """판정 답(``repeat`` 밖)대로 — 넣지 않음 · 카드 · 기다리는 말(한 상담뿐) · 더함 · 새 지식(모듈 설명). ``done_as`` 는 넣으면 셀
    이름을 바꾼다(기다리던 말을 올림). ``wraps`` 는 고치기 글이 짚은 항목의 지금 글을 품는다는 뜻 — 그 글을 통째로 기다리는 말 · 새
    항목으로 쓰면 같은 말이 또 생기니 판정자가 고른 더한 문장만 쓴다(더한 문장이 없으면 넣지 않는다 — ``place_unknown``)."""
    if verdict.verdict in DROPPED:
        return DROPPED[verdict.verdict], None, [], None, None
    if verdict.verdict == CONTRADICTS:
        clash = f"{CLASH_HEAD}회사 지식 「{verdict.clash[0]}」 ↔ 직원 「{verdict.clash[1]}」"
        return _try_card(session, verdict.target, {**card, "clash": clash}), None, [], None, None
    title, text = card["title"], card["text"]
    if wraps:
        if verdict.verdict != ADDS or not verdict.added:
            return DROPPED[UNKNOWN], None, [], None, None
        text = verdict.added
        card = {**card, "text": text}
    numbers = _numbers_ok([title, text], known, replies)  # 다른 말은 숫자 관문을 여기서 처음 본다(새로 만들기는 이미 지났다)
    if said.heard < held.MIN_CHATS:  # 되풀이 문턱 — 한 상담에서만 들은 말은 넣지 않고 기다린다
        if not numbers:
            return "numbers", None, [], None, None
        held.hold(session, brand=SEND_BRAND, title=title, text=text, chats=said.chats, turns=said.ids,
                  evidence=card["common"]["evidence"], now=card["now"], vector=vector)
        session.commit()
        return "held", None, [], None, None
    merged = _similar_cards(session, text) if pointing else []
    if verdict.verdict == ADDS:
        added = _adds(session, raw, card, verdict, known=known, replies=replies, approved=approved)
        if added is not None:
            return added[0], added[1], merged, done_as or "placed_added", None
    if not numbers:
        return "numbers", None, [], None, None
    code, make = _filer(session, {**raw, "op": "create"}, **card, approved=approved, skip_gates=SKIP)
    return code, make, merged, done_as or "placed_new", None


def _repeat(session: Any, verdict: Placement, said: Said, *, pointed: str, cfg: Any, client: Any,
            **ctx: Any) -> Placed:
    """``repeat`` — 기다리는 말과 같은 말(모듈 설명 '되풀이 문턱'). 근거를 합치고, 상담이 두 곳 이상이 되면 지금 지식 기준으로
    한 번 더 물어 넣는다."""
    card = ctx["card"]
    row = held.held_row(session, verdict.target)
    if row is None:  # 판정 사이에 올라감 · 버려짐 — 꼴이 틀린 답처럼
        return DROPPED[UNKNOWN], None, [], None, None
    held.add_turns(row, chats=said.chats, turns=said.ids, evidence=card["common"]["evidence"], now=card["now"])
    session.commit()
    chats = frozenset(row.chat_ids)
    if max(len(chats), said.heard) < held.MIN_CHATS:  # 같은 상담의 되풀이 — 근거만 더하고 기다린다
        return "held", None, [], None, None
    both = Said(tuple(row.turn_ids), chats, said.reasons, said.why, max(len(chats), said.heard))
    common = {**card["common"], "evidence": list(row.evidence), "reason": _reason(len(chats), said, waited=True)}
    again = place(session, key=pointed or None, title=card["title"], text=card["text"], cfg=cfg, now=card["now"],
                  client=client, vector=ctx["vector"])  # 기다리는 말 없이 — 지금 지식 기준으로만
    session.commit()
    out = _settle(session, again, both, **{**ctx, "card": {**card, "common": common}}, done_as="promoted")
    if out[1] is not None:  # 넣기가 되면 부르는 쪽이 올림으로 적는다
        return (*out[:4], row.id)
    if again.verdict in _GONE or out[0] == "conflict_card":  # 판정을 못 함 · 관문에 막힘은 기다린 채(다음 되풀이에 다시)
        held.finish(session, row, held.DROPPED if again.verdict in _GONE else held.PROMOTED)
        session.commit()
    return out


def _flat(text: Optional[str]) -> str:
    """빈칸을 하나로 줄인 글(같음 · 품음 견주기)."""
    return " ".join((text or "").split())


def _is_same(raw: dict[str, Any], target: Any, text: str, approved: Sequence[str]) -> bool:
    """같음 관문 — 고치기 글은 지금 글을 품으니 짚은 항목 글과 똑같을 때만(예전 :func:`._filer` 와 같다), 그 밖은 반영된 지식
    글과 :data:`.handoff_learning_gates.SAME_SIMILARITY` 이상 비슷하면."""
    if raw.get("op") == UPDATE:
        return _flat(target.text) == _flat(text)
    return any(text_similarity(text, one) >= SAME_SIMILARITY for one in approved)


def _placed(session: Any, raw: dict[str, Any], card: dict[str, Any], *, said: Said, replies: dict[str, list[str]],
            known: str, approved: Sequence[str], cfg: Any, client: Any) -> Placed:
    """놓을 자리 판정(모듈 설명) → :data:`Placed`."""
    title, text, now = card["title"], card["text"], card["now"]
    pointing = raw.get("op") in POINTING
    pointed = raw["key"].strip() if pointing and isinstance(raw.get("key"), str) else ""
    target = current_object(session, pointed) if pointed else None
    if pointing and (target is None or target.status != STATUS_ACTIVE):  # 무엇과 다른지 · 무엇을 고칠지 모르는 안은 넣지 않는다
        return "target", None, [], None, None
    # 짚은 안은 겹침을 엇갈림 카드를 빼고 본다(카드에 담긴 말이 지식이 되면 그 카드를 합쳐 닫는다)
    seen = [s for s in card["seen"] if not str(s[1] or "").startswith(CARD_PREFIX)] if pointing else card["seen"]
    if _is_same(raw, target, text, approved):
        return "same", None, [], None, None
    dup = _duplicate(text, seen)
    if dup is not None:
        return dup, None, [], None, None
    vector = learned_vector(session, title=title, text=text, now=now)
    waiting = held.near(session, brand=SEND_BRAND, text=text, vector=vector)
    verdict = place(session, key=pointed or None, title=title, text=text, cfg=cfg, now=now, client=client, vector=vector,
                    held=waiting)
    session.commit()  # 판정자 부르기가 연 트랜잭션을 닫는다
    wraps = raw.get("op") == UPDATE and bool(_flat(target.text)) and _flat(target.text) in _flat(text)
    ctx = dict(raw=raw, card={**card, "seen": seen}, replies=replies, known=known, approved=approved, pointing=pointing,
               vector=vector, wraps=wraps)
    if verdict.verdict == REPEAT:
        return _repeat(session, verdict, said, pointed=pointed, cfg=cfg, client=client, **ctx)
    return _settle(session, verdict, said, **ctx)


def _embed_applied(session: Any, keys: Sequence[str], now: datetime.datetime) -> None:
    """바로 반영한 항목의 뜻 찾기 벡터(모듈 설명) — 꺼짐 · 상한 · 실패면 넣지 않고 배우기는 계속(수 · 코드만 적는다)."""
    if not keys:
        return
    try:
        embed_items(session, keys, cfg=read_chat_settings(session), now=now)
    except (EmbedUnavailable, SQLAlchemyError) as exc:
        session.rollback()
        logger.warning("[CS 넘김 학습] 바로 반영한 항목 %d개의 뜻 찾기 벡터를 못 넣음 code=%s", len(keys),
                       getattr(exc, "code", type(exc).__name__))


def file_proposals(session: Any, raw: Sequence[dict[str, Any]], cases: Sequence[dict[str, Any]], *,
                   now: datetime.datetime, known: str, approved: Sequence[str],
                   auto: Optional[AutoLearn] = None, cfg: Any = None, client: Any = None) -> dict[str, int]:
    """관문(우리 쪽) → 놓을 자리 판정 → 되풀이 문턱 → 제안 길. 넣은 수(``filed``) · 바로 반영한 수(``applied``) · 엇갈림 카드 수
    (``conflict_card``) · 바로 고침(``differs_fixed`` — 바로 반영한 것만) · 판정으로 넣은 새 지식(``placed_new``) · 더함
    (``placed_added``) · 기다리는 말로 모음(``held``) · 기다리던 말을 올림(``promoted``)과 막힌 까닭별 수. 넣은 안마다 커밋한다.

    Args:
        cases: 이번에 두뇌에 보낸 사례(차례 id · 상담 id · 가린 직원 답 · 넘긴 까닭).
        known: 숫자 허용 글(회사 지식 반영 · 확정 + 상담 승인 지식).
        approved: 반영된 지식 글(같음 관문).
        auto: 바로 반영(:mod:`.handoff_learning_gates` 설명 — 없으면 승인 대기로만).
        cfg · client: 놓을 자리 판정자(학습 돈 줄 · 패널 설정 — 끼운 판정자도 ``cfg`` 도 없으면 ``place_unavailable``).
    """
    by_id = {case["turn_id"]: case for case in cases}
    seen = seen_proposals(session)
    held.expire(session, now)
    session.commit()
    counts: dict[str, int] = {"filed": 0}
    applied: list[str] = []
    for number, item in enumerate(raw[:MAX_FILED * 2], start=1):
        code, title, text, why, ids = _check(item, by_id, known)
        make, merged, done, fix, waited = None, [], None, False, None
        if code is None and counts["filed"] >= MAX_FILED:
            code = "cap"
        if code is None:
            chats = frozenset(str(by_id[i]["chat_id"]) for i in ids)
            said = Said(tuple(ids), chats, tuple(sorted({REASON_WORDS.get(by_id[i]["reason"], "그 밖") for i in ids})),
                        why, len(chats))
            allowed = "\n".join([known, *(by_id[i]["reply"] or "" for i in ids)])
            common = dict(reason=_reason(len(chats), said), proposer=Proposer.agent_named(AGENT),
                          evidence=_sources(ids, by_id), now=naive_utc(now), known=allowed)
            card = dict(title=title, text=text, number=number, common=common, now=now, seen=seen)
            if item.get("op") == DIFFERS:
                wanted = item.get("key").strip() if isinstance(item.get("key"), str) else ""
                fixed, merged, customers = _fix_text(session, item, wanted, set(chats))
                said = dataclasses.replace(said, heard=customers)  # 앞 엇갈림 카드의 손님도 같은 말을 들었다
                if _duplicate(text, seen) == "rejected_before":  # 사장님이 거절 · 지운 말 — 손님이 둘이어도 다시 안 고친다
                    code, fixed, merged = "rejected_before", None, []
                elif fixed is not None:  # 서로 다른 손님 둘 이상 — 그 항목을 바로 고친다(D267)
                    why_fix = f"넘긴 상담 배우기 · 지금 지식과 다른 직원 답 · 서로 다른 손님 {customers}곳 — {why}"[:500]
                    code, make = _filer(session, {**item, "op": UPDATE}, title=title, text=fixed, number=number,
                                        common={**common, "reason": why_fix}, now=now, seen=seen,
                                        approved=approved, skip_gates=SKIP)
                    fix, done = make is not None, "differs_fixed"
            if make is None and code not in ("same", "rejected_before"):  # 놓을 자리 판정(모듈 설명)
                code, make, same, done, waited = _placed(session, item, card, said=said, replies=_replies(ids, by_id),
                                                         known=known, approved=approved, cfg=cfg, client=client)
                merged = sorted({*merged, *same}) if make is not None else []
        if make is not None:
            try:
                change = make()
                session.commit()
                seen = [(CHANGE_OPEN, None, title, text), *seen]  # 한 번에 비슷한 안 둘이 들어가지 않게
                row = held.held_row(session, held.held_key(waited)) if waited is not None else None
                if row is not None:  # 기다리던 말이 지식(제안)으로 올라갔다
                    held.finish(session, row, held.PROMOTED)
                    session.commit()
                extra = "applied" if auto is not None else None
                extra = apply_now(session, change, auto, now) or extra
                if extra == "applied":  # 같은 말을 모아 둔 앞 카드는 이 고침 · 새 지식 · 더함에 합쳐졌다
                    close_cards(session, merged, now)
                    applied.append(change.item_key)
                if done is not None and (extra == "applied" or done != "differs_fixed"):
                    counts[done] = counts.get(done, 0) + 1
                session.commit()
                if extra:  # 넣은 수(filed)와 따로 센다 — 바로 반영함 · 반영이 막혀 승인 대기에 남음
                    counts[extra] = counts.get(extra, 0) + 1
            except BrainStoreError as exc:  # 관문 · 글 관문 · 근거 · 거절 · 대상 · 꼴 — 넣지 않고 센다
                session.rollback()
                code = _store_code(exc)
                if fix:  # 바로 고침이 관문에 막혔다 — 카드로
                    code = _try_card(session, str(item.get("key") or "").strip() or None, card, fallback=code)
        if code == "conflict_card":
            seen = [(CHANGE_OPEN, None, title, text), *seen]
        counts[code or "filed"] = counts.get(code or "filed", 0) + 1
    _embed_applied(session, applied, now)
    return counts
