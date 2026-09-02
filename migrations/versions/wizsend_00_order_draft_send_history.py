"""WIZ-SEND-01: order_drafts.send_history 추가 (초안 발송 이력, 서버 전용 쓰기)

Revision ID: wizsend_00
Revises: phonewide_01
Create Date: 2026-09-02

모바일 마법사 4단계에서 주문 등록 **전에** 실측 PUSH·예약안내 알림톡을 보낼 수 있게 되면서,
그 발송 흔적을 남길 자리가 필요해졌다. ``order_drafts.payload`` 는 매 autosave 마다
클라이언트가 통째로 덮으므로 거기 쓰면 다음 자동저장 한 번에 사라진다 — 서버만 쓰는 별도
컬럼이 이 컬럼의 존재 이유다.

모양은 ``{kind: entry}``:

* ``alimtalk_measurement``          — 주문 ``structured_data`` 정본 이력과 동일한 dict
* ``channeltalk_push_measure_room`` — 실측방 수동 push 메타와 동일한 dict

주문 등록(``POST /api/erp/order-draft/submit``) 시 새 주문 ``structured_data`` 로 승계되고
초안 행은 그대로 삭제되므로, 이 컬럼은 초안 수명(7일 TTL) 안에서만 산다. 기존 행은 NULL 로
남고 서비스는 NULL 을 ``{}`` 로 읽는다 — 백필 불필요.

상수 동결: ``models`` 를 import 하지 않는다(과거 마이그레이션 소급 오염 방지).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'wizsend_00'
down_revision: Union[str, None] = 'phonewide_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'order_drafts'
COLUMN = 'send_history'
# models.JSONColumn 과 같은 형태를 리터럴로 재현한다(모델 import 금지 — 상수 동결).
_JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def upgrade() -> None:
    """order_drafts.send_history(JSON, nullable) 를 추가한다."""
    op.add_column(TABLE, sa.Column(COLUMN, _JSON_TYPE, nullable=True))


def downgrade() -> None:
    """send_history 컬럼을 제거한다.

    초안은 TTL 7일 임시 행이고 이력은 등록 시 주문으로 승계되므로, 이 컬럼을 되돌려도
    영구 데이터는 잃지 않는다(아직 등록되지 않은 초안의 발송 흔적만 사라진다).
    """
    op.drop_column(TABLE, COLUMN)
