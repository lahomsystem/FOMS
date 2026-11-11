"""넘김 메모 — AI 가 초안을 안 쓰고 넘긴 차례(두뇌 넘김 · 보내기 전 검사 걸림)에 '직원이 직접 답해 주세요' 비공개 메모 한 번.

운영 7일(11-11 무렵) 두뇌 넘김 '모름' 약 98건 · 검사 걸림 약 91건이 건너뜀 기록으로만 남아, 직원은 AI 가 손을 뗀 줄 몰랐다.
관리 화면 '넘김 메모'(:mod:`.handoff_memo_settings`, 처음 끔)가 켜지고 초안 스위치가 '메모'일 때만 올린다 — 끄면 예전 그대로
기록만이다. 15분 바퀴와 빠른 길이 같은 차례 꼴(:meth:`.drafting_pass.DraftPass.hand_off`)로 부른다.

- **차례 기록은 그대로**: 먼저 예전처럼 건너뜀(``skipped`` · 넘김 · 검사 코드 · 가린 초안)을 커밋한 **뒤에** 올린다. 건너뛴 줄은
  다시 집지 않으므로 차례 하나에 메모는 많아야 하나다(다시 집기 · 다시 시도 · 죽었다 살아나도 또 올리지 않는다). 올린 메모 id 는
  같은 줄에 한 번만 적는다(:func:`.turns.record_note_memo`). 초안 지표(초안 뜸 · 보냄)와 [보내기] · [수정하기] 화면은 올림
  (``posted``) 줄만 보므로 그대로다. 'AI 냐 사람이냐' 한 줄 메모(:mod:`.ask_human`)는 두뇌를 부르지 않은 넘김이라 예전 길이다.
- **올리기 전 다시 읽기**: 그 상담 글을 다시 읽어 선점한 손님 글이 아직 마지막이고 그 뒤 공개 직원 답이 없을 때만 올린다(직원이
  이미 답했거나 손님이 더 썼으면 안 올림 — 다음 차례가 맡는다). 같은 미답 묶음의 마지막 AI 메모가 같은 까닭의 넘김 메모면
  또 올리지 않는다(직원은 이미 안다 — 'AI 냐' 한 줄 메모와 같은 생각).
- **글**: 첫 줄 :data:`.drafting_read.HANDOFF_MEMO_HEAD` · ``까닭:`` 한 줄(코드를 쉬운 말로 — 코드 글자는 싣지 않는다) · 두뇌가
  남긴 직원 참고가 있으면 초안 메모와 같은 '직원 참고' 칸(한 번 가려서). 손님께 보낼 답(검사에 걸린 초안 포함)은 싣지 않는다.
- **메모 길은 하나**: 바퀴가 넘긴 메모 감싸개(:func:`.memo.post_private_memo`) 그대로. 단추는 관리 화면 '[배우기] · [흘리기]
  단추'가 켜지고 초안 [보내기] 단추가 '채널톡 안 작은 창'일 때만 단다(:func:`.send.handoff_buttons` — 누르면
  :mod:`.handoff_send`; [수정하기] 화면 · 초안 보내기 길은 건너뛴 줄을 열지 않는다). 단추 꼴이 틀려 메모를 못 올리면 단추 없이
  한 번 더 올린다. 비공개를 확인 못 하면 초안 메모와 같은 막는 장치(:func:`.drafting_post.guard_side_memo` — 스위치 끔 · 저장만
  + 관리자 알림 + 바퀴 멈춤).
- **실패해도 바퀴는 그대로**: 읽기 실패 · 올리기 실패 · 닿았는지 모름 · 예상 밖 오류는 상담 id · 코드만 남기고 넘어간다(다시
  올리지 않는다). TERM 은 삼키지 않는다. 글(손님 글 · 직원 참고)은 로그 · 예외 · 요약에 싣지 않는다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from sqlalchemy.exc import SQLAlchemyError

from foms.services.cs_agent.drafting_post import guard_side_memo, memo_on
from foms.services.cs_agent.drafting_read import (
    HANDOFF_MEMO_HEAD, MEMO_HEAD, MEMO_NOTE_HEAD, ChatLine, freshness, read_lines,
)
from foms.services.cs_agent.handoff_memo_settings import handoff_buttons_on, handoff_memo_on
from foms.services.cs_agent.masking import mask
from foms.services.cs_agent.memo import MEMO_BRAND, REASON_BAD_BUTTONS, memo_allowed
from foms.services.cs_agent.send import handoff_buttons
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.turns import STATE_SKIPPED, TurnStateError, record_note_memo
from foms.services.cs_agent.turns_fields import ID_PATTERN

logger = logging.getLogger(__name__)

__all__ = [
    "CHECK_EMPTY", "CHECK_UNKNOWN", "CHECK_WORDS", "CODE_CHECK", "CODE_HANDOFF", "HANDOFF_TEXTS", "HANDOFF_UNKNOWN",
    "MEMO_CODES", "REASON_LABEL", "memo_body", "post_handoff_memo", "reason_text",
]

#: 메모를 남기는 건너뜀 코드 — :data:`.drafting.SKIP_HANDOFF` · :data:`.drafting.SKIP_CHECK` 와 같다(drafting 이 이 모듈을 부를
#: 쪽이라 거꾸로 import 하지 않는다 · 시험이 맞춘다). 나머지 건너뜀(이메일 · 사진만 · 가림 · 그사이 새 글 · 거절 …)은 메모 없음.
CODE_HANDOFF, CODE_CHECK = "handoff", "check_failed"
MEMO_CODES: tuple[str, ...] = (CODE_HANDOFF, CODE_CHECK)
REASON_LABEL = "까닭: "

#: 두뇌가 고른 넘김 까닭(:data:`.brain_prompt.HANDOFF_REASONS`) → 쉬운 말 한 문장.
HANDOFF_TEXTS: dict[str, str] = {
    "unsure": "회사 지식에 없는 내용이에요",
    "human_only_amount": "사람이 정하는 금액을 묻는 상담이에요",
    "discount_refund": "할인 · 환불 상담이라 사람이 답해야 해요",
    "schedule": "일정을 정하는 상담이라 사람이 답해야 해요",
    "complaint": "불만 상담이라 사람이 답해야 해요",
    "order_lookup": "주문 내역을 찾아봐야 답할 수 있어요",
    "photo": "사진을 봐야 답할 수 있어요",
    "asked_if_ai": "손님이 상대가 사람인지 AI 인지 물었어요",
    "other": "AI 가 답하기 어려운 상담이에요",
}
HANDOFF_UNKNOWN = "AI 가 답하기 어려운 상담이라 넘겼어요"
#: 보내기 전 검사의 막는 코드(:data:`.checks.REASONS` — 말투 경고는 막지 않아 뺀다) → 초안에 있던 것(이름 꼴). 여럿이면
#: 겹침 없이 ' · ' 로 잇고 끝에 '이 · 가 있어 막았어요'를 한 번만 붙인다.
CHECK_WORDS: dict[str, str] = {
    "other_brand": "다른 브랜드 이름",
    "account_number": "안내 계좌가 아닌 계좌 번호",
    "phone_number": "승인 안 된 전화번호",
    "discount_promise": "할인 약속처럼 보이는 말",
    "refund_promise": "환불 약속처럼 보이는 말",
    "date_promise": "날짜를 확답하는 말",
    "contact_time_promise": "연락 시간 약속처럼 보이는 말",
    "internal_words": "회사 안에서만 쓰는 말",
    "ai_mention": "AI 라고 밝히는 말",
    "human_claim": "사람이라고 하는 말",
    "mask_marker": "가린 표시",
    "link_not_allowed": "허용 안 된 링크",
    "number_not_allowed": "승인 안 된 숫자",
    "date_not_confirmed": "확정 안 된 날짜",
    "human_only_amount": "사람이 정하는 금액",
    "private_memo_leak": "내부 메모에 있던 문장",
    "example_only_word": "지난 사례에만 있는 낱말",
    "talktalk_outside": "톡톡 밖으로 옮기자는 말",
    "talktalk_link": "톡톡에서 못 쓰는 바깥 링크",
    "talktalk_phone_ask": "톡톡에서 손님 번호를 묻는 말",
}
CHECK_EMPTY = "초안이 비어 있었어요"  # 'empty' — 다른 코드와 같이 와도 이 말 하나
CHECK_UNKNOWN = "초안이 보내기 전 검사에 걸려 막았어요"


# ── 글 ───────────────────────────────────────────────────────────────────
def _subject(word: str) -> str:
    """이름 꼴 뒤 토씨 — 마지막 글자에 받침이 있으면 '이', 없으면 '가'."""
    last = word[-1]
    return "이" if "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 else "가"


def reason_text(code: str, *, handoff_reason: Any = None, check_codes: Sequence[Any] = ()) -> str:
    """``까닭:`` 뒤 한 문장 — 검사 걸림은 막은 것들, 두뇌 넘김은 까닭 코드의 쉬운 말(모르는 코드는 두루 쓰는 말)."""
    if code == CODE_CHECK:
        names = [getattr(item, "code", item) for item in check_codes]
        if "empty" in names:
            return CHECK_EMPTY
        words = list(dict.fromkeys(CHECK_WORDS[name] for name in names if name in CHECK_WORDS))
        if not words:
            return CHECK_UNKNOWN
        return f"초안에 {' · '.join(words)}{_subject(words[-1])} 있어 막았어요"
    return HANDOFF_TEXTS.get(handoff_reason, HANDOFF_UNKNOWN) if isinstance(handoff_reason, str) else HANDOFF_UNKNOWN


def memo_body(code: str, *, handoff_reason: Any = None, check_codes: Sequence[Any] = (), staff_note: Any = "") -> str:
    """넘김 메모 글 — 첫 줄 표지 · 까닭 한 줄 · (직원 참고가 있으면) 초안 메모와 같은 '직원 참고' 칸(한 번 가려서)."""
    note = mask(staff_note).strip() if isinstance(staff_note, str) and staff_note.strip() else ""
    reason = reason_text(code, handoff_reason=handoff_reason, check_codes=check_codes)
    lines = [HANDOFF_MEMO_HEAD, REASON_LABEL + reason]
    return "\n".join([*lines, MEMO_NOTE_HEAD, note] if note else lines)


def _head(text: str) -> list[str]:
    """메모의 첫 두 줄(표지 · 까닭) — 같은 넘김 메모인지 견준다(직원 참고는 차례마다 달라 보지 않는다)."""
    return [part.strip() for part in text.strip().splitlines()[:2]]


def _repeated(lines: Sequence[ChatLine], text: str) -> bool:
    """같은 미답 묶음(마지막 공개 직원 글 뒤)의 마지막 AI 메모가 같은 까닭의 넘김 메모인가."""
    after = max((i for i, line in enumerate(lines) if line.meta.is_answer), default=-1)
    ours = [line.text for line in lines[after + 1:]
            if line.meta.is_private and line.text.lstrip().startswith((MEMO_HEAD, HANDOFF_MEMO_HEAD))]
    return bool(ours) and _head(ours[-1]) == _head(text)


# ── 올리기 ───────────────────────────────────────────────────────────────
def post_handoff_memo(ctx: Any, row: Any, code: str, *, codes: Sequence[Any] = (), note: Any = "") -> Optional[str]:
    """건너뛴 차례에 넘김 메모 한 번(모듈 설명). 이번 바퀴를 멈출 까닭 — 막는 장치가 섰을 때만, 나머지는 ``None``.

    ``ctx`` 는 초안 바퀴의 재료(:class:`.drafting_pass.DraftPass` — 세션 · 지금 · 깃발 · 감싸개 · 읽기 도우미 · 요약 · 스위치),
    ``row`` 는 방금 건너뜀으로 커밋한 차례 줄, ``codes`` 는 검사 문제(코드 글자 또는 ``code`` 속성), ``note`` 는 두뇌의 직원 참고.
    """
    if code not in MEMO_CODES or ctx.stop.is_set():
        return None
    chat_id, sent = _send(ctx, row, code, codes, note)
    if sent is None:
        return None
    if sent.outcome_unknown or not sent.posted:
        logger.warning("[CS 넘김 메모] 못 올렸다 — 다시 올리지 않는다 chat=%s code=%s reason=%s", chat_id, code, sent.reason)
        return None
    halt = guard_side_memo(ctx, chat_id, sent)  # 비공개를 확인 못 했으면 스위치부터(초안 메모와 같은 규칙 — R7-1 · R7-2)
    _remember(ctx, row, chat_id, sent.message_id)
    ctx.summary.handoff_memos += 1
    logger.info("[CS 넘김 메모] 올렸다 chat=%s code=%s", chat_id, code)
    return halt


def _send(ctx: Any, row: Any, code: str, codes: Sequence[Any], note: Any) -> tuple[Optional[str], Optional[Any]]:
    """줄 상태 · 스위치 · 허용 상담 · 다시 읽기 · 같은 메모 확인 뒤 메모 감싸개를 부른다 — (상담 id, 감싸개 결과 | 안 불렀으면
    ``None``). 건너뜀으로 끝난 줄이고 메모 id 가 아직 없을 때만 부른다.

    예상 밖 오류는 코드만 남기고 결과 ``None``(바퀴는 그대로 — 그 차례는 이미 건너뜀으로 끝났다). TERM 은 그대로 올린다.
    """
    chat_id: Optional[str] = None
    try:
        chat_id, claimed_id = row.chat_id, row.last_user_message_id
        if row.state != STATE_SKIPPED or row.memo_message_id or not (
                handoff_memo_on(read_settings(ctx.session, log=False)) and memo_on(ctx) and memo_allowed(chat_id)):
            ctx.session.commit()
            return chat_id, None
        text = memo_body(code, handoff_reason=row.handoff_reason, check_codes=codes, staff_note=note)
        ctx.session.commit()  # 읽기 트랜잭션을 닫는다 — 채널톡을 부르는 동안 열어 두지 않는다
        lines = read_lines(ctx.reader, MEMO_BRAND, chat_id)
        if freshness(lines, claimed_id) or _repeated(lines, text):
            return chat_id, None
        ctx.stop.check()  # 쓰기 전
        buttons = _buttons(ctx, row, chat_id)
        if not buttons:
            return chat_id, ctx.poster(chat_id, text, brand=MEMO_BRAND, reader=ctx.reader)
        sent = ctx.poster(chat_id, text, brand=MEMO_BRAND, reader=ctx.reader, buttons=buttons)
        if sent.reason != REASON_BAD_BUTTONS:
            return chat_id, sent
        logger.warning("[CS 넘김 메모] 단추 꼴이 틀려 단추 없이 다시 올린다 chat=%s", chat_id)
        return chat_id, ctx.poster(chat_id, text, brand=MEMO_BRAND, reader=ctx.reader)
    except Exception as exc:  # 넘김 메모는 덤이다 — 어떤 실패도 초안 바퀴를 멈추지 않는다(TERM 만 올린다)
        ctx.session.rollback()
        if ctx.stop.is_set():
            raise
        logger.warning("[CS 넘김 메모] 못 올렸다 — 차례는 건너뜀 그대로 chat=%s code=%s err=%s", chat_id, code,
                       type(exc).__name__)
        return chat_id, None


def _buttons(ctx: Any, row: Any, chat_id: str) -> tuple[Any, ...]:
    """[배우기] · [흘리기] 단추 — 관리 화면 단추 칸 · '[보내기] 버튼' 켬 · 여는 곳 '채널톡 안 작은 창'일 때만(아니면 빈 값)."""
    cfg = read_settings(ctx.session, log=False)
    ctx.session.commit()  # 읽기 트랜잭션을 닫는다 — 채널톡을 부르는 동안 열어 두지 않는다
    if not (handoff_buttons_on(cfg) and cfg.get("send_buttons_enabled")):
        return ()
    return handoff_buttons(row.id, chat_id, path=cfg.get("send_button_path"))


def _remember(ctx: Any, row: Any, chat_id: str, message_id: Any) -> None:
    """올린 메모 id 를 그 줄에 한 번 적는다 — 못 적어도(id 없음 · 그사이 바뀜 · DB 오류) 메모는 이미 올라갔다(기록만 빠진다)."""
    if not isinstance(message_id, str) or not ID_PATTERN.fullmatch(message_id):
        return
    try:
        record_note_memo(row, memo_message_id=message_id, now=ctx.now)
        ctx.session.commit()
    except (TurnStateError, SQLAlchemyError) as exc:
        ctx.session.rollback()
        logger.warning("[CS 넘김 메모] 메모 id 를 못 적었다 — 메모는 올라갔다 chat=%s err=%s", chat_id, type(exc).__name__)
