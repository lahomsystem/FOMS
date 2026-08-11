"""ORDER-DIFF-01: 주문 필드 변경 원장(order_field_changes) 테이블

Revision ID: orderdiff_01
Revises: seclog_time_00
Create Date: 2026-08-11

ORDER-DIFF-00 은 저장 1회의 변경을 ``security_logs.detail['changes']`` JSONB 로 남겼다.
행 단위 조회는 되지만 **필드 기준 질의**("최근 한 달에 실측일이 바뀐 주문 전부", "출고가를
내린 사람")가 JSONB 배열 해체를 요구해 인덱스를 타지 못한다. SAP 의 ``CDHDR``/``CDPOS`` 처럼
헤더(``security_logs``)와 항목(이 테이블)을 나눈다.

* ``change_set_id`` — 저장 1회 묶음. 헤더의 ``detail['change_set']`` 과 같은 값이라 **FK 없이**
  헤더↔항목이 이어진다.
* ``path_template`` — 품목 인덱스를 지운 질의 키(``items.*.price``).

**FK 를 걸지 않는다**: ``order_events`` 와 같은 이유(AUDIT-LOG T9 / ``auditlife_00``) — 감사
원장이 감사 대상과 생명주기를 공유하면 주문 hard purge 가 이력까지 지운다.

인덱스 이름·컬럼 순서는 ``models.OrderFieldChange.__table_args__`` 와 **완전히 같아야** 한다
(create_all 부트스트랩 레인과 alembic 레인의 스키마 정합 — PG 왕복 테스트가 강제).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(테이블/컬럼명 리터럴).
``downgrade()`` 는 테이블을 통째로 지운다 — 원장이므로 되돌리면 그 기간의 변경 이력이 사라진다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'orderdiff_01'
down_revision: Union[str, None] = 'seclog_time_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'order_field_changes'
TEMPLATE_INDEX = 'ix_order_field_changes_template_time'
ORDER_INDEX = 'ix_order_field_changes_order_time'
CHANGE_SET_INDEX = 'ix_order_field_changes_change_set'


def upgrade() -> None:
    """변경 원장 테이블 + 조회 인덱스 3종 생성."""
    op.create_table(
        TABLE,
        # SQLite 레인에서는 INTEGER 여야 rowid 별칭(자동증가)이 된다 — models 와 같은 variant.
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer, 'sqlite'), primary_key=True),
        sa.Column('change_set_id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(length=120), nullable=False),
        sa.Column('path_template', sa.String(length=120), nullable=False),
        sa.Column('item_index', sa.Integer(), nullable=True),
        sa.Column('item_name', sa.String(length=120), nullable=True),
        sa.Column('op', sa.String(length=8), nullable=False),
        sa.Column('before_value', sa.Text(), nullable=True),
        sa.Column('after_value', sa.Text(), nullable=True),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(TEMPLATE_INDEX, TABLE, ['path_template', 'created_at'])
    op.create_index(ORDER_INDEX, TABLE, ['order_id', 'created_at'])
    op.create_index(CHANGE_SET_INDEX, TABLE, ['change_set_id'])


def downgrade() -> None:
    """생성 역순으로 인덱스 → 테이블 제거(헤더 security_logs 는 무접촉)."""
    op.drop_index(CHANGE_SET_INDEX, table_name=TABLE)
    op.drop_index(ORDER_INDEX, table_name=TABLE)
    op.drop_index(TEMPLATE_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
