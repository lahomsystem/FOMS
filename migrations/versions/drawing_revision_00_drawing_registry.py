"""DRAWING-REVISION-BACKFILL-00: drawing revision/request 정본 UUID registry

Revision ID: drawing_revision_00
Revises: wdc_link_fence_00
Create Date: 2026-07-26

§5.2 DRAWING-REVISION-BACKFILL-00 의 ``drawing_revisions`` / ``drawing_revision_requests``
(도면 개정 실행·수정요청의 DB-global UUID registry)를 신설한다. 도면 이력은 오늘 주문마다
flat ``structured_data['drawing_transfer_history']``(TRANSFER/REQUEST_REVISION/CONFIRM_RECEIPT
가 뒤섞여 append 되는 단일 리스트)·``drawing_status``·``drawing_current_files``·
``blueprint.customer_confirmed`` 로만 기록돼, 개정별 안정 identity 도 current/receipt/
customer-confirm/open-request 포인터도 남지 않는다. 이 registry 는 TRANSFER 마다 안정 UUID
revision row 를, REQUEST_REVISION 마다 UUID request row 를 발급해
:func:`~foms.services.orders.state_axes.read_drawing_revision_registry` 의 canonical
pointer(``current_revision_id`` / ``receipt_revision_id`` /
``customer_confirmed_revision_id`` / ``current_revision_request_id``)와 shape 를 정합시킨다.

이 마이그레이션은 **순수 스키마 추가** 다: 테이블만 만들고, 기존 flat drawing 데이터
(``drawing_transfer_history``·``drawing_current_files``·attachment)는 그대로 둔다(backfill 은
flat 을 복제만 하고 삭제/재작성하지 않는다 — attachment 삭제 금지). revision/request 를 읽는
전이(개정 발급·전달)의 활성화는 하류 STATE-DRAWING-01 소관이므로 이 단계는 runtime 의미
변경이 0 이다. DDL 은 ``models.DrawingRevision`` / ``models.DrawingRevisionRequest``
(create_all 테스트 lane)과 SSOT 를 공유한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'drawing_revision_00'
down_revision: Union[str, None] = 'wdc_link_fence_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """drawing_revisions + drawing_revision_requests 생성 + 포인터 partial-unique."""
    op.create_table(
        'drawing_revisions',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),  # TRANSFERRED|RETURNED|CONFIRMED|SUPERSEDED
        # 개정 순번(주문 내 TRANSFER 발생 순 1-based) — provenance·정렬.
        sa.Column('revision_no', sa.Integer(), nullable=False),
        # 전달(발급) 스냅샷 — flat TRANSFER entry 의 transferred_at/by_user_name/note/files.
        sa.Column('transferred_at', sa.DateTime(), nullable=True),
        sa.Column('transferred_by', sa.String(length=120), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('files', postgresql.JSONB(), nullable=True),
        # receipt(도면 수령 확인) 스냅샷 — flat CONFIRM_RECEIPT entry 의 at/by_user_name.
        sa.Column('receipt_confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('receipt_confirmed_by', sa.String(length=120), nullable=True),
        # customer-confirm 스냅샷 — flat blueprint.confirmed_at/confirmed_by.
        sa.Column('customer_confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('customer_confirmed_by', sa.String(length=120), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_receipt', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_customer_confirmed', sa.Boolean(), nullable=False, server_default='false'),
        # 발급 근거 drawing_transfer_history 인덱스(provenance·backfill 멱등 키).
        sa.Column('legacy_seq', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_drawing_revisions_order_id', 'drawing_revisions', ['order_id'])
    # 한 주문의 current revision 은 최대 1개(current_revision_id 포인터 DB 표현).
    op.create_index(
        'uq_drawing_revision_current', 'drawing_revisions',
        ['order_id'], unique=True, postgresql_where=sa.text('is_current'),
    )
    # 한 주문의 receipt revision(수령 확인분)은 최대 1개(receipt_revision_id 포인터).
    op.create_index(
        'uq_drawing_revision_receipt', 'drawing_revisions',
        ['order_id'], unique=True, postgresql_where=sa.text('is_receipt'),
    )
    # 한 주문의 customer-confirmed revision 은 최대 1개(customer_confirmed_revision_id 포인터).
    op.create_index(
        'uq_drawing_revision_customer', 'drawing_revisions',
        ['order_id'], unique=True, postgresql_where=sa.text('is_customer_confirmed'),
    )
    # 한 주문의 한 legacy transfer entry 에 revision 은 최대 1개(중복 발급 방지·backfill 멱등).
    op.create_index(
        'uq_drawing_revision_legacy', 'drawing_revisions',
        ['order_id', 'legacy_seq'], unique=True,
        postgresql_where=sa.text('legacy_seq IS NOT NULL'),
    )

    op.create_table(
        'drawing_revision_requests',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        # 요청 대상 revision(발급 시점 current revision) 의 soft link(FK 아님 — 형제 registry
        # 와 느슨 결합·삭제 순서 무관). None = 대상 미상.
        sa.Column('revision_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),  # OPEN|RESOLVED
        # 요청 스냅샷 — flat REQUEST_REVISION entry 의 at/by_user_name/note/files/대상 도면 key.
        sa.Column('requested_at', sa.DateTime(), nullable=True),
        sa.Column('requested_by', sa.String(length=120), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('files', postgresql.JSONB(), nullable=True),
        sa.Column('target_drawing_keys', postgresql.JSONB(), nullable=True),
        sa.Column('is_open', sa.Boolean(), nullable=False, server_default='false'),
        # 발급 근거 drawing_transfer_history 인덱스(provenance·backfill 멱등 키).
        sa.Column('legacy_seq', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index(
        'ix_drawing_revision_requests_order_id', 'drawing_revision_requests', ['order_id'],
    )
    # 한 주문의 열린(open) 수정요청은 최대 1개("duplicate open request 0" 불변식 DB 강제·
    # current_revision_request_id 포인터). 종결(RESOLVED)은 여러 개 이력으로 남는다.
    op.create_index(
        'uq_drawing_request_open', 'drawing_revision_requests',
        ['order_id'], unique=True, postgresql_where=sa.text('is_open'),
    )
    # 한 주문의 한 legacy request entry 에 request 는 최대 1개(중복 발급 방지·backfill 멱등).
    op.create_index(
        'uq_drawing_request_legacy', 'drawing_revision_requests',
        ['order_id', 'legacy_seq'], unique=True,
        postgresql_where=sa.text('legacy_seq IS NOT NULL'),
    )


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블 제거."""
    op.drop_index('uq_drawing_request_legacy', table_name='drawing_revision_requests')
    op.drop_index('uq_drawing_request_open', table_name='drawing_revision_requests')
    op.drop_index('ix_drawing_revision_requests_order_id', table_name='drawing_revision_requests')
    op.drop_table('drawing_revision_requests')

    op.drop_index('uq_drawing_revision_legacy', table_name='drawing_revisions')
    op.drop_index('uq_drawing_revision_customer', table_name='drawing_revisions')
    op.drop_index('uq_drawing_revision_receipt', table_name='drawing_revisions')
    op.drop_index('uq_drawing_revision_current', table_name='drawing_revisions')
    op.drop_index('ix_drawing_revisions_order_id', table_name='drawing_revisions')
    op.drop_table('drawing_revisions')
