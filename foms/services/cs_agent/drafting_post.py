"""초안 놓기 — 저장만 · 내부 메모 올리기와 메모 막는 장치(공개로 확인 → 끔 · 확인 못 함 → 저장만, 관리자 알림).

:mod:`.drafting`(초안 차례)이 검사 · 직전 다시 읽기를 마친 초안을 넘긴다 — 500줄 상한으로 나눴다(drafting_read 와 같은 꼴).
플랜 C3-1 · C3-3 · 설계서 4절 8 · 원장 R7-1 · R7-2 · R7-5 · R7-11.

- **저장만**: 초안 스위치가 ``store`` 이거나 운영 밖 시험 상담 허용 목록 밖이면 가린 초안만 기록한다(R1-4). 메모 바로
  전에 스위치를 DB 에서 다시 읽는다 — 바퀴 도중 꺼지면(사람 · 막는 장치) 그 뒤 차례는 메모 없이 저장만 한다.
- **메모**: '올리는 중'을 먼저 커밋 → 감싸개(루프의 읽기 도우미를 넘긴다 — 올린 뒤 다시 읽기도 TERM 을 본다, R7-11) → 결과를
  적는다. 감싸개를 부른 뒤로는 깃발과 상관없이 적는다(이미 일어난 일이다).

  - 닿았는지 모름 → '올리는 중' 그대로 + 이번 바퀴 멈춤. 보내기 실패 → ``failed``(보내기 실패 코드 — ``send_`` 앞말) + 멈춤.
    그 줄을 다시 집을 땐 두뇌를 다시 부르지 않고 저장된 초안을 다시 검사 · 다시 읽어 올린다(:mod:`.drafting`, R7-5).
  - 올렸는데 **공개로 확인** → 올림 기록과 같은 트랜잭션에서 초안 스위치를 ``off`` 로 쓰고 커밋 → 관리자 앱 안 알림
    (:data:`NOTIFY_MEMO_PUBLIC`) → 멈춤(R7-1). **비공개를 확인 못 함**(못 찾음 · 읽기 실패 · id 없음) → 스위치를 ``store`` →
    알림(:data:`NOTIFY_MEMO_UNVERIFIED`) → 멈춤(R7-2). 기록을 못 적어도(그사이 바뀜 · DB 오류) 스위치는 따로 바꾼다. 스위치의
    다른 칸은 그대로다. 다시 켜는 것은 사람이다.
  - **memo 로 켜기 전 할 일**: 스테이징에서 우리 봇 메모가 Open API 글 목록에 오는지 먼저 본다 — 안 오면 모든 메모가 '못 찾음'
    이라 첫 메모에서 '저장만'으로 돌아간다(그물이 비면 공개 확인 장치가 한 번도 켜지지 않기 때문이다).
- 알림은 감시 보고와 같은 길(:func:`.report.post_admin_notification` — ADMIN 역할 전원 · OS 푸시 없음). 글에는 상담 id ·
  데스크 주소 · 메모 id · 코드만 싣는다(손님 글 · 초안 없음).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, Sequence

from sqlalchemy.exc import SQLAlchemyError

from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.drafting_read import memo_text
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.memo import MEMO_BRAND, REASON_NOT_PRIVATE, SEND_PREFIX, memo_allowed
from foms.services.cs_agent.report import desk_link, post_admin_notification
from foms.services.cs_agent.turns import (
    DRAFT_MEMO, DRAFT_OFF, DRAFT_STORE, TurnStateError, draft_mode, mark_failed, mark_posted, mark_posting, mark_stored,
    set_draft_mode,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FAIL_SEND", "HALT_PUBLIC", "HALT_SEND_FAILED", "HALT_SEND_UNKNOWN", "HALT_UNVERIFIED", "NOTIFY_MEMO_PUBLIC",
    "NOTIFY_MEMO_UNVERIFIED", "SKIP_DRAFT_MASK_LEAK", "is_send_failure", "place",
]

#: 알림 유형(``notifications.notification_type``) — 감시 보고(``CS_MORNING_REPORT`` …)와 같은 ``CS_`` 줄기.
NOTIFY_MEMO_PUBLIC = "CS_MEMO_PUBLIC"
NOTIFY_MEMO_UNVERIFIED = "CS_MEMO_UNVERIFIED"
HALT_PUBLIC, HALT_UNVERIFIED = "memo_not_private", "memo_unverified"
HALT_SEND_UNKNOWN, HALT_SEND_FAILED = "memo_unknown", "memo_send_failed"
SKIP_DRAFT_MASK_LEAK = "draft_mask_leak"
#: 보내기 실패 코드 — 감싸개 이유가 ``send_`` 로 시작하지 않으면 이 코드(다시 집을 때 ``send_`` 앞말로 가른다).
FAIL_SEND, UNVERIFIED = SEND_PREFIX + "failed", "not_verified"
_ID = re.compile(r"[\x21-\x7e]{1,64}")  # 채널톡 id 꼴(차례 기록과 같다)
_ALERTS = {
    DRAFT_OFF: (NOTIFY_MEMO_PUBLIC, "AI 초안 메모가 손님에게 보였을 수 있다 — 초안을 껐다",
                "off — 메모 · 저장 모두 멈춤",
                "데스크에서 그 메모가 손님에게 보이는지 보고 지운다 · 까닭을 고친 뒤 사람이 다시 켠다"),
    DRAFT_STORE: (NOTIFY_MEMO_UNVERIFIED, "AI 초안 메모의 비공개를 확인 못 했다 — '저장만'으로 바꿨다",
                  "store — 메모 멈춤 · 저장만",
                  "데스크에서 그 메모가 비공개인지 본다 · 스테이징에서 봇 메모가 Open API 글 목록에 오는지 확인한 뒤 "
                  "사람이 memo 로 다시 켠다"),
}


def is_send_failure(error_code: Any) -> bool:
    """보내기 실패로 끝난 줄의 이유 코드인가(``send_`` 앞말) — 다시 집으면 두뇌 대신 저장된 초안을 다시 올린다."""
    return isinstance(error_code, str) and error_code.startswith(SEND_PREFIX)


def place(ctx: Any, row: Any, chat_id: str, *, draft: str, staff_note: str, masked: str,
          warnings: Sequence[str]) -> Optional[str]:
    """검사를 마친 초안을 놓는다 — 메모 스위치 · 허용된 상담이면 메모, 아니면 저장만. 이번 바퀴를 멈출 까닭(없으면 ``None``).

    ``ctx`` 는 초안 바퀴의 재료(세션 · 지금 · 깃발 · 감싸개 · 읽기 도우미 · 요약 · ``skip``)다. 메모 직전에 초안 스위치를
    DB 에서 다시 읽는다 — 바퀴 도중 꺼졌으면(사람 · 막는 장치, R7-1) 그 뒤로는 메모를 쓰지 않고 저장만 한다.
    """
    if ctx.mode == DRAFT_MEMO and draft_mode(ctx.session) == DRAFT_MEMO and memo_allowed(chat_id):
        return _post(ctx, row, chat_id, draft=draft, staff_note=staff_note, masked=masked, warnings=warnings)
    ctx.stop.check()  # 쓰기 전
    try:
        mark_stored(row, masked_draft=masked, check_codes=warnings, now=ctx.now)
    except MaskLeak as exc:
        logger.warning("[CS 초안] 가린 초안에 개인정보 꼴이 남아 건너뜀 chat=%s counts=%s", chat_id, exc.counts)
        return ctx.skip(row, SKIP_DRAFT_MASK_LEAK)
    ctx.session.commit()
    ctx.summary.stored += 1
    ctx.summary.not_allowed += int(ctx.mode == DRAFT_MEMO)
    return None


def _post(ctx: Any, row: Any, chat_id: str, *, draft: str, staff_note: str, masked: str,
          warnings: Sequence[str]) -> Optional[str]:
    """메모 — '올리는 중'을 먼저 커밋 → 감싸개 → 결과 적기(R1-3). 감싸개를 부른 뒤로는 깃발과 상관없이 결과를 적는다."""
    ctx.stop.check()  # 쓰기 전 — 깃발 뒤엔 올리기를 시작하지 않는다
    try:
        mark_posting(row, masked_draft=masked, check_codes=warnings, now=ctx.now)
    except MaskLeak as exc:
        logger.warning("[CS 초안] 가린 초안에 개인정보 꼴이 남아 건너뜀 chat=%s counts=%s", chat_id, exc.counts)
        return ctx.skip(row, SKIP_DRAFT_MASK_LEAK)
    ctx.session.commit()  # 채널톡을 부르기 전에 '올리는 중'을 커밋한다 — 죽어도 복구 단계가 찾는다
    sent = ctx.poster(chat_id, memo_text(draft, staff_note), brand=MEMO_BRAND, reader=ctx.reader)
    if sent.outcome_unknown:
        ctx.summary.unknown += 1
        logger.warning("[CS 초안] 메모가 닿았는지 모른다 — 올리는 중 그대로 · 이번 바퀴 멈춤 chat=%s", chat_id)
        return HALT_SEND_UNKNOWN
    if not sent.posted:
        code = sent.reason if is_send_failure(sent.reason) else FAIL_SEND
        mark_failed(row, error_code=code, now=ctx.now)
        ctx.session.commit()
        ctx.summary.failed += 1
        logger.warning("[CS 초안] 메모를 못 올렸다 — 이번 바퀴 멈춤 chat=%s reason=%s", chat_id, sent.reason)
        return HALT_SEND_FAILED
    message_id = sent.message_id if isinstance(sent.message_id, str) and _ID.fullmatch(sent.message_id) else None
    reason = None if sent.verified else (sent.reason or UNVERIFIED)
    guard = None if sent.verified else (DRAFT_OFF if sent.reason == REASON_NOT_PRIVATE else DRAFT_STORE)
    _record_posted(ctx, row, chat_id, message_id, reason, guard)
    ctx.summary.posted += 1
    if guard is None:
        return None
    ctx.summary.unverified += 1
    logger.error("[CS 초안] 메모를 올렸지만 비공개를 확인 못 했다 — 초안 스위치를 %s 로 chat=%s message=%s reason=%s",
                 guard, chat_id, message_id, reason)
    _alert(ctx, chat_id, message_id, guard, reason)
    return HALT_PUBLIC if guard == DRAFT_OFF else HALT_UNVERIFIED


def _record_posted(ctx: Any, row: Any, chat_id: str, message_id: Optional[str], reason: Optional[str],
                   guard: Optional[str]) -> None:
    """올림 기록과 막는 장치(초안 스위치)를 한 트랜잭션에 쓰고 커밋한다. 기록을 못 적으면(그사이 바뀜 · DB 오류) 막는 장치만
    따로 쓴다 — 공개로 보였을 수 있는 메모 뒤에 스위치가 켜진 채 남으면 안 된다."""
    try:
        mark_posted(row, memo_message_id=message_id, error_code=reason, now=ctx.now)
        if guard is not None:
            set_draft_mode(ctx.session, guard, reason=reason, now=ctx.now)
        ctx.session.commit()
        return
    except (TurnStateError, SQLAlchemyError):
        ctx.session.rollback()
        if guard is None:
            raise
    logger.error("[CS 초안] 올림 기록을 못 적었다 — 초안 스위치만 따로 바꾼다 chat=%s mode=%s", chat_id, guard)
    set_draft_mode(ctx.session, guard, reason=reason, now=ctx.now)
    ctx.session.commit()


def _alert(ctx: Any, chat_id: str, message_id: Optional[str], guard: str, reason: Optional[str]) -> None:
    """관리자 앱 안 알림 1건(감시 보고와 같은 길). 실패해도 스위치는 이미 바뀌었다 — 오류만 남긴다."""
    kind, title, switch_line, todo = _ALERTS[guard]
    message = "\n".join((f"[상담] {desk_link(MEMO_BRAND, chat_id)}", f"[메모 id] {message_id or '없음'}",
                         f"[까닭] {reason}", f"[초안 스위치] {switch_line}", f"[할 일] {todo}"))
    try:
        post_admin_notification(ctx.session, kind=kind, title=title, message=message, now=naive_utc(ctx.now))
        ctx.session.commit()
    except SQLAlchemyError:
        ctx.session.rollback()
        logger.error("[CS 초안] 관리자 알림을 못 남겼다 — 초안 스위치는 이미 바꿨다 chat=%s kind=%s", chat_id, kind)
