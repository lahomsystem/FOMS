"""의미 찾기 근원별 넣기 — ``brain_item`` · ``chatbot_question`` · ``cs_case``(사장님 D114 · 근원 종류 결정 11-02).

- **회사 지식 항목**(``brain_item``): 지금 판이 바뀌었거나(판 번호 · 글 지문) 새 항목이면 넣고, 은퇴 · 범위가 바뀐 항목은 지운다.
  넣는 글은 :func:`.embeddings.doc_text`(가격 재량 · 관리 범위 · 개인정보 · 계좌 같은 번호는 빼고).
- **물어보기 질문**(``chatbot_question``): 가린 질문만. 물을 때 찾기에 이미 만든 벡터를 그 자리에서 남기고
  (:func:`.embeddings.store_question_vector`), 여기서는 남지 못한 질문만 채운다. 질문을 1년 뒤 지우면 벡터도 같이 지운다.
- **상담 사례**(``cs_case``): 가린 손님 질문 + 가린 직원 답 — 사례 기억과 같은 재료 · 같은 다듬기 · 같은 가림 검사
  (:func:`foms.services.cs_agent.case_material.case_pair` — 하나라도 걸리면 그 줄은 건너뜀) + 계좌 같은 번호 검사.
  **백필만**(설정 ``cs_case_embeddings_enabled`` 처음 끔) — 상담 초안의 비슷한 사례 고르기는 아직 바꾸지 않는다(따로 평가 뒤).
- 모든 근원이 같은 돈 줄 · 하루 상한 · 시간 상한(:func:`.embeddings.embed_texts`)을 쓴다. ``apply`` 가 거짓이면 세기만(돈 0).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainObject, BrainQuestion
from foms.persistence.main.models import CsAgentTurn
from foms.services.brain.chat_settings import CASE_FIELD, EMBED_FIELD, ChatSettings
from foms.services.brain.constants import IDENTITY_TYPES, STATUS_ACTIVE
from foms.services.brain.embeddings import (
    MAX_BATCH, SOURCE_CASE, SOURCE_ITEM, SOURCE_QUESTION, doc_text, drop_vectors, embed_texts,
    estimate_cost, off_reason, safe_text, store_vector, stored, text_hash,
)
from foms.services.brain.store import is_current
from foms.services.cs_agent.case_material import case_pair
from foms.services.cs_agent.case_memory import LEARNING_OUTCOMES

#: 근원 → (설정 칸, Voyage ``input_type``). 질문은 다른 질문과 견줄 '물음', 항목 · 사례는 '문서'.
SOURCES: dict[str, tuple[str, str]] = {SOURCE_ITEM: (EMBED_FIELD, "document"), SOURCE_QUESTION: (EMBED_FIELD, "query"),
                                       SOURCE_CASE: (CASE_FIELD, "document")}
#: 밤 단계가 다루는 근원(상담 사례는 백필 스크립트로만).
NIGHTLY_SOURCES: tuple[str, ...] = (SOURCE_ITEM, SOURCE_QUESTION)
Todo = tuple[str, Optional[int], str]  # (근원 키, 근원 판, 넣을 글)


def item_todo(session: Any, limit: int) -> list[Todo]:
    """새로 넣을 회사 지식 항목 — 지금 판인데 벡터가 없거나 판 · 글 지문이 다른 것."""
    have = stored(session, SOURCE_ITEM)
    out: list[Todo] = []
    for row in session.execute(select(BrainObject).where(is_current(BrainObject), BrainObject.status == STATUS_ACTIVE,
                                                         BrainObject.item_type.in_(IDENTITY_TYPES))
                               .order_by(BrainObject.item_key)).scalars():
        body = doc_text(row)
        if body is not None and have.get(row.item_key) != (row.version, text_hash(body)):
            out.append((row.item_key, row.version, body))
            if len(out) >= limit:
                break
    return out


def question_todo(session: Any, limit: int) -> list[Todo]:
    """벡터가 없는 물어보기 가린 질문(검사를 넘은 것만 — 새 것부터)."""
    have = stored(session, SOURCE_QUESTION)
    out: list[Todo] = []
    for qid, masked in session.execute(select(BrainQuestion.id, BrainQuestion.masked_question)
                                       .order_by(BrainQuestion.id.desc())):
        if str(qid) not in have and safe_text(masked or ""):
            out.append((str(qid), None, masked))
            if len(out) >= limit:
                break
    return out


def case_text(question: Optional[str], answer: Optional[str]) -> Optional[str]:
    """상담 사례 글 — 사례 기억과 같은 다듬기 · 가림 검사(하나라도 걸리면 ``None``) + 계좌 같은 번호 검사."""
    pair = case_pair(question or "", answer or "")
    if pair is None:
        return None
    body = f"손님: {pair[0]}\n직원: {pair[1]}"
    return body if safe_text(body) else None


def case_todo(session: Any, limit: int) -> list[Todo]:
    """벡터가 없거나 글이 바뀐 상담 사례 — 사례 기억 재료와 같은 줄(그대로 · 고침 · 직접 답 · 떼어 두지 않음 · 질문과 사람 답 있음)."""
    have = stored(session, SOURCE_CASE)
    rows = session.execute(select(CsAgentTurn.id, CsAgentTurn.masked_question, CsAgentTurn.staff_reply_masked)
                           .where(CsAgentTurn.outcome.in_(LEARNING_OUTCOMES), CsAgentTurn.held_out.is_(False),
                                  CsAgentTurn.masked_question.isnot(None), CsAgentTurn.staff_reply_masked.isnot(None))
                           .order_by(CsAgentTurn.id.desc()))
    out: list[Todo] = []
    for turn_id, question, answer in rows:
        body = case_text(question, answer)
        if body is not None and have.get(str(turn_id), (None, ""))[1] != text_hash(body):
            out.append((str(turn_id), None, body))
            if len(out) >= limit:
                break
    return out


_TODO = {SOURCE_ITEM: item_todo, SOURCE_QUESTION: question_todo, SOURCE_CASE: case_todo}


def drop_stale_items(session: Any) -> int:
    """지금 판이 없거나 넣지 않을 항목(은퇴 · 범위 바뀜)의 벡터 줄을 지운다."""
    keep = {row.item_key for row in session.execute(select(BrainObject).where(
        is_current(BrainObject), BrainObject.status == STATUS_ACTIVE)).scalars() if doc_text(row) is not None}
    return drop_vectors(session, SOURCE_ITEM, set(stored(session, SOURCE_ITEM)) - keep)


def _run_one(session: Any, kind: str, *, cfg: ChatSettings, now: datetime.datetime, limit: int,
             apply: bool) -> dict[str, Any]:
    """근원 하나 — 꺼짐이면 까닭, 아니면 모의 실행(수 · 어림 돈) 또는 넣기."""
    switch, input_type = SOURCES[kind]
    reason = off_reason(session, cfg, switch)
    if reason is not None:
        return {"off": reason}
    todo = _TODO[kind](session, limit)
    if not apply:
        return {"pending": len(todo), "estimate_usd": str(estimate_cost([b for _k, _v, b in todo])), "applied": False}
    done = 0
    for start in range(0, len(todo), MAX_BATCH):
        chunk = todo[start:start + MAX_BATCH]
        vectors = embed_texts(session, [b for _k, _v, b in chunk], input_type=input_type, cfg=cfg, now=now)
        for (key, version, body), vector in zip(chunk, vectors):
            store_vector(session, kind, key, version, vector, text_hash(body), now)
        session.commit()
        done += len(chunk)
    out: dict[str, Any] = {"pending": len(todo), "embedded": done, "applied": True}
    if kind == SOURCE_ITEM:
        out["removed"] = drop_stale_items(session)
        session.commit()
    return out


def run_embed(session: Any, *, cfg: ChatSettings, now: datetime.datetime, sources: Iterable[str] = NIGHTLY_SOURCES,
              limit: int = 500, apply: bool = False) -> dict[str, Any]:
    """근원마다 넣기 — ``{근원: 요약}``. 실패는 :class:`foms.services.brain.embeddings.EmbedUnavailable`(앞 근원은 이미 커밋)."""
    return {kind: _run_one(session, kind, cfg=cfg, now=now, limit=limit, apply=apply) for kind in sources}
