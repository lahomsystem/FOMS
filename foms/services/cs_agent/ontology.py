"""바꿔 묻기 대응 — 회사 지식 표(온톨로지)의 다른 이름 · 용어 · 규격을 AI 상담 초안에 잇는다(사장님 11-11 '온톨로지화해야 다양한
변형에 대응').

조사(11-11): 회사 지식 표(:mod:`foms.services.brain`)는 유형 · 링크 · 다른 이름(SKOS 이름표 — :mod:`foms.services.brain.labels`)을
가진 온톨로지인데, 상담 초안은 그 표에서 다시 만든 **지식 문서 사본**(기준 답 · 사실 · 정책 · 가격 규칙 · 사장님 결정 · 제작 조건의
``[id] (종류) 글`` 줄)만 읽었다. 다른 이름 · 용어 · 규격 · 절차 항목은 AI 에게 가지 않았고, 지시문은 '근거 없으면 넘긴다'만 말했고,
숫자 검사는 글자 그대로 같은 값만 통과시켰다. 관리 패널 '바꿔 묻기 대응'(:mod:`.onto_settings`, 처음 끔) 세 칸이 하나씩 고친다.

- **다른 말 · 용어 · 규격 싣기**(:func:`load_ontology`): 지금 판 · 반영(active) · 보기 범위 '모두' · 유효 기간 안 · 라홈과 공통
  항목만 읽는다. 지식 문서 항목(실음 칸 ``doc_id``)은 그 항목 줄 아래에 '다른 말' 한 줄, 문서에 없는 유형(:data:`EXTRA_TYPES`)은
  따로 한 칸에 ``[키] (용어) 이름 — 글`` 줄로 싣는다. [내부] 표시 글 · 개인정보 꼴이 있는 이름표는 싣지 않는다. 덧붙인 항목 글은
  숫자 허용 목록에도 든다([사람] 표시 글은 빼고 — :meth:`Ontology.spoken_texts`). 덧붙인 항목은 근거 id 로 고르지 않는다(고를 수
  있는 근거 id 는 지식 문서 항목 그대로 — 지표 · [사람] 금액 막기가 그 id 를 본다).
- **같은 뜻이면 답하기**(:data:`ONTO_RULE`): 지시문 8번과 지식 머리말을 바꾼다.
- **숫자 같은 값**: :mod:`.checks_same` — 부르는 쪽이 :meth:`.knowledge_doc.ApprovedKnowledge.same_values` 를 넘긴다.

글 줄은 같은 묶음이면 같은 바이트다(키 순서) — 프롬프트 캐시가 깨지지 않는다.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainObject
from foms.services.brain.constants import BRAND_COMMON, SCOPE_ALL, STATUS_ACTIVE, TYPE_KINDS
from foms.services.brain.labels import aliases_of, pref_of
from foms.services.brain.store import in_force, is_current, started
from foms.services.cs_agent.knowledge_doc import HUMAN_ONLY_MARK, INTERNAL_MARK, ApprovedKnowledge
from foms.services.cs_agent.masking import leak_counts
from foms.services.cs_agent.onto_settings import ONTO_OFF, OntoFlags, onto_flags
from foms.services.cs_agent.ontology_text import EXTRA_HEAD, ONTO_HEAD, ONTO_RULE, OLD_RULE
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.state import KST

logger = logging.getLogger(__name__)

__all__ = [
    "EXTRA_HEAD", "EXTRA_TYPES", "ONTO_HEAD", "ONTO_RULE", "OLD_RULE", "Ontology", "OntoItem", "load_ontology",
    "with_ontology",
]

#: 지식 문서에 없는 온톨로지 유형 → 줄에 쓰는 말.
EXTRA_TYPES: dict[str, str] = {"term": "용어", "spec": "규격", "process_step": "절차", "product_line": "제품 라인",
                               "option": "옵션"}
MAX_EXTRA, MAX_ALIASES, MAX_ALIAS_CHARS, MAX_ROWS = 200, 8, 40, 2000
@dataclass(frozen=True)
class OntoItem:
    """지식 문서에 없는 온톨로지 항목 하나(용어 · 규격 · 절차 …)."""

    key: str
    kind: str
    name: str
    text: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ontology:
    """초안에 잇는 온톨로지 재료 — 세 칸 값 · 지식 문서 항목 id 별 다른 말 · 덧붙인 항목."""

    flags: OntoFlags = ONTO_OFF
    aliases: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    extra: tuple[OntoItem, ...] = ()

    def spoken_texts(self) -> tuple[str, ...]:
        """덧붙인 항목 글 가운데 숫자 허용 목록이 되는 것([사람] 표시 글은 뺀다 — [내부]는 싣지 않았다)."""
        return tuple(item.text for item in self.extra if HUMAN_ONLY_MARK not in item.text)


def _clean_labels(name: str, payload: Any, *, skip: str = "") -> tuple[str, ...]:
    """보일 이름표 — 대표 이름(항목 글과 다를 때) + 다른 이름(숨은 이름 빼고), 겹침 · 너무 긴 것 · 개인정보 꼴 빼고."""
    labels = [pref_of(name, payload), *aliases_of(payload, hidden=False)]
    out: list[str] = []
    for label in labels:
        label = " ".join(str(label).split())
        if (not label or label == skip or len(label) > MAX_ALIAS_CHARS or label in out
                or any(leak_counts(label).values())):
            continue
        out.append(label)
    return tuple(out[:MAX_ALIASES])


def load_ontology(session: Any, brand: str, flags: OntoFlags, *, today: Optional[datetime.date] = None) -> Ontology:
    """회사 지식 표에서 다른 말 · 덧붙일 항목을 읽는다(DB 읽기만). '싣기' 칸이 꺼졌으면 빈 재료(세 칸 값만)."""
    if not flags.labels:
        return Ontology(flags)
    day = today or datetime.datetime.now(KST).date()
    stmt = (select(BrainObject.item_key, BrainObject.item_type, BrainObject.name, BrainObject.text, BrainObject.payload)
            .where(is_current(BrainObject), BrainObject.status == STATUS_ACTIVE,
                   BrainObject.brand.in_((brand, BRAND_COMMON)), BrainObject.visibility == SCOPE_ALL,
                   BrainObject.item_type.in_((*TYPE_KINDS, *EXTRA_TYPES)), in_force(BrainObject, day),
                   started(BrainObject, day))
            .order_by(BrainObject.item_type, BrainObject.item_key).limit(MAX_ROWS))
    aliases: dict[str, tuple[str, ...]] = {}
    extra: list[OntoItem] = []
    for key, item_type, name, text, payload in session.execute(stmt):
        payload = payload if isinstance(payload, dict) else {}
        body = " ".join(str(text or "").split())
        if INTERNAL_MARK in body:
            continue
        if item_type in TYPE_KINDS:
            doc_id = payload.get("doc_id")
            labels = _clean_labels(name, payload, skip=str(doc_id or ""))
            if isinstance(doc_id, str) and labels:
                aliases[doc_id] = labels
        elif body and len(extra) < MAX_EXTRA:
            extra.append(OntoItem(str(key), EXTRA_TYPES[item_type], pref_of(name, payload), body,
                                  _clean_labels(name, payload, skip=pref_of(name, payload))))
    return Ontology(flags, aliases, tuple(extra))


def with_ontology(session: Any, knowledge: ApprovedKnowledge) -> ApprovedKnowledge:
    """승인 지식에 바꿔 묻기 대응 재료를 붙인다(관리 패널 세 칸 — 모두 꺼졌으면 그대로). 읽기가 실패하면 그대로(초안은 계속)."""
    try:
        flags = onto_flags(read_settings(session, log=False))
        if not flags.any:
            return knowledge
        return dataclasses.replace(knowledge, onto=load_ontology(session, knowledge.brand, flags))
    except Exception as exc:  # failopen: intentional: 바꿔 묻기 재료는 덤이다 — 못 읽으면 예전 재료로 초안을 쓴다
        session.rollback()
        logger.warning("[CS 지식] 바꿔 묻기 재료를 못 읽어 예전 재료로 쓴다 err=%s", type(exc).__name__)
        return knowledge
