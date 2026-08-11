"""ORDER-ITEM-UID: order_field_changes 에 품목 안정 식별자 컬럼 추가

Revision ID: itemuid_00
Revises: orderdiff_01
Create Date: 2026-08-11

품목 변경은 지금까지 위치 인덱스(``item_index``)로만 식별됐다. 인덱스는 저장마다 밀리므로
"이 품목이 어떻게 바뀌어 왔나"를 물을 수 없었고, 중간 삽입이 여러 품목 변경으로 기록됐다.
``structured_data['items'][].uid`` (서버 발급 UUID4)를 원장에도 남겨 품목 축 이력을 연다.

**인덱스는 붙이지 않는다** — 그 질의를 하는 화면이 아직 없다. 쓰지 않는 인덱스는 쓰기 비용만
늘린다(필요해질 때 붙인다). ``models.OrderFieldChange`` 와 컬럼 정의가 같아야 한다
(create_all 레인과 alembic 레인 정합 — PG 왕복 테스트가 강제).

기존 행 백필은 없다(그때는 uid 자체가 없었다) — NULL 로 남고 ``item_index`` 로만 읽힌다.
마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'itemuid_00'
down_revision: Union[str, None] = 'orderdiff_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'order_field_changes'
COLUMN = 'item_uid'


def upgrade() -> None:
    """품목 안정 식별자 컬럼 추가(nullable — 기존 행은 NULL 로 남는다)."""
    op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=36), nullable=True))


def downgrade() -> None:
    """컬럼 제거(원장 행 자체는 보존 — item_index 로 계속 읽힌다)."""
    op.drop_column(TABLE, COLUMN)
