"""Phase B: add erp_measurement_date and erp_construction_date

Revision ID: phase_b_erp_date_cols
Revises: phase_c_indexes
Create Date: 2026-03-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'phase_b_erp_date_cols'
down_revision: Union[str, None] = 'phase_c_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # orders 테이블에 정규화 날짜 컬럼 2개 추가
    op.add_column('orders', sa.Column('erp_measurement_date', sa.String(10), nullable=True))
    op.add_column('orders', sa.Column('erp_construction_date', sa.String(10), nullable=True))
    
    # 인덱스 생성
    op.create_index('ix_orders_erp_measurement_date', 'orders', ['erp_measurement_date'])
    op.create_index('ix_orders_erp_construction_date', 'orders', ['erp_construction_date'])

def downgrade() -> None:
    # 인덱스 제거
    op.drop_index('ix_orders_erp_measurement_date', table_name='orders')
    op.drop_index('ix_orders_erp_construction_date', table_name='orders')
    
    # 컬럼 제거
    op.drop_column('orders', 'erp_construction_date')
    op.drop_column('orders', 'erp_measurement_date')
