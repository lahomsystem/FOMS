"""AS-AXIS-01: AS 축 플랫 투영 컬럼 + 부분 인덱스

Revision ID: asaxis_00
Revises: naverdock_00
Create Date: 2026-08-17

AS 대시보드의 목록·카운트 술어가 ``orders.status`` 단독이라, 그 컬럼이 overlay projection
(AS > logistics > main)임에도 외부 write 한 번에 AS 목록이 통째로 사라졌다(2026-08-14 사고
55건). AS 축의 정본은 ``structured_data['as_lifecycle']`` 인데 JSONB 라 SQL 술어로 쓰기
어렵다 → ``erp_stage_code`` 와 같은 계열의 플랫 투영 컬럼을 하나 둔다.

값 도메인은 ``state_axes.AS_VALUES``(RECEIVED/IN_PROGRESS/COMPLETED)이며 AS 이력이 없으면
NULL 이다. ``'NONE'`` 문자열을 쓰지 않는 이유: 전체 행의 대다수가 AS 이력이 없어서, NULL
이어야 부분 인덱스가 AS 행만 담는다(현재 3,551행 중 AS 566행).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(DDL 은 ``models.Order``
와 SSOT 를 공유하지만 문자열로 고정한다). 백필은 이 리비전이 아니라
``tools/ops/backfill_as_axis_status.py`` 가 맡는다 — 유도 규칙이 앱 코드(SSOT)에 있고,
대용량 UPDATE 를 마이그레이션 트랜잭션에 넣지 않기 위해서다.

``downgrade()`` 는 인덱스·컬럼 제거다. 이 컬럼은 파생값이라 원본 데이터 손실이 없다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'asaxis_00'
down_revision: Union[str, None] = 'naverdock_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'orders'
COLUMN = 'as_axis_status'
INDEX = 'ix_orders_as_axis_status'


def upgrade() -> None:
    """AS 축 투영 컬럼 + AS 행만 담는 부분 인덱스."""
    op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=16), nullable=True))
    op.create_index(
        INDEX, TABLE, [COLUMN],
        unique=False,
        postgresql_where=sa.text(f'{COLUMN} IS NOT NULL'),
    )


def downgrade() -> None:
    """인덱스·컬럼 제거 — 파생값이라 원본 데이터는 그대로다."""
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, COLUMN)
