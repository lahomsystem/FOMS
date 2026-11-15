"""FOMS 접목판 표 셋(ORM) — DDL 정본은 마이그레이션 ``graft_00`` 과 같다(``tests/domains/test_graft_store.py`` 가 견준다).

설계서 2026-11-14-foms-graft 3.4.

- ``ErpActionProposal`` (``erp_action_proposals``) — AI 직원이 만든 ERP 할 일 제안 한 줄. 회사 지식 제안 표(``brain_changes``)를
  다시 쓰지 않는다(그 표의 검사 제약 · 제안함 질의가 지식 꼴을 믿는다). 생명주기는 :mod:`foms.services.erp_actions.lifecycle`.
- ``BrainUsageEvent`` (``brain_usage_events``) — '쓰인 곳' 한 번 한 줄(지식 키 · ERP 물건 키 ``erp:order/<번호>``). 합 표
  ``brain_usage`` 는 그대로 둔다. 쓰기 · 읽기 도우미는 :mod:`foms.services.brain.usage_events`.
- ``AiAgentRun`` (``ai_agent_runs``) — AI 직원 실행 기록(단계마다 도구 · 걸린 시간 — 코드 · 수만, 글 없음).

- 주문 · 사람 번호 칸에는 FK 가 없다 — 주문 · 계정을 지워도 기록은 남는다(감사 원장 규칙).
- '같은 할 일 제안은 열린 것 하나'는 부분 유일 색인(``status = 'open'``)이 막는다 — PostgreSQL · SQLite 모두(``sqlite_where``).
- 이 모듈은 services 를 import 하지 않는다(층 규칙). 상태 이름 목록은 :mod:`foms.services.erp_actions.registry` 와 같은
  글자이고 시험이 견준다.
"""

from __future__ import annotations

import datetime
from typing import Sequence

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Index, Integer, String, Text, func
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB

from db import Base

_JSON = JSON().with_variant(JSONB, 'postgresql')

#: 제안 상태 일곱(생명주기 — 설계서 3.4). 검사 제약 · 마이그레이션 · 할 일 목록이 같은 글자를 쓴다.
PROPOSAL_STATUSES: tuple[str, ...] = (
    'open', 'executing', 'executed', 'failed', 'rejected', 'expired', 'superseded',
)
#: 열린 제안 조건 — 부분 유일 색인 · 읽기 질의가 같은 글자를 쓴다.
OPEN_SQL = "status = 'open'"


def _utcnow() -> datetime.datetime:
    """UTC naive 지금(다른 표의 ``now_utc_naive`` 와 같은 뜻 — persistence 는 services 를 import 하지 않는다)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(마이그레이션 ``in_check`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


class ErpActionProposal(Base):
    """할 일 제안 한 줄 — 무엇을(``action``) · 누가(``proposed_by``) · 어느 주문에 · 넣을 값 · 미리 본 바뀜 · 근거 · 상태 · 결정 · 결과."""

    __tablename__ = 'erp_action_proposals'

    id = Column(Integer, primary_key=True)
    action = Column(String(40), nullable=False)  # 할 일 목록 이름(foms/services/erp_actions/registry.py)
    proposed_by = Column(String(64), nullable=False)  # 'agent:cs' · 'agent:ops' · 'agent:schedule'
    order_id = Column(Integer, nullable=True)  # FK 없음 — 주문을 지워도 기록은 남는다
    params = Column(_JSON, nullable=True)  # 실행기에 넣을 값(개인정보 꼴 없음)
    preview = Column(_JSON, nullable=True)  # [{"field", "before", "after"}] — 제안 때 계산
    reason = Column(Text, nullable=True)  # 가린 글만 · 500자
    evidence = Column(_JSON, nullable=True)  # [{"kind", "ref", "label"}] 여덟까지
    level = Column(Integer, nullable=False)  # 제안 때 수준(1 · 2)
    status = Column(String(16), nullable=False)
    reject_code = Column(String(24), nullable=True)
    base_version = Column(Integer, nullable=True)  # 제안 때 orders.mutation_version
    dedupe_key = Column(String(120), nullable=False)  # '<action>:<order_id>:<값 지문>'
    source_kind = Column(String(16), nullable=True)  # 'cs_turn' · 'sweep' …
    source_ref = Column(String(64), nullable=True)
    decided_by = Column(Integer, nullable=True)  # 사람(로그인 사용자)만 — FK 없음
    decided_at = Column(DateTime, nullable=True)
    decided_action = Column(String(16), nullable=True)
    view_ms = Column(Integer, nullable=True)
    edited_params = Column(_JSON, nullable=True)  # 고쳐서 승인한 값
    result = Column(_JSON, nullable=True)  # 실행 결과(코드 · 변경 묶음 번호 — 글 없음)
    error_code = Column(String(48), nullable=True)
    snoozed_until = Column(DateTime, nullable=True)
    snoozed_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(_in_check('status', PROPOSAL_STATUSES), name='ck_erp_action_proposals_status'),
        Index('ix_erp_action_proposals_status_created', 'status', 'created_at'),
        Index('ix_erp_action_proposals_order_status', 'order_id', 'status'),
        Index('uq_erp_action_proposals_open_dedupe', 'dedupe_key', unique=True,
              postgresql_where=sql_text(OPEN_SQL), sqlite_where=sql_text(OPEN_SQL)),
    )


class BrainUsageEvent(Base):
    """쓰인 곳 한 줄 — 어느 키(지식 · ERP 물건)를 · 어느 쪽이(``reader``) · 무엇 때문에(``ref_kind`` · ``ref_id``) · 언제."""

    __tablename__ = 'brain_usage_events'

    id = Column(Integer, primary_key=True)
    item_key = Column(String(120), nullable=False)
    reader = Column(String(16), nullable=False)  # 'cs_draft' · 'erp_action' · 'chatbot'
    ref_kind = Column(String(16), nullable=False)
    ref_id = Column(String(64), nullable=False)
    used_at = Column(DateTime, nullable=False, default=_utcnow, server_default=func.now())

    __table_args__ = (
        Index('ix_brain_usage_events_key_used', 'item_key', 'used_at'),
        Index('ix_brain_usage_events_ref', 'ref_kind', 'ref_id'),
    )


class AiAgentRun(Base):
    """AI 직원 실행 한 번 — 누가 · 언제 · 전체 걸린 시간 · 무엇 때문에 · 단계(도구 · 한 일 · 걸린 시간) · 끝 · 만든 제안 수."""

    __tablename__ = 'ai_agent_runs'

    id = Column(Integer, primary_key=True)
    agent = Column(String(16), nullable=False)  # foms/services/ai_staff/registry.py 의 열쇠
    started_at = Column(DateTime, nullable=False, default=_utcnow, server_default=func.now())
    total_ms = Column(Integer, nullable=True)
    source_kind = Column(String(16), nullable=True)
    source_ref = Column(String(64), nullable=True)
    steps = Column(_JSON, nullable=True)  # [{"tool", "what", "detail", "ms"}] — 코드 · 수만
    outcome = Column(String(24), nullable=True)
    proposals = Column(Integer, nullable=False, default=0, server_default=sql_text('0'))

    __table_args__ = (
        Index('ix_ai_agent_runs_agent_started', 'agent', 'started_at'),
    )
