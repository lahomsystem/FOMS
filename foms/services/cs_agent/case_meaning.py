"""③ 비슷한 지난 상담을 뜻으로도 찾기 — 지금 손님 글(가린 글)을 Voyage AI 벡터로 바꿔, 상담 사례 벡터(``cs_case`` — 가린 손님
질문 + 가린 직원 답) 가운데 뜻이 가까운 것을 사례 고르기(:func:`.case_material.similar_cases`)에 더한다(사장님 D197 ③ · 설계서
2026-11-12 온톨로지 10절 15 — **처음 끔**).

- **켜는 조건**: 관리 칸 '뜻으로도 비슷한 상담 찾기'(:data:`.onto_settings.ONTO_CASES_FIELD`) + 회사 지식 물어보기 설정의
  '의미 찾기' · 하루 돈 상한 · 열쇠 env · 벡터 표(:func:`foms.services.brain.embeddings.off_reason`) + '상담 사례 벡터'
  (:data:`foms.services.brain.chat_settings.CASE_FIELD`). 하나라도 없으면 부르지 않는다(빈 목록 — 글자 비슷함만, 예전 그대로).
- **나가는 글**: 사례 고르기가 쓰는 지금 손님 글(:func:`.case_material.current_question` — 이미 가림 검사를 넘은 글)을 한 번 더
  :func:`foms.services.brain.embeddings.safe_text` 로 본 것만. 돈은 의미 찾기 돈 줄 · 상한 안.
- **고르기**: 같은 브랜드 · 재료가 되는 사례(그대로 · 고침 · 직접 답 · 떼어 두지 않음)의 이 모델 벡터 가운데 비슷함
  :data:`CASE_MEANING_MIN` 이상. 글자 비슷함 순위와 :func:`merge_ranks` (RRF)로 섞는다 — 둘 다에 든 사례가 위로.
"""

from __future__ import annotations

import datetime
from typing import Any, Sequence

from sqlalchemy import String, cast

from foms.persistence.brain.vectors import brain_embeddings
from foms.persistence.main.models import CsAgentTurn
from foms.services.brain.chat_settings import CASE_FIELD, read_chat_settings
from foms.services.brain.embeddings import SOURCE_CASE, nearest_rows, off_reason, query_vector, safe_text

__all__ = ["CASE_MEANING_MIN", "RRF_K", "meaning_case_ids", "merge_ranks"]

CASE_MEANING_MIN = 0.5
RRF_K = 60


def meaning_case_ids(session: Any, query: str, *, usable: Sequence[Any], now: datetime.datetime, limit: int) -> list[int]:
    """가린 지금 손님 글 → 뜻이 가까운 사례 차례 번호(가까운 것부터). 못 쓰면 빈 목록(던지지 않는다 — DB 오류는 부르는 쪽)."""
    cfg = read_chat_settings(session)
    if not cfg.get(CASE_FIELD) or off_reason(session, cfg) is not None or not query or not safe_text(query):
        return []
    vector = query_vector(session, query, cfg=cfg, now=now)
    if vector is None:
        return []
    on = brain_embeddings.c.source_key == cast(CsAgentTurn.id, String)
    ranked = nearest_rows(session, vector, source_kind=SOURCE_CASE, target=CsAgentTurn, on=on, where=usable,
                          limit=limit)
    return [int(key) for key, score in ranked if score >= CASE_MEANING_MIN]


def merge_ranks(text_ids: Sequence[int], meaning_ids: Sequence[int], limit: int) -> list[int]:
    """두 순위(글자 비슷함 · 뜻 비슷함)를 RRF 로 섞어 위에서 ``limit`` 개 — 같은 점수면 글자 순위 · 새 사례 먼저."""
    score: dict[int, float] = {}
    for ranks in (text_ids, meaning_ids):
        for place, turn_id in enumerate(ranks):
            score[turn_id] = score.get(turn_id, 0.0) + 1.0 / (RRF_K + place + 1)
    first = {turn_id: place for place, turn_id in enumerate(text_ids)}
    order = sorted(score, key=lambda t: (-score[t], first.get(t, len(text_ids)), -t))
    return order[:int(limit)]
