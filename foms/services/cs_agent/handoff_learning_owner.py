"""넘긴 상담 배우기 — **사장님이 ③ 답으로 정한 지식은 사람 없는 길로 다시 바꾸지 않는다**(설계서 2026-11-26 온톨로지 잇기 3.2 ·
카드 비평 S1).

예전에는 사장님이 「회사 지식이 맞아요」로 닫은 뒤에도, 직원이 같은 뜻을 다른 말로 손님 두 곳에 하면 글자 비슷함 관문(거절된 안과
0.8 이상)을 비켜 그 지식이 직원 말로 바로 고쳐졌다. 이제 대상이 사장님이 정한 지식이면 밤 배우기의 사람 없는 길 둘을 타지 않는다
(:mod:`.handoff_learning_route` 가 부른다):

- **다른 말 바로 고침**(서로 다른 손님 둘 이상 — D267) → 바로 고치지 않고 놓을 자리 판정(판정자는 '사장님이 이미 정한 것' 줄을
  본다 — :func:`.handoff_learning_place.decided_lines`)과 카드 길로.
- **판정으로 넣은 고침의 바로 반영**(더함 등 — 그 지식을 고치는 안) → 넣되 바로 반영하지 않는다(승인 대기 — 사람이 넣는다).

'사장님이 정한 지식'은 표를 새로 두지 않고 제안 줄에서 가른다(:func:`owner_decided` — 답으로 닫힌 질문 카드의 대상 키 · 그 답이
다룬 키, :func:`foms.services.brain.answers.answered_about`). 방금 정한 것 되돌리기로 다시 연 카드는 세지 않는다. 멈춘 수는
:data:`OWNER_REDO` 이름으로 넣기 결과에 더한다(밤 줄에 싣는 일은 부르는 쪽 몫).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange
from foms.services.brain.answers import answered_about
from foms.services.brain.constants import OP_UPDATE

__all__ = ["OWNER_REDO", "auto_unless_owner", "owner_decided"]

#: 넣기 결과(:func:`.handoff_learning_route.file_proposals`)의 칸 — 사장님이 정한 지식이라 사람 없는 길을 멈춘 수.
OWNER_REDO = "owner_redo"


def owner_decided(session: Any, key: Any) -> bool:
    """사장님이 ③ 답으로 정한 지식인가(모듈 설명) — 빈 키는 거짓."""
    wanted = key.strip() if isinstance(key, str) else ""
    if not wanted:
        return False
    return session.execute(select(BrainChange.id).where(answered_about([wanted])).limit(1)).first() is not None


def auto_unless_owner(session: Any, change: Any, auto: Any) -> tuple[Optional[Any], bool]:
    """넣은 안의 바로 반영을 넘길지 — 사장님이 정한 지식을 고치는 안이면 ``(None, True)``(승인 대기에 둔다), 그 밖은
    ``(auto, False)``. 바로 반영이 꺼져 있으면 보지 않는다."""
    if auto is None or change is None or getattr(change, "op", None) != OP_UPDATE:
        return auto, False
    if owner_decided(session, getattr(change, "item_key", None)):
        return None, True
    return auto, False
