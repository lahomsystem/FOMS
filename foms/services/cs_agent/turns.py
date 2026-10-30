"""초안 차례 기록 — (상담, 마지막 손님 글 id) 선점 · 상태 · 시도 상한 · '올리는 중' 복구 재료 · 초안 스위치.

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C3-1(중복 방지는 DB) · C3-3 · 설계서 4절 8 · 9 · 6절. 원장 R1-2 · R1-3 ·
R1-20 · R1-22. 표는 ``models.CsAgentTurn``(마이그레이션 ``csagent_01``). **함수는 커밋하지 않는다 — 부르는 쪽이 커밋한다.**

- **선점(R1-2)**: (상담, 마지막 손님 글 id) 고유 줄을 '있으면 무시하고 넣기'(``INSERT … ON CONFLICT DO NOTHING RETURNING``
  — SQLite · PostgreSQL 같은 문장)로 만든다. 이미 있으면 ``None`` — 손님 글 하나에 메모는 하나다. 실패로 끝난 줄만
  :data:`MAX_ATTEMPTS` 전까지 같은 줄을 다시 집는다(조건부 UPDATE 한 문장 — 둘이 겹쳐도 하나만 집는다).
- **상태**: ``claimed`` → ``posting`` → ``posted``, 또는 ``claimed`` → ``stored`` · ``skipped``, ``claimed`` · ``posting`` →
  ``failed``. 빠른 길(C10-1)이 둘을 더한다 — ``claimed`` · ``posted`` · ``stored`` → ``superseded``(손님이 더 써서 갈아 끼움 —
  '지난 초안', :func:`mark_superseded`), ``claimed`` · ``failed`` → ``staff_replied``(직원이 먼저 공개 답 — :func:`mark_staff_replied`).
- **주인 · 만료(원장 R10-2)**: 선점할 때 주인(:func:`claim_owner`)과 만료(지금 + ``ttl``)를 적는다. 만료가 지난 ``claimed`` 줄
  (:func:`expired_claims`)은 죽은 차례다 — 정리하는 쪽이 ``failed`` 로 바꾸면 시도 상한 안에서 다시 집힌다. 살아 있던 주인이
  나중에 쓰려 해도 조건부 쓰기가 0 줄이라 올리지 않는다. '올리는 중'은 채널톡을 부르기 **전에** 커밋한다(R1-3) — 재시작 때 남은 줄은 :func:`stale_posting` 으로 찾아
  채널톡의 우리 봇 메모와 맞춘다. 올라갔는지 모르는 실패는 ``failed`` 로 바꾸지 않는다(다시 집으면 메모가 둘이 된다).
  설정 문제 · 401 · 403 · 돈 상한은 :func:`release_turn` — 시도를 세지 않고 ``failed`` 로 돌려놓는다(원장 R7-4).
- **조건부 쓰기(원장 R7-8)**: 줄을 쓰는 함수는 모두 한 문장 ``UPDATE … WHERE id AND state = 지금 상태 AND attempts =
  선점 때 시도 수`` 다. 선점한 세션은 그 시도 수를 줄에 따로 붙여 두므로(칸 아님) 커밋 뒤 줄을 다시 읽어도 바뀌지 않는다 —
  그사이 다른 바퀴가 정리 · 다시 집기를 했으면 바뀐 줄이 0 이라 :class:`TurnConflict` 이고 부르는 쪽은 올리지 않는다.
- **글(R1-20)**: 가린 칸(``masked_draft`` · ``staff_reply_masked``)에만 글을 둔다. 받은 글도 한 번 더 가리고
  가림 검사(:func:`~foms.services.cs_agent.masking.require_masked`)가 0 일 때만 넣는다. 두뇌 결과는 코드 · 숫자 칸만 옮긴다.
- **초안 스위치(설계서 6절 · R1-22)**: 바로 끄기 줄(:data:`SWITCH_KEY`)의 ``draft`` 칸 — ``off`` · ``store``(저장만) ·
  ``memo``. 줄 · 칸이 없거나 값이 비었거나 꼴이 틀리면 ``off``(막는 쪽으로 닫힘). ``loop`` 칸은 감시 루프 규칙 그대로다.
  막는 장치는 :func:`set_draft_mode` 로 그 칸만 바꾼다(다른 칸은 그대로 — R7-1 · R7-2). 다시 켜는 것은 사람이다.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import socket
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import object_session
from sqlalchemy.orm.attributes import set_committed_value

from foms.persistence.main.models import CsAgentTurn, SystemSetting
from foms.services.cs_agent.channel_read import CHANNEL_BRANDS, naive_utc
from foms.services.cs_agent.turns_fields import (  # 칸 꼴 검사(500줄 상한으로 나눔)
    ID_PATTERN as _ID, check_codes as _check_codes, checked_id as _checked_id, code as _code, cost as _cost,
    count as _count, masked_or_none as _masked_or_none, reason as _reason,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DRAFT_MEMO", "DRAFT_MODES", "DRAFT_OFF", "DRAFT_STORE", "MAX_ATTEMPTS", "STATES", "SWITCH_KEY", "SWITCH_OFF",
    "SWITCH_ON", "TurnConflict", "TurnStateError", "claim_owner", "claim_turn", "draft_mode", "expired_claims", "retry_due",
    "mark_failed", "mark_posted", "mark_posting", "mark_skipped", "mark_staff_replied", "mark_stored", "mark_superseded",
    "read_switch", "record_brain_result", "record_handoff", "record_staff_reply", "release_turn", "set_draft_mode",
    "stale_posting",
]

STATE_CLAIMED, STATE_POSTING, STATE_POSTED = "claimed", "posting", "posted"
STATE_STORED, STATE_SKIPPED, STATE_FAILED = "stored", "skipped", "failed"
STATE_SUPERSEDED, STATE_STAFF_REPLIED = "superseded", "staff_replied"  # 빠른 길 — '지난 초안' · '직원 답함'
STATES: tuple[str, ...] = (STATE_CLAIMED, STATE_POSTING, STATE_POSTED, STATE_STORED, STATE_SKIPPED, STATE_FAILED,
                           STATE_SUPERSEDED, STATE_STAFF_REPLIED)
#: 손님 글 하나에 차례를 여는 상한(두뇌 호출 상한 — 원장 R1-3). 실패로 끝난 줄은 이 수까지만 다시 집는다.
MAX_ATTEMPTS = 3
#: 만료를 적지 않은 옛 선점 줄(csagent_02 전)은 이만큼 손대지 않았으면 죽은 차례로 본다(예전 15분 바퀴 정리 기준).
LEGACY_CLAIM_AFTER = datetime.timedelta(minutes=20)
#: 실패 줄 다시 집기 간격 — 시도 수마다 이만큼 더 기다린다(짧은 장애에 시도 셋을 몇 초 만에 다 쓰지 않게, 검수 R13-3).
RETRY_STEP = datetime.timedelta(seconds=30)
#: 만료로 정리한 실패는 이미 만료(시간 상한 + 여유)만큼 기다렸다 — 다시 집기 간격을 더하지 않는다.
CLAIM_EXPIRED = "claim_expired"

#: 바로 끄기 줄 — ``loop.SWITCH_KEY`` 와 같은 줄이다(loop 가 이 모듈을 부를 쪽이라 거꾸로 import 하지 않는다 · 시험이 맞춘다).
SWITCH_KEY = "cs_agent_switch"
LOOP_FIELD = "loop"
SWITCH_ON, SWITCH_OFF = "on", "off"
DRAFT_FIELD = "draft"
DRAFT_OFF, DRAFT_STORE, DRAFT_MEMO = "off", "store", "memo"
DRAFT_MODES: tuple[str, ...] = (DRAFT_OFF, DRAFT_STORE, DRAFT_MEMO)

_TURNS = CsAgentTurn.__table__
_INSERT_BUILDERS: dict[str, Callable[[Any], Any]] = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}
#: 선점한 세션이 줄에 붙여 두는 '선점 때 시도 수'(파이썬 값 — 표 칸이 아니라 커밋 · 다시 읽기에도 그대로 남는다).
_CLAIM_ATTR = "_cs_claimed_attempts"
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


class TurnStateError(RuntimeError):
    """허락되지 않은 상태 바꾸기 — 부르는 쪽 실수다(메시지엔 상태 이름만)."""


class TurnConflict(TurnStateError):
    """조건부 쓰기가 0 줄을 바꿨다 — 그사이 다른 바퀴가 그 줄을 바꿨다(정리 · 다시 집기). 부르는 쪽은 올리지 않는다."""


# ── 선점 ─────────────────────────────────────────────────────────────────
def claim_owner(kind: str) -> str:
    """선점 주인 이름 — ``<길>:<호스트>:<pid>``(빈칸 없는 ASCII 64자까지). 로그 · 기록의 '누가 집었나' 표지다."""
    raw = f"{kind}:{socket.gethostname()}:{os.getpid()}"
    return re.sub(r"[^\x21-\x7e]", "-", raw)[:64]


def claim_turn(session: Any, brand: str, chat_id: str, last_user_message_id: str, *,
               now: datetime.datetime, owner: Optional[str] = None,
               ttl: Optional[datetime.timedelta] = None) -> Optional[CsAgentTurn]:
    """(상담, 마지막 손님 글 id) 차례를 선점한다 — 새 줄(또는 다시 집은 실패 줄)이면 그 줄, 이미 있으면 ``None``.

    부르는 쪽은 받은 줄을 **바로 커밋**한다. PostgreSQL 에서 두 바퀴가 겹치면 뒤 바퀴의 넣기는 앞 바퀴가 커밋 · 되돌리기를
    할 때까지 기다렸다가 아무것도 넣지 않는다(되돌렸으면 뒤 바퀴가 집는다).

    Args:
        session: DB 세션.
        brand: 상담 브랜드(채널 짝 상수에 있는 이름).
        chat_id: 채널톡 상담 id.
        last_user_message_id: 이 차례를 연 손님 글의 채널톡 메시지 id.
        now: 지금(시간대 있는 값 — 표에는 UTC naive).
        owner: 선점 주인(:func:`claim_owner` — 없으면 비움).
        ttl: 선점 만료까지(없으면 비움 — 정리는 ``updated_at`` 로 본다).

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
    if owner is not None and not _ID.fullmatch(owner):
        raise ValueError("선점 주인 꼴이 아니다")
    at = naive_utc(now)
    claim = {"claim_owner": owner, "claim_expires_at": None if ttl is None else at + ttl}
    builder = _INSERT_BUILDERS.get(session.get_bind().dialect.name)
    if builder is None:
        raise RuntimeError("있으면 무시하고 넣기를 모르는 DB")
    inserted = (builder(_TURNS)
                .values(brand=brand, chat_id=chat_id, last_user_message_id=last_user_message_id,
                        state=STATE_CLAIMED, attempts=1, created_at=at, updated_at=at, **claim)
                .on_conflict_do_nothing(index_elements=["chat_id", "last_user_message_id"])
                .returning(_TURNS.c.id))
    turn_id = session.execute(inserted).scalar()
    if turn_id is None:
        retry = (update(_TURNS)
                 .where(_TURNS.c.chat_id == chat_id, _TURNS.c.last_user_message_id == last_user_message_id,
                        _TURNS.c.state == STATE_FAILED, _TURNS.c.attempts < MAX_ATTEMPTS)
                 .values(state=STATE_CLAIMED, attempts=_TURNS.c.attempts + 1, error_code=None, updated_at=at, **claim)
                 .returning(_TURNS.c.id))
        turn_id = session.execute(retry).scalar()
    if turn_id is None:
        return None
    turn = session.get(CsAgentTurn, turn_id, populate_existing=True)
    setattr(turn, _CLAIM_ATTR, int(turn.attempts))  # 이 세션의 선점 표지 — 뒤 쓰기는 모두 이 시도 수를 조건으로 건다
    return turn


# ── 상태 바꾸기(조건부 UPDATE 한 문장 — 커밋은 부르는 쪽) ──────────────────
def mark_posting(row: CsAgentTurn, *, masked_draft: Optional[str], check_codes: Iterable[Any] = (),
                 now: datetime.datetime) -> None:
    """'올리는 중' — 메모를 올리기 바로 전. 부르는 쪽이 **커밋한 뒤에** 채널톡을 부른다(R1-3).

    올릴 초안의 가린 사본(``None`` 이면 두지 않음)과 검사 코드를 같이 적는다. 가림 검사가 0 이 아니면 아무것도 바꾸지
    않고 :class:`~foms.services.cs_agent.masking.MaskLeak`. 그사이 줄을 다른 바퀴가 바꿨으면 :class:`TurnConflict`.
    """
    draft, codes = _masked_or_none(masked_draft), _check_codes(check_codes)
    _write(row, (STATE_CLAIMED,), {"masked_draft": draft, "check_codes": codes}, target=STATE_POSTING, now=now)


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
    _write(row, (STATE_POSTING,), {"memo_message_id": message_id, "error_code": code}, target=STATE_POSTED, now=now)


def mark_stored(row: CsAgentTurn, *, masked_draft: Optional[str], check_codes: Iterable[Any] = (),
                now: datetime.datetime) -> None:
    """저장만 — 초안을 기록에만 두고 올리지 않는다(초안 스위치 ``store`` · 운영 밖 허용 목록 밖 상담)."""
    draft, codes = _masked_or_none(masked_draft), _check_codes(check_codes)
    _write(row, (STATE_CLAIMED,), {"masked_draft": draft, "check_codes": codes}, target=STATE_STORED, now=now)


def mark_skipped(row: CsAgentTurn, *, reason: str, check_codes: Iterable[Any] = (),
                 masked_draft: Optional[str] = None, now: datetime.datetime) -> None:
    """건너뜀 — 이 차례엔 올리지 않는다(넘김 · 검사에 걸림 · 그사이 사람이 답함 · 손님이 더 씀 등). 이유는 ``error_code``."""
    code, draft, codes = _reason(reason), _masked_or_none(masked_draft), _check_codes(check_codes)
    _write(row, (STATE_CLAIMED,), {"error_code": code, "masked_draft": draft, "check_codes": codes},
           target=STATE_SKIPPED, now=now)


def mark_failed(row: CsAgentTurn, *, error_code: str, now: datetime.datetime) -> bool:
    """실패 — 채널톡에 아무것도 안 올라갔을 때만 쓴다(올라갔는지 모르면 '올리는 중'으로 두고 복구 단계에 맡긴다).

    Returns:
        다시 집을 수 있으면 True(선점 횟수 < :data:`MAX_ATTEMPTS`) — 다음 바퀴의 :func:`claim_turn` 이 같은 줄을 집는다.
    """
    code = _reason(error_code)
    _write(row, (STATE_CLAIMED, STATE_POSTING), {"error_code": code}, target=STATE_FAILED, now=now)
    return int(row.attempts or 0) < MAX_ATTEMPTS


def release_turn(row: CsAgentTurn, *, error_code: str, now: datetime.datetime) -> None:
    """선점을 시도로 세지 않고 돌려놓는다 — ``failed`` + 시도 수 하나 되돌림(원장 R7-4). 다음 바퀴가 같은 시도 수로 다시 집는다.

    손님 차례 탓이 아닌 멈춤(두뇌 설정이 안 됨 · 401 · 403 · 돈 상한)에 쓴다 — 그런 바퀴가 이어져도 차례가 시도 상한에 닿아
    영영 끝나지 않는다. 선점한 줄(``claimed``)만.
    """
    _write(row, (STATE_CLAIMED,), {"error_code": _reason(error_code)}, target=STATE_FAILED, now=now, attempts_delta=-1)


def mark_superseded(row: CsAgentTurn, *, masked_draft: Optional[str] = None, check_codes: Iterable[Any] = (),
                    now: datetime.datetime) -> None:
    """지난 초안 — 집은 뒤(만드는 중 · 올린 뒤) 같은 상담에 손님 새 글이 와 이 차례를 갈아 끼운다(빠른 길, 설계서 17.2).

    선점한 줄이면 만든 초안의 가린 사본 · 검사 코드를 같이 적는다(``None`` 이면 두지 않음). 올렸거나 저장한 줄은 칸을 그대로
    두고 상태만 바꾼다. 앞 메모를 지울지는 부르는 쪽 몫이다(C10-2 시험 뒤).
    """
    values: dict[str, Any] = {}
    if masked_draft is not None:
        values = {"masked_draft": _masked_or_none(masked_draft), "check_codes": _check_codes(check_codes)}
    _write(row, (STATE_CLAIMED, STATE_POSTED, STATE_STORED), values, target=STATE_SUPERSEDED, now=now)


def mark_staff_replied(row: CsAgentTurn, *, masked_draft: Optional[str] = None, now: datetime.datetime) -> None:
    """직원 답함 — 직원이 먼저 공개 답을 해 아직 안 끝난 차례(선점 · 실패)를 닫는다. 초안은 올리지 않는다(빠른 길)."""
    values = {} if masked_draft is None else {"masked_draft": _masked_or_none(masked_draft)}
    _write(row, (STATE_CLAIMED, STATE_FAILED), values, target=STATE_STAFF_REPLIED, now=now)


def record_handoff(row: CsAgentTurn, *, reason: str) -> None:
    """두뇌 없이 코드가 사람에게 넘긴 까닭(넘김 칸)을 선점한 줄에 적는다 — 예: 손님이 'AI 냐 사람이냐' 물음(설계서 17.8)."""
    _write(row, (STATE_CLAIMED,), {"handoff": True, "handoff_reason": _reason(reason)})


def expired_claims(session: Any, now: datetime.datetime, *, limit: int = 100) -> list[CsAgentTurn]:
    """죽은 선점 — 만료(``claim_expires_at``)가 ``now`` 보다 앞인 ``claimed`` 줄, 오래된 것부터. 15분 바퀴 정리와 빠른 길이 같이 쓴다.

    만료를 적지 않은 옛 줄은 ``updated_at`` 이 :data:`LEGACY_CLAIM_AFTER` 넘게 지났을 때 죽은 차례로 본다(검수 R13 — 한 규칙).
    """
    at = naive_utc(now)
    dead = or_(CsAgentTurn.claim_expires_at < at,
               and_(CsAgentTurn.claim_expires_at.is_(None), CsAgentTurn.updated_at < at - LEGACY_CLAIM_AFTER))
    stmt = (select(CsAgentTurn)
            .where(CsAgentTurn.state == STATE_CLAIMED, dead)
            .order_by(CsAgentTurn.updated_at, CsAgentTurn.id)
            .limit(int(limit))
            .execution_options(populate_existing=True))
    return list(session.scalars(stmt))


def retry_due(row: Any, now: datetime.datetime) -> bool:
    """실패 줄을 지금 다시 집어도 되나 — 시도 상한 전이고 ``updated_at + RETRY_STEP × 시도 수`` 가 지났을 때(한 규칙, R13-2 · 3).

    ``row`` 는 ``state`` · ``attempts`` · ``error_code`` · ``updated_at``(UTC naive) 칸이 있는 줄 · 읽은 꼴이면 된다.
    만료로 정리한 줄(:data:`CLAIM_EXPIRED`)은 이미 만료만큼 기다렸으니 바로 집는다.
    """
    attempts = int(row.attempts or 0)
    if row.state != STATE_FAILED or attempts >= MAX_ATTEMPTS:
        return False
    if row.error_code == CLAIM_EXPIRED or row.updated_at is None:
        return True
    return naive_utc(now) >= row.updated_at + RETRY_STEP * attempts


def record_brain_result(row: CsAgentTurn, result: Any) -> None:
    """두뇌 결과에서 코드 · 숫자 칸만 옮긴다(덕 타이핑 — 없는 속성은 비운다). 초안 · 직원 참고 같은 글은 옮기지 않는다.

    읽는 속성: ``intent`` · ``handoff`` · ``fallback_used``(참 · 거짓) · ``handoff_reason`` · ``model`` · ``effort`` ·
    ``input_tokens`` · ``output_tokens`` · ``cache_read_tokens``(또는 ``cache_read_input_tokens``) ·
    ``cache_write_tokens``(또는 ``cache_creation_input_tokens``) · ``cost_usd`` · ``latency_ms``. 꼴이 틀린 값(글처럼 생긴
    코드 · 음수)은 비우고 경고한다. 대체 모델이 답했으면 ``fallback_used`` 가 참이다(설계서 11.1 의 4 · 원장 R7-12).

    Raises:
        TurnStateError: 선점한 줄(``claimed``)이 아니다(그사이 바뀌었으면 :class:`TurnConflict`).
    """
    values: dict[str, Any] = {column: _code(getattr(result, column, None), limit, column)
                              for column, limit in _BRAIN_CODES}
    for flag in ("handoff", "fallback_used"):
        value = getattr(result, flag, None)
        if value is not None and not isinstance(value, bool):
            logger.warning("[CS 초안] 기록 칸 꼴이 틀려 비운다 field=%s", flag)
            value = None
        values[flag] = value
    for column, names in _BRAIN_COUNTS:
        value = next((getattr(result, name) for name in names if getattr(result, name, None) is not None), None)
        values[column] = _count(value, column)
    values["cost_usd"] = _cost(getattr(result, "cost_usd", None))
    _write(row, (STATE_CLAIMED,), values)


def record_staff_reply(row: CsAgentTurn, staff_reply: Optional[str], *, judgment: Optional[str] = None,
                       now: datetime.datetime) -> None:
    """직원 최종 답(공개 manager 글)의 가린 사본과 '같은 뜻' 판정 코드를 끝난 줄에 적는다(R1-20 — 같은 가림 · 검사).

    Raises:
        MaskLeak: 가린 뒤에도 가림 검사가 0 이 아니다(아무것도 바꾸지 않는다).
        TurnStateError: 끝난 줄(``posted`` · ``stored`` · ``skipped``)이 아니다.
    """
    reply = _masked_or_none(staff_reply)
    code = _code(judgment, 16, "judgment")
    _write(row, (STATE_POSTED, STATE_STORED, STATE_SKIPPED), {"staff_reply_masked": reply, "judgment": code}, now=now)


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


def read_switch(session: Any) -> bool:
    """감시 루프 바로 끄기(``loop`` 칸) — 돌려도 되면 True. 줄이 없거나 ``{"loop": "on"}`` 이면 돈다.

    줄은 있는데 값이 비었거나(NULL) 꼴이 틀린 값(``{"loop": "of"}`` · 글자 하나 등)은 끈 것으로 본다 — 끄려고 손댄
    값이 오타로 켜진 채 남으면 안 된다(원장 R5-8). 감시 루프(바퀴 시작)와 초안 바퀴(두뇌 부르기 전마다)가 같이 쓴다 —
    ``loop.read_switch`` 는 이 함수다(loop 가 초안 바퀴를 부르므로 초안 바퀴가 loop 를 import 하지 않게 여기 둔다).
    """
    row = session.get(SystemSetting, SWITCH_KEY, populate_existing=True)
    if row is None:
        return True
    value = row.setting_value
    loop_value = value.get(LOOP_FIELD, SWITCH_ON) if isinstance(value, dict) else None
    if loop_value == SWITCH_ON:
        return True
    if loop_value != SWITCH_OFF:
        logger.warning("[CS 감시] 바로 끄기 값의 꼴이 틀려 끈 것으로 본다 key=%s", SWITCH_KEY)
    return False


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


def set_draft_mode(session: Any, mode: str, *, reason: str, now: datetime.datetime) -> dict:
    """초안 스위치(``draft`` 칸)만 바꾼다 — 줄을 잠그고 다른 칸(``loop`` · ``changed_at``)은 그대로, 버전 +1.

    ``loop.set_switch`` 와 같은 꼴이다(그쪽도 ``draft`` 칸을 남긴다). 막는 장치가 부른다: 공개로 확인된 메모 → ``off``,
    비공개를 확인 못 함 → ``store``(원장 R7-1 · R7-2). 바꾼 때 · 까닭 코드를 ``draft_changed_at`` · ``draft_reason`` 칸에
    남긴다. 커밋은 부르는 쪽(올림 기록과 한 트랜잭션). 다시 켜는 것은 사람이다.

    Returns:
        새로 쓴 값.
    """
    if mode not in DRAFT_MODES:
        raise ValueError("모르는 초안 스위치 값")
    code = _reason(reason)
    row = session.get(SystemSetting, SWITCH_KEY, populate_existing=True, with_for_update=True)
    old = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    value = {**old, DRAFT_FIELD: mode, "draft_changed_at": naive_utc(now).isoformat(timespec="seconds"),
             "draft_reason": code}
    if row is None:
        session.add(SystemSetting(setting_key=SWITCH_KEY, setting_value=value,
                                  description="AI 상담팀원 바로 끄기 · 초안 스위치(매 바퀴 읽음, 플랜 C1-3 · C3-1)"))
    else:
        row.setting_value = value
        row.version = int(row.version or 1) + 1
    return value


# ── 칸 꼴 ────────────────────────────────────────────────────────────────
def _write(row: CsAgentTurn, allowed: tuple[str, ...], values: dict[str, Any], *, target: Optional[str] = None,
           now: Optional[datetime.datetime] = None, attempts_delta: int = 0) -> None:
    """줄 쓰기 한 문장 — ``UPDATE … WHERE id AND state = 지금 상태 AND attempts = 선점 때 시도 수``(원장 R7-8).

    지금 상태가 ``allowed`` 밖이면 :class:`TurnStateError`(아무것도 안 씀). 바뀐 줄이 0 이면 :class:`TurnConflict` — 그사이
    다른 바퀴가 줄을 바꿨다. 시도 수는 선점 표지(없으면 지금 값)다. 성공하면 ORM 줄에도 같은 값을 '읽은 값'으로 넣는다
    (ORM 이 같은 줄을 조건 없이 다시 쓰지 않게).
    """
    session = object_session(row)
    if session is None:
        raise TurnStateError("세션에 없는 줄은 쓰지 않는다")
    changes = dict(values)
    if now is not None:
        changes["updated_at"] = naive_utc(now)
    state = row.state
    if state not in allowed:
        raise TurnStateError(f"{state} → {target or state} 는 허락되지 않는다")
    claimed = getattr(row, _CLAIM_ATTR, None)
    attempts = int(row.attempts if claimed is None else claimed)
    if target is not None:
        changes["state"] = target
    if attempts_delta:
        changes["attempts"] = attempts + attempts_delta
    stmt = (update(_TURNS).where(_TURNS.c.id == row.id, _TURNS.c.state == state, _TURNS.c.attempts == attempts)
            .values(changes))
    if session.execute(stmt).rowcount != 1:
        raise TurnConflict(f"{state} 줄이 그사이 바뀌었다 — 쓰지 않는다")
    for key, value in changes.items():
        set_committed_value(row, key, value)
