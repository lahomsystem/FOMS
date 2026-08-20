"""NAVER-INGEST-01 T12: sync_status 에 COLLECTED 추가 (수집과 주문 생성 분리)

Revision ID: navercollect_00
Revises: naver_triage_00
Create Date: 2026-08-14

수집이 곧 주문 생성이던 구조를 바꾼다. 스윕은 이제 원본만 보관하고(``COLLECTED``),
사람이 관리 화면에서 "주문 만들기"를 눌렀을 때만 ``create_order()`` 가 돈다
(그 시점에 ``LINKED`` 로 전환). 기존 값의 뜻은 그대로다:

* ``COLLECTED`` — 수집 성공, **주문 미생성**(사람 대기). 신규.
* ``LINKED`` — 주문이 만들어져 연결됨.
* ``PENDING_REVIEW`` — 매핑 실패(주문 없음).
* ``FAILED`` — 수집 자체 실패.

기존 행은 손대지 않는다 — 이미 주문이 붙어 있으므로 ``LINKED`` 가 여전히 맞다.
CHECK 제약만 넓히는 것이라 되돌리기도 값 확인 없이 안전하지 않다: downgrade 는
``COLLECTED`` 행이 남아 있으면 제약 재생성에서 실패한다(의도 — 데이터를 조용히 버리지 않는다).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'navercollect_00'
down_revision: Union[str, None] = 'naver_triage_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'external_order_links'
CONSTRAINT = 'ck_external_order_link_status'
OLD_VALUES = "sync_status IN ('LINKED','PENDING_REVIEW','FAILED')"
NEW_VALUES = "sync_status IN ('COLLECTED','LINKED','PENDING_REVIEW','FAILED')"


def upgrade() -> None:
    """CHECK 제약을 COLLECTED 포함으로 교체."""
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT, type_='check')
        batch.create_check_constraint(CONSTRAINT, NEW_VALUES)


def downgrade() -> None:
    """COLLECTED 를 뺀 원래 제약으로 복원(COLLECTED 행이 있으면 실패한다 — 의도)."""
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT, type_='check')
        batch.create_check_constraint(CONSTRAINT, OLD_VALUES)
