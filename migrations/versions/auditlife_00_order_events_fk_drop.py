"""AUDIT-LOG T9: order_events → orders FK(ON DELETE CASCADE) 분리

Revision ID: auditlife_00
Revises: seclog_struct_00
Create Date: 2026-08-07

``order_events`` 는 감사 원장인데 감사 **대상**(``orders``)과 생명주기를 공유하고 있었다 —
``order_id`` FK 가 ``ON DELETE CASCADE`` 라서 주문 hard purge(DELETE-RETENTION-01)가 그
주문의 이벤트 이력까지 함께 지운다. "누가 언제 무엇을 바꿨나"의 답이 삭제 행위 하나로 통째로
사라지는 구조 결함이라(스펙 §4 T9·§8 결정 ④), FK 를 떼어 원장을 독립시킨다.

* ``order_id`` 는 **NOT NULL + 인덱스 유지** — 컬럼도 인덱스도 건드리지 않는다.
  조회 조인은 ``models.OrderEvent.order`` 의 명시 ``primaryjoin`` 이 담당한다.
* ``DROP CONSTRAINT IF EXISTS`` — 재생성 경로(``scripts/ops/erp_build_step_runner.py``)
  나 과거 부트스트랩에 따라 제약이 이미 없는 DB 가 있을 수 있어 방어적으로 건다.
* ``downgrade`` 는 CASCADE FK 를 그대로 되살린다. FK 분리 이후 주문이 hard purge 되었다면
  고아 이벤트가 남아 있고, 그 상태에서는 **PostgreSQL 의 제약 검증이 스스로 실패**한다
  (fail-closed 가 공짜로 얻어진다 — 전용 차단 로직을 두지 않는 이유). 운영자가 원인을 즉시
  알 수 있도록 고아 수만 사전 안내한다.

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(테이블/제약명 리터럴).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

revision: str = 'auditlife_00'
down_revision: Union[str, None] = 'seclog_struct_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'order_events'
COLUMN = 'order_id'
# PostgreSQL 기본 명명(<table>_<column>_fkey). create_all 레인·운영 DB·
# erp_build_step_runner 의 raw DDL 이 모두 이 이름으로 만든다(실 카탈로그 확인 완료).
FK_NAME = 'order_events_order_id_fkey'

_ORPHAN_COUNT_SQL = sa.text(
    "SELECT count(*) FROM order_events e "
    "WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.id = e.order_id)"
)


def upgrade() -> None:
    """``order_events.order_id`` 의 CASCADE FK 제거(컬럼·인덱스·NOT NULL 은 불변)."""
    op.execute(f'ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {FK_NAME}')


def downgrade() -> None:
    """CASCADE FK 재부착. 고아 이벤트가 있으면 PG 제약 검증이 스스로 실패한다."""
    try:
        orphans = op.get_bind().execute(_ORPHAN_COUNT_SQL).scalar() or 0
    except SQLAlchemyError as exc:
        # 안내용 조회일 뿐이다 — 실패해도 downgrade 자체는 그대로 진행하고, 부적격이면
        # 아래 ADD CONSTRAINT 가 PG 검증으로 막는다(안내 실패가 판정을 대신하지 않는다).
        print(f'[auditlife_00] 고아 이벤트 사전 카운트 생략(조회 실패): {exc}')
    else:
        if orphans:
            print(
                f'[auditlife_00] 주의: orders 에 없는 order_events 가 {orphans}건 있다. '
                f'{FK_NAME} 재생성은 PostgreSQL 제약 검증에서 실패한다 — '
                '해당 이벤트를 보존할지 삭제할지 먼저 결정해야 한다.'
            )
    op.execute(
        f'ALTER TABLE {TABLE} ADD CONSTRAINT {FK_NAME} '
        f'FOREIGN KEY ({COLUMN}) REFERENCES orders(id) ON DELETE CASCADE'
    )
