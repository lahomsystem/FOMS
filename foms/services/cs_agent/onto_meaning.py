"""단계 2 보조 '뜻으로도 물건 찾기' — 이름표로 아무것도 못 찾은 차례만, 가린 손님 글을 Voyage AI 벡터로 바꿔 뜻이 가까운
제품 라인 · 옵션에 잇는다(사장님 D197 ② · 설계서 2026-11-12 온톨로지 10절 13 — **처음 끔**).

- **켜는 조건 셋**: 관리 칸 '물건 찾아 따라가기' + '뜻으로도 물건 찾기'(:data:`.onto_settings.ONTO_MEANING_FIELD`) + 회사 지식
  물어보기 설정의 '의미 찾기' · 하루 돈 상한 · 열쇠 env · 벡터 표(:func:`foms.services.brain.embeddings.off_reason`). 하나라도
  없으면 부르지 않는다(빈 목록 — 초안은 예전 그대로).
- **나가는 글**: 손님 글을 :func:`.masking.mask` 로 가린 뒤 끝 :data:`QUERY_CHARS` 글자만, 그리고 회사 지식 의미 찾기와 같은
  검사(:func:`foms.services.brain.embeddings.safe_text` — 가림 검사 0 · 계좌 같은 번호 없음)를 지난 것만. 돈은 의미 찾기 돈 줄 · 상한 안.
  가린 상담 글이 바깥(미국)으로 나가므로 처리방침 국외 이전 항목 고침 · Voyage '학습에 쓰지 않기' 뒤에 켠다.
- **고르기**: 같은 판 · 반영 · 보기 범위 모두 · 그 브랜드와 공통 · 기간 안의 제품 라인 · 옵션 벡터 가운데 비슷함
  :data:`MIN_SIMILARITY` 이상, 위에서 :data:`MAX_MEANING` 개. 묶음 칸에는 '뜻으로 찾음 — 손님이 말한 물건이 아닐 수 있다'가 붙는다
  (:mod:`.onto_block`). 기준 값은 다시 돌려 보기(D182)로 고친다.
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Sequence

from foms.persistence.brain.models import BrainObject
from foms.services.brain.chat_settings import read_chat_settings
from foms.services.brain.embeddings import nearest_where, off_reason, query_vector, safe_text
from foms.services.cs_agent.masking import mask
from foms.services.cs_agent.onto_find import ITEM_TYPES, OntoHit, hits_for, visible

__all__ = ["MAX_MEANING", "MIN_SIMILARITY", "QUERY_CHARS", "find_by_meaning", "meaning_query"]

MIN_SIMILARITY = 0.55
MAX_MEANING = 3
QUERY_CHARS = 600


def meaning_query(texts: Sequence[str], *, customer_names: Iterable[str] = (), staff_names: Iterable[str] = ()) -> str:
    """손님 글 → 보낼 글(가림 · 끝 :data:`QUERY_CHARS` 글자). 검사를 못 지나면 빈 글."""
    names, staff = list(customer_names), list(staff_names)
    body = " ".join(mask(text, customer_names=names, staff_names=staff) for text in texts if text and text.strip())
    body = " ".join(body.split())[-QUERY_CHARS:]
    return body if safe_text(body) else ""


def find_by_meaning(session: Any, texts: Sequence[str], *, brand: str, day: datetime.date, now: datetime.datetime,
                    customer_names: Iterable[str] = (), staff_names: Iterable[str] = ()) -> list[OntoHit]:
    """가린 손님 글 → 뜻이 가까운 물건(못 쓰면 빈 목록 — 던지지 않는다)."""
    cfg = read_chat_settings(session)
    if off_reason(session, cfg) is not None:
        return []
    query = meaning_query(texts, customer_names=customer_names, staff_names=staff_names)
    if not query:
        return []
    vector = query_vector(session, query, cfg=cfg, now=now)
    if vector is None:
        return []
    ranked = nearest_where(session, vector, (BrainObject.item_type.in_(ITEM_TYPES), *visible(BrainObject, brand, day)),
                           limit=MAX_MEANING)
    return hits_for(session, [key for key, score in ranked if score >= MIN_SIMILARITY], brand=brand, day=day,
                    by_meaning=True)
