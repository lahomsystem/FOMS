"""GRAFT-00: FOMS 접목판 — 할 일 제안 · 쓰인 곳 기록 · AI 직원 실행 기록 표 셋

Revision ID: graft_00
Revises: prodpart_00
Create Date: 2026-11-14

설계 정본: ``docs/specs/2026-11-14-foms-graft_SPEC.md`` 3.4(사용자 "이대로 구현" 승인 11-14).

* ``erp_action_proposals`` — AI 직원이 만든 ERP 할 일 제안(제안 → 사람 승인 → 지금 기능 실행 → 기록). 회사 지식 제안 표
  ``brain_changes`` 를 다시 쓰지 않는다. 주문 · 사람 번호 칸에 FK 가 없다(감사 원장 — 주문을 지워도 기록이 남는다).
  '같은 할 일 제안은 열린 것 하나'는 부분 유일 색인 ``uq_erp_action_proposals_open_dedupe``(``status = 'open'``)이 막는다 —
  PostgreSQL · SQLite 둘 다.
* ``brain_usage_events`` — 쓰인 곳 한 번 한 줄(지식 키 · ERP 물건 키). 합 표 ``brain_usage`` 는 그대로 둔다.
* ``ai_agent_runs`` — AI 직원 실행 기록(단계마다 도구 · 걸린 시간 — 코드 · 수만).

**빈 표 셋을 더하기만** 한다(데이터를 바꾸지 않는다 · 빈 표라 CONCURRENTLY · advisory lock 이 필요 없다). ``downgrade()`` 는
표 셋을 지운다(그 사이에 쌓인 제안 · 쓰인 곳 · 실행 기록이 사라진다 — 주문 · 지식 · 감사 줄은 그대로). DDL 은
``foms/persistence/graft/models.py`` 와 같다(``tests/domains/test_graft_store.py`` 가 견준다). models 를 import 하지 않는다.
"""
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'graft_00'
down_revision: Union[str, None] = 'prodpart_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')

#: 제안 상태 일곱(작성 시점 스냅샷 — 모델 · 할 일 목록과 같은 글자인지는 시험이 본다).
PROPOSAL_STATUSES = ('open', 'executing', 'executed', 'failed', 'rejected', 'expired', 'superseded')
#: 열린 제안 조건(부분 유일 색인).
OPEN_SQL = "status = 'open'"

#: 표마다 칸 — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = 표 칸 순서(``id`` 다음).
COLUMNS: dict[str, tuple[tuple[str, sa.types.TypeEngine, bool, object], ...]] = {
    'erp_action_proposals': (
        ('action', sa.String(40), False, None),
        ('proposed_by', sa.String(64), False, None),
        ('order_id', sa.Integer(), True, None),
        ('params', _JSON, True, None),
        ('preview', _JSON, True, None),
        ('reason', sa.Text(), True, None),
        ('evidence', _JSON, True, None),
        ('level', sa.Integer(), False, None),
        ('status', sa.String(16), False, None),
        ('reject_code', sa.String(24), True, None),
        ('base_version', sa.Integer(), True, None),
        ('dedupe_key', sa.String(120), False, None),
        ('source_kind', sa.String(16), True, None),
        ('source_ref', sa.String(64), True, None),
        ('decided_by', sa.Integer(), True, None),
        ('decided_at', sa.DateTime(), True, None),
        ('decided_action', sa.String(16), True, None),
        ('view_ms', sa.Integer(), True, None),
        ('edited_params', _JSON, True, None),
        ('result', _JSON, True, None),
        ('error_code', sa.String(48), True, None),
        ('snoozed_until', sa.DateTime(), True, None),
        ('snoozed_by', sa.Integer(), True, None),
        ('created_at', sa.DateTime(), False, sa.func.now()),
        ('expires_at', sa.DateTime(), True, None),
    ),
    'brain_usage_events': (
        ('item_key', sa.String(120), False, None),
        ('reader', sa.String(16), False, None),
        ('ref_kind', sa.String(16), False, None),
        ('ref_id', sa.String(64), False, None),
        ('used_at', sa.DateTime(), False, sa.func.now()),
    ),
    'ai_agent_runs': (
        ('agent', sa.String(16), False, None),
        ('started_at', sa.DateTime(), False, sa.func.now()),
        ('total_ms', sa.Integer(), True, None),
        ('source_kind', sa.String(16), True, None),
        ('source_ref', sa.String(64), True, None),
        ('steps', _JSON, True, None),
        ('outcome', sa.String(24), True, None),
        ('proposals', sa.Integer(), False, sa.text('0')),
    ),
}
#: 검사 제약 — (이름, 칸, 값들).
CHECKS: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    'erp_action_proposals': (('ck_erp_action_proposals_status', 'status', PROPOSAL_STATUSES),),
    'brain_usage_events': (),
    'ai_agent_runs': (),
}
#: 색인 — (이름, 칸들, 유일, 부분 조건 또는 None). 순서 = upgrade 순서.
INDEXES: dict[str, tuple[tuple[str, tuple[str, ...], bool, Optional[str]], ...]] = {
    'erp_action_proposals': (
        ('ix_erp_action_proposals_status_created', ('status', 'created_at'), False, None),
        ('ix_erp_action_proposals_order_status', ('order_id', 'status'), False, None),
        ('uq_erp_action_proposals_open_dedupe', ('dedupe_key',), True, OPEN_SQL),
    ),
    'brain_usage_events': (
        ('ix_brain_usage_events_key_used', ('item_key', 'used_at'), False, None),
        ('ix_brain_usage_events_ref', ('ref_kind', 'ref_id'), False, None),
    ),
    'ai_agent_runs': (
        ('ix_ai_agent_runs_agent_started', ('agent', 'started_at'), False, None),
    ),
}


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def _create(table: str) -> None:
    """표 하나 — 칸 · 검사 제약 → 색인(부분 색인은 PostgreSQL · SQLite 같은 조건)."""
    op.create_table(
        table,
        sa.Column('id', sa.Integer(), primary_key=True),
        *(sa.Column(name, type_, nullable=nullable, server_default=default)
          for name, type_, nullable, default in COLUMNS[table]),
        *(sa.CheckConstraint(in_check(column, values), name=name) for name, column, values in CHECKS[table]),
    )
    for name, columns, unique, where_sql in INDEXES[table]:
        where = sa.text(where_sql) if where_sql else None
        op.create_index(name, table, list(columns), unique=unique, postgresql_where=where, sqlite_where=where)


def upgrade() -> None:
    """빈 표 셋 — 칸 · 검사 제약 → 색인."""
    for table in COLUMNS:
        _create(table)


def downgrade() -> None:
    """만든 역순 — 색인 → 표."""
    for table in reversed(tuple(COLUMNS)):
        for name, _columns, _unique, _where in reversed(INDEXES[table]):
            op.drop_index(name, table_name=table)
        op.drop_table(table)
