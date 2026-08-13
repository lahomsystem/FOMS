"""ORDER-REASON-00: 주문 변경 사유(order_change_reasons) 테이블

Revision ID: orderreason_00
Revises: naver_link_00
Create Date: 2026-08-13

ORDER-DIFF-00/01 이 "무엇이 어떻게 바뀌었나"를 남긴다. 남은 공백이 **"왜"** 다 — 금액·일정
분쟁에서 "고객 요청"과 "우리 입력 실수"는 책임 소재가 정반대인데 값만 남은 원장에서는
똑같이 보인다.

* ``change_set_id`` — 저장 1회 묶음이자 **unique**. 사유는 저장 1회에 하나뿐이고 감사 원장이라
  덮어쓰지 않는다(중복 첨부는 API 가 409 로 막고, DB 도 unique 로 강제한다).
* ``reason_code`` — 목록 코드(자유 문자열 아님). 사유 기준 집계가 인덱스를 타야 한다.

**FK 를 걸지 않는다**: ``order_field_changes``·``order_events`` 와 같은 이유
(AUDIT-LOG T9 / ``auditlife_00``) — 감사 원장이 감사 대상과 생명주기를 공유하면 주문
hard purge 가 이력까지 지운다.

인덱스 이름·컬럼 순서는 ``models.OrderChangeReason.__table_args__`` 와 **완전히 같아야** 한다
(create_all 부트스트랩 레인과 alembic 레인의 스키마 정합 — PG 왕복 테스트가 강제).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(테이블/컬럼명 리터럴).
``downgrade()`` 는 테이블을 통째로 지운다 — 되돌리면 그 기간의 사유 기록이 사라진다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'orderreason_00'
down_revision: Union[str, None] = 'naver_link_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'order_change_reasons'
CHANGE_SET_INDEX = 'ux_order_change_reasons_change_set'
CODE_INDEX = 'ix_order_change_reasons_code_time'
ORDER_INDEX = 'ix_order_change_reasons_order_time'


def upgrade() -> None:
    """사유 테이블 + 인덱스 3종(unique 1 포함) 생성."""
    op.create_table(
        TABLE,
        # SQLite 레인에서는 INTEGER 여야 rowid 별칭(자동증가)이 된다 — models 와 같은 variant.
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer, 'sqlite'), primary_key=True),
        sa.Column('change_set_id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('reason_code', sa.String(length=32), nullable=False),
        sa.Column('reason_note', sa.String(length=200), nullable=True),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(CHANGE_SET_INDEX, TABLE, ['change_set_id'], unique=True)
    op.create_index(CODE_INDEX, TABLE, ['reason_code', 'created_at'])
    op.create_index(ORDER_INDEX, TABLE, ['order_id', 'created_at'])


def downgrade() -> None:
    """생성 역순으로 인덱스 → 테이블 제거(변경 원장·헤더는 무접촉)."""
    op.drop_index(ORDER_INDEX, table_name=TABLE)
    op.drop_index(CODE_INDEX, table_name=TABLE)
    op.drop_index(CHANGE_SET_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
