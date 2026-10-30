"""초안 차례 — 감시 루프 바퀴 끝에서 라홈 '답 필요' 상담에 AI 초안을 쓴다(초안 스위치: 저장만 · 내부 메모).

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C3-1 · 설계서 4절(한 상담 글이 지나가는 길 — 순서 고정) · 6절 · 15.2 의 8.
원장 §3 20 · 21행 · 검수 R7 이 넘긴 일도 여기서 한다. 부품은 이미 있고 이 모듈은 잇기만 한다 — 두뇌 :func:`.brain.draft_reply` ·
차례 기록 :mod:`.turns` · 검사 :func:`.checks.check_draft` · 지식 :func:`.knowledge.load_approved` · 재료 읽기
:mod:`.drafting_read` · 놓기(저장만 · 메모 · 메모 막는 장치) :mod:`.drafting_post`. :func:`run_drafting` 한 바퀴(순서 고정):

0. **정리 · 준비** — 두뇌를 부르다 죽어 ``claimed`` 로 :data:`STALE_CLAIM_AFTER` 넘게 남은 줄은 ``failed``(시도 상한까지 다시
   집음). 오래 남은 ``posting`` 은 세기만 한다(다시 올리지 않는다 — 복구 단계 몫). 오늘(KST) 콘솔 돈 상한 응답으로 멈춘 줄이
   있거나 라홈 Open API 키가 없거나 **두뇌 준비**(:func:`.brain.check_ready` — 키 · 하루 상한 env · 승인 지식 · 디버그 로그
   막기 · 돈 줄 · **지금** 상한과 오늘 돈)가 안 됐으면 **줄을 하나도 만들지 않고** 멈춘다(원장 R7-4). 코드 하루 상한은 그때그때
   견주므로 상한을 올리면 다음 바퀴부터 다시 돈다.
1. **고르기** — 루프가 낸 열린 상담 상태에서 라홈 · 답 필요 · 맺음 글뿐 아님 · 마지막 손님 글 뒤 공개 직원 글 없음(우선순위 순).
   운영 시간 안 · 밖 모두(R7-7 결정 — 처음 2주는 '저장만'으로 PC 시범과 같은 범위를 견준다). 하우드는 고르지 않는다.
   마지막 손님 글이 운영 시간으로 '묵은 상담 기준'(관리 화면 설정 — 처음 값 :data:`MAX_WAIT_BUSINESS_DAYS`)을 넘긴
   상담도 고르지 않는다 — 켜는 날 밀린 상담에 하루 돈을 먼저 쓰지 않게(원장 D50, 주말 · 공휴일은 세지 않는다).
   한 바퀴 두뇌 상한도 관리 화면 설정이다(처음 값 :data:`MAX_BRAIN_CALLS` — 바퀴마다 새로 읽는다).
2. **선점** — 이미 있는 줄을 먼저 한 번에 읽어 다시 집을 수 없는 차례(실패 줄은 다시 집기 간격 — :func:`.turns.retry_due`
   — 전이면 아직)는 건너뛰고, (상담, 마지막 손님 글 id) 줄을
   :func:`.turns.claim_turn` 으로 잡아 바로 커밋한다. 뒤 쓰기는 모두 조건부라(R7-8) 그사이 다른 바퀴가 줄을 바꿨으면 올리지 않는다.
3. **읽기** — 매체(이메일이면 건너뜀) · 최근 글. 선점한 손님 글이 아직 마지막 손님 글이고 그 뒤 공개 직원 글이 없어야 한다
   (선점한 글이 읽기에 아직 없으면 다시 집을 실패 — R13-6). 재료는 공개 손님 · 직원 글만(R1-12). 손님 글에 글자가 없으면
   (사진만) 건너뜀. 손님이 'AI 냐 사람이냐' 물으면 두뇌 없이 사람에게(:mod:`.drafting_pass` — 두 길 공통, 설계서 17.8).
4. **두뇌** — ``purpose="draft"`` · 라홈 운영 시간이면 ``daytime`` · 15분 루프면 ``realtime=False``(빠른 길은 참) · 재료에 같은 브랜드
   비슷한 지난 사례(:func:`.case_material.similar_cases` — L0, 허용 목록에 넣지 않고 사례에만 있는 이름은 검사의 예시 낱말로).
   두뇌는 세션을 여러 번 커밋한다 — 우리 쓰기(선점)는 그 전에 커밋해 둔다. 캐시 표시를 실은 요청인데 캐시 읽기 0 인 호출만
   세고(표시 없는 요청 — 방침 끔 · 밤 — 은 빼고, 검수 R9) 바퀴마다 한 번 경고한다(R7-12).
5. **검사** — :func:`.checks.check_draft`(브랜드 · 매체를 늘 넘긴다 · 허용 목록은 승인 지식 글만 — 손님 글의 금액도, [사람]
   항목 글도 넣지 않는다). 걸리면 코드만 남기고 올리지 않는다.
6. **직전 다시 읽기** — 그사이 손님이 더 썼거나(``stale``) 공개 직원 글이 왔으면(``human_replied``) 올리지 않는다.
7. **놓기** — :func:`.drafting_post.place` (저장만 · 메모 · 공개 확인이면 스위치 끔 · 확인 못 함이면 저장만으로 + 알림).
   보내기 실패로 다시 집은 줄은 두뇌를 다시 부르지 않고 저장된 초안으로 5 · 6 · 7 만 한다(R7-5).

오류: 두뇌 안에서 준비 안 됨(:class:`.brain.BrainNotReady` — 401 · 403 포함) · 돈 상한은 **시도를 세지 않고** 돌려놓고
(:func:`.turns.release_turn`) 이번 바퀴 멈춤 · 가림 검사(:class:`.masking.MaskLeak`)는 그 상담만 건너뜀(로그엔 칸별 숫자만) ·
두뇌 못 씀은 실패(다시 집음 — 답 꼴만 틀렸으면 다음 상담으로, 그 밖엔 멈춤) · 읽기 실패 · 한도도 실패 + 멈춤 · 메모가 닿았는지
모름 · 보내기 실패도 멈춤. **넘김 · 거절은 메모 없이 기록만**(``skipped`` — 채널톡 쓰기 0 이 가장 안전하다: AI 가 답하면 안 된다고
본 상담이고, 직원 참고 칸은 검사를 안 거친 모델 글이며, 그 상담은 이미 아침 보고 '답 필요'에 있다). 넘김 까닭 코드는 남는다.

TERM: 선점 전 · 두뇌 전 · 쓰기 전마다 깃발을 보고, 서 있으면 지금 줄을 ``failed`` 로 돌려놓고 멈춘다(LLM 답은 버린다 — R4-4).
바퀴 도중 끄기: 선점 전 · 두뇌 전마다 비상 정지(:func:`.turns.read_switch`) · 초안 스위치(:func:`.turns.draft_mode`) · 관리 화면
빠른 길 스위치를 DB 에서 다시 읽고, 꺼졌거나 다른 길로 바뀌었으면 그 줄은 시도로 세지 않고 돌려놓고 바퀴를 멈춘다(``switched_off``).
글(손님 글 · 초안 · 직원 참고)은 로그 · 요약 · 예외에 싣지 않는다 — 요약은 숫자만, 로그는 상담 id · 코드 · 숫자만. 손님 프로필
이름 · 직원 이름은 지금 읽기 도우미가 주지 않아 가림에 넘기지 않는다(빈 목록 — 이름꼴 가림 · 검사는 그대로 돈다).
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Any, Callable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from foms.persistence.main.models import CsAgentChat, CsAgentTurn
from foms.services.channel_client import _open_api_headers
from foms.services.common.business_calendar import is_business_day as calendar_is_business_day
from foms.services.cs_agent.brain import (
    API_SPEND_LIMIT, BAD_RESPONSE, BrainNotReady, BrainUnavailable, DraftRequest, DraftResult,
    SpendCapReached, check_ready, draft_reply,
)
from foms.services.cs_agent.brain_prompt import PURPOSE_DRAFT
from foms.services.cs_agent.case_material import case_only_names, similar_cases
from foms.services.cs_agent.channel_read import ChannelRateLimited, ChannelReadError, naive_utc
from foms.services.cs_agent.checks import check_draft
from foms.services.cs_agent.drafting_pass import HUMAN_ONLY_MARK, DraftPass as _Pass  # noqa: F401 — 예전 이름
from foms.services.cs_agent.drafting_post import is_send_failure, place
from foms.services.cs_agent.drafting_read import (
    MEDIUM_EMAIL, ChatLine, conversation, freshness, memo_snippets, no_text_reason, read_lines, read_medium,
)
from foms.services.cs_agent.drafting_summary import DraftSummary
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.masking import MaskLeak, mask
from foms.services.cs_agent.memo import MemoResult, post_private_memo
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.state import (
    BRAND_HOURS, KST, BusinessDayFn, ChatState, business_minutes_between, sort_by_priority,
)
from foms.services.cs_agent.turns import (
    CLAIM_EXPIRED, DRAFT_MEMO, DRAFT_STORE, LEGACY_CLAIM_AFTER, STATE_CLAIMED, STATE_FAILED, TurnStateError, claim_turn,
    expired_claims, mark_failed, record_brain_result, retry_due, stale_posting,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BRAND", "DRAFT_BUDGET_SECONDS", "MAX_BRAIN_CALLS", "STALE_CLAIM_AFTER", "STALE_POSTING_AFTER", "DraftSummary",
    "run_drafting",
]

BRAND = "LAHOM"  # 초안을 쓰는 브랜드 — 하우드는 쓰기 허락 전이라 고르지 않는다(설계서 6절 단계 1)
#: 한 바퀴 두뇌 호출 상한(처음 값 — 관리 화면이 바꾼다). 시간 상한(초)은 선점 전에 본다 — 두뇌 한 번이 90초까지 걸릴 수
#: 있다(11.1 의 5).
MAX_BRAIN_CALLS = 10
DRAFT_BUDGET_SECONDS = 240.0
#: 마지막 손님 글이 이만큼(운영일 — 라홈 운영 시간 기준) 넘게 묵은 상담은 고르지 않는다(원장 D50, 처음 값 — 관리 화면이 바꾼다).
MAX_WAIT_BUSINESS_DAYS = 1
#: 15분 바퀴 선점 만료 — 이보다 오래 ``claimed`` 인 줄은 두뇌를 부르다 죽은 차례다(만료 칸이 정본, 옛 줄은 ``updated_at``).
STALE_CLAIM_AFTER = LEGACY_CLAIM_AFTER
#: 이보다 오래 ``posting`` 인 줄을 센다(올라갔는지 모름 — 복구 단계 몫, 다시 올리지 않는다).
STALE_POSTING_AFTER = datetime.timedelta(minutes=20)
#: 다시 올린 메모의 직원 참고 칸(처음 참고는 기록에 없다 — 표에는 가린 초안만 둔다).
REPOST_NOTE = "다시 올린 초안이다 — 처음 직원 참고는 기록에 남기지 않았다"
_CONSOLE_LIMIT_CODES = (API_SPEND_LIMIT,)  # 그날 멈춤 — 코드 하루 상한(DAILY_CAP_REACHED)은 준비 확인이 그때그때 견준다
_CHAT_CHUNK = 500

# 건너뜀 · 실패 · 멈춤 코드(기록 줄 ``error_code`` · 요약 칸 — 글이 아니다). 읽기 · 놓기 쪽 코드는 그 모듈에 있다.
SKIP_EMAIL, SKIP_BAD_REQUEST, SKIP_MASK_LEAK = "email", "bad_request", "mask_leak"
SKIP_HANDOFF, SKIP_REFUSED, SKIP_CHECK = "handoff", "refused", "check_failed"
FAIL_STALE_CLAIM, FAIL_STOPPED, FAIL_ERROR = CLAIM_EXPIRED, "stopped", "error"
FAIL_READ, FAIL_RATE_LIMITED = "read_failed", "rate_limited"
HALT_NOT_CONFIGURED, HALT_NOT_READY, HALT_SPEND = "not_configured", "not_ready", "spend_cap"
HALT_BRAIN, HALT_CONFLICT, HALT_CALLS, HALT_TIME = "brain_unavailable", "turn_conflict", "call_cap", "time_budget"
HALT_SWITCHED_OFF = "switched_off"  # 바퀴 도중 비상 정지 · 초안 끔


# ── 고르기 · 정리 ────────────────────────────────────────────────────────
def _candidates(session: Any, states: Sequence[ChatState], *, now: datetime.datetime,
                is_business_day: Optional[BusinessDayFn] = None,
                max_wait_days: float = MAX_WAIT_BUSINESS_DAYS) -> tuple[list[tuple[str, str]], int]:
    """고르기 — ((상담 id, 마지막 손님 글 id) 목록, 너무 묵어 뺀 수), 우선순위 순(아침 보고와 같다).

    마지막 손님 글 뒤 공개 직원 글이 있으면 빼고, 마지막 손님 글이 운영일 ``max_wait_days`` 를 넘겼으면 세고 뺀다.
    """
    picked = [s.chat_id for s in sort_by_priority(states) if s.brand == BRAND and s.needs_reply and not s.closing_only]
    rows: dict[str, Any] = {}
    for start in range(0, len(picked), _CHAT_CHUNK):
        stmt = select(CsAgentChat.chat_id, CsAgentChat.last_user_message_id, CsAgentChat.last_user_at,
                      CsAgentChat.last_answer_at).where(CsAgentChat.chat_id.in_(picked[start:start + _CHAT_CHUNK]))
        rows.update({row.chat_id: row for row in session.execute(stmt)})
    open_hour, close_hour = BRAND_HOURS[BRAND]
    max_wait = max_wait_days * (close_hour - open_hour) * 60
    out: list[tuple[str, str]] = []
    too_old = 0
    for chat_id in picked:
        row = rows.get(chat_id)
        if row is None or not row.last_user_message_id or row.last_user_at is None:
            continue
        if row.last_answer_at is not None and row.last_answer_at >= row.last_user_at:
            continue
        last_user_at = row.last_user_at.replace(tzinfo=datetime.timezone.utc)  # 표는 UTC naive
        if business_minutes_between(last_user_at, now, BRAND, is_business_day=is_business_day) > max_wait:
            too_old += 1
            continue
        out.append((chat_id, row.last_user_message_id))
    return out, too_old


def _existing(session: Any, candidates: Sequence[tuple[str, str]]) -> dict[tuple[str, str], Any]:
    """고른 차례에 이미 있는 줄(상태 · 시도 수 · 이유 코드)을 한 번에 — 상담 id 로 읽고 손님 글 id 로 맞춘다."""
    wanted, found = set(candidates), {}
    chats = sorted({chat_id for chat_id, _ in candidates})
    for start in range(0, len(chats), _CHAT_CHUNK):
        stmt = select(CsAgentTurn.chat_id, CsAgentTurn.last_user_message_id, CsAgentTurn.state, CsAgentTurn.attempts,
                      CsAgentTurn.error_code, CsAgentTurn.updated_at).where(
            CsAgentTurn.chat_id.in_(chats[start:start + _CHAT_CHUNK]))
        found.update({key: row for row in session.execute(stmt)
                      if (key := (row.chat_id, row.last_user_message_id)) in wanted})
    return found


def _recover(session: Any, now: datetime.datetime, stop: Any, summary: DraftSummary) -> None:
    """죽은 선점(:func:`.turns.expired_claims` — 만료 칸, 옛 줄은 ``updated_at`` 20분)은 실패로(다시 집음), 오래 남은
    '올리는 중'은 세기만 한다(원장 20행 — 다시 올리지 않는다). 빠른 길의 만료 정리와 같은 규칙이다(검수 R13)."""
    for row in expired_claims(session, now):
        stop.check()  # 쓰기 전
        mark_failed(row, error_code=FAIL_STALE_CLAIM, now=now)
        summary.recovered += 1
    session.commit()
    summary.stale_posting = len(stale_posting(session, now - STALE_POSTING_AFTER))
    session.commit()
    if summary.recovered or summary.stale_posting:
        logger.warning("[CS 초안] 오래 남은 차례 — 선점 %d건은 실패로(다시 집음) · 올리는 중 %d건은 복구 단계 몫(다시 올리지 않음)",
                       summary.recovered, summary.stale_posting)


def _console_limit_today(session: Any, now: datetime.datetime) -> bool:
    """오늘(KST) 콘솔(작업 공간) 돈 상한 응답으로 멈춘 줄이 있나 — 화면 상한을 올려도 풀리지 않아 그날은 부르지 않는다.
    다음 날 그 줄을 다시 집는다(원장 21행). 코드 하루 상한은 여기서 보지 않는다(준비 확인이 지금 상한과 오늘 돈으로 견준다)."""
    day = now.date()
    start = naive_utc(datetime.datetime(day.year, day.month, day.day, tzinfo=KST))
    stmt = select(CsAgentTurn.id).where(CsAgentTurn.state == STATE_FAILED,
                                        CsAgentTurn.error_code.in_(_CONSOLE_LIMIT_CODES),
                                        CsAgentTurn.updated_at >= start).limit(1)
    return session.scalar(stmt) is not None


def _daytime(now: datetime.datetime, cal: BusinessDayFn) -> bool:
    """라홈 운영 시간(평일 · 공휴일 쉼)인가 — 두뇌의 캐시 방침('운영 시간만')에 쓴다."""
    open_hour, close_hour = BRAND_HOURS[BRAND]
    return bool(cal(now.date())) and open_hour <= now.hour < close_hour


# ── 한 바퀴 ──────────────────────────────────────────────────────────────
def _halted(session: Any, summary: DraftSummary, code: str) -> DraftSummary:
    """선점 전에 멈춘다(읽기 트랜잭션을 닫는다)."""
    session.commit()
    summary.halted[code] = 1
    logger.warning("[CS 초안] 이번 바퀴 초안을 쓰지 않는다 code=%s", code)
    return summary


def _reclaimable(prev: Any, now: datetime.datetime) -> bool:
    """이미 있는 줄을 지금 다시 집을 수 있나 — 실패 · 시도 상한 전 · 다시 집기 간격이 지남(:func:`.turns.retry_due`)."""
    return retry_due(prev, now)


def run_drafting(session: Any, *, states: Sequence[ChatState], reader: Any, now: datetime.datetime, stop: Any,
                 mode: str, is_business_day: Optional[BusinessDayFn] = None,
                 brain: Callable[..., DraftResult] = draft_reply,
                 poster: Callable[..., MemoResult] = post_private_memo, limit: Optional[int] = None,
                 clock: Callable[[], float] = time.monotonic, budget_seconds: float = DRAFT_BUDGET_SECONDS,
                 ready: Callable[..., Any] = check_ready, summary: Optional[DraftSummary] = None,
                 picks: Optional[Sequence[tuple[str, str]]] = None,
                 pass_type: Optional[Callable[..., Any]] = None) -> DraftSummary:
    """초안 한 바퀴(모듈 설명의 순서). 감시 루프가 상태 · 보고 뒤에 부른다 — 스위치가 ``store`` · ``memo`` 가 아니면 일 0.

    Args:
        session: DB 세션(이 함수 · 두뇌가 커밋한다).
        states: 감시 루프가 낸 열린 상담 상태.
        reader: 채널톡 Open API 읽기 도우미(:class:`~.channel_read.OpenApiReader` — 루프가 쓰는 것, 기다림이 깃발을 본다).
        now: 지금(시간대 있는 값).
        stop: 감시 루프 멈춤 깃발(``check`` · ``is_set``).
        mode: 초안 스위치 값(:func:`.turns.draft_mode`).
        is_business_day: 운영일 판정(시험 주입).
        brain: 두뇌(시험은 가짜). poster: 메모 감싸개(시험은 가짜 — 루프의 읽기 도우미를 넘겨 다시 읽는다).
        limit: 한 바퀴 두뇌 호출 상한(없으면 관리 화면 설정). clock · budget_seconds: 시간 상한(선점 전에 본다).
        ready: 두뇌 준비 확인(기본 :func:`.brain.check_ready` — 선점 전에 한 번).
        summary: 채울 결과(루프는 멈춰도 센 수가 남게 미리 만들어 넘긴다).
        picks · pass_type: 빠른 길(:mod:`.realtime`)이 모아 받기로 이미 고른 (상담, 손님 글 id) 목록과 바꾼 차례 꼴 — 주면
            고르기(1)를 건너뛰고 선점 · 두뇌 · 검사 · 놓기 순서는 그대로 쓴다.

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
    if _console_limit_today(session, now):
        return _halted(session, summary, HALT_SPEND)
    if _open_api_headers(BRAND) is None:
        return _halted(session, summary, HALT_NOT_CONFIGURED)
    knowledge = load_approved(session, BRAND)
    try:
        ready(BRAND, knowledge, session=session, now=now)  # 고르기 · 선점 전 — 안 됐으면 줄을 만들지 않는다(R7-4)
    except BrainNotReady as exc:
        logger.warning("[CS 초안] 두뇌 준비가 안 돼 줄을 만들지 않고 멈춘다 code=%s", exc.code)
        return _halted(session, summary, HALT_NOT_READY)
    except SpendCapReached:
        return _halted(session, summary, HALT_SPEND)
    cfg = read_settings(session)  # 바퀴마다 새로 — 화면에서 저장하면 다음 바퀴부터
    limit = cfg.get("max_brain_calls_per_pass") if limit is None else limit
    if picks is None:
        candidates, summary.too_old = _candidates(session, states, now=now, is_business_day=is_business_day,
                                                  max_wait_days=cfg.get("max_wait_business_days"))
    else:
        candidates = list(picks)
    existing = _existing(session, candidates)
    session.commit()  # 읽기 트랜잭션을 닫는다 — 채널톡 · 두뇌를 부르는 동안 열어 두지 않는다
    summary.candidates = len(candidates)
    ctx = (pass_type or _Pass)(session, reader=reader, now=now, stop=stop, mode=mode, brain=brain, poster=poster,
                               knowledge=knowledge, daytime=_daytime(now, is_business_day or calendar_is_business_day),
                               summary=summary, clock=clock)
    for chat_id, message_id in candidates:
        prev = existing.get((chat_id, message_id))
        if prev is not None and not _reclaimable(prev, now):
            summary.already += 1  # 끝났거나 일하는 줄 — 선점(넣기)도 하지 않는다
            continue
        if summary.brain_calls >= limit or clock() >= deadline:
            summary.halted[HALT_CALLS if summary.brain_calls >= limit else HALT_TIME] = 1
            break
        if ctx.switched_off():  # 바퀴 도중 비상 정지 · 초안 끔 · 다른 길로 바뀜 — 선점하지 않는다(R13-7)
            summary.halted[HALT_SWITCHED_OFF] = 1
            break
        stop.check()  # 선점 전
        try:
            row = claim_turn(session, BRAND, chat_id, message_id, now=ctx.claim_at(), owner=ctx.owner, ttl=ctx.claim_ttl)
        except ValueError:
            session.rollback()
            logger.warning("[CS 초안] 상담 · 글 id 꼴이 아니라 고르지 않는다 chat=%s", chat_id)
            continue
        session.commit()  # 선점을 먼저 커밋 — 두뇌가 세션을 커밋하기 전에 우리 쓰기를 끝낸다(원장 21행)
        if row is None:
            summary.already += 1
            continue
        summary.claimed += 1
        repost = prev is not None and is_send_failure(prev.error_code) and row.masked_draft is not None
        halt = _guarded_turn(ctx, row, chat_id, message_id, repost=repost)
        if halt:
            summary.halted[halt] = 1
            break
    if summary.cache_cold:
        logger.warning("[CS 초안] 캐시 표시를 실었는데 캐시 읽기 0 인 두뇌 호출 %d번 — 앞부분 캐시가 안 먹는다(최소 길이 · 바뀌는 값 확인)",
                       summary.cache_cold)
    return summary


def _guarded_turn(ctx: _Pass, row: CsAgentTurn, chat_id: str, claimed_id: str, *, repost: bool) -> Optional[str]:
    """한 차례. 줄이 그사이 바뀌었으면(R7-8) 손대지 않고 멈춘다. 예상 밖 예외(TERM 포함)면 선점한 줄을 실패로 돌려놓고 올린다."""
    try:
        return _draft_turn(ctx, row, chat_id, claimed_id, repost=repost)
    except TurnStateError as exc:
        ctx.session.rollback()
        logger.warning("[CS 초안] 차례 줄이 그사이 바뀌어 손대지 않고 멈춘다 chat=%s why=%s", chat_id, type(exc).__name__)
        return HALT_CONFLICT
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
    except (SQLAlchemyError, TurnStateError):
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


def _draft_turn(ctx: _Pass, row: CsAgentTurn, chat_id: str, claimed_id: str, *, repost: bool) -> Optional[str]:
    """선점한 차례 하나 — 읽기 → (다시 올리기 | 두뇌 → 검사) → 직전 다시 읽기 → 놓기. 이번 바퀴를 멈출 까닭(없으면 ``None``)."""
    medium, halt = _read(ctx, row, chat_id, lambda: read_medium(ctx.reader, BRAND, chat_id))
    if halt:
        return halt
    if medium == MEDIUM_EMAIL:
        return ctx.skip(row, SKIP_EMAIL)
    lines, halt = _read(ctx, row, chat_id, lambda: read_lines(ctx.reader, BRAND, chat_id))
    if halt:
        return halt
    stored = row.masked_draft if repost else None
    early = freshness(lines, claimed_id) or no_text_reason(lines)
    if early:
        return ctx.skip(row, early, masked=stored)
    if ctx.asks_human(lines):  # 'AI 냐 사람이냐' 물음이면 두 길 모두 두뇌 · 초안 없이 사람에게(설계서 17.1 · 17.8)
        return ctx.hand_to_human(row, chat_id, lines)
    if repost:  # 이 읽기가 직전 다시 읽기다 — 두뇌를 다시 부르지 않는다
        return _check_and_place(ctx, row, chat_id, claimed_id, medium, lines, draft=stored, note="", reread=False)
    cases = similar_cases(ctx.session, BRAND, lines)  # L0 사례(DB 오류면 빈 사례) — 허용 목록엔 넣지 않는다
    try:
        request = DraftRequest(brand=BRAND, chat_id=chat_id, medium=medium, purpose=PURPOSE_DRAFT, daytime=ctx.daytime,
                               messages=conversation(lines), customer_names=(), staff_names=(),
                               knowledge=ctx.knowledge, realtime=ctx.realtime, cases=cases)
    except ValueError:
        return ctx.skip(row, SKIP_BAD_REQUEST)
    ctx.stop.check()  # 두뇌 전
    if ctx.switched_off():  # 바퀴 도중 꺼졌으면(다른 길로 바뀜 포함) 부르지 않는다 — 시도로 세지 않고 돌려놓는다
        return ctx.release(row, HALT_SWITCHED_OFF, halt=HALT_SWITCHED_OFF)
    ctx.summary.brain_calls += 1
    try:
        result = ctx.brain(request, session=ctx.session, now=ctx.now)
    except SpendCapReached as exc:
        return ctx.release(row, exc.code, halt=HALT_SPEND)
    except BrainNotReady as exc:
        return ctx.release(row, exc.code, halt=HALT_NOT_READY)
    except MaskLeak as exc:
        logger.warning("[CS 초안] 가림 검사 0 아님 — 그 상담만 건너뜀 chat=%s counts=%s", chat_id, exc.counts)
        return ctx.skip(row, SKIP_MASK_LEAK)
    except BrainUnavailable as exc:
        return ctx.fail(row, exc.code, halt=None if exc.code == BAD_RESPONSE else HALT_BRAIN)
    ctx.stop.check()  # TERM 이 두뇌를 부르는 동안 왔으면 답을 버린다(R4-4)
    ctx.summary.cache_cold += int(result.cache_marked and not result.cache_read_tokens)  # 표시 없는 요청(끔 · 밤)은 빼고
    record_brain_result(row, result)
    if result.refused or result.handoff:
        return ctx.skip(row, SKIP_REFUSED if result.refused else SKIP_HANDOFF)
    names = case_only_names(cases, (*(line.text for line in lines), *(item.text for item in ctx.knowledge.items)))
    return _check_and_place(ctx, row, chat_id, claimed_id, medium, lines, draft=result.draft,
                            note=result.staff_note, evidence=result.evidence_ids, examples=names)


def _check_and_place(ctx: _Pass, row: CsAgentTurn, chat_id: str, claimed_id: str, medium: Optional[str],
                     lines: Sequence[ChatLine], *, draft: str, note: str, evidence: Sequence[str] = (),
                     examples: Sequence[str] = (), reread: bool = True) -> Optional[str]:
    """검사 → (직전 다시 읽기) → 놓기. 다시 올리기는 막 읽은 글로 보니 다시 읽지 않고, 직원 참고는 기록에 없어 정한 글을 쓴다.

    다시 올리기의 [사람] 금액 표시는 근거 id 가 기록에 없어 끄지만, 허용 목록에서 [사람] 항목 글이 빠져 있어 그 금액은 그대로
    막힌다(같은 초안이 처음 올릴 때 이미 같은 검사를 통과했다).
    """
    check = check_draft(draft, brand=BRAND, medium=medium, allowed_numbers=ctx.allowed,
                        private_snippets=(*memo_snippets(lines), note), example_only_words=examples,
                        human_only_amounts=bool(ctx.human_only.intersection(evidence)))
    masked = mask(draft)
    if not check.ok:
        return ctx.skip(row, SKIP_CHECK, codes=check.problems, masked=masked)
    if reread:
        fresh, halt = _read(ctx, row, chat_id, lambda: read_lines(ctx.reader, BRAND, chat_id))
        if halt:
            return halt
        stale = freshness(fresh, claimed_id)
        if stale:
            return ctx.skip(row, stale, masked=masked)
    else:
        ctx.summary.reposted += 1
    return place(ctx, row, chat_id, draft=draft, staff_note=note if reread else REPOST_NOTE, masked=masked,
                 warnings=[problem.code for problem in check.warnings])
