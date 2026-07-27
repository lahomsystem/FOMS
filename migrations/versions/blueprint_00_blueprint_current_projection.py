"""BLUEPRINT-01: blueprint scalar → typed current projection safe backfill

Revision ID: blueprint_00
Revises: construction_backfill_00
Create Date: 2026-07-27

§5.2 BLUEPRINT-01. legacy blueprint route(P0-11)는 도면 이미지를 ``orders.blueprint_image_url``
scalar 에 직접 썼다. 이 마이그레이션은 그 scalar 를 **typed current projection**
(``structured_data['blueprint']['current']``)으로 **무손실 backfill(100%)** 한다.

* **safe backfill**: ``/api/files/view/<key>`` 형태이고 그 key 가 대상 order 기준 canonical
  (``validate_upload_key`` 통과)일 때만 ``object_key`` 를 유도한다(exact). 외부/비정규 URL 은
  **object_key 를 자동 추정하지 않고**(ambiguous auto-map 금지) 원문 URL 을 ``view_url`` 로
  보존한다 → 어느 쪽이든 원문 무손실.
* **scalar 유지**: read 소비처(템플릿·검색·storage cleanup)가 아직 scalar 를 읽으므로
  ``orders.blueprint_image_url`` 컬럼은 **drop 하지 않는다**(전환 안전 — projection 병행).
  이 마이그레이션은 scalar 를 읽기만 하고 수정하지 않는다.
* **멱등·resume**: 이미 ``current`` projection 이 있는 order 는 건드리지 않는다.

backfill/coverage 로직 SSOT 는 :mod:`foms.services.orders.blueprint_projection`. downgrade 는
``provenance='migration_backfill'`` 로 표시된 projection 만 제거하고 ticket projection·다른
blueprint sub-key·scalar 는 보존한다.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session

revision: str = 'blueprint_00'
down_revision: Union[str, None] = 'construction_backfill_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """legacy blueprint scalar 를 typed current projection 으로 safe backfill(100%)."""
    from foms.services.orders.blueprint_projection import apply_blueprint_backfill

    session = Session(bind=op.get_bind())
    apply_blueprint_backfill(session, apply=True)
    session.flush()


def downgrade() -> None:
    """migration_backfill provenance 의 current projection 만 제거(ticket/scalar 보존)."""
    from foms.services.orders.blueprint_projection import remove_backfill_projection

    session = Session(bind=op.get_bind())
    remove_backfill_projection(session)
    session.flush()
