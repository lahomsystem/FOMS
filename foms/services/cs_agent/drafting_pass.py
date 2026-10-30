"""초안 차례 한 바퀴의 재료와 쓰기 도우미 — 15분 바퀴(:mod:`.drafting`)의 꼴, 빠른 길(:mod:`.realtime`)이 물려받아 바꾼다.

:mod:`.drafting` 이 500줄 상한에 닿아 따로 뒀다(drafting_read · drafting_post · drafting_summary 와 같은 꼴). 쓰기 전마다 TERM 깃발을
본다. 두 길이 같이 쓰는 규칙(검수 R13):

- **스위치 다시 읽기(R13-7)**: 선점 전 · 두뇌 전마다 비상 정지 · 초안 스위치 · 관리 화면 빠른 길 스위치를 DB 에서 새로 읽는다 —
  빠른 길이 켜지면 15분 바퀴가, 꺼지면 빠른 길이 그 자리에서 멈춘다(두 길이 같이 초안을 쓰지 않는다).
- **'AI 냐 사람이냐'(R13-9 · 설계서 17.1 · 17.8 '늘 사람에게')**: 두 길 모두 두뇌 전에 :mod:`.ask_human` 으로 거른다. 두뇌 없이 넘김
  까닭만 적고, 메모 스위치면 비공개 한 줄 메모 — 같은 미답 묶음에 그 메모가 이미 있으면 다시 올리지 않는다.
- **안 보이는 손님 글(R13-6)**: 선점한 글이 채널톡 읽기에 아직 없으면 건너뜀이 아니라 다시 집을 실패다.
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Any, Callable, Optional, Sequence

from foms.persistence.main.models import CsAgentTurn
from foms.services.cs_agent.ask_human import ASK_HUMAN_MEMO, ASK_HUMAN_MEMO_HEAD, ASKED_IF_AI, any_asks_if_human
from foms.services.cs_agent.drafting_post import memo_on, post_note
from foms.services.cs_agent.drafting_read import SKIP_NOT_VISIBLE, ChatLine
from foms.services.cs_agent.drafting_summary import DraftSummary
from foms.services.cs_agent.knowledge import ApprovedKnowledge
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.memo import memo_allowed
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.turns import (
    DRAFT_OFF, LEGACY_CLAIM_AFTER, claim_owner, draft_mode, mark_failed, mark_skipped, read_switch, record_handoff,
    release_turn,
)

logger = logging.getLogger("foms.services.cs_agent.drafting")

__all__ = ["HUMAN_ONLY_MARK", "DraftPass", "pending_customer_lines"]

HUMAN_ONLY_MARK = "[사람]"  # 승인 지식에서 사람만 말하는 항목 표시 — 그 글의 숫자는 허용 목록에 넣지 않는다


def pending_customer_lines(lines: Sequence[ChatLine]) -> list[ChatLine]:
    """마지막 공개 직원 글 뒤의 글(같은 미답 묶음) — 손님 글 · 비공개 메모 모두."""
    after = max((i for i, line in enumerate(lines) if line.meta.is_answer), default=-1)
    return list(lines[after + 1:])


class DraftPass:
    """한 바퀴의 재료와 쓰기 도우미. 15분 바퀴의 꼴이고, 빠른 길은 :attr:`realtime` · 선점 시각 · 만료 · 건너뜀만 바꾼다."""

    #: 두뇌 시간 상한 길(실시간 · 15분) · 선점 주인 이름 앞말 · 선점 만료(15분 바퀴는 예전 20분).
    realtime, owner_kind, claim_ttl = False, "pass", LEGACY_CLAIM_AFTER

    def __init__(self, session: Any, *, reader: Any, now: datetime.datetime, stop: Any, mode: str,
                 brain: Callable[..., Any], poster: Callable[..., Any], knowledge: ApprovedKnowledge,
                 daytime: bool, summary: DraftSummary, clock: Callable[[], float] = time.monotonic) -> None:
        """재료를 담는다. 허용 목록은 승인 지식 글만 — [사람] 항목 글 · 손님 글 금액은 넣지 않는다(손님 예산에 맞춰 주게 된다)."""
        self.session, self.reader, self.now, self.stop, self.mode = session, reader, now, stop, mode
        self.brain, self.poster, self.knowledge, self.daytime, self.summary = brain, poster, knowledge, daytime, summary
        self.allowed = tuple(item.text for item in knowledge.items if HUMAN_ONLY_MARK not in item.text)
        self.human_only = frozenset(item.item_id for item in knowledge.items if HUMAN_ONLY_MARK in item.text)
        self.owner = claim_owner(self.owner_kind)
        self.clock = clock  # 빠른 길이 선점 시각을 잴 때 쓴다(15분 바퀴는 시간 상한 시계를 여기서 읽지 않는다)

    def claim_at(self) -> datetime.datetime:
        """선점 시각 — 15분 바퀴는 바퀴 시각 그대로(빠른 길은 실제 지금 시각으로 바꾼다)."""
        return self.now

    def switched_off(self) -> bool:
        """비상 정지 · 초안 끔이거나, 관리 화면 빠른 길 스위치가 이 길과 다르면 참(DB 에서 새로 읽는다 — R13-7)."""
        session = self.session
        if not read_switch(session) or draft_mode(session) == DRAFT_OFF:
            return True
        return bool(read_settings(session, log=False).get("realtime_enabled")) != self.realtime

    def asks_human(self, lines: Sequence[ChatLine]) -> bool:
        """마지막 공개 직원 글 뒤 손님 글 가운데 'AI 냐 사람이냐' 물음이 있나(:mod:`.ask_human`)."""
        return any_asks_if_human(line.text for line in pending_customer_lines(lines) if line.meta.is_customer_signal)

    def hand_to_human(self, row: CsAgentTurn, chat_id: str, lines: Sequence[ChatLine]) -> Optional[str]:
        """두뇌 없이 사람에게 — 넘김 까닭을 적고, 메모 스위치면 비공개 한 줄 메모(같은 묶음에 이미 있으면 다시 안 올림),
        아니면 기록만(건너뜀). 이번 바퀴를 멈출 까닭을 돌려준다."""
        self.stop.check()  # 쓰기 전
        record_handoff(row, reason=ASKED_IF_AI)
        self.summary.asked_human += 1
        logger.info("[CS 초안] 손님이 'AI 냐 사람이냐' 물어 두뇌 없이 사람에게 chat=%s", chat_id)
        posted = any(line.meta.is_private and line.text.lstrip().startswith(ASK_HUMAN_MEMO_HEAD)
                     for line in pending_customer_lines(lines))
        if not posted and memo_on(self) and memo_allowed(chat_id):
            return post_note(self, row, chat_id, text=ASK_HUMAN_MEMO)
        return self.skip(row, ASKED_IF_AI)

    def skip(self, row: CsAgentTurn, code: str, *, codes: Sequence[Any] = (), masked: Optional[str] = None,
             halt: Optional[str] = None) -> Optional[str]:
        """건너뜀으로 적고 커밋(가린 초안이 가림 검사에 걸리면 초안 없이). 이번 바퀴를 멈출 까닭(``halt``)을 돌려준다.

        선점한 손님 글이 채널톡 읽기에 아직 없으면(:data:`.drafting_read.SKIP_NOT_VISIBLE`) 건너뜀이 아니라 다시 집을 실패다.
        """
        if code == SKIP_NOT_VISIBLE:
            return self.fail(row, code, halt=halt)
        self.stop.check()  # 쓰기 전
        chat_id = row.chat_id
        try:
            mark_skipped(row, reason=code, check_codes=codes, masked_draft=masked, now=self.now)
        except MaskLeak:
            mark_skipped(row, reason=code, check_codes=codes, now=self.now)
        self.session.commit()
        self.summary.skipped[code] = self.summary.skipped.get(code, 0) + 1
        logger.info("[CS 초안] 건너뜀 chat=%s code=%s", chat_id, code)
        return halt

    def fail(self, row: CsAgentTurn, code: str, *, halt: Optional[str] = None) -> Optional[str]:
        """실패로 적고 커밋(시도 상한 전이면 다시 집기 간격 뒤 다시 집는다). 이번 바퀴를 멈출 까닭을 돌려준다."""
        self.stop.check()  # 쓰기 전
        chat_id = row.chat_id
        retry = mark_failed(row, error_code=code, now=self.now)
        self.session.commit()
        self.summary.failed += 1
        logger.warning("[CS 초안] 실패 chat=%s code=%s retry=%s", chat_id, code, retry)
        return halt

    def release(self, row: CsAgentTurn, code: str, *, halt: str) -> str:
        """시도를 세지 않고 돌려놓고 커밋(R7-4 — 손님 차례 탓이 아닌 멈춤). 이번 바퀴를 멈출 까닭을 돌려준다."""
        self.stop.check()  # 쓰기 전
        chat_id = row.chat_id
        release_turn(row, error_code=code, now=self.now)
        self.session.commit()
        self.summary.released += 1
        logger.warning("[CS 초안] 시도로 세지 않고 돌려놓고 멈춘다 chat=%s code=%s", chat_id, code)
        return halt
