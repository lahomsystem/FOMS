"""NAVER-INGEST-01 T14-B: external_order_links 도크 반영 상태 컬럼

Revision ID: naverdock_00
Revises: navercollect_00
Create Date: 2026-08-14

주문 편집 화면 옆 "네이버 원본 도크"의 체크(반영 표시)·귀속(추가옵션→본품 지정) 상태다.
브라우저에만 두면 탭을 닫는 순간 사라지고 팀원끼리 공유도 안 되므로 서버에 저장한다
(2026-08-14 사용자 결정: 체크 즉시 저장).

``reviewed_at`` 을 재사용하지 않는 이유: 그건 **트리아지 큐 이탈** 축이고(첫 확인 시각
불변 계약), 도크 체크는 **항목별 반영 표시** 축이라 해제(토글)가 가능해야 한다. 섞으면
체크 해제가 확인 이력을 지우게 된다.

JSONB 한 컬럼인 이유: 상태가 {checked, checked_by, checked_at, assigned_main,
assigned_by, assigned_at} 묶음이고 질의 축이 아니다(항상 링크 단위로 통째로 읽는다).
DDL 은 ``models.ExternalOrderLink`` 와 SSOT 를 공유한다(create_all 레인 동일).
마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다.

``downgrade()`` 는 컬럼 제거 — 도크 체크·귀속 표시가 사라질 뿐 주문 데이터는 불변이다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'naverdock_00'
down_revision: Union[str, None] = 'navercollect_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'external_order_links'


def upgrade() -> None:
    """도크 반영 상태 JSONB 컬럼 1개."""
    op.add_column(TABLE, sa.Column('triage_state', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """컬럼 제거 — 도크 체크·귀속 표시만 사라진다(주문 데이터 불변)."""
    op.drop_column(TABLE, 'triage_state')
