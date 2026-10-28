"""초안 차례 — 감시 루프 바퀴 끝에서 라홈 '답 필요' 상담에 AI 초안을 쓴다(초안 스위치: 저장만 · 내부 메모).

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C3-1 · 설계서 4절(한 상담 글이 지나가는 길 — 순서 고정) · 6절 · 15.2 의 8.
원장 §3 20 · 21행이 넘긴 일도 여기서 한다. 부품은 이미 있고 이 모듈은 잇기만 한다 — 두뇌 :func:`.brain.draft_reply` ·
메모 :func:`.memo.post_private_memo` · 차례 기록 :mod:`.turns` · 검사 :func:`.checks.check_draft` · 지식
:func:`.knowledge.load_approved` · 재료 읽기 :mod:`.drafting_read`. :func:`run_drafting` 한 바퀴(순서를 바꾸지 않는다):

0. **정리 · 준비** — 두뇌를 부르다 죽어 ``claimed`` 로 :data:`STALE_CLAIM_AFTER` 넘게 남은 줄은 ``failed``(시도 상한까지 다시
   집음). 오래 남은 ``posting`` 은 세기만 한다(올라갔는지 모른다 — 다시 올리지 않고 우리 봇 메모와 맞추는 복구 단계에 맡긴다).
   오늘(KST) 돈 상한으로 실패한 줄이 있으면 그날은 두뇌를 더 부르지 않는다. 라홈 Open API 키 · 승인 지식이 없어도 멈춘다.
1. **고르기** — 루프가 낸 열린 상담 상태에서 라홈 · 답 필요 · 맺음 글뿐 아님 · 마지막 손님 글 뒤 공개 직원 글 없음(우선순위 순).
   운영 시간 안 · 밖 모두 — 양은 스위치와 상한이 정한다. 하우드는 고르지 않는다.
2. **선점** — (상담, 마지막 손님 글 id) 줄을 :func:`.turns.claim_turn` 으로 잡고 바로 커밋한다. 이미 있으면 건너뛴다.
3. **읽기** — 매체(이메일이면 건너뜀 — 첫 판) · 최근 글. 선점한 손님 글이 아직 마지막 손님 글이고 그 뒤 공개 직원 글이 없어야
   한다. 재료는 공개 손님 · 직원 글만(R1-12). 손님 글에 글자가 없으면(사진만) 건너뜀.
4. **두뇌** — ``purpose="draft"`` · 라홈 운영 시간이면 ``daytime`` · 15분 루프라 ``realtime=False``. 두뇌는 세션을 두 번
   커밋한다(원장 21행) — 우리 쓰기(선점)는 그 전에 커밋해 둔다.
5. **검사** — :func:`.checks.check_draft`(브랜드 · 매체를 늘 넘긴다 · 허용 목록은 승인 지식 글만 — 손님 글의 금액도, [사람]
   항목 글도 넣지 않는다). 걸리면 코드만 남기고 올리지 않는다.
6. **직전 다시 읽기** — 그사이 손님이 더 썼거나(``stale``) 공개 직원 글이 왔으면(``human_replied``) 올리지 않는다.
7. **올리기** — ``store`` 면 가린 초안만 기록. ``memo`` 면 '올리는 중'을 먼저 커밋 → 메모 → '올림'(R1-3). 운영 밖 시험 상담
   허용 목록 밖 상담은 저장만(R1-4). 닿았는지 모르면 '올리는 중' 그대로 둔다 — 실패로 바꾸면 다시 집어 메모가 둘이 될 수 있다.

오류: 준비 안 됨(:class:`.brain.BrainNotReady` — 설정 문제라 다음 상담도 같다)은 건너뜀(코드) + 이번 바퀴 멈춤 · 가림
검사(:class:`.masking.MaskLeak`)는 그 상담만 건너뜀(로그엔 칸별 숫자만) · 돈 상한은 실패(다음 날 다시 집음) + 그날 멈춤 ·
두뇌 못 씀은 실패(다시 집음 — 답 꼴만 틀렸으면 다음 상담으로, 그 밖엔 이번 바퀴 멈춤) · 읽기 실패 · 한도도 실패 + 멈춤.
올렸는데 비공개를 확인 못 하면 '올림' 그대로 + ERROR(공개로 확인되면 이번 바퀴 멈춤).

**넘김 · 거절은 메모 없이 기록만**(``skipped`` — 브리프 결정, 더 안전한 쪽): AI 가 답하면 안 된다고 본 상담(불만 · 환불 ·
할인 · 일정)이라 채널톡 쓰기 0 이 가장 안전하다 · 직원 참고 칸은 보내기 전 검사를 거치지 않는 모델 글이다 · 거절은 참고 칸도
없다 · 그 상담은 이미 아침 보고 '답 필요'에 있다. 넘김 까닭 코드는 기록 줄에 남는다(판정 표 재료).

TERM: 선점 전 · 두뇌 전 · 쓰기 전마다 깃발을 보고, 서 있으면 지금 줄을 ``failed`` 로 돌려놓고 멈춘다(LLM 답은 버린다 — R4-4).
메모 감싸개를 부른 뒤에는 깃발과 상관없이 결과를 적는다(이미 일어난 일이다). 글(손님 글 · 초안 · 직원 참고)은 로그 · 요약 ·
예외에 싣지 않는다 — 요약은 숫자만, 로그는 상담 id · 코드 · 숫자만. 손님 프로필 이름 · 직원 이름은 지금 읽기 도우미가 주지
않아 가림에 넘기지 않는다(빈 목록 — 이름꼴 가림 · 검사는 그대로 돈다).
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from foms.persistence.main.models import CsAgentChat, CsAgentTurn
from foms.services.channel_client import _open_api_headers
from foms.services.common.business_calendar import is_business_day as calendar_is_business_day
from foms.services.cs_agent.brain import (
    API_SPEND_LIMIT, BAD_RESPONSE, DAILY_CAP_REACHED, BrainNotReady, BrainUnavailable, DraftRequest, DraftResult,
    SpendCapReached, draft_reply,
)
from foms.services.cs_agent.brain_prompt import PURPOSE_DRAFT
from foms.services.cs_agent.channel_read import ChannelRateLimited, ChannelReadError, naive_utc
from foms.services.cs_agent.checks import check_draft
from foms.services.cs_agent.drafting_read import (
    MEDIUM_EMAIL, ChatLine, conversation, freshness, memo_snippets, memo_text, no_text_reason, read_lines, read_medium,
)
from foms.services.cs_agent.knowledge import ApprovedKnowledge, load_approved
from foms.services.cs_agent.masking import MaskLeak, mask
from foms.services.cs_agent.memo import REASON_NOT_PRIVATE, MemoResult, memo_allowed, post_private_memo
from foms.services.cs_agent.state import BRAND_HOURS, KST, BusinessDayFn, ChatState, sort_by_priority
from foms.services.cs_agent.turns import (
    DRAFT_MEMO, DRAFT_STORE, STATE_CLAIMED, STATE_FAILED, claim_turn, mark_failed, mark_posted, mark_posting,
    mark_skipped, mark_stored, record_brain_result, stale_posting,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BRAND", "DRAFT_BUDGET_SECONDS", "MAX_BRAIN_CALLS", "STALE_CLAIM_AFTER", "STALE_POSTING_AFTER", "DraftSummary",
    "run_drafting",
]

BRAND = "LAHOM"  # 초안을 쓰는 브랜드 — 하우드는 쓰기 허락 전이라 고르지 않는다(설계서 6절 단계 1)
#: 한 바퀴 두뇌 호출 상한. 시간 상한(초)은 선점 전에 본다 — 두뇌 한 번이 90초 · 한 번 더까지 걸릴 수 있다(11.1 의 5).
MAX_BRAIN_CALLS = 10
DRAFT_BUDGET_SECONDS = 240.0
#: 이보다 오래 ``claimed`` 인 줄은 두뇌를 부르다 죽은 차례다(대표 잠금이 바퀴를 하나만 돌리고 바퀴는 이보다 짧다).
STALE_CLAIM_AFTER = datetime.timedelta(minutes=20)
#: 이보다 오래 ``posting`` 인 줄을 센다(올라갔는지 모름 — 복구 단계 몫, 다시 올리지 않는다).
STALE_POSTING_AFTER = datetime.timedelta(minutes=20)
HUMAN_ONLY_MARK = "[사람]"  # 승인 지식에서 사람만 말하는 항목 표시 — 그 글의 숫자는 허용 목록에 넣지 않는다
_ID = re.compile(r"[\x21-\x7e]{1,64}")  # 채널톡 id 꼴(차례 기록과 같다)
_SPEND_CODES = (DAILY_CAP_REACHED, API_SPEND_LIMIT)
_CHAT_CHUNK = 500

# 건너뜀 · 실패 · 멈춤 코드(기록 줄 ``error_code`` · 요약 칸 — 글이 아니다). 읽기 쪽 건너뜀은 :mod:`.drafting_read`.
SKIP_EMAIL, SKIP_BAD_REQUEST = "email", "bad_request"
SKIP_MASK_LEAK, SKIP_DRAFT_MASK_LEAK = "mask_leak", "draft_mask_leak"
SKIP_HANDOFF, SKIP_REFUSED, SKIP_CHECK = "handoff", "refused", "check_failed"
FAIL_STALE_CLAIM, FAIL_STOPPED, FAIL_ERROR = "claim_expired", "stopped", "error"
FAIL_READ, FAIL_RATE_LIMITED, FAIL_SEND, UNVERIFIED = "read_failed", "rate_limited", "send_failed", "not_verified"
HALT_NOT_CONFIGURED, HALT_NO_KNOWLEDGE, HALT_SPEND = "not_configured", "no_knowledge", "spend_cap"
HALT_NOT_READY, HALT_BRAIN, HALT_PUBLIC = "not_ready", "brain_unavailable", "memo_not_private"
HALT_CALLS, HALT_TIME = "call_cap", "time_budget"


@dataclass
class DraftSummary:
    """한 바퀴 초안 결과 — 숫자만(상담 id · 글 없음). :meth:`counts` 가 바퀴 요약 JSON 의 ``drafting`` 칸이다."""

    candidates: int = 0  # 고른 상담
    claimed: int = 0  # 이번에 선점한 차례(실패 줄 다시 집음 포함)
    already: int = 0  # 차례가 이미 있어 건너뜀(손님 글 하나에 초안 하나)
    brain_calls: int = 0
    stored: int = 0
    posted: int = 0
    unverified: int = 0  # 올렸지만 비공개를 확인 못 함(ERROR 로그)
    unknown: int = 0  # 닿았는지 모름 — '올리는 중' 그대로
    not_allowed: int = 0  # 메모 스위치지만 운영 밖 시험 상담 허용 목록 밖이라 저장만
    failed: int = 0
    recovered: int = 0  # 오래 남은 선점 → 실패(다시 집음)
    stale_posting: int = 0  # 오래 남은 '올리는 중'(복구 단계 몫)
    skipped: dict[str, int] = field(default_factory=dict)  # 건너뜀 코드 → 수
    halted: dict[str, int] = field(default_factory=dict)  # 이번 바퀴를 멈춘 까닭(하나)

    def counts(self) -> dict[str, Any]:
        """JSON 한 덩어리 — 숫자와 코드 이름 → 숫자만."""
        return dataclasses.asdict(self)


# ── 고르기 · 정리 ────────────────────────────────────────────────────────
def _candidates(session: Any, states: Sequence[ChatState]) -> list[tuple[str, str]]:
    """고르기 — (상담 id, 마지막 손님 글 id), 우선순위 순(아침 보고와 같다). 마지막 손님 글 뒤 공개 직원 글이 있으면 뺀다."""
    picked = [s.chat_id for s in sort_by_priority(states) if s.brand == BRAND and s.needs_reply and not s.closing_only]
    rows: dict[str, Any] = {}
    for start in range(0, len(picked), _CHAT_CHUNK):
        stmt = select(CsAgentChat.chat_id, CsAgentChat.last_user_message_id, CsAgentChat.last_user_at,
                      CsAgentChat.last_answer_at).where(CsAgentChat.chat_id.in_(picked[start:start + _CHAT_CHUNK]))
        rows.update({row.chat_id: row for row in session.execute(stmt)})
    out: list[tuple[str, str]] = []
    for chat_id in picked:
        row = rows.get(chat_id)
        if row is None or not row.last_user_message_id or row.last_user_at is None:
            continue
        if row.last_answer_at is not None and row.last_answer_at >= row.last_user_at:
            continue
        out.append((chat_id, row.last_user_message_id))
    return out


def _recover(session: Any, now: datetime.datetime, stop: Any, summary: DraftSummary) -> None:
    """오래 남은 선점 줄은 실패로(다시 집음), 오래 남은 '올리는 중'은 세기만 한다(원장 20행 — 다시 올리지 않는다)."""
    stmt = (select(CsAgentTurn)
            .where(CsAgentTurn.state == STATE_CLAIMED, CsAgentTurn.updated_at < naive_utc(now - STALE_CLAIM_AFTER))
            .order_by(CsAgentTurn.updated_at, CsAgentTurn.id).limit(100)
            .execution_options(populate_existing=True))
    for row in list(session.scalars(stmt)):
        stop.check()  # 쓰기 전
        mark_failed(row, error_code=FAIL_STALE_CLAIM, now=now)
        summary.recovered += 1
    session.commit()
    summary.stale_posting = len(stale_posting(session, now - STALE_POSTING_AFTER))
    session.commit()
    if summary.recovered or summary.stale_posting:
        logger.warning("[CS 초안] 오래 남은 차례 — 선점 %d건은 실패로(다시 집음) · 올리는 중 %d건은 복구 단계 몫(다시 올리지 않음)",
                       summary.recovered, summary.stale_posting)


def _spend_stopped_today(session: Any, now: datetime.datetime) -> bool:
    """오늘(KST) 돈 상한으로 실패한 줄이 있나 — 있으면 그날은 두뇌를 더 부르지 않는다. 다음 날 그 줄을 다시 집는다(원장 21행)."""
    day = now.date()
    start = naive_utc(datetime.datetime(day.year, day.month, day.day, tzinfo=KST))
    stmt = select(CsAgentTurn.id).where(CsAgentTurn.state == STATE_FAILED, CsAgentTurn.error_code.in_(_SPEND_CODES),
                                        CsAgentTurn.updated_at >= start).limit(1)
    return session.scalar(stmt) is not None


def _daytime(now: datetime.datetime, cal: BusinessDayFn) -> bool:
    """라홈 운영 시간(평일 · 공휴일 쉼)인가 — 두뇌의 1시간 캐시 표시에 쓴다."""
    open_hour, close_hour = BRAND_HOURS[BRAND]
    return bool(cal(now.date())) and open_hour <= now.hour < close_hour


# ── 한 바퀴 ──────────────────────────────────────────────────────────────
class _Pass:
    """한 바퀴의 재료와 쓰기 도우미 — 쓰기 전마다 TERM 깃발을 본다."""

    def __init__(self, session: Any, *, reader: Any, now: datetime.datetime, stop: Any, mode: str,
                 brain: Callable[..., DraftResult], poster: Callable[..., MemoResult], knowledge: ApprovedKnowledge,
                 daytime: bool, summary: DraftSummary) -> None:
        """재료를 담는다. 허용 목록은 승인 지식 글만 — [사람] 항목 글 · 손님 글 금액은 넣지 않는다(손님 예산에 맞춰 주게 된다)."""
        self.session, self.reader, self.now, self.stop, self.mode = session, reader, now, stop, mode
        self.brain, self.poster, self.knowledge, self.daytime, self.summary = brain, poster, knowledge, daytime, summary
        self.allowed = tuple(item.text for item in knowledge.items if HUMAN_ONLY_MARK not in item.text)
        self.human_only = frozenset(item.item_id for item in knowledge.items if HUMAN_ONLY_MARK in item.text)

    def skip(self, row: CsAgentTurn, code: str, *, codes: Sequence[Any] = (), masked: Optional[str] = None,
             halt: Optional[str] = None) -> Optional[str]:
        """건너뜀으로 적고 커밋(가린 초안이 가림 검사에 걸리면 초안 없이). 이번 바퀴를 멈출 까닭(``halt``)을 돌려준다."""
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
        """실패로 적고 커밋(시도 상한 전이면 다음 바퀴가 다시 집는다). 이번 바퀴를 멈출 까닭을 돌려준다."""
        self.stop.check()  # 쓰기 전
        chat_id = row.chat_id
        retry = mark_failed(row, error_code=code, now=self.now)
        self.session.commit()
        self.summary.failed += 1
        logger.warning("[CS 초안] 실패 chat=%s code=%s retry=%s", chat_id, code, retry)
        return halt


def _halted(session: Any, summary: DraftSummary, code: str) -> DraftSummary:
    """선점 전에 멈춘다(읽기 트랜잭션을 닫는다)."""
    session.commit()
    summary.halted[code] = 1
    logger.warning("[CS 초안] 이번 바퀴 초안을 쓰지 않는다 code=%s", code)
    return summary


def run_drafting(session: Any, *, states: Sequence[ChatState], reader: Any, now: datetime.datetime, stop: Any,
                 mode: str, is_business_day: Optional[BusinessDayFn] = None,
                 brain: Callable[..., DraftResult] = draft_reply,
                 poster: Callable[..., MemoResult] = post_private_memo, limit: int = MAX_BRAIN_CALLS,
                 clock: Callable[[], float] = time.monotonic, budget_seconds: float = DRAFT_BUDGET_SECONDS,
                 summary: Optional[DraftSummary] = None) -> DraftSummary:
    """초안 한 바퀴(모듈 설명의 순서). 감시 루프가 상태 · 보고 뒤에 부른다 — 스위치가 ``store`` · ``memo`` 가 아니면 일 0.

    Args:
        session: DB 세션(이 함수 · 두뇌가 커밋한다).
        states: 감시 루프가 낸 열린 상담 상태.
        reader: 채널톡 Open API 읽기 도우미(:class:`~.channel_read.OpenApiReader` — 루프가 쓰는 것, 기다림이 깃발을 본다).
        now: 지금(시간대 있는 값).
        stop: 감시 루프 멈춤 깃발(``check`` · ``is_set``).
        mode: 초안 스위치 값(:func:`.turns.draft_mode`).
        is_business_day: 운영일 판정(시험 주입).
        brain: 두뇌(시험은 가짜). poster: 메모 감싸개(시험은 가짜 — 기본은 올린 뒤 자기 읽기 도우미로 다시 읽는다).
        limit: 한 바퀴 두뇌 호출 상한. clock · budget_seconds: 시간 상한(선점 전에 본다).
        summary: 채울 결과(루프는 멈춰도 센 수가 남게 미리 만들어 넘긴다).

    Returns:
        :class:`DraftSummary`.

    Raises:
        PassStopped: TERM 깃발(그때 선점한 줄은 ``failed`` 로 돌려놓았다).
        SQLAlchemyError: DB 오류 — 감시 루프 · 러너가 기록하고 다음 바퀴로 간다.
        ValueError: 시간대 없는 ``now``(UTC · KST 가 섞이면 조용히 틀린다).
    """
    summary = summary if summary is not None else DraftSummary()
    if mode not in (DRAFT_STORE, DRAFT_MEMO):
        return summary
    if now.tzinfo is None:
        raise ValueError("시간대가 없는 시각은 받지 않는다")
    now = now.astimezone(KST)
    deadline = clock() + budget_seconds
    stop.check()
    _recover(session, now, stop, summary)
    if _spend_stopped_today(session, now):
        return _halted(session, summary, HALT_SPEND)
    if _open_api_headers(BRAND) is None:
        return _halted(session, summary, HALT_NOT_CONFIGURED)
    knowledge = load_approved(session, BRAND)
    if knowledge.problem or not knowledge.items:
        return _halted(session, summary, HALT_NO_KNOWLEDGE)
    candidates = _candidates(session, states)
    session.commit()  # 읽기 트랜잭션을 닫는다 — 채널톡 · 두뇌를 부르는 동안 열어 두지 않는다
    summary.candidates = len(candidates)
    ctx = _Pass(session, reader=reader, now=now, stop=stop, mode=mode, brain=brain, poster=poster,
                knowledge=knowledge, daytime=_daytime(now, is_business_day or calendar_is_business_day),
                summary=summary)
    for chat_id, message_id in candidates:
        if summary.brain_calls >= limit or clock() >= deadline:
            summary.halted[HALT_CALLS if summary.brain_calls >= limit else HALT_TIME] = 1
            break
        stop.check()  # 선점 전
        try:
            row = claim_turn(session, BRAND, chat_id, message_id, now=now)
        except ValueError:
            session.rollback()
            logger.warning("[CS 초안] 상담 · 글 id 꼴이 아니라 고르지 않는다 chat=%s", chat_id)
            continue
        session.commit()  # 선점을 먼저 커밋 — 두뇌가 세션을 커밋하기 전에 우리 쓰기를 끝낸다(원장 21행)
        if row is None:
            summary.already += 1
            continue
        summary.claimed += 1
        halt = _guarded_turn(ctx, row, chat_id, message_id)
        if halt:
            summary.halted[halt] = 1
            break
    return summary


def _guarded_turn(ctx: _Pass, row: CsAgentTurn, chat_id: str, claimed_id: str) -> Optional[str]:
    """한 차례. 예상 밖 예외(TERM 포함)면 선점한 줄을 실패로 돌려놓고(다시 집음) 그대로 올린다."""
    try:
        return _draft_turn(ctx, row, chat_id, claimed_id)
    except Exception:
        _release(ctx, row, chat_id, FAIL_STOPPED if ctx.stop.is_set() else FAIL_ERROR)
        raise


def _release(ctx: _Pass, row: CsAgentTurn, chat_id: str, code: str) -> None:
    """선점한 줄(``claimed``)만 실패로 바꾼다 — '올리는 중'은 올라갔는지 몰라 그대로 둔다. TERM 뒤 쓰기는 이것 하나다."""
    session = ctx.session
    try:
        session.rollback()
        session.refresh(row)
        if row.state == STATE_CLAIMED:
            mark_failed(row, error_code=code, now=ctx.now)
            session.commit()
            ctx.summary.failed += 1
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 초안] 선점 줄을 실패로 못 바꿨다 — 다음 바퀴 정리가 맡는다 chat=%s code=%s", chat_id, code)
        return
    logger.warning("[CS 초안] 차례 중 멈춤 · 오류 chat=%s code=%s state=%s", chat_id, code, row.state)


def _read(ctx: _Pass, row: CsAgentTurn, chat_id: str, fetch: Callable[[], Any]) -> tuple[Any, Optional[str]]:
    """읽기 한 번 — (값, None). 실패면 그 줄을 실패로 적고 (None, 멈출 까닭)(한도 · 오류 모두 이번 바퀴 멈춤)."""
    try:
        return fetch(), None
    except ChannelRateLimited:
        return None, ctx.fail(row, FAIL_RATE_LIMITED, halt=FAIL_RATE_LIMITED)
    except ChannelReadError as exc:
        logger.warning("[CS 초안] 상담 글 읽기 실패 chat=%s status=%s", chat_id, exc.status)
        return None, ctx.fail(row, FAIL_READ, halt=FAIL_READ)


def _draft_turn(ctx: _Pass, row: CsAgentTurn, chat_id: str, claimed_id: str) -> Optional[str]:
    """선점한 차례 하나 — 읽기 → 두뇌 → 검사 → 직전 다시 읽기 → 저장 · 메모. 이번 바퀴를 멈출 까닭(없으면 ``None``)."""
    medium, halt = _read(ctx, row, chat_id, lambda: read_medium(ctx.reader, BRAND, chat_id))
    if halt:
        return halt
    if medium == MEDIUM_EMAIL:
        return ctx.skip(row, SKIP_EMAIL)
    lines, halt = _read(ctx, row, chat_id, lambda: read_lines(ctx.reader, BRAND, chat_id))
    if halt:
        return halt
    early = freshness(lines, claimed_id) or no_text_reason(lines)
    if early:
        return ctx.skip(row, early)
    try:
        request = DraftRequest(brand=BRAND, chat_id=chat_id, medium=medium, purpose=PURPOSE_DRAFT, daytime=ctx.daytime,
                               messages=conversation(lines), customer_names=(), staff_names=(),
                               knowledge=ctx.knowledge, realtime=False)
    except ValueError:
        return ctx.skip(row, SKIP_BAD_REQUEST)
    ctx.stop.check()  # 두뇌 전
    ctx.summary.brain_calls += 1
    try:
        result = ctx.brain(request, session=ctx.session, now=ctx.now)
    except SpendCapReached as exc:
        return ctx.fail(row, exc.code, halt=HALT_SPEND)
    except BrainNotReady as exc:
        return ctx.skip(row, exc.code, halt=HALT_NOT_READY)
    except MaskLeak as exc:
        logger.warning("[CS 초안] 가림 검사 0 아님 — 그 상담만 건너뜀 chat=%s counts=%s", chat_id, exc.counts)
        return ctx.skip(row, SKIP_MASK_LEAK)
    except BrainUnavailable as exc:
        return ctx.fail(row, exc.code, halt=None if exc.code == BAD_RESPONSE else HALT_BRAIN)
    ctx.stop.check()  # TERM 이 두뇌를 부르는 동안 왔으면 답을 버린다(R4-4)
    record_brain_result(row, result)
    if result.refused or result.handoff:
        return ctx.skip(row, SKIP_REFUSED if result.refused else SKIP_HANDOFF)
    return _check_and_place(ctx, row, chat_id, claimed_id, medium, lines, result)


def _check_and_place(ctx: _Pass, row: CsAgentTurn, chat_id: str, claimed_id: str, medium: Optional[str],
                     lines: Sequence[ChatLine], result: DraftResult) -> Optional[str]:
    """검사 → 직전 다시 읽기 → 저장만 · 메모."""
    check = check_draft(result.draft, brand=BRAND, medium=medium, allowed_numbers=ctx.allowed,
                        private_snippets=(*memo_snippets(lines), result.staff_note),
                        human_only_amounts=bool(ctx.human_only.intersection(result.evidence_ids)))
    masked = mask(result.draft)
    if not check.ok:
        return ctx.skip(row, SKIP_CHECK, codes=check.problems, masked=masked)
    fresh, halt = _read(ctx, row, chat_id, lambda: read_lines(ctx.reader, BRAND, chat_id))
    if halt:
        return halt
    stale = freshness(fresh, claimed_id)
    if stale:
        return ctx.skip(row, stale, masked=masked)
    warnings = [problem.code for problem in check.warnings]
    if ctx.mode == DRAFT_MEMO and memo_allowed(chat_id):
        return _post(ctx, row, chat_id, result, masked, warnings)
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


def _post(ctx: _Pass, row: CsAgentTurn, chat_id: str, result: DraftResult, masked: str,
          warnings: Sequence[str]) -> Optional[str]:
    """메모 — '올리는 중'을 먼저 커밋 → 감싸개 → 결과 적기(R1-3). 감싸개를 부른 뒤로는 깃발과 상관없이 결과를 적는다."""
    ctx.stop.check()  # 쓰기 전 — 깃발 뒤엔 올리기를 시작하지 않는다
    try:
        mark_posting(row, masked_draft=masked, check_codes=warnings, now=ctx.now)
    except MaskLeak as exc:
        logger.warning("[CS 초안] 가린 초안에 개인정보 꼴이 남아 건너뜀 chat=%s counts=%s", chat_id, exc.counts)
        return ctx.skip(row, SKIP_DRAFT_MASK_LEAK)
    ctx.session.commit()  # 채널톡을 부르기 전에 '올리는 중'을 커밋한다 — 죽어도 복구 단계가 찾는다
    sent = ctx.poster(chat_id, memo_text(result.draft, result.staff_note), brand=BRAND)
    if sent.outcome_unknown:
        ctx.summary.unknown += 1
        logger.warning("[CS 초안] 메모가 닿았는지 모른다 — 올리는 중 그대로(복구 단계 몫) chat=%s", chat_id)
        return None
    if not sent.posted:
        mark_failed(row, error_code=sent.reason or FAIL_SEND, now=ctx.now)
        ctx.session.commit()
        ctx.summary.failed += 1
        logger.warning("[CS 초안] 메모를 못 올렸다 chat=%s reason=%s", chat_id, sent.reason)
        return None
    message_id = sent.message_id if isinstance(sent.message_id, str) and _ID.fullmatch(sent.message_id) else None
    mark_posted(row, memo_message_id=message_id, error_code=None if sent.verified else (sent.reason or UNVERIFIED),
                now=ctx.now)
    ctx.session.commit()
    ctx.summary.posted += 1
    if sent.verified:
        return None
    ctx.summary.unverified += 1
    logger.error("[CS 초안] 메모를 올렸지만 비공개를 확인 못 했다 chat=%s message=%s reason=%s", chat_id, message_id,
                 sent.reason)
    return HALT_PUBLIC if sent.reason == REASON_NOT_PRIVATE else None
