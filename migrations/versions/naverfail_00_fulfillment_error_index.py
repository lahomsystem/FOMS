"""external_order_links: 발주확인·발송처리 실패 조회용 부분 인덱스.

왜: 워크벤치 결과 띠는 **모든 탭 매 렌더**에서 "실패 사유가 있는 링크"를 찾는다
(``triage_state -> 'fulfillment' ->> 'last_error'``). 실패는 희소해서 인덱스가 없으면
``ORDER BY created_at DESC LIMIT n`` 이 조기 종료를 못 하고 매 요청 전체 스캔이 된다 —
이 저장소의 hot path JSONB 스캔 금지 규칙에 걸린다.

부분 인덱스로 둔다: 조건에 맞는 행(= 실패가 남아 있는 링크)만 담으므로 크기가 작고,
성공/정상 행의 INSERT·UPDATE 는 인덱스를 건드리지 않는다.

PostgreSQL 전용이다. SQLite 레인은 JSONB 연산자가 없어 그대로 건너뛴다(테스트 레인은
데이터가 작아 인덱스가 없어도 동작이 같다).

Revision ID: naverfail_00
Revises: navergroup_00
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa


revision = 'naverfail_00'
down_revision = 'navergroup_00'
branch_labels = None
depends_on = None

INDEX = 'ix_external_order_link_fulfillment_error'

CREATE_SQL = f"""
CREATE INDEX IF NOT EXISTS {INDEX}
    ON external_order_links (channel, created_at DESC)
    WHERE (triage_state -> 'fulfillment' ->> 'last_error') IS NOT NULL
      AND (triage_state -> 'fulfillment' ->> 'last_error') <> ''
"""


def upgrade() -> None:
    """실패가 남아 있는 링크만 담는 부분 인덱스를 만든다(PostgreSQL 전용)."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.execute(sa.text(CREATE_SQL))


def downgrade() -> None:
    """인덱스를 되돌린다(파생 구조라 잃어도 데이터는 그대로다)."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.execute(sa.text(f'DROP INDEX IF EXISTS {INDEX}'))
