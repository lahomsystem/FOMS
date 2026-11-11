"""넘김 학습 관문(우리 쪽) · 넣기 — master brain 제안 길로만(:mod:`.handoff_learning` 이 두뇌 안을 받은 뒤 부른다).

하나라도 못 넘으면 넣지 않고 까닭 코드별 수만 센다(글 없음). 차례(값이 싼 것부터):

1. **꼴**: 동작(새로 만들기 · 고치기) · 유형(사실 · 정책) · 이름 1 ~ :data:`MAX_TITLE` 자 한 줄 · 글 1 ~ :data:`MAX_TEXT` 자 ·
   까닭 1 ~ :data:`MAX_WHY` 자 한 줄.
2. **가림**: 이름 · 글 · 까닭에 개인정보 꼴 · 가림 표시 · 한자 0(:func:`foms.services.brain.gates.text_gates` — 제안 길이 보지
   않는 까닭 글도 여기서 본다).
3. **근거**: 근거 차례가 모두 이번에 읽은 사례 안이고 손님(상담) :data:`EVIDENCE_MIN_CHATS` 곳 이상 — 한 손님 사례로도 안을 낸다
   (사장님 11-11 '넘긴 상담마다 배워 다음 상담에' — 늘 사장님 승인을 거친다). 숫자만 아래 4번이 두 곳을 본다.
4. **숫자**: 이름 · 글 · 까닭의 숫자 조각마다(:func:`foms.services.brain.gates.numbers_known` — 조각 통째로 같은 수) 회사 지식 ·
   상담 승인 지식에 이미 있거나, **근거로 고른 직원 답 가운데 서로 다른 손님 :data:`NUMBER_MIN_CHATS` 곳 이상**에 있어야 한다 —
   한 손님에게만 말한 금액 · 날짜(그 손님 몫)가 지식으로 들어오지 않게. 제안 길의 숫자 관문에는 고른 직원 답을 더한 허용 글을
   넘긴다(같은 숫자만 지난다).
5. **대상**(고치기): 라홈 사실 · 정책 지금 항목만(:func:`.handoff_learning_prompt.updatable`), 글이 바뀌어야 한다.
6. **같음**: 새로 만들기 글이 반영된 지식 글과 :data:`SAME_SIMILARITY` 이상 비슷하면 넣지 않는다(``same``).
7. **겹침**: 넘김 학습이 낸 열린 · 거절된 안과 글이 :data:`DUP_SIMILARITY` 이상 비슷하면(``open_proposal`` ·
   ``rejected_before``), 고칠 항목에 누구든 열린 안이 있으면(``open_proposal``) 넣지 않는다.
8. **부딪침**: 제안 길의 에이전트 관문(:mod:`foms.services.brain.ai_gates` — 승인 지식과 두 순서 판정, 판정을 못 하면 막음)이
   막으면 ``brain_<관문>`` 으로 센다. 승인 지식과 다른 말은 **넣지 않는다**(회사 지식이 정본 — 엇갈림 카드로 승인 항목을 '확인
   필요'로 만드는 길은 쓰지 않는다. 직원 한 사람의 그날 답으로 승인 지식을 흔들지 않게).

넣기: :func:`foms.services.brain.proposals.propose_create` · ``propose_update`` 에 제안한 이 ``agent:`` :data:`AGENT` 로. 새로
만들기는 지식 문서 유형 항목(사실 · 정책 — 승인하면 같은 저장점에서 라홈 지식 문서를 표로 다시 써 다음 초안 재료가 된다,
:mod:`foms.services.brain.photo_cards` 와 같은 꼴). 근거는 차례 번호(``case:<id>``)뿐이다(직원 번호 · 상담 id 없음). 안마다
커밋한다(부딪침 판정자의 모델 부르기가 세션을 커밋한다 — 사진 카드와 같다). 자동 반영은 없다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Callable, Optional, Sequence

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange
from foms.services.brain.constants import (
    CHANGE_OPEN, CHANGE_REJECTED, OP_CREATE, OP_UPDATE, SCOPE_ALL, STATUS_ACTIVE, TYPE_GRADES,
)
from foms.services.brain.errors import BrainError as BrainStoreError
from foms.services.brain.errors import BrainGateError
from foms.services.brain.gates import FAIL, numbers_known, text_gates
from foms.services.brain.proposals import Proposer, after_values, propose_create, propose_update
from foms.services.brain.store import current_object
from foms.services.cs_agent.case_memory import text_similarity
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.handoff_learning_prompt import ITEM_TYPES, OPS, REASON_WORDS, updatable
from foms.services.cs_agent.send import SEND_BRAND
from foms.services.cs_agent.state import KST

__all__ = [
    "AGENT", "DUP_SIMILARITY", "EVIDENCE_MIN_CHATS", "MAX_FILED", "NUMBER_MIN_CHATS", "SAME_SIMILARITY", "file_proposals", "seen_proposals",
]

#: 제안한 이(``agent:cs_handoff_learning``) — 화면 이름표는 :data:`foms.services.brain.display.AGENT_LABELS`(시험이 맞춘다).
AGENT = "cs_handoff_learning"
MAX_FILED, MAX_SEEN = 10, 200
MAX_TITLE, MAX_TEXT, MAX_WHY = 40, 600, 300
SAME_SIMILARITY, DUP_SIMILARITY = 0.85, 0.8
NUMBER_MIN_CHATS = 2
#: 근거 손님(상담) 수 하한 — 사실 · 정책은 한 손님 사례로도 낸다(승인이 관문). 숫자는 :data:`NUMBER_MIN_CHATS`.
EVIDENCE_MIN_CHATS = 1
TAG, SOURCE, REF_PREFIX = "handoff-learn", "handoff_learn", "handoff_learn:"
APPROVED_BY = "넘긴 상담 배우기 카드"  # 지식 문서 승인 칸(실제 승인은 카드 승인 — 사진 카드와 같은 꼴)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _line(value: Any, limit: int) -> Optional[str]:
    """한 줄 글(앞뒤 빈칸 뺌 · 1 ~ 상한 자) — 아니면 ``None``."""
    text = value.strip() if isinstance(value, str) else ""
    return text if text and len(text) <= limit and "\n" not in text else None


def _body(value: Any) -> Optional[str]:
    """지식 글(앞뒤 빈칸 뺌 · 1 ~ :data:`MAX_TEXT` 자) — 아니면 ``None``."""
    text = value.strip() if isinstance(value, str) else ""
    return text if text and len(text) <= MAX_TEXT else None


def seen_proposals(session: Any) -> list[tuple[str, Optional[str], str, str]]:
    """넘김 학습이 낸 열린 · 거절된 안 — (상태, 키, 이름, 글) 새 것부터 :data:`MAX_SEEN` 개(겹침 관문 · 지시문 '이미 낸 제안')."""
    stmt = (select(BrainChange.status, BrainChange.item_key, BrainChange.fields)
            .where(BrainChange.proposed_by == Proposer.agent_named(AGENT).name,
                   BrainChange.status.in_((CHANGE_OPEN, CHANGE_REJECTED)), BrainChange.op.in_((OP_CREATE, OP_UPDATE)))
            .order_by(BrainChange.id.desc()).limit(MAX_SEEN))
    out = []
    for status, key, fields in session.execute(stmt):
        values = after_values(fields)
        payload = values.get("payload") if isinstance(values.get("payload"), dict) else {}
        if isinstance(values.get("text"), str) and values["text"].strip():
            out.append((status, key, str(payload.get("pref_label") or key or ""), values["text"]))
    return out


def _evidence(raw: dict[str, Any], by_id: dict[int, dict[str, Any]]) -> list[int]:
    """근거 관문 — 통과면 근거 차례 id(정렬), 아니면 빈 목록."""
    ids = raw.get("evidence_turn_ids")
    if not isinstance(ids, list) or not ids or any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
        return []
    if not set(ids) <= set(by_id):
        return []
    chats = {by_id[i]["chat_id"] for i in ids}
    return sorted(set(ids)) if len(chats) >= EVIDENCE_MIN_CHATS else []


def _sources(ids: Sequence[int], by_id: dict[int, dict[str, Any]]) -> list[str]:
    """제안 근거 — 사례(손님 갈래)마다 ``case:id`` + 답한 직원(채널톡 상담원 id)마다 ``staff:id``. 회사 지식 제안 길의 근거 관문
    (서로 다른 사람 둘)이 손님 한 명 + 답한 직원 한 명으로도 지나게(사장님 11-11 — 한 손님 사례로도 안을 낸다)."""
    staff = sorted({str(by_id[i]["staff"]) for i in ids if by_id[i].get("staff")})
    return [*(f"case:{i}" for i in ids), *(f"staff:{person}" for person in staff)]


def _numbers_ok(texts: Sequence[str], known: str, replies: dict[str, list[str]]) -> bool:
    """숫자 관문 — 조각마다 이미 있는 지식에 있거나, 서로 다른 손님 :data:`NUMBER_MIN_CHATS` 곳 이상의 고른 직원 답에 있다."""
    for token in (token for text in texts for token in _NUMBER.findall(text)):
        if numbers_known(token, known):
            continue
        if sum(1 for said in replies.values() if any(numbers_known(token, one) for one in said)) < NUMBER_MIN_CHATS:
            return False
    return True


def _duplicate(text: str, seen: Sequence[tuple[str, Optional[str], str, str]]) -> Optional[str]:
    """겹침 관문 — 넘김 학습이 낸 비슷한 안이 열려 있으면 ``open_proposal``, 거절됐으면 ``rejected_before``(키 상관없이)."""
    for status, _key, _label, seen_text in seen:
        if text_similarity(text, seen_text) >= DUP_SIMILARITY:
            return "open_proposal" if status == CHANGE_OPEN else "rejected_before"
    return None


def _open_on(session: Any, key: str) -> bool:
    """그 키에 누구든 열린 안이 있나(동작 상관없이)."""
    return session.execute(select(BrainChange.id).where(BrainChange.status == CHANGE_OPEN,
                                                        BrainChange.item_key == key).limit(1)).first() is not None


def _doc_values(item_type: str, title: str, text: str, doc_id: str, today: str) -> dict[str, Any]:
    """새 사실 · 정책 → 지식 문서 유형 값 칸(:func:`foms.services.brain.doc_bridge.doc_item_of` 가 문서 항목으로 바꾼다). 이름은
    한글 이름(문서 id 의 날 숫자가 제안 길 숫자 관문에 걸리지 않게 — 이름 · 글의 숫자는 관문을 지난 것뿐이다)."""
    return {"name": title, "text": text, "status": STATUS_ACTIVE, "risk_grade": TYPE_GRADES[item_type],
            "checked_at": today, "evidence_kind": "case", "evidence_ref": f"{REF_PREFIX}{doc_id}",
            "visibility": SCOPE_ALL,
            "payload": {"doc_id": doc_id, "intents": [], "tags": [TAG], "source": SOURCE, "approved_by": APPROVED_BY,
                        "approved_at": today, "pref_label": title}}


def _filer(session: Any, raw: dict[str, Any], *, title: str, text: str, number: int, common: dict[str, Any],
           now: datetime.datetime, seen: Sequence[Any], approved: Sequence[str],
           ) -> tuple[Optional[str], Optional[Callable[[], Any]]]:
    """대상 · 같음 · 겹침 관문 → (막힌 까닭 코드, 넣는 함수)."""
    local = now.astimezone(KST)
    if raw.get("op") == "create":
        if any(text_similarity(text, known) >= SAME_SIMILARITY for known in approved):
            return "same", None
        dup = _duplicate(text, seen)
        if dup is not None:
            return dup, None
        doc_id = f"handoff-{local:%Y%m%d}-{number}"
        key, item_type = f"lahom/{doc_id}", raw["item_type"]
        if current_object(session, key) is not None or _open_on(session, key):
            return "open_proposal", None
        values = _doc_values(item_type, title, text, doc_id, local.date().isoformat())
        return None, lambda: propose_create(session, key=key, brand=SEND_BRAND, layer="common", item_type=item_type,
                                            values=values, **common)
    wanted = raw.get("key").strip() if isinstance(raw.get("key"), str) else ""
    target = current_object(session, wanted) if wanted else None
    if target is None or not updatable(target):
        return "target", None
    if " ".join((target.text or "").split()) == " ".join(text.split()):
        return "same", None
    dup = _duplicate(text, seen)
    if dup is not None or _open_on(session, target.item_key):
        return dup or "open_proposal", None
    return None, lambda: propose_update(session, key=target.item_key, base_version=target.version,
                                        after={"text": text}, **common)


def _store_code(exc: BrainStoreError) -> str:
    """제안 길이 막은 까닭 코드 — 관문이면 ``brain_<관문 이름>``, 그 밖은 오류 코드(소문자)."""
    if isinstance(exc, BrainGateError):
        return "brain_" + "_".join(sorted(set(exc.failed)))
    return str(getattr(exc, "code", "brain")).lower()


def _check(raw: dict[str, Any], by_id: dict[int, dict[str, Any]], known: str
           ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], list[int]]:
    """꼴 · 가림 · 근거 · 숫자 관문 → (막힌 까닭, 이름, 글, 까닭, 근거 차례)."""
    title, text, why = _line(raw.get("title"), MAX_TITLE), _body(raw.get("text")), _line(raw.get("why"), MAX_WHY)
    if raw.get("op") not in OPS or raw.get("item_type") not in ITEM_TYPES or None in (title, text, why):
        return "form", None, None, None, []
    gates = text_gates([title, text, why], "")
    if gates["mask"] == FAIL or gates["hanja"] == FAIL:
        return "mask", None, None, None, []
    ids = _evidence(raw, by_id)
    if not ids:
        return "evidence", None, None, None, []
    replies: dict[str, list[str]] = {}
    for turn_id in ids:
        replies.setdefault(by_id[turn_id]["chat_id"], []).append(by_id[turn_id]["reply"] or "")
    if not _numbers_ok([title, text, why], known, replies):
        return "numbers", None, None, None, []
    return None, title, text, why, ids


def file_proposals(session: Any, raw: Sequence[dict[str, Any]], cases: Sequence[dict[str, Any]], *,
                   now: datetime.datetime, known: str, approved: Sequence[str]) -> dict[str, int]:
    """관문(우리 쪽) → 제안 길. 넣은 수(``filed``)와 막힌 까닭별 수. 넣은 안마다 커밋한다.

    Args:
        cases: 이번에 두뇌에 보낸 사례(차례 id · 상담 id · 가린 직원 답 · 넘긴 까닭).
        known: 숫자 허용 글(회사 지식 반영 · 확정 + 상담 승인 지식).
        approved: 반영된 지식 글(같음 관문).
    """
    by_id = {case["turn_id"]: case for case in cases}
    seen = seen_proposals(session)
    session.commit()
    counts: dict[str, int] = {"filed": 0}
    for number, item in enumerate(raw[:MAX_FILED * 2], start=1):
        code, title, text, why, ids = _check(item, by_id, known)
        make = None
        if code is None and counts["filed"] >= MAX_FILED:
            code = "cap"
        if code is None:
            reasons = sorted({REASON_WORDS.get(by_id[i]["reason"], "그 밖") for i in ids})
            chats = len({by_id[i]["chat_id"] for i in ids})
            reason = f"넘긴 상담 배우기 · 근거 상담 {chats}곳 · 넘긴 까닭 {' · '.join(reasons)} — {why}"[:500]
            allowed = "\n".join([known, *(by_id[i]["reply"] or "" for i in ids)])
            common = dict(reason=reason, proposer=Proposer.agent_named(AGENT), evidence=_sources(ids, by_id),
                          now=naive_utc(now), known=allowed)
            code, make = _filer(session, item, title=title, text=text, number=number, common=common, now=now,
                                seen=seen, approved=approved)
        if make is not None:
            try:
                make()
                session.commit()
                seen = [(CHANGE_OPEN, None, title, text), *seen]  # 한 번에 비슷한 안 둘이 들어가지 않게
            except BrainStoreError as exc:  # 글 관문 · 부딪침 · 근거 · 거절 · 대상 · 꼴 — 넣지 않고 센다
                session.rollback()
                code = _store_code(exc)
        counts[code or "filed"] = counts.get(code or "filed", 0) + 1
    return counts
