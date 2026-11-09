"""CHAT-DEL-01 2단계: 사내 채팅 표 4개 · 작업 대기열 chat_attachment_id 칸 지우기

Revision ID: chat_drop_01
Revises: fcomm_02
Create Date: 2026-11-09

설계 정본: ``docs/specs/2026-11-07-internal-chat-removal_SPEC.md`` §4(사용자 11-09 승인 "운영까지").
1단계(#762)가 코드를 지웠고, 표는 운영 실측(11-09 읽기 전용) 방 1 · 참여자 1 · 메시지 2(2026-02-20) · 첨부 0,
대기열 ``CHAT_ATTACHMENT`` 줄 0 이었다. 지우는 3줄은 같은 날 오프사이트 덤프에 남아 있다.

upgrade:

1. 대기열 CHECK 두 개(``ck_dseo_source_one_of`` · ``ck_dseo_source_domain``)를 지운다.
2. ``domain_side_effect_outbox.chat_attachment_id`` 칸을 지운다(그 칸의 FK 도 같이 없어진다).
3. CHECK 두 개를 ``CHAT_ATTACHMENT`` 를 뺀 7도메인으로 다시 만든다(작성 시점 스냅샷 — models 를 import 하지 않는다.
   ORM ``models.DOMAIN_SIDE_EFFECT_ONE_OF_CHECK_SQL`` 과 byte-identical 이어야 한다, 선례 ``order_import_00``).
   ``CHAT_ATTACHMENT`` 줄이 남아 있으면 여기서 CHECK 가 실패해 마이그레이션이 멈춘다(지우기 전 안전장치).
4. 표 4개를 자식부터 지운다(색인 · trgm 색인 · 표 안 FK 는 표와 같이 없어진다).

downgrade: 빈 표 4개 · 색인(trgm 2개 포함) · 칸 · FK · 8도메인 CHECK 를 다시 만든다. **지운 줄은 돌아오지 않는다.**
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'chat_drop_01'
down_revision: Union[str, None] = 'fcomm_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OUTBOX = 'domain_side_effect_outbox'

# 작성 시점(7도메인) 스냅샷 — models.py 의 DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN 과 같은 순서 · 내용.
_CHAT_DROP01_FK_BY_DOMAIN = {
    'ORDER_EVENT': 'order_event_id',
    'NOTIFICATION_EVENT': 'notification_event_id',
    'ADDRESS_LEARNING': 'address_learning_request_id',
    'WIZARD_PENDING': 'wizard_pending_id',
    'UPLOAD_TICKET': 'upload_ticket_id',
    'UPLOAD_DRAFT': 'upload_draft_id',
    'ORDER_IMPORT_ARTIFACT': 'order_import_artifact_id',
}

#: 지우기 전(8도메인) — downgrade 복원용. CHAT_ATTACHMENT 는 UPLOAD_DRAFT 다음 자리였다.
_PRIOR_FK_BY_DOMAIN = {
    'ORDER_EVENT': 'order_event_id',
    'NOTIFICATION_EVENT': 'notification_event_id',
    'ADDRESS_LEARNING': 'address_learning_request_id',
    'WIZARD_PENDING': 'wizard_pending_id',
    'UPLOAD_TICKET': 'upload_ticket_id',
    'UPLOAD_DRAFT': 'upload_draft_id',
    'CHAT_ATTACHMENT': 'chat_attachment_id',
    'ORDER_IMPORT_ARTIFACT': 'order_import_artifact_id',
}

_CHAT_TABLES_CHILD_FIRST = ('chat_attachments', 'chat_messages', 'chat_room_members', 'chat_rooms')


def _domain_in_sql(fk_by_domain: dict) -> str:
    """``source_domain IN (...)`` CHECK 식을 도메인 dict 로부터 만든다."""
    return "source_domain IN (" + ", ".join("'%s'" % d for d in fk_by_domain) + ")"


def _one_of_sql(fk_by_domain: dict) -> str:
    """exact one-of FK 매트릭스 CHECK 식을 도메인 dict 로부터 만든다(models 생성기와 동일 규칙)."""
    cols = list(fk_by_domain.values())
    clauses = []
    for domain, own in fk_by_domain.items():
        parts = ["source_domain = '%s'" % domain, "%s IS NOT NULL" % own]
        parts += ["%s IS NULL" % c for c in cols if c != own]
        clauses.append("(" + " AND ".join(parts) + ")")
    return " OR ".join(clauses)


def _replace_checks(fk_by_domain: dict) -> None:
    op.create_check_constraint('ck_dseo_source_domain', _OUTBOX, _domain_in_sql(fk_by_domain))
    op.create_check_constraint('ck_dseo_source_one_of', _OUTBOX, _one_of_sql(fk_by_domain))


def upgrade() -> None:
    """대기열 CHECK 7도메인 · chat_attachment_id 칸 지우기 · 채팅 표 4개 지우기."""
    op.drop_constraint('ck_dseo_source_one_of', _OUTBOX, type_='check')
    op.drop_constraint('ck_dseo_source_domain', _OUTBOX, type_='check')
    op.drop_column(_OUTBOX, 'chat_attachment_id')
    _replace_checks(_CHAT_DROP01_FK_BY_DOMAIN)
    for table in _CHAT_TABLES_CHILD_FIRST:
        op.drop_table(table)


def downgrade() -> None:
    """빈 채팅 표 4개 · 색인 · 대기열 칸 · FK · 8도메인 CHECK 복원(지운 줄은 돌아오지 않는다)."""
    op.create_table(
        'chat_rooms',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id'), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'chat_room_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('room_id', sa.Integer(), sa.ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.Column('last_read_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('room_id', sa.Integer(), sa.ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('message_type', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('file_info', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_chat_messages_room_id', 'chat_messages', ['room_id'])
    op.create_index('ix_chat_messages_created_at', 'chat_messages', ['created_at'])
    op.create_table(
        'chat_attachments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('message_id', sa.Integer(), sa.ForeignKey('chat_messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_type', sa.String(50), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('storage_url', sa.String(1000), nullable=False),
        sa.Column('thumbnail_url', sa.String(1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_chat_attachments_message_id', 'chat_attachments', ['message_id'])
    # phase_f_trgm_search_indexes 가 만들던 trgm 색인 2개(빈 표라 CONCURRENTLY 없이).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_rooms_name_trgm ON chat_rooms USING gin (name gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_messages_content_trgm ON chat_messages USING gin (content gin_trgm_ops)")

    op.drop_constraint('ck_dseo_source_one_of', _OUTBOX, type_='check')
    op.drop_constraint('ck_dseo_source_domain', _OUTBOX, type_='check')
    op.add_column(_OUTBOX, sa.Column('chat_attachment_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'domain_side_effect_outbox_chat_attachment_id_fkey', _OUTBOX,
        'chat_attachments', ['chat_attachment_id'], ['id'], ondelete='CASCADE',
    )
    _replace_checks(_PRIOR_FK_BY_DOMAIN)
