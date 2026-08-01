"""WDC-LINK-BACKFILL-00: canonical estimate<->order link (estimate_order_links_v2)

Revision ID: wdc_link_backfill_00
Revises: drawing_revision_00
Create Date: 2026-07-26

§5.2 WDC-LINK-BACKFILL-00 의 canonical ``estimate_order_links_v2``(``EstimateOrderLinkV2``)를
신설한다. legacy ``EstimateOrderMatch``(V1, ``wdcalculator_models``)는 오늘 estimate↔order 매칭을
``(estimate_id, order_id)`` 로만 기록하고 **unique pair 제약이 없어** 중복 pair 가 물리적으로
가능하다. 이 canonical 테이블은 그 pair 를 유일화하고(``uq_estimate_order_link_v2_pair``), 이
row 를 만든 위상(``source_topology``)·발급 근거 V1 id(``source_match_id``)·발급 resume run
(``backfill_run_id``, ``V2_BACKFILL_*`` phase)을 provenance 로 남긴다.

이 마이그레이션은 **순수 스키마 추가** 다: canonical 테이블만 만들고 legacy ``EstimateOrderMatch``
테이블/row 는 손대지 않는다(V1 병행·V1 cleanup 0 — cleanup 은 WDC-LINK-CLEANUP-01 하류 몫).
canonical row 를 발급하는 topology-aware backfill(SAME online atomic dual-write / SEPARATE
FROZEN apply) 은 ``foms.services.orders.backfill_estimate_order_links`` 다. DDL 은
``models.EstimateOrderLinkV2``(create_all 테스트 lane)과 SSOT 를 공유한다.

``estimate_id``/``order_id`` 는 SEPARATE 위상에서 cross-DB 라 물리 FK 를 걸지 않는다(V1 의
``order_id`` 와 동일한 논리 참조 규약).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'wdc_link_backfill_00'
down_revision: Union[str, None] = 'drawing_revision_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """canonical estimate_order_links_v2 생성(unique pair + topology check). V1 무변경."""
    op.create_table(
        'estimate_order_links_v2',
        sa.Column('id', sa.Integer(), primary_key=True),
        # 논리 참조(물리 FK 아님 — SEPARATE 위상 cross-DB).
        sa.Column('estimate_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        # 이 row 를 만든 위상(phase conflation 감사용).
        sa.Column('source_topology', sa.String(length=20), nullable=False),
        # provenance: 발급 근거 V1 estimate_order_matches.id(중복 pair 는 최소 id).
        sa.Column('source_match_id', sa.Integer(), nullable=True),
        # 발급 resume run id(V2_BACKFILL_* phase) — checkpoint 원장·phase run ID 연결.
        sa.Column('backfill_run_id', sa.String(length=64), nullable=True),
        sa.Column('linked_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('estimate_id', 'order_id', name='uq_estimate_order_link_v2_pair'),
        sa.CheckConstraint(
            "source_topology IN ('SAME_DATABASE','SEPARATE_DATABASE')",
            name='ck_estimate_order_link_v2_topology',
        ),
    )
    op.create_index(
        'ix_estimate_order_links_v2_estimate_id', 'estimate_order_links_v2', ['estimate_id']
    )
    op.create_index(
        'ix_estimate_order_links_v2_order_id', 'estimate_order_links_v2', ['order_id']
    )


def downgrade() -> None:
    """canonical 테이블 제거(V1 은 애초에 손대지 않았으므로 복원 없음)."""
    op.drop_index('ix_estimate_order_links_v2_order_id', table_name='estimate_order_links_v2')
    op.drop_index('ix_estimate_order_links_v2_estimate_id', table_name='estimate_order_links_v2')
    op.drop_table('estimate_order_links_v2')
