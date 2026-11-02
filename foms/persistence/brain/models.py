"""HAUD master brain 표 다섯(ORM) — DDL 정본은 마이그레이션 ``brain_00`` + ``brain_01``(제안 줄 액션 이름 · 기준 판 바뀜 칸)과
같다(``tests/domains/test_brain_store.py`` 가 견준다).

설계서 2026-11-02-haud-master-brain 4절 · 6절 · 7.5 끝 '저장 꼴' · 10.3.

- ``BrainObject`` · ``BrainLink`` 는 **쌓기만 하는 판 행**이다. 고침 = 새 판 줄 + 앞 줄 ``superseded_at``. 쓰는 길은
  :mod:`foms.services.brain.apply` 한 곳뿐이다(설계서 5절 '액션으로만').
- '지금 판은 하나'는 부분 유일 색인(``superseded_at IS NULL``)이 막는다 — PostgreSQL · SQLite 모두(``sqlite_where``).
- 사람 번호 칸에는 FK 가 없다 — 계정을 지워도 지식 이력이 남는다(설계서 17.5). 손님 · 직원 개인정보 칸은 없다.
- 이 모듈은 :mod:`models` 끝에서 불려 ``Base`` 에 올라간다(create_all 레인 · alembic env 모두 같은 metadata).
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Column, Date, DateTime, DDL, Index, Integer, String, Text, event, func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB

from db import Base

_JSON = JSON().with_variant(JSONB, 'postgresql')
#: 지금 줄(대체되지 않은 판) 조건 — 부분 색인 · 읽기 질의가 같은 글자를 쓴다.
CURRENT_SQL = 'superseded_at IS NULL'


def _utcnow() -> datetime.datetime:
    """UTC naive 지금(다른 표의 ``now_utc_naive`` 와 같은 뜻 — persistence 는 services 를 import 하지 않는다)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _current_index(name: str, *columns: str, unique: bool = False) -> Index:
    """지금 줄만 담는 부분 색인(PostgreSQL · SQLite 같은 조건)."""
    where = sql_text(CURRENT_SQL)
    return Index(name, *columns, unique=unique, postgresql_where=where, sqlite_where=where)


class _VersionRow:
    """판 행 공통 칸 — 확신 · 유효 기간 · 기록 · 대체 시각 · 근거 · 만든 이 · 사람 승인자 · 제안 · 판."""

    confidence = Column(String(16), nullable=False)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=_utcnow, server_default=func.now())
    superseded_at = Column(DateTime, nullable=True)
    evidence_kind = Column(String(16), nullable=True)
    evidence_ref = Column(String(200), nullable=True)
    created_by = Column(String(64), nullable=False)  # 'user:<id>' · 'agent:<이름>' · 'import'
    human_approver_id = Column(Integer, nullable=True)  # 사람 승인 동작만 채움(R10-18) — FK 없음
    change_id = Column(Integer, nullable=True)
    release_no = Column(Integer, nullable=True)


class BrainObject(_VersionRow, Base):
    """지식 항목 판 한 줄. ``item_key`` 는 전역 키, ``version`` 은 그 키의 판 번호(1 부터)."""

    __tablename__ = 'brain_objects'

    id = Column(Integer, primary_key=True)
    item_key = Column(String(120), nullable=False)
    version = Column(Integer, nullable=False)
    brand = Column(String(8), nullable=False)  # LAHOM · HAUD · COMMON
    layer = Column(String(16), nullable=False)
    item_type = Column(String(32), nullable=False)
    name = Column(String(200), nullable=False)
    text = Column(Text, nullable=True)
    status = Column(String(16), nullable=False)
    risk_grade = Column(String(8), nullable=True)
    checked_at = Column(Date, nullable=True)
    stale_after = Column(Date, nullable=True)
    evidence_count = Column(Integer, nullable=False, default=0, server_default=sql_text('0'))
    visibility = Column(String(32), nullable=False)
    copies = Column(_JSON, nullable=True)
    usage_count = Column(Integer, nullable=False, default=0, server_default=sql_text('0'))
    payload = Column(_JSON, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('draft','active','retired')", name='ck_brain_objects_status'),
        CheckConstraint("confidence IN ('confirmed','evidenced','observed')", name='ck_brain_objects_confidence'),
        CheckConstraint("layer IN ('common','cs','drawing','production')", name='ck_brain_objects_layer'),
        Index('uq_brain_objects_key_version', 'item_key', 'version', unique=True),
        _current_index('uq_brain_objects_current_key', 'item_key', unique=True),
        _current_index('uq_brain_objects_current_brand_type_key', 'brand', 'item_type', 'item_key', unique=True),
        _current_index('ix_brain_objects_layer_type', 'layer', 'item_type'),
        Index('ix_brain_objects_name_trgm', 'name', postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'},
              postgresql_where=sql_text(CURRENT_SQL)).ddl_if(dialect='postgresql'),
        Index('ix_brain_objects_text_trgm', 'text', postgresql_using='gin', postgresql_ops={'text': 'gin_trgm_ops'},
              postgresql_where=sql_text(CURRENT_SQL)).ddl_if(dialect='postgresql'),
    )


# trgm 색인은 pg_trgm 확장이 있어야 만들어진다 — create_all 레인에서 이 표가 orders 보다 먼저 만들어질 수 있다(이름 순).
event.listen(BrainObject.__table__, 'before_create',
             DDL('CREATE EXTENSION IF NOT EXISTS pg_trgm').execute_if(dialect='postgresql'))


class BrainLink(_VersionRow, Base):
    """종류 있는 링크 판 한 줄 — (종류, 시작 키, 끝 키)가 정체. 끝 키는 brain 키 또는 바깥 정본(``calc:`` · ``setting:``)."""

    __tablename__ = 'brain_links'

    id = Column(Integer, primary_key=True)
    kind = Column(String(16), nullable=False)
    from_key = Column(String(120), nullable=False)
    to_key = Column(String(120), nullable=False)
    version = Column(Integer, nullable=False)
    payload = Column(_JSON, nullable=True)

    __table_args__ = (
        CheckConstraint("confidence IN ('confirmed','evidenced','observed')", name='ck_brain_links_confidence'),
        Index('uq_brain_links_identity_version', 'kind', 'from_key', 'to_key', 'version', unique=True),
        _current_index('uq_brain_links_current', 'kind', 'from_key', 'to_key', unique=True),
        _current_index('ix_brain_links_from_kind', 'from_key', 'kind'),
        _current_index('ix_brain_links_to_kind', 'to_key', 'kind'),
    )


class BrainChange(Base):
    """제안 한 줄 — 칸별 전 → 후(``fields``) · 기준 판 · 까닭 · 근거 id · 등급 · 층 · 관문 결과 · 상태 · 결정."""

    __tablename__ = 'brain_changes'

    id = Column(Integer, primary_key=True)
    op = Column(String(16), nullable=False)
    item_key = Column(String(120), nullable=True)
    link_kind = Column(String(16), nullable=True)
    link_from = Column(String(120), nullable=True)
    link_to = Column(String(120), nullable=True)
    brand = Column(String(8), nullable=True)
    layer = Column(String(16), nullable=True)
    item_type = Column(String(32), nullable=True)
    base_version = Column(Integer, nullable=True)
    fields = Column(_JSON, nullable=True)  # {칸: {"before": …, "after": …}}
    reason = Column(Text, nullable=True)
    evidence = Column(_JSON, nullable=True)  # 근거 id 목록
    grade = Column(String(8), nullable=False)
    gates = Column(_JSON, nullable=True)
    status = Column(String(16), nullable=False)
    reject_code = Column(String(24), nullable=True)
    rollback_of_version = Column(Integer, nullable=True)
    proposed_by = Column(String(64), nullable=False)
    decided_by = Column(Integer, nullable=True)  # 사람(로그인 사용자)만 — FK 없음
    result_version = Column(Integer, nullable=True)
    release_no = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow, server_default=func.now())
    decided_at = Column(DateTime, nullable=True)
    # brain_01 — 만든 액션 · 닫은 액션 이름(정본 목록 foms/services/brain/actions.py) · 기준 판이 바뀐 때(D104)
    action = Column(String(32), nullable=True)
    decided_action = Column(String(32), nullable=True)
    base_changed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("op IN ('create','update','retire','delete','link_add','link_remove')",
                        name='ck_brain_changes_op'),
        CheckConstraint("status IN ('open','applied','rejected','expired')", name='ck_brain_changes_status'),
        Index('ix_brain_changes_status_created', 'status', 'created_at'),
        Index('ix_brain_changes_item_key', 'item_key', 'status'),
    )


class BrainRelease(Base):
    """하루 판 · 층 한 줄 — 같은 번호는 그날 모든 층이 같이 쓴다(층마다 되돌릴 수 있게 층 칸)."""

    __tablename__ = 'brain_releases'

    id = Column(Integer, primary_key=True)
    number = Column(Integer, nullable=False)
    layer = Column(String(16), nullable=False)
    day = Column(Date, nullable=False)
    counts = Column(_JSON, nullable=True)  # 동작 → 수
    diff = Column(_JSON, nullable=True)  # 키만(글 없음)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=_utcnow, server_default=func.now())

    __table_args__ = (
        CheckConstraint("layer IN ('common','cs','drawing','production')", name='ck_brain_releases_layer'),
        Index('uq_brain_releases_number_layer', 'number', 'layer', unique=True),
        Index('ix_brain_releases_day', 'day'),
    )


class BrainQuestion(Base):
    """직원 챗봇 기록 한 줄(설계서 10.3) — 가린 글만. ``asker_id`` 는 ADMIN 만 본다(직원별 모아 보기 화면 없음)."""

    __tablename__ = 'brain_questions'

    id = Column(Integer, primary_key=True)
    asked_at = Column(DateTime, nullable=False, default=_utcnow, server_default=func.now())
    asker_id = Column(Integer, nullable=True)
    masked_question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    evidence_keys = Column(_JSON, nullable=True)
    unknown = Column(Boolean, nullable=False, default=False, server_default=sql_text('false'))
    confidence = Column(String(16), nullable=True)
    ask_team = Column(String(16), nullable=True)
    layer = Column(String(16), nullable=True)
    feedback = Column(String(16), nullable=True)
    feedback_note = Column(Text, nullable=True)
    model = Column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint("feedback IN ('helpful','not_helpful','wrong')", name='ck_brain_questions_feedback'),
        Index('ix_brain_questions_asked_at', 'asked_at'),
    )
