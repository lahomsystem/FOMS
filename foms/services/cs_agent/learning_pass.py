"""15분 바퀴의 학습 몫 — 사진 설명 뽑기(:mod:`.photo_desc`) · 주간 고침 안(:mod:`.weekly_fix`) · 사진 학습 → 회사 지식 제안
(:mod:`.photo_learning` — 설계서 17.11.1 의 7)을 차례로 부른다(설계서 17.6.1).

감시 루프(:mod:`.loop`)가 초안 스위치가 꺼지지 않은 바퀴에서만 부른다 — 빠른 길(:mod:`.realtime`)은 부르지 않는다. 두 길은 각자
패널 칸 · 비상 정지 · 학습 돈 상한을 다시 본다. 학습 몫이 실패해도 바퀴(보정 · 아침 보고 · 초안)는 이어 간다 — 실패는 길 이름과
예외 종류 코드로 경고 로그에 남긴다(글 · 상담 id 없음). TERM 멈춤은 그대로 올린다.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Optional

from sqlalchemy.exc import SQLAlchemyError

from foms.services.cs_agent.brain_spend import BrainError
from foms.services.cs_agent.photo_desc import run_photo_desc
from foms.services.cs_agent.photo_learning import run_photo_learning
from foms.services.cs_agent.weekly_fix import run_weekly_fix

logger = logging.getLogger(__name__)

__all__ = ["run_learning"]

#: 학습 몫이 바퀴를 깨지 않게 받는 실패 — 두뇌 · DB · 저장소(입출력) · 그림 꼴. 그 밖의 예외는 버그라 그대로 올린다.
_HANDLED = (BrainError, SQLAlchemyError, OSError, ValueError)


def _quiet(result: dict[str, Any]) -> bool:
    """꺼진 길(``off``)이면 요약에 싣지 않는다 — 끈 동안 바퀴 요약은 예전 그대로."""
    return set(result) == {"off"}


def run_learning(session: Any, *, now: datetime.datetime, stop_check: Callable[[], None],
                 client: Any = None, storage: Any = None, reader: Any = None) -> Optional[dict[str, Any]]:
    """학습 몫 한 번. 돈 길이 있으면 ``{"photo_desc": {...}, "weekly_fix": {...}, "photo_learning": {...}}``(숫자 · 코드만),
    모두 꺼졌으면 ``None``. ``reader`` 는 상담 전체 대화(설계서 17.11.2)를 읽는 감시 바퀴의 채널톡 읽기 도우미다."""
    out: dict[str, Any] = {}
    steps = (("photo_desc", lambda: run_photo_desc(session, now=now, client=client, storage=storage)),
             ("weekly_fix", lambda: run_weekly_fix(session, now=now, client=client, reader=reader)),
             ("photo_learning", lambda: run_photo_learning(session, now=now, client=client, reader=reader)))
    for name, step in steps:
        stop_check()  # 길마다 앞에서 TERM 을 본다(멈춤은 그대로 올라간다)
        try:
            result = step()
        except _HANDLED as exc:
            session.rollback()
            logger.warning("[CS 학습] %s 실패 — 바퀴는 이어 간다 code=%s", name,
                           exc.code if isinstance(exc, BrainError) else type(exc).__name__)
            result = {"error": type(exc).__name__}
        if not _quiet(result):
            out[name] = result
    return out or None
