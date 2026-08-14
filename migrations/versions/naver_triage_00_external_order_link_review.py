"""NAVER-INGEST-01 T8: external_order_links 트리아지(사람 확인) 컬럼

Revision ID: naver_triage_00
Revises: naver_link_00
Create Date: 2026-08-13

수집 주문은 담당자 없고 규격도 안 채워진 **반쪽 초안**으로 들어온다(v1 은 옵션을 파싱하지
않는다). 사람이 마무리해야 하는데 그 대상 목록이 없으면 아무도 안 채우고 조용히 쌓인다.
이 두 컬럼이 "아직 사람이 안 본 수집 건" 큐의 정본이다(스펙 §8.3).

* ``reviewed_at`` NULL = 확인 대기(큐에 뜬다). 값이 있으면 큐에서 빠진다.
* ``reviewed_by_user_id`` 는 ``ON DELETE SET NULL`` — 사람이 퇴사해 계정이 지워져도
  "확인됐다"는 사실 자체는 남아야 한다(지워지면 그 건이 큐에 되살아난다).

``sync_status`` 에 값을 더하지 않은 이유: 그건 **수집 결과** 축(LINKED/PENDING_REVIEW/
FAILED)이고 이건 **사람 처리** 축이다. 섞으면 "수집은 성공했지만 사람이 아직 안 본" 상태를
표현할 수 없다.

부분 인덱스(``reviewed_at IS NULL``)는 큐 조회 전용이다 — 확인 완료분이 쌓여도 인덱스가
커지지 않는다. DDL 은 ``models.ExternalOrderLink`` 와 SSOT 를 공유한다(create_all 레인 동일).
마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다.

``downgrade()`` 는 인덱스 → FK → 컬럼 순으로 제거한다. 되돌리면 확인 이력이 사라지므로
이미 확인한 건이 전부 큐에 되살아난다(무손실 역변환이 아님을 명시).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'naver_triage_00'
down_revision: Union[str, None] = 'naver_link_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'external_order_links'
# PostgreSQL 기본 명명(<table>_<column>_fkey). ORM 의 ``ForeignKey`` 는 이름을 주지
# 않으므로 create_all 레인이 이 이름으로 만든다 — 마이그레이션이 다른 이름을 쓰면
# downgrade 가 UndefinedObject 로 죽는다(같은 테이블 order_id FK 도 이 규칙이다).
FK_NAME = 'external_order_links_reviewed_by_user_id_fkey'
INDEX_NAME = 'ix_external_order_link_pending_review'


def upgrade() -> None:
    """트리아지 컬럼 2개 + 확인 대기 부분 인덱스."""
    op.add_column(TABLE, sa.Column('reviewed_at', sa.DateTime(), nullable=True))
    op.add_column(TABLE, sa.Column('reviewed_by_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        FK_NAME, TABLE, 'users', ['reviewed_by_user_id'], ['id'], ondelete='SET NULL',
    )
    # 확인 대기 건만 담는 부분 인덱스 — 처리 완료분이 쌓여도 큐 조회 비용이 늘지 않는다.
    op.create_index(
        INDEX_NAME, TABLE, ['channel', 'created_at'],
        postgresql_where=sa.text('reviewed_at IS NULL'),
    )


def downgrade() -> None:
    """생성 역순 제거. 확인 이력이 사라져 처리 완료 건이 큐에 되살아난다."""
    op.drop_index(INDEX_NAME, table_name=TABLE)
    op.drop_constraint(FK_NAME, TABLE, type_='foreignkey')
    op.drop_column(TABLE, 'reviewed_by_user_id')
    op.drop_column(TABLE, 'reviewed_at')
