"""NAVER-SETTLE v1.1 T13: naver_settle_case 주문 역조회 인덱스 1종

Revision ID: naversettle_01
Revises: naversettle_00
Create Date: 2026-09-02

왜 필요한가
-----------
정산 실무 탭(``/api/settlement/rows``)에 "네이버 정산" 컬럼이 붙으면서
``foms.services.settlement_rows._naver_settle_map`` 이 **모집단 주문 id 전량**으로
``naver_settle_case`` 를 역조회한다(운영 ERP 모집단 1,978건, 화면 진입마다 1회).
``naversettle_00`` 이 만든 인덱스 3종은 전부 ``search_date`` 축(조회일 파티션)이라
``foms_order_id`` 조건을 하나도 못 받는다 — 그대로 두면 이 hot path 가 표 전량
Seq Scan 이 된다(정산 행은 관측 1,284행/월로 계속 늘어난다).

왜 이 모양인가
--------------
* **``(channel, foms_order_id)`` 복합**: 조회가 항상 채널을 함께 고정한다
  (``channel == 'NAVER' AND foms_order_id IN (...)``). 채널이 늘어도 같은 인덱스를 쓴다.
* **부분 인덱스(``foms_order_id IS NOT NULL``)**: 배송비·기타비용 행처럼 붙을 주문이
  아예 없는 행(``product_order_type != 'PROD_ORDER'``)은 이 경로에서 영원히 조회되지
  않는다. ``ix_nsc_unmatched`` 와 같은 규율이다 — 이력이 쌓여도 인덱스가 함께 부풀지 않는다.
  SQLite 테스트 레인은 ``postgresql_where`` 를 무시하고 일반 인덱스로 만든다(동작 동일).

상수 동결: ``models`` 를 import 하지 않는다 — 표·컬럼·인덱스 이름을 리터럴로 적는다.
(모델이 나중에 바뀌어도 이 마이그레이션의 결과는 그대로여야 한다.)

``downgrade()`` 는 인덱스만 지운다. 데이터 손실이 없는 완전 가역 변경이다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'naversettle_01'
down_revision: Union[str, None] = 'naversettle_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

T_SETTLE_CASE = 'naver_settle_case'
IX_FOMS_ORDER = 'ix_nsc_foms_order'


def upgrade() -> None:
    """주문 역조회용 부분 인덱스 1종을 만든다(스키마 확장만, 데이터 변경 0)."""
    op.create_index(
        IX_FOMS_ORDER,
        T_SETTLE_CASE,
        ['channel', 'foms_order_id'],
        postgresql_where=sa.text('foms_order_id IS NOT NULL'),
    )


def downgrade() -> None:
    """인덱스를 걷어낸다. 행은 건드리지 않으므로 손실 없이 되돌아간다."""
    op.drop_index(IX_FOMS_ORDER, table_name=T_SETTLE_CASE)
