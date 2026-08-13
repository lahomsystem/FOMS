"""AS-FRESH-01 T1: order_attachments.as_log_id (AS 첨부 ↔ 타임라인 기록 결합)

Revision ID: asfresh_00
Revises: naver_link_00
Create Date: 2026-08-13

AS 첨부는 지금까지 ``category='as'`` 하나로만 묶여 있었다. 그래서 "이 기록의 사진"이라는
개념이 데이터에 없었고, 채널톡 AS PUSH 가 회차를 가릴 수 없어 3개월 전 사진과 방금 올린
사진을 한 메시지에 섞어 보냈다(AS-FRESH-01 §1).

``as_log_id`` 는 ``structured_data['shipment']['as_log']`` 항목 id(``al_<epoch_ms>_<hex4>``)를
가리키는 **약한 참조**다. FK 를 걸 대상이 JSONB 안에 있어 DB 제약으로는 표현할 수 없고,
검증은 등록 라우트가 소유한다(존재하지 않는 id 는 400). 기존 첨부는 NULL 로 남으며 소급
배정하지 않는다 — 추정 배정은 오귀속을 만든다.

인덱스는 ``(order_id, as_log_id)`` 복합이다. 조회는 항상 "이 주문의 첨부를 기록별로"라
단독 인덱스는 쓸모가 없다.

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(리터럴 고정).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'asfresh_00'
down_revision: Union[str, None] = 'naver_link_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'order_attachments'
COLUMN = 'as_log_id'
INDEX = 'ix_order_attachments_as_log_id'


def upgrade() -> None:
    """as_log_id 컬럼 + (order_id, as_log_id) 조회 인덱스."""
    op.add_column(TABLE, sa.Column(COLUMN, sa.String(64), nullable=True))
    op.create_index(INDEX, TABLE, ['order_id', COLUMN])


def downgrade() -> None:
    """인덱스 → 컬럼 역순 제거. 결합 정보는 사라진다(첨부 행 자체는 무손실)."""
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, COLUMN)
