"""external_order_links.group_key — 묶음('집') 키 컬럼 + 조회 인덱스.

왜: 확인 큐는 (주문번호·수취인 전화·주소)로 집을 가르는데, 이력 표는 주문번호만 봤다.
주소는 ``raw_snapshot`` 안에서 파이썬으로 조립해야 나오므로 SQL 이 못 세기 때문이다.
그래서 분할배송(같은 주문번호·다른 주소)에서 두 화면의 집 수가 영구히 어긋났다.
값을 컬럼으로 복사해 두면 두 화면이 같은 정의를 쓰면서 이력은 여전히 SQL 로 셀 수 있다.

이 마이그레이션은 **구조만** 바꾼다. 기존 행 채우기(backfill)는
``scripts/maintenance/backfill_naver_group_key.py`` 가 따로 한다 — 값 계산이 원본 파싱
코드(``mapping.group_key_text``)에 의존하는데, 마이그레이션이 그 코드를 import 하면
나중에 파싱 규칙이 바뀔 때 **과거 마이그레이션의 결과가 소급해서 달라진다**.
마이그레이션은 그 시점에 고정된 사실만 담아야 한다.

Revision ID: navergroup_00
Revises: naver_relation_00
  운영 실제 계보 정합 — 2026-08-24 SPEC 4장(승격 체인 재직렬화).
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = 'navergroup_00'
down_revision = 'naver_relation_00'
branch_labels = None
depends_on = None

TABLE = 'external_order_links'
COLUMN = 'group_key'
INDEX = 'ix_external_order_link_group'


def upgrade() -> None:
    """묶음키 컬럼과 (channel, group_key) 인덱스를 더한다.

    nullable 로 둔다 — 기존 행에는 값이 없고, 읽는 쪽이 ``external_order_no`` 로
    폴백하므로 backfill 전에도 화면은 예전과 같이 동작한다.
    """
    op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=200), nullable=True))
    op.create_index(INDEX, TABLE, ['channel', COLUMN])


def downgrade() -> None:
    """인덱스·컬럼을 되돌린다(값은 파생이라 잃어도 backfill 로 복구된다)."""
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, COLUMN)
