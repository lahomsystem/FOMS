"""NOTICE-01: 공지 폰 알림 + 배지 — notices.push_sent_at · notice_acks.notification_id

Revision ID: notice_01
Revises: csagent_05
Create Date: 2026-11-02

설계 정본: docs/specs/2026-11-02-foms-notices_SPEC.md §7(폰 알림 · 배지). 설계서는 ``notice_00`` 뒤에 잇는다고 적었지만
그 사이 ``csagent_06`` · ``csagent_05`` 가 먼저 들어가 머리가 ``csagent_05`` 다 — 머리 하나를 지키려고 그 뒤로 잇는다.

* ``notices.push_sent_at`` — 폰 알림을 보낸(또는 끝난 예약 공지라 보내지 않기로 정한) 때(UTC). 비면 아직 안 보냄 — 웹 만들기와
  SIDEFX 예약 스캔이 ``UPDATE ... WHERE push_sent_at IS NULL`` 선점으로 한 번만 보낸다. **업그레이드 때 이미 있는 공지는
  지금 때로 채운다** — 배포 직후 SIDEFX 스캔이 옛 공지를 한꺼번에 울리지 않게 한다(데이터 변경은 이 한 번뿐).
* ``notice_acks.notification_id`` — 이 사람에게 보낸 ``FOMS_NOTICE`` 알림. 공지를 읽거나 확인하면 그 알림 상태도 읽음으로
  바꿔 앱 · 종 배지 숫자가 준다. 알림 줄이 지워지면 비운다(ON DELETE SET NULL, 이름 ``fk_notice_acks_notification_id``).

``downgrade()`` 는 FK → 칸 순서로 지운다(보낸 때 · 알림 연결이 사라진다 — 공지 · 확인 기록 · 알림 줄은 남는다).
DDL 은 models.py ``Notice.push_sent_at`` · ``NoticeAck.notification_id`` 와 같다. 상수 동결 원칙에 따라 models 를 import 하지 않는다.
"""
import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'notice_01'
down_revision: Union[str, None] = 'csagent_05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTICES = 'notices'
ACKS = 'notice_acks'
FK_NAME = 'fk_notice_acks_notification_id'


def upgrade() -> None:
    """칸 둘 + FK, 그리고 이미 있는 공지는 보낸 것으로 친다."""
    op.add_column(NOTICES, sa.Column('push_sent_at', sa.DateTime(), nullable=True))
    op.add_column(ACKS, sa.Column('notification_id', sa.Integer(), nullable=True))
    op.create_foreign_key(FK_NAME, ACKS, 'notifications', ['notification_id'], ['id'], ondelete='SET NULL')
    # 배포 직후 옛 공지가 폰에 한꺼번에 울리지 않게 — 이미 있는 줄은 지금 보낸 것으로 친다(UTC naive 규약).
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    op.get_bind().execute(
        sa.text("UPDATE notices SET push_sent_at = :now WHERE push_sent_at IS NULL"), {"now": now}
    )


def downgrade() -> None:
    """FK → notice_acks.notification_id → notices.push_sent_at."""
    op.drop_constraint(FK_NAME, ACKS, type_='foreignkey')
    op.drop_column(ACKS, 'notification_id')
    op.drop_column(NOTICES, 'push_sent_at')
