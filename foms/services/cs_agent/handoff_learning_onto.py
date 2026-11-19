"""넘긴 상담 배우기의 온톨로지 안 넣기 — 상황 · 제작 조건 · 비슷한 말 · 잇기(사장님 11-19 '매일 학습하고 온톨로지 만들고 계속
업그레이드').

두뇌가 사실 · 정책 안과 같이 낸 ``ontology`` 목록(:func:`.handoff_learning_prompt.raw_ontology` — 사진 학습과 같은 꼴)을 사진
학습의 넣기 길(:func:`.photo_learning._filer`)로 넣는다. 제안한 이는 넘긴 상담 배우기(``agent:cs_handoff_learning``)다.

관문(우리 쪽 — 하나라도 못 넘으면 넣지 않고 까닭 코드별 수만 센다):

1. **꼴**: 까닭 한 줄.
2. **가림 · 숫자**(:func:`.photo_learning._clean`): 개인정보 꼴 · 가림 표시 0, 숫자는 이미 있는 지식 글에 있는 것만.
3. **근거**: 근거 차례가 모두 이번에 읽은 사례 안(한 손님 사례로도 낸다 — 넘긴 상담 배우기와 같은 기준).
4. 대상 · 같음 · 겹침은 :func:`.photo_learning._filer`, 글 · 부딪침 · 근거 관문은 제안 길.

``auto``(패널 '배운 것 바로 반영')면 넣은 안을 그 자리에서 반영한다(:func:`.handoff_learning_gates.apply_now`). 안마다 커밋한다.
로그 · 결과에는 숫자 · 코드만 싣는다(글 없음).
"""

from __future__ import annotations

import datetime
from typing import Any, Optional, Sequence

from foms.services.brain.apply import AutoLearn
from foms.services.brain.errors import BrainError as BrainStoreError
from foms.services.brain.store import current_object
from foms.services.cs_agent import photo_learning
from foms.services.cs_agent.handoff_learning_gates import AGENT, _sources, _store_code, apply_now
from foms.services.cs_agent.send import SEND_BRAND
from foms.services.cs_agent.state import KST

__all__ = ["MAX_ONTOLOGY", "file_ontology"]

MAX_ONTOLOGY = 20


def _ids(raw: dict[str, Any], by_id: dict[int, dict[str, Any]]) -> list[int]:
    """근거 관문 — 통과면 근거 차례 id(정렬), 아니면 빈 목록."""
    ids = raw.get("evidence_turn_ids")
    if not isinstance(ids, list) or not ids or any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
        return []
    return sorted(set(ids)) if set(ids) <= set(by_id) else []


def file_ontology(session: Any, raw: Sequence[dict[str, Any]], cases: Sequence[dict[str, Any]], *,
                  now: datetime.datetime, known: str, auto: Optional[AutoLearn] = None) -> dict[str, int]:
    """온톨로지 안 → 관문 → 제안 길(모듈 설명). 넣은 수(``filed``) · 바로 반영한 수(``applied``)와 막힌 까닭별 수."""
    by_id = {case["turn_id"]: case for case in cases}
    day = f"{now.astimezone(KST):%Y%m%d-h%Hm%M}"
    counts: dict[str, int] = {"filed": 0}
    for number, item in enumerate(raw[:MAX_ONTOLOGY * 2], start=1):
        why = photo_learning._line(item.get("why"), photo_learning.MAX_WHY)
        texts = [str(item.get(n) or "") for n in ("name", "text", "why")] + [str(a) for a in item.get("aliases") or []]
        code: Optional[str] = None
        if why is None:
            code = "form"
        elif not photo_learning._clean(texts, known):
            code = "mask"
        elif not (ids := _ids(item, by_id)):
            code = "evidence"
        elif counts["filed"] >= MAX_ONTOLOGY:
            code = "cap"
        if code is None and item.get("kind") == "update":
            target = current_object(session, str(item.get("key") or "")) if item.get("key") else None
            if target is None or target.brand != SEND_BRAND:  # 공통 글(하우드도 같이 쓴다)은 고치지 않는다
                code = "target"
        if code is None:
            chats = len({by_id[i]["chat_id"] for i in ids})
            reason = f"넘긴 상담 배우기 · 근거 상담 {chats}곳 — {why}"[:500]
            code, make = photo_learning._filer(session, item, key=f"lahom/handoff-onto-{day}-{number}", reason=reason,
                                               evidence=_sources(ids, by_id), now=now, known=known, agent_name=AGENT)
            if make is not None:
                try:
                    change = make()
                    session.commit()
                    extra = apply_now(session, change, auto, now) or ("applied" if auto is not None else None)
                    session.commit()
                    if extra:
                        counts[extra] = counts.get(extra, 0) + 1
                except BrainStoreError as exc:  # 글 관문 · 부딪침 · 근거 · 거절 · 대상 — 넣지 않고 센다
                    session.rollback()
                    code = _store_code(exc)
        counts[code or "filed"] = counts.get(code or "filed", 0) + 1
    return counts
