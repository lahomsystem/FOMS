"""NAVER-INGEST-BACKFILL: external_order_links 매칭 축 사본 컬럼 3개 + 부분 인덱스 3개

Revision ID: naverbf_00
Revises: naverdisp_00
Create Date: 2026-09-01

"오늘 실측인데 안 붙은 집" 매칭(``bulk_dispatch.find_unlinked_matches``)의 축은 수취인
전화·주문자 전화·수령인명인데, 셋 다 ``raw_snapshot``(JSONB) 안에 있고 전화는 정규화가
필요해 SQL 이 좁힐 수 없었다. 그래서 미연결 링크를 **id 내림차순 300행**만 훑는 캡이
걸려 있었고, 과거 주문 소급 수집(백필)으로 미연결이 1,500행대가 되면 그 캡이 즉시
차버려 띠가 조용히 잘린다(경고 로그만 남는다).

``group_key`` 와 같은 규약의 사본 컬럼이다 — 정본은 여전히 ``raw_snapshot`` 이고, 이
컬럼들은 SQL 이 좁힐 수 있게 두는 필터 전용 사본이다. 값이 없는 옛 행은 읽는 쪽이 종전
스캔 경로로 폴백하므로 채우기 전에도 화면이 죽지 않는다.

인덱스는 **미연결 행만** 담는 부분 인덱스다(``order_id IS NULL``). 붙고 나면 매칭 대상이
아니므로 인덱스가 수집 이력 전체 크기로 자라지 않는다.

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(리터럴만 쓴다).
데이터 채움은 여기서 하지 않는다 — 파싱 규칙이 서비스 코드에 있어 여기 복제하면 규칙이
두 벌이 된다. 채움은 ``tools/ops/backfill_link_match_keys.py`` 가 한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "naverbf_00"
down_revision: Union[str, None] = "naverdisp_00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "external_order_links"
_COLUMNS = (
    ("recipient_name", sa.String(length=80)),
    ("recipient_phone_digits", sa.String(length=20)),
    ("orderer_phone_digits", sa.String(length=20)),
)
_INDEXES = (
    ("ix_external_order_link_match_recipient_phone", ["channel", "recipient_phone_digits"]),
    ("ix_external_order_link_match_orderer_phone", ["channel", "orderer_phone_digits"]),
    ("ix_external_order_link_match_name", ["channel", "recipient_name"]),
)


def upgrade() -> None:
    """사본 컬럼 3개와 미연결 전용 부분 인덱스 3개를 만든다."""
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}
    for name, type_ in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, type_, nullable=True))
    for name, columns in _INDEXES:
        op.create_index(name, _TABLE, columns,
                        postgresql_where=sa.text("order_id IS NULL"))


def downgrade() -> None:
    """인덱스 → 컬럼 역순 제거. 사본이라 지워도 정본(raw_snapshot)은 그대로다."""
    for name, _columns in _INDEXES:
        op.drop_index(name, table_name=_TABLE)
    for name, _type in _COLUMNS:
        op.drop_column(_TABLE, name)
