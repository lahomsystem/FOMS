"""NOTIF-ROLE-01: notifications.target_role (역할 대상 알림)

Revision ID: notifrole_00
Revises: naver_relation_00
Create Date: 2026-08-20

관리자 전원에게 가는 알림은 지금까지 **수신자 수만큼 별개 Notification row** 로
만들어졌다. 알림 SSOT 는 ``공유 Notification 1건 + 수신자별 notification_user_states``
인데, 대상을 "역할"로 적을 칸이 없어 코드가 사람 수만큼 사건을 복제한 것이다.
``target_role`` 은 그 칸이다 — ``target_type='ROLE'`` 일 때 이 역할의 활성 사용자
전원에게 state 를 만들고, 사건은 다시 row 1건으로 돌아온다.

NULL 은 "역할 대상이 아님"(기존 ORDER/ALL/TEAM/USER 경로 전부) — 레거시 행 백필은
없다. 역할 목록·기본 역할 같은 값 판정은 코드 몫이라 CHECK 제약을 걸지 않는다
(역할이 늘 때마다 마이그레이션을 다시 쓰게 된다). 인덱스는 "이 역할 대상 알림"
조회용 1개만 만든다 — 이름은 ``create_all`` 기본값(``index=True``)과 같아야 신규
부트스트랩 DB 와 마이그레이션 계보가 갈라지지 않는다(MIGCHAIN-01 왕복 게이트).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(리터럴 고정).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "notifrole_00"
down_revision: Union[str, None] = "naver_relation_00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "notifications"
COLUMN = "target_role"
INDEX_NAME = "ix_notifications_target_role"


def upgrade() -> None:
    """nullable VARCHAR(20) 컬럼 + 조회 인덱스. 기존 행은 NULL(역할 대상 아님)."""
    op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=20), nullable=True))
    op.create_index(INDEX_NAME, TABLE, [COLUMN])


def downgrade() -> None:
    """생성 역순 제거. 역할 대상 알림은 수신 대상을 잃는다(무손실 역변환 아님)."""
    op.drop_index(INDEX_NAME, table_name=TABLE)
    op.drop_column(TABLE, COLUMN)
