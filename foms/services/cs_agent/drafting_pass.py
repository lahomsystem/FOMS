"""초안 차례 한 바퀴의 재료와 쓰기 도우미 — 15분 바퀴(:mod:`.drafting`)의 꼴, 빠른 길(:mod:`.realtime`)이 물려받아 바꾼다.

:mod:`.drafting` 이 500줄 상한에 닿아 따로 뒀다(drafting_read · drafting_post · drafting_summary 와 같은 꼴). 쓰기 전마다 TERM 깃발을
본다. 두 길이 같이 쓰는 규칙(검수 R13):

- **스위치 다시 읽기(R13-7)**: 선점 전 · 두뇌 전마다 비상 정지 · 초안 스위치 · 관리 화면 빠른 길 스위치를 DB 에서 새로 읽는다 —
  빠른 길이 켜지면 15분 바퀴가, 꺼지면 빠른 길이 그 자리에서 멈춘다(두 길이 같이 초안을 쓰지 않는다).
- **'AI 냐 사람이냐'(R13-9 · 설계서 17.1 · 17.8 '늘 사람에게')**: 두 길 모두 두뇌 전에 :mod:`.ask_human` 으로 거른다. 두뇌 없이 넘김
  까닭만 적고, 메모 스위치면 비공개 한 줄 메모 — 같은 미답 묶음에 그 메모가 이미 있으면 다시 올리지 않는다.
- **넘김 메모**: 두뇌 넘김 · 검사 걸림은 예전처럼 건너뜀으로 적은 뒤, 관리 화면 '넘김 메모'(처음 끔)가 켜졌으면 까닭 메모를 한 번
  올린다(:meth:`DraftPass.hand_off` → :mod:`.handoff_memo` — 두 길 공통, 실패해도 바퀴는 그대로).
- **안 보이는 손님 글(R13-6)**: 선점한 글이 채널톡 읽기에 아직 없으면 건너뜀이 아니라 다시 집을 실패다.
- **손님 사진(설계서 17.11.1)**: 차례마다 한 번 읽어(:mod:`.photo_step`) 결과를 들고 있다 — 사진만 온 글 판정 · 두뇌 사진 칸 ·
  견적 도면 길 · 직원 참고 줄 · 차례 줄 쓰임이 같은 결과를 쓴다.
- **주문 확인(설계서 2026-11-12 온톨로지 5.6)**: 주문 문의 때만 본인 확인된 ERP 주문 칸을 싣는다(:mod:`.order_step` — 끄면 그대로).
  그 차례 결과를 들고 있다가 검사 확정 날 · 허용 글 · 직원 참고 줄에 쓴다.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import time
from typing import Any, Callable, Optional, Sequence

from foms.persistence.main.models import CsAgentTurn
from foms.services.cs_agent.ask_human import ASK_HUMAN_MEMO, ASK_HUMAN_MEMO_HEAD, ASKED_IF_AI, any_asks_if_human
from foms.services.cs_agent.drafting_post import memo_on, post_note
from foms.services.cs_agent.drafting_read import SKIP_NOT_VISIBLE, ChatLine, customer_texts
from foms.services.cs_agent.drafting_summary import DraftSummary
from foms.services.cs_agent.handoff_memo import post_handoff_memo
from foms.services.cs_agent.image_settings import MODE_DRAFT as PHOTOS_IN_DRAFT, image_mode
from foms.services.cs_agent.image_step import turn_hook as image_hook
from foms.services.cs_agent.knowledge import ApprovedKnowledge
from foms.services.cs_agent.knowledge_doc import HUMAN_ONLY_MARK
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.memo import memo_allowed
from foms.services.cs_agent.onto_block import onto_block
from foms.services.cs_agent.onto_find import find_items
from foms.services.cs_agent.onto_meaning import find_by_meaning
from foms.services.cs_agent.onto_settings import onto_graph_on, onto_meaning_on
from foms.services.cs_agent.order_step import OrderTurn, lookup_after, lookup_first
from foms.services.cs_agent.photo_step import PhotoRead, note_line, read_photos, with_usage
from foms.services.cs_agent.quote_step import QuoteStep, prepare as prepare_quote
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.turns import (
    DRAFT_OFF, LEGACY_CLAIM_AFTER, claim_owner, draft_mode, mark_failed, mark_skipped, read_switch, record_handoff,
    record_quote, release_turn,
)
from foms.services.datetime_kst import get_today_kst

logger = logging.getLogger("foms.services.cs_agent.drafting")

__all__ = ["HUMAN_ONLY_MARK", "DraftPass", "pending_customer_lines"]



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
                 daytime: bool, summary: DraftSummary, clock: Callable[[], float] = time.monotonic,
                 quoter: Optional[Callable[..., Any]] = None, catalog_reader: Optional[Callable[[], Any]] = None,
                 image_client: Any = None, image_transport: Any = None,
                 image_sleep: Optional[Callable[[float], None]] = None) -> None:
        """재료를 담는다. 허용 목록은 승인 지식 글만 — [사람] · [내부] 항목 글 · 손님 글 금액은 넣지 않는다(손님 예산에 맞춰
        주게 된다 · 내부 규칙이 샌다 — D164).

        견적 계산 넣기(C10-6)가 켜진 차례만 계산기 값 줄이 그 차례 허용 목록에 더해진다(:meth:`quote`). ``quoter`` ·
        ``catalog_reader`` 는 뽑기 두뇌 · 계산기 설정 읽기, ``image_client`` · ``image_transport`` · ``image_sleep`` 은 그림 읽기
        두뇌 · 파일 받기 · 기다림(설계서 17.11 — 시험은 가짜, 없으면 진짜).
        """
        self.session, self.reader, self.now, self.stop, self.mode = session, reader, now, stop, mode
        self.brain, self.poster, self.knowledge, self.daytime, self.summary = brain, poster, knowledge, daytime, summary
        self.allowed = knowledge.spoken_texts()
        self.human_only = frozenset(item.item_id for item in knowledge.items if HUMAN_ONLY_MARK in item.text)
        self.owner = claim_owner(self.owner_kind)
        self.clock = clock  # 빠른 길이 선점 시각을 잴 때 쓴다(15분 바퀴는 시간 상한 시계를 여기서 읽지 않는다)
        self.quoter, self.catalog_reader = quoter, catalog_reader
        self.image_client, self.image_transport, self.image_sleep = image_client, image_transport, image_sleep
        self.photo_reads: dict[int, Optional[PhotoRead]] = {}  # 차례 줄 id → 사진 읽기(차례마다 한 번)
        self.image_outcomes: dict[int, Any] = {}  # 차례 줄 id → 묶음 읽기 결과(:func:`.photo_step.turn_read`)
        self.order_turns: dict[int, OrderTurn] = {}  # 차례 줄 id → 주문 확인(:mod:`.order_step`)
        self.onto_blocks: dict[int, tuple[str, ...]] = {}  # 차례 줄 id → 걸린 물건 칸(:mod:`.onto_block`)

    def photos(self, row: CsAgentTurn, lines: Sequence[ChatLine]) -> Optional[PhotoRead]:
        """손님 사진 읽기(:func:`.photo_step.read_photos` — 끔 · 파일 없음이면 ``None``). 같은 차례면 앞 결과."""
        if row.id not in self.photo_reads:
            self.photo_reads[row.id] = read_photos(self, row, lines)
        return self.photo_reads[row.id]

    def photo_only_ok(self, row: CsAgentTurn, lines: Sequence[ChatLine]) -> bool:
        """사진만 온 글에 초안을 써도 되나 — '초안에 씀'이고 읽은 사진이 하나라도 있을 때만(17.11.1 의 4)."""
        if image_mode(read_settings(self.session, log=False)) != PHOTOS_IN_DRAFT:
            return False
        photo = self.photos(row, lines)
        return photo is not None and photo.read > 0

    def with_photos(self, row: CsAgentTurn, request: Any, lines: Sequence[ChatLine]) -> Any:
        """초안 재료에 사진 칸('초안에 씀'일 때만 — 끔 · 직원 참고만이면 그대로)."""
        photo = self.photos(row, lines)
        return photo.apply(request) if photo is not None else request

    def photo_usage(self, row: CsAgentTurn, base: Any) -> Any:
        """쓰임에 이번 차례 사진 읽기의 토큰 · 돈 · 시간을 더한다(읽지 않았으면 그대로)."""
        return with_usage(base, self.photo_reads.get(row.id))

    def photo_note(self, row: CsAgentTurn, quote_note: str) -> str:
        """직원 참고 줄 — 사진 줄(:func:`.photo_step.note_line`) · 주문 확인 줄 뒤에 견적 계산 줄(없으면 빈 글 — 예전 그대로)."""
        order = self.order_turns.get(row.id)
        parts = (note_line(self.photo_reads.get(row.id)), order.note() if order is not None else "", quote_note)
        return "\n".join(part for part in parts if part)

    def order_first(self, row: CsAgentTurn, request: Any, lines: Sequence[ChatLine]) -> Any:
        """두뇌 전 주문 확인(:func:`.order_step.lookup_first` — 끔 · 물은 적 없음이면 그대로)."""
        return lookup_first(self, row, request, lines)

    def order_again(self, row: CsAgentTurn, request: Any, result: Any, lines: Sequence[ChatLine],
                    medium: Optional[str]) -> Any:
        """두뇌가 주문 문의로 넘긴 뒤(:func:`.order_step.lookup_after` — 끔 · 주문 문의 아님이면 그대로)."""
        return lookup_after(self, row, request, result, lines, medium)

    def order_checks(self, row: CsAgentTurn) -> tuple[tuple[Any, ...], tuple[str, ...]]:
        """이 차례 주문 확인 · 걸린 물건 칸의 (검사 확정 날, 허용 글) — 없으면 빈 것."""
        order = self.order_turns.get(row.id)
        dates, allowed = (order.dates(), order.allowed()) if order is not None else ((), ())
        return dates, (*allowed, *self.onto_blocks.get(row.id, ()))

    def with_onto(self, row: CsAgentTurn, request: Any, lines: Sequence[ChatLine]) -> Any:
        """물건 찾아 따라가기(설계서 온톨로지 5절 — 끔이면 설정 한 번 읽기뿐, 그대로). 확인된 주문 품목 이름도 찾기 재료."""
        cfg = read_settings(self.session, log=False)
        if not onto_graph_on(cfg):
            return request
        order = self.order_turns.get(row.id)
        extra = order.facts.products if order is not None and order.facts is not None else ()
        texts, day = customer_texts(lines), get_today_kst()
        hits = find_items(self.session, texts, brand=row.brand, day=day, extra=extra)
        if not hits and onto_meaning_on(cfg):  # 이름표로 못 찾으면 뜻으로(D197 ② — 가린 글만, 처음 끔)
            hits = find_by_meaning(self.session, texts, brand=row.brand, day=day, now=self.now,
                                   customer_names=request.customer_names, staff_names=request.staff_names)
        block = tuple(onto_block(hits))
        if not block:
            return request
        self.onto_blocks[row.id] = block
        return dataclasses.replace(request, onto_lines=block)

    def quote(self, row: CsAgentTurn, request: Any, lines: Sequence[ChatLine]) -> Optional[QuoteStep]:
        """견적 계산 넣기(:func:`.quote_step.prepare` — 끔 · 견적 말 없음이면 ``None``, 예전 그대로). 두뇌 오류는 올린다.

        결과 값(상태 · 두뇌 줄 · 허용 금액 줄)과 뽑기 쓰임은 초안 두뇌 **전에** 차례 줄에 적고 커밋한다 — 보내기 · 고칠 말 ·
        다시 올리기 검사가 다시 쓰고(R17-1 · R17-2), 초안 두뇌가 실패해도 뽑기 돈이 남는다(R17-3). 이번 시도가 견적을 넣지
        않았는데 지난 시도의 기록이 있으면 지운다.
        """
        texts = [line.text for line in pending_customer_lines(lines) if line.meta.is_customer_signal]
        step = prepare_quote(session=self.session, knowledge=self.knowledge, request=request, texts=texts,
                             now=self.now, stop=self.stop, summary=self.summary, quoter=self.quoter,
                             catalog_reader=self.catalog_reader, drawing=image_hook(self, row, request, lines))
        if step is None and row.quote_lines is None:
            return None
        self.stop.check()  # 쓰기 전
        record_quote(row, quote_lines=step.record() if step is not None else None,
                     usage=self.photo_usage(row, step.usage) if step is not None else None)
        self.session.commit()
        return step

    def quote_to_human(self, row: CsAgentTurn, chat_id: str, code: str) -> Optional[str]:
        """견적 계산이 안 돼 초안 없이 사람에게 — 넘김 까닭을 적고 건너뜀(메모 없음 — 두뇌 넘김과 같다)."""
        self.stop.check()  # 쓰기 전
        record_handoff(row, reason=code)
        logger.info("[CS 초안] 견적 계산이 안 돼 사람에게 chat=%s code=%s", chat_id, code)
        return self.skip(row, code)

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

    def hand_off(self, row: CsAgentTurn, code: str, *, codes: Sequence[Any] = (), masked: Optional[str] = None,
                 note: str = "") -> Optional[str]:
        """두뇌 넘김 · 검사 걸림 — 예전처럼 건너뜀(:meth:`skip` — 빠른 길 꼴 그대로)을 적고 커밋한 뒤, 관리 화면 '넘김 메모'가
        켜졌으면 까닭 메모 한 번(:func:`.handoff_memo.post_handoff_memo` — ``note`` 는 두뇌의 직원 참고). 멈출 까닭을 돌려준다."""
        halt = self.skip(row, code, codes=codes, masked=masked)
        return post_handoff_memo(self, row, code, codes=codes, note=note) or halt

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
