"""초안 차례 기록 — (상담, 마지막 손님 글 id) 선점 · 상태 · 시도 상한 · '올리는 중' 복구 재료 · 초안 스위치.

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C3-1(중복 방지는 DB) · C3-3 · 설계서 4절 8 · 9 · 6절. 원장 R1-2 · R1-3 ·
R1-20 · R1-22. 표는 ``models.CsAgentTurn``(마이그레이션 ``csagent_01``). **함수는 커밋하지 않는다 — 부르는 쪽이 커밋한다.**

- **선점(R1-2)**: (상담, 마지막 손님 글 id) 고유 줄을 '있으면 무시하고 넣기'(``INSERT … ON CONFLICT DO NOTHING RETURNING``
  — SQLite · PostgreSQL 같은 문장)로 만든다. 이미 있으면 ``None`` — 손님 글 하나에 메모는 하나다. 실패로 끝난 줄만
  :data:`MAX_ATTEMPTS` 전까지 같은 줄을 다시 집는다(조건부 UPDATE 한 문장 — 둘이 겹쳐도 하나만 집는다).
- **상태**: ``claimed`` → ``posting`` → ``posted``, 또는 ``claimed`` → ``stored`` · ``skipped``, ``claimed`` · ``posting`` →
  ``failed``. '올리는 중'은 채널톡을 부르기 **전에** 커밋한다(R1-3) — 재시작 때 남은 줄은 :func:`stale_posting` 으로 찾아
  채널톡의 우리 봇 메모와 맞춘다. 올라갔는지 모르는 실패는 ``failed`` 로 바꾸지 않는다(다시 집으면 메모가 둘이 된다).
- **글(R1-20)**: 가린 칸(``masked_draft`` · ``staff_reply_masked``)에만 글을 둔다. 받은 글도 한 번 더 가리고
  가림 검사(:func:`~foms.services.cs_agent.masking.require_masked`)가 0 일 때만 넣는다. 두뇌 결과는 코드 · 숫자 칸만 옮긴다.
- **초안 스위치(설계서 6절 · R1-22)**: 바로 끄기 줄(:data:`SWITCH_KEY`)의 ``draft`` 칸 — ``off`` · ``store``(저장만) ·
  ``memo``. 줄 · 칸이 없거나 값이 비었거나 꼴이 틀리면 ``off``(막는 쪽으로 닫힘). ``loop`` 칸은 감시 루프 규칙 그대로다.
"""

from __future__ import annotations

import datetime
import enum
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql, sqlite

from foms.persistence.main.models import CsAgentTurn, SystemSetting
from foms.services.cs_agent.channel_read import CHANNEL_BRANDS, naive_utc
from foms.services.cs_agent.masking import mask, require_masked

logger = logging.getLogger(__name__)

__all__ = [
    "DRAFT_MEMO",
    "DRAFT_MODES",
    "DRAFT_OFF",
    "DRAFT_STORE",
    "MAX_ATTEMPTS",
    "STATES",
    "SWITCH_KEY",
    "TurnStateError",
    "claim_turn",
    "draft_mode",
    "mark_failed",
    "mark_posted",
    "mark_posting",
    "mark_skipped",
    "mark_stored",
    "record_brain_result",
    "record_staff_reply",
    "stale_posting",
]

STATE_CLAIMED, STATE_POSTING, STATE_POSTED = "claimed", "posting", "posted"
STATE_STORED, STATE_SKIPPED, STATE_FAILED = "stored", "skipped", "failed"
STATES: tuple[str, ...] = (STATE_CLAIMED, STATE_POSTING, STATE_POSTED, STATE_STORED, STATE_SKIPPED, STATE_FAILED)
#: 손님 글 하나에 차례를 여는 상한(두뇌 호출 상한 — 원장 R1-3). 실패로 끝난 줄은 이 수까지만 다시 집는다.
MAX_ATTEMPTS = 3

#: 바로 끄기 줄 — ``loop.SWITCH_KEY`` 와 같은 줄이다(loop 가 이 모듈을 부를 쪽이라 거꾸로 import 하지 않는다 · 시험이 맞춘다).
SWITCH_KEY = "cs_agent_switch"
DRAFT_FIELD = "draft"
DRAFT_OFF, DRAFT_STORE, DRAFT_MEMO = "off", "store", "memo"
DRAFT_MODES: tuple[str, ...] = (DRAFT_OFF, DRAFT_STORE, DRAFT_MEMO)

_TURNS = CsAgentTurn.__table__
_INSERT_BUILDERS: dict[str, Callable[[Any], Any]] = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}
#: 채널톡 id 꼴 — 빈칸 없는 ASCII 64자까지(손님 글이 자리를 바꿔 들어오면 여기서 걸린다).
_ID = re.compile(r"[\x21-\x7e]{1,64}")
#: 코드 칸 꼴 — 빈칸 · 줄바꿈 없는 짧은 이름(한글 이름도 된다). 글처럼 생긴 값은 칸에 넣지 않는다.
_CODE = re.compile(r"[\w.:/\-]+")
_CHECK_CODE = re.compile(r"[a-z][a-z0-9_]{0,47}")
_REASON_MAX = 48
#: 두뇌 결과의 코드 칸과 길이 상한(표 칸 길이).
_BRAIN_CODES: tuple[tuple[str, int], ...] = (("intent", 32), ("handoff_reason", 64), ("model", 64), ("effort", 16))
#: 두뇌 결과의 숫자 칸 → 읽을 속성 이름(앞에서부터 — 뒤 이름은 Anthropic usage 칸 이름).
_BRAIN_COUNTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("input_tokens", ("input_tokens",)),
    ("output_tokens", ("output_tokens",)),
    ("cache_read_tokens", ("cache_read_tokens", "cache_read_input_tokens")),
    ("cache_write_tokens", ("cache_write_tokens", "cache_creation_input_tokens")),
    ("latency_ms", ("latency_ms",)),
)
_INT_MAX = 2**31 - 1
#: 비용 칸 ``Numeric(12, 6)`` — 소수 여섯째 자리, 정수 여섯 자리까지.
_COST_SCALE = Decimal(10) ** -6
_COST_MAX = Decimal(10) ** 6 - _COST_SCALE


class TurnStateError(RuntimeError):
    """허락되지 않은 상태 바꾸기 — 부르는 쪽 실수다(메시지엔 상태 이름만)."""


# ── 선점 ─────────────────────────────────────────────────────────────────
def claim_turn(session: Any, brand: str, chat_id: str, last_user_message_id: str, *,
               now: datetime.datetime) -> Optional[CsAgentTurn]:
    """(상담, 마지막 손님 글 id) 차례를 선점한다 — 새 줄(또는 다시 집은 실패 줄)이면 그 줄, 이미 있으면 ``None``.

    부르는 쪽은 받은 줄을 **바로 커밋**한다. PostgreSQL 에서 두 바퀴가 겹치면 뒤 바퀴의 넣기는 앞 바퀴가 커밋 · 되돌리기를
    할 때까지 기다렸다가 아무것도 넣지 않는다(되돌렸으면 뒤 바퀴가 집는다).

    Args:
        session: DB 세션.
        brand: 상담 브랜드(채널 짝 상수에 있는 이름).
        chat_id: 채널톡 상담 id.
        last_user_message_id: 이 차례를 연 손님 글의 채널톡 메시지 id.
        now: 지금(시간대 있는 값 — 표에는 UTC naive).

    Returns:
        선점한 :class:`CsAgentTurn`(``state='claimed'``) 또는 ``None``.

    Raises:
        ValueError: 모르는 브랜드 · id 꼴이 아님 · 시간대 없는 ``now``.
        RuntimeError: PostgreSQL · SQLite 가 아닌 DB.
    """
    if brand not in set(CHANNEL_BRANDS.values()):
        raise ValueError("모르는 브랜드")
    if not all(isinstance(value, str) and _ID.fullmatch(value) for value in (chat_id, last_user_message_id)):
        raise ValueError("상담 · 글 id 꼴이 아니다")
    at = naive_utc(now)
    builder = _INSERT_BUILDERS.get(session.get_bind().dialect.name)
    if builder is None:
        raise RuntimeError("있으면 무시하고 넣기를 모르는 DB")
    inserted = (builder(_TURNS)
                .values(brand=brand, chat_id=chat_id, last_user_message_id=last_user_message_id,
                        state=STATE_CLAIMED, attempts=1, created_at=at, updated_at=at)
                .on_conflict_do_nothing(index_elements=["chat_id", "last_user_message_id"])
                .returning(_TURNS.c.id))
    turn_id = session.execute(inserted).scalar()
    if turn_id is None:
        retry = (update(_TURNS)
                 .where(_TURNS.c.chat_id == chat_id, _TURNS.c.last_user_message_id == last_user_message_id,
                        _TURNS.c.state == STATE_FAILED, _TURNS.c.attempts < MAX_ATTEMPTS)
                 .values(state=STATE_CLAIMED, attempts=_TURNS.c.attempts + 1, error_code=None, updated_at=at)
                 .returning(_TURNS.c.id))
        turn_id = session.execute(retry).scalar()
    if turn_id is None:
        return None
    return session.get(CsAgentTurn, turn_id, populate_existing=True)


# ── 상태 바꾸기(ORM 줄만 고친다 — 커밋은 부르는 쪽) ──────────────────────
def mark_posting(row: CsAgentTurn, *, masked_draft: Optional[str], check_codes: Iterable[Any] = (),
                 now: datetime.datetime) -> None:
    """'올리는 중' — 메모를 올리기 바로 전. 부르는 쪽이 **커밋한 뒤에** 채널톡을 부른다(R1-3).

    올릴 초안의 가린 사본(``None`` 이면 두지 않음)과 검사 코드를 같이 적는다. 가림 검사가 0 이 아니면 아무것도 바꾸지
    않고 :class:`~foms.services.cs_agent.masking.MaskLeak`.
    """
    draft, codes = _masked_or_none(masked_draft), _check_codes(check_codes)
    _move(row, (STATE_CLAIMED,), STATE_POSTING, now)
    row.masked_draft, row.check_codes = draft, codes


def mark_posted(row: CsAgentTurn, *, memo_message_id: Optional[str], error_code: Optional[str] = None,
                now: datetime.datetime) -> None:
    """올림 — 채널톡이 메모를 받았다(복구 단계가 우리 봇 메모를 찾았을 때도).

    Args:
        row: '올리는 중' 줄.
        memo_message_id: 올린 메모의 채널톡 메시지 id(모르면 ``None``).
        error_code: 올렸지만 비공개를 확인 못 한 이유(메모 결과의 ``reason`` — 확인됐으면 ``None``).
        now: 지금(시간대 있는 값).
    """
    message_id = None if memo_message_id is None else _checked_id(memo_message_id)
    code = None if error_code is None else _reason(error_code)
    _move(row, (STATE_POSTING,), STATE_POSTED, now)
    row.memo_message_id, row.error_code = message_id, code


def mark_stored(row: CsAgentTurn, *, masked_draft: Optional[str], check_codes: Iterable[Any] = (),
                now: datetime.datetime) -> None:
    """저장만 — 초안을 기록에만 두고 올리지 않는다(초안 스위치 ``store`` · 운영 밖 허용 목록 밖 상담)."""
    draft, codes = _masked_or_none(masked_draft), _check_codes(check_codes)
    _move(row, (STATE_CLAIMED,), STATE_STORED, now)
    row.masked_draft, row.check_codes = draft, codes


def mark_skipped(row: CsAgentTurn, *, reason: str, check_codes: Iterable[Any] = (),
                 masked_draft: Optional[str] = None, now: datetime.datetime) -> None:
    """건너뜀 — 이 차례엔 올리지 않는다(넘김 · 검사에 걸림 · 그사이 사람이 답함 · 손님이 더 씀 등). 이유는 ``error_code``."""
    code, draft, codes = _reason(reason), _masked_or_none(masked_draft), _check_codes(check_codes)
    _move(row, (STATE_CLAIMED,), STATE_SKIPPED, now)
    row.error_code, row.masked_draft, row.check_codes = code, draft, codes


def mark_failed(row: CsAgentTurn, *, error_code: str, now: datetime.datetime) -> bool:
    """실패 — 채널톡에 아무것도 안 올라갔을 때만 쓴다(올라갔는지 모르면 '올리는 중'으로 두고 복구 단계에 맡긴다).

    Returns:
        다시 집을 수 있으면 True(선점 횟수 < :data:`MAX_ATTEMPTS`) — 다음 바퀴의 :func:`claim_turn` 이 같은 줄을 집는다.
    """
    code = _reason(error_code)
    _move(row, (STATE_CLAIMED, STATE_POSTING), STATE_FAILED, now)
    row.error_code = code
    return int(row.attempts or 0) < MAX_ATTEMPTS


def record_brain_result(row: CsAgentTurn, result: Any) -> None:
    """두뇌 결과에서 코드 · 숫자 칸만 옮긴다(덕 타이핑 — 없는 속성은 비운다). 초안 · 직원 참고 같은 글은 옮기지 않는다.

    읽는 속성: ``intent`` · ``handoff``(참 · 거짓) · ``handoff_reason`` · ``model`` · ``effort`` · ``input_tokens`` ·
    ``output_tokens`` · ``cache_read_tokens``(또는 ``cache_read_input_tokens``) · ``cache_write_tokens``(또는
    ``cache_creation_input_tokens``) · ``cost_usd`` · ``latency_ms``. 꼴이 틀린 값(글처럼 생긴 코드 · 음수)은 비우고 경고한다.

    Raises:
        TurnStateError: 선점한 줄(``claimed``)이 아니다.
    """
    if row.state != STATE_CLAIMED:
        raise TurnStateError(f"두뇌 결과는 선점한 줄에만 적는다(지금 {row.state})")
    for column, limit in _BRAIN_CODES:
        setattr(row, column, _code(getattr(result, column, None), limit, column))
    handoff = getattr(result, "handoff", None)
    if handoff is not None and not isinstance(handoff, bool):
        logger.warning("[CS 초안] 기록 칸 꼴이 틀려 비운다 field=handoff")
        handoff = None
    row.handoff = handoff
    for column, names in _BRAIN_COUNTS:
        value = next((getattr(result, name) for name in names if getattr(result, name, None) is not None), None)
        setattr(row, column, _count(value, column))
    row.cost_usd = _cost(getattr(result, "cost_usd", None))


def record_staff_reply(row: CsAgentTurn, staff_reply: Optional[str], *, judgment: Optional[str] = None,
                       now: datetime.datetime) -> None:
    """직원 최종 답(공개 manager 글)의 가린 사본과 '같은 뜻' 판정 코드를 끝난 줄에 적는다(R1-20 — 같은 가림 · 검사).

    Raises:
        MaskLeak: 가린 뒤에도 가림 검사가 0 이 아니다(아무것도 바꾸지 않는다).
        TurnStateError: 끝난 줄(``posted`` · ``stored`` · ``skipped``)이 아니다.
    """
    reply = _masked_or_none(staff_reply)
    code = _code(judgment, 16, "judgment")
    if row.state not in (STATE_POSTED, STATE_STORED, STATE_SKIPPED):
        raise TurnStateError(f"직원 답은 끝난 줄에만 짝짓는다(지금 {row.state})")
    row.staff_reply_masked, row.judgment, row.updated_at = reply, code, naive_utc(now)


# ── 복구 재료 · 스위치 ───────────────────────────────────────────────────
def stale_posting(session: Any, older_than: datetime.datetime, *, limit: int = 100) -> list[CsAgentTurn]:
    """'올리는 중'으로 ``older_than``(시간대 있는 시각) 전부터 남은 줄 — 올리다 죽은 차례, 오래된 것부터.

    복구 단계가 그 상담의 채널톡 글에서 우리 봇 메모(:data:`foms.services.cs_agent.memo.MEMO_BOT_NAME`)를 찾아
    :func:`mark_posted`(찾음) 또는 :func:`mark_failed`(없음)로 정리한다.
    """
    stmt = (select(CsAgentTurn)
            .where(CsAgentTurn.state == STATE_POSTING, CsAgentTurn.updated_at < naive_utc(older_than))
            .order_by(CsAgentTurn.updated_at, CsAgentTurn.id)
            .limit(int(limit))
            .execution_options(populate_existing=True))
    return list(session.scalars(stmt))


def draft_mode(session: Any) -> str:
    """초안 스위치 — ``off`` · ``store`` · ``memo``. 쓰지 않고 읽기만 한다(매 바퀴 DB 에서 새로 읽는다).

    줄이 없거나 ``draft`` 칸이 없으면 ``off``. 줄은 있는데 값이 비었거나(NULL) 꼴이 틀리면(대문자 · 오타 · 글자가 아님)
    경고하고 ``off`` — 켜려고 손댄 값이 오타로 켜진 채 남지 않고, 끄려고 손댄 값도 꺼진다(원장 R5-8 과 같은 규칙).
    """
    row = session.get(SystemSetting, SWITCH_KEY, populate_existing=True)
    if row is None:
        return DRAFT_OFF
    value = row.setting_value
    if isinstance(value, dict) and DRAFT_FIELD not in value:
        return DRAFT_OFF
    mode = value.get(DRAFT_FIELD) if isinstance(value, dict) else None
    if isinstance(mode, str) and mode in DRAFT_MODES:
        return mode
    logger.warning("[CS 초안] 초안 스위치 값의 꼴이 틀려 끈 것으로 본다 key=%s", SWITCH_KEY)
    return DRAFT_OFF


# ── 칸 꼴 ────────────────────────────────────────────────────────────────
def _move(row: CsAgentTurn, allowed: tuple[str, ...], target: str, now: datetime.datetime) -> None:
    """상태를 ``target`` 으로 — 지금 상태가 ``allowed`` 안일 때만(아니면 :class:`TurnStateError`, 아무것도 안 바뀜)."""
    at = naive_utc(now)
    if row.state not in allowed:
        raise TurnStateError(f"{row.state} → {target} 는 허락되지 않는다")
    row.state, row.updated_at = target, at


def _masked_or_none(text: Optional[str]) -> Optional[str]:
    """가린 사본 — 한 번 더 가리고 가림 검사가 0 일 때만 돌려준다. ``None`` · 빈 글은 ``None``."""
    if text is None:
        return None
    if not isinstance(text, str):
        raise TypeError("가린 글은 글자열이다")
    return require_masked(mask(text)) if text.strip() else None


def _check_codes(codes: Iterable[Any]) -> list[str]:
    """검사 코드 목록(겹침 없이 순서대로). 코드 글자열이나 ``code`` 속성이 있는 검사 결과 항목을 받는다."""
    if isinstance(codes, (str, bytes)):
        raise TypeError("check_codes 는 코드 목록이다")
    out: list[str] = []
    for item in codes:
        code = getattr(item, "code", item)
        if not isinstance(code, str) or not _CHECK_CODE.fullmatch(code):
            raise ValueError("검사 코드 꼴이 아니다(영문 소문자 · 숫자 · 밑줄)")
        if code not in out:
            out.append(code)
    return out


def _checked_id(value: Any) -> str:
    """채널톡 id 꼴인 값만."""
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("채널톡 id 꼴이 아니다")
    return value


def _reason(value: Any) -> str:
    """이유 코드(비면 안 된다)."""
    code = _code(value, _REASON_MAX, "error_code")
    if code is None:
        raise ValueError("이유 코드 꼴이 아니다")
    return code


def _code(value: Any, limit: int, field: str) -> Optional[str]:
    """코드 칸 값 — 꼴이 맞는 짧은 이름만. 비었으면 ``None``, 꼴이 틀리면 경고하고 ``None``(값은 로그에 싣지 않는다)."""
    if isinstance(value, enum.Enum):
        value = value.value
    if value is None or value == "":
        return None
    if isinstance(value, str) and len(value) <= limit and _CODE.fullmatch(value):
        return value
    logger.warning("[CS 초안] 기록 칸 꼴이 틀려 비운다 field=%s", field)
    return None


def _count(value: Any, field: str) -> Optional[int]:
    """0 이상 정수 칸(토큰 · 밀리초). 꼴이 틀리면 경고하고 ``None``."""
    if value is None:
        return None
    if not isinstance(value, bool) and isinstance(value, (int, float, Decimal)):
        try:
            number = int(round(value))
        except (ValueError, OverflowError, InvalidOperation):
            number = -1
        if 0 <= number <= _INT_MAX:
            return number
    logger.warning("[CS 초안] 기록 칸 꼴이 틀려 비운다 field=%s", field)
    return None


def _cost(value: Any) -> Optional[Decimal]:
    """비용(달러) — 0 이상, 소수 여섯째 자리까지. 꼴이 틀리면 경고하고 ``None``."""
    if value is None:
        return None
    if not isinstance(value, bool) and isinstance(value, (int, float, Decimal)):
        try:
            cost = Decimal(str(value))
        except InvalidOperation:
            cost = Decimal("NaN")
        if cost.is_finite() and Decimal(0) <= cost <= _COST_MAX:
            return cost.quantize(_COST_SCALE)
    logger.warning("[CS 초안] 기록 칸 꼴이 틀려 비운다 field=cost_usd")
    return None
