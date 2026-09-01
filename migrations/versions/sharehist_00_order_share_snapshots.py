"""SHARE-HIST-00: 고객 열람 계약서 원장(order_share_snapshots) 테이블

Revision ID: sharehist_00
Revises: naverdisp_00
Create Date: 2026-09-01

공유 계약서를 라이브 반영으로 바꾼 뒤(2026-09-01) 생긴 공백을 메운다 — 같은 링크가 늘 최신
주문 값을 보여주므로 **고객이 그날 본 계약서**가 어디에도 남지 않는다. 법적 효력 문구가 있는
문서라 분쟁 시 제시할 근거가 필요하다.

``order_field_changes`` 로 대신할 수 없다: 그쪽은 주문 값의 변경 이력이고, 계약서 표면에는
회사정보·계좌(발주사 판정 1벌)·스냅샷 화이트리스트 버전·발급 시점 고정 계약번호가 함께
들어간다. 재생하면 당시 화면과 달라진다 — 그래서 **열람 시점 렌더 dict 그대로** 남긴다.

* **FK 없음** — ``order_field_changes``·``order_change_reasons``·``order_events`` 와 같은
  이유(AUDIT-LOG T9 / ``auditlife_00``): 증거 원장이 감사 대상과 생명주기를 공유하면 주문
  hard purge 가 증거까지 지운다.
* **UNIQUE 없음** — ``(share_token_id, content_hash)`` 를 unique 로 묶으면 금액이 A→B→A 로
  되돌아갔을 때 세 번째 상태가 첫 행에 흡수돼 시간축이 무너진다. 중복 판정은 그 토큰의
  최신 행과만 한다(애플리케이션 규칙).
* ``snapshot`` 은 ``sa.JSON().with_variant(JSONB)`` — models.py ``JSONColumn`` 과 타입 정합
  (기존 json/jsonb 드리프트에 추가하지 않는다).
* server_default 없음 — 모든 insert 가 ORM 경로. migration_chain 지문(create_all ↔ 마이그레이션
  재생, nullable/default 예외 없이 일치)을 위해 models.py 정의와 컬럼 단위로 동일하게 유지한다.

인덱스 이름·컬럼 순서는 ``models.OrderShareSnapshot.__table_args__`` 와 **완전히 같아야** 한다
(create_all 부트스트랩 레인과 alembic 레인의 스키마 정합 — PG 왕복 테스트가 강제).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(테이블/컬럼명 리터럴).
``downgrade()`` 는 테이블 drop — 되돌리면 그 기간의 열람 증거가 사라진다(주문 원본은 무손실).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'sharehist_00'
down_revision: Union[str, None] = 'naverdisp_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'order_share_snapshots'
TOKEN_INDEX = 'ix_order_share_snapshots_token_id'
ORDER_INDEX = 'ix_order_share_snapshots_order_time'


def upgrade() -> None:
    """열람 원장 테이블 + 인덱스 2종 생성(unique 없음 — 시간축 보존)."""
    op.create_table(
        TABLE,
        # SQLite 레인에서는 INTEGER 여야 rowid 별칭(자동증가)이 된다 — models 와 같은 variant.
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer, 'sqlite'), primary_key=True),
        sa.Column('share_token_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('snapshot', sa.JSON().with_variant(JSONB(), 'postgresql'), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('first_viewed_at', sa.DateTime(), nullable=False),
        sa.Column('last_viewed_at', sa.DateTime(), nullable=False),
        sa.Column('view_count', sa.Integer(), nullable=False),
    )
    op.create_index(TOKEN_INDEX, TABLE, ['share_token_id', 'id'])
    op.create_index(ORDER_INDEX, TABLE, ['order_id', 'first_viewed_at'])


def downgrade() -> None:
    """생성 역순으로 인덱스 → 테이블 제거(공유 토큰·주문은 무접촉)."""
    op.drop_index(ORDER_INDEX, table_name=TABLE)
    op.drop_index(TOKEN_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
