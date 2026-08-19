"""AS-SORT-01: order_attachments.sort_order (AS 첨부 표시·전송 순서)

Revision ID: assort_00
Revises: asaxis_00
Create Date: 2026-08-19

AS 첨부의 화면·채널톡 순서는 지금까지 ``id`` 오름차순(=병렬 업로드 완료 순)이었다.
사용자가 미리보기에서 정한 순서와 어긋나고, PUSH 확인창 배열도 서버가 id 로 다시
정렬해 버렸다. ``sort_order`` 는 그 정본이다. NULL 은 레거시 행 — 읽기 경로는
``id ASC`` 로 폴백한다. UNIQUE 는 걸지 않는다(재정렬 스왑·병렬 INSERT).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(리터럴 고정).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "assort_00"
down_revision: Union[str, None] = "asaxis_00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "order_attachments"
COLUMN = "sort_order"


def upgrade() -> None:
    """nullable integer 컬럼. 기존 행은 NULL (id 폴백)."""
    op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    """순서 정보만 사라진다(첨부 행·파일은 무손실)."""
    op.drop_column(TABLE, COLUMN)
