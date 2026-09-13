"""NVMIRROR-01: external_order_links 클레임 축 사본 컬럼 4개

Revision ID: nvmirror_00
Revises: mgrroom_00
Create Date: 2026-09-13

``raw_snapshot`` 평균이 **2,194 bytes** 라 PostgreSQL TOAST 임계(약 2KB)를 넘는다 — 즉 대부분의
스냅샷이 본체 밖에 있고, 그 컬럼을 건드리는 조회는 행마다 TOAST 를 한 번 더 읽는다. 운영에서
같은 스캔을 두 방식으로 재면 차이가 그대로 보인다(2026-09-13, 2,388행).

    raw_snapshot 에서 스칼라 두 개를 뽑는다 →  Buffers: shared hit=14736,  50.519 ms
    raw_snapshot 을 아예 안 건드린다       →  Buffers: shared hit=  249,   0.953 ms

스칼라 투영은 이미 쓰고 있으므로 투영으로는 더 줄지 않는다 — **컬럼을 건드리는 것 자체**가
비용이다. 그래서 자주 보는 값을 사본 컬럼으로 뺀다.

``place_order_status``·``group_key``·``recipient_*`` 와 **같은 규약**이다: 정본은 여전히
``raw_snapshot`` 이고 이 컬럼들은 필터·집계 전용 사본이며, 값이 없는 옛 행은 읽는 쪽이 종전
스냅샷 경로로 폴백한다(그래서 채우기 전에도 답이 안 바뀐다).

인덱스는 만들지 않는다 — 지금 병목은 인덱스 부재가 아니라 TOAST 읽기이고, 컬럼만으로 위
53배가 나온다. 필요해지면 실측 뒤 따로 판단한다(스펙 §5-4).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(리터럴만 쓴다).
데이터 채움은 여기서 하지 않는다 — 클레임 판정 규칙(``mapping.extract_claim``)이 서비스
코드에 있어 여기 복제하면 규칙이 두 벌이 된다. 채움은
``scripts/maintenance/backfill_link_claim_mirror.py`` 가 한다.

스펙: docs/specs/2026-09-13-naver-link-claim-mirror_SPEC.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "nvmirror_00"
down_revision: Union[str, None] = "mgrroom_00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "external_order_links"
#: 길이는 원본 값이 아니라 **우리가 자르는 상한**이다 — 채널이 더 긴 코드를 보내도 사본이
#: 터지지 않게 서비스 코드가 잘라 넣는다(사본이 수집을 막아선 안 된다).
_COLUMNS = (
    ("product_order_status", sa.String(length=30)),
    ("claim_status", sa.String(length=40)),
    ("claim_type", sa.String(length=20)),
    ("payment_amount", sa.Integer()),
)


def upgrade() -> None:
    """사본 컬럼 4개를 만든다(전부 nullable, server_default 없음)."""
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}
    for name, type_ in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    """컬럼 4개 제거. 사본이라 지워도 정본(``raw_snapshot``)은 그대로다."""
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}
    for name, _type in _COLUMNS:
        if name in existing:
            op.drop_column(_TABLE, name)
