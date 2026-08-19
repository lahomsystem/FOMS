"""NAVER-INGEST-02 T16-B: external_order_links 관계 축 + 발주 상태 컬럼

Revision ID: naver_relation_00
Revises: assort_00
Create Date: 2026-08-19

수집 판정이 ``productOrderStatus == PAYED`` 하나뿐이라 **취소 후 재결제**와 **기존 주문의
차액 결제**가 전부 새 집으로 들어온다(스테이징 실데이터: 같은 고객 2회 4명, 소액 단독 2집).
사람이 "이건 기존 주문에 붙는 건"이라고 고를 수 있으려면 그 판정을 담을 축이 필요하다.

* ``relation`` — ``NEW``(새 주문) / ``ADDON``(추가결제) / ``REPAY``(재결제).
  ``sync_status``(수집 결과)·``reviewed_at``(사람 확인)과 **다른 축**이다. 섞으면
  "수집 성공 + 사람 확인 + 기존 주문에 붙임"을 표현할 수 없다.
* ``place_order_status`` — 원본 ``placeOrderStatus`` 의 사본. 정본은 ``raw_snapshot`` 이지만
  그 JSONB 로 목록을 필터하면 인덱스 없는 스캔이 된다(hot path 규칙). 필터 전용 사본이다.

백필: 기존 행의 ``relation`` 은 전부 ``NEW``(server_default 가 채운다). ``place_order_status``
는 ``raw_snapshot`` 에서 뽑아 채운다 — **``mapping`` 을 import 하지 않고** 이 파일 안에서
직접 판독한다(마이그레이션 상수 동결 원칙: live 코드가 바뀌어도 과거 마이그레이션 결과는
그대로여야 한다). JSON 경로는 ``productOrder.placeOrderStatus``, 평평한 응답 대비로
최상위·``order`` 도 본다.

``downgrade()`` 는 인덱스 → 체크 제약 → 컬럼 순으로 지운다. 되돌리면 사람이 고른 관계 판정이
사라진다(무손실 역변환 아님) — ADDON/REPAY 로 붙인 링크는 ``order_id`` 만 남아 새 주문과
구분되지 않는다.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'naver_relation_00'
down_revision: Union[str, None] = 'assort_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'external_order_links'
CHECK_NAME = 'ck_external_order_link_relation'
INDEX_NAME = 'ix_external_order_link_place'

#: 백필 배치 크기. 원본 JSONB 가 건당 수 KB라 한 번에 다 들지 않는다.
BATCH = 500


def _place_status(raw) -> str:
    """원본 스냅샷에서 ``placeOrderStatus`` 를 뽑는다(이 마이그레이션 안에 동결).

    Args:
        raw: ``raw_snapshot`` 값(dict 또는 JSON 문자열, SQLite 레인은 문자열로 온다).

    Returns:
        상태 문자열. 없거나 못 읽으면 빈 문자열.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return ''
    if not isinstance(raw, dict):
        return ''
    product_order = raw.get('productOrder')
    if not isinstance(product_order, dict):
        product_order = raw
    order = raw.get('order') if isinstance(raw.get('order'), dict) else {}
    value = product_order.get('placeOrderStatus') or order.get('placeOrderStatus')
    return str(value).strip() if value is not None else ''


def upgrade() -> None:
    """관계 축·발주 상태 컬럼 + 체크 제약 + 필터 인덱스 + 발주 상태 백필."""
    op.add_column(TABLE, sa.Column('relation', sa.String(length=10), nullable=False,
                                   server_default='NEW'))
    op.add_column(TABLE, sa.Column('place_order_status', sa.String(length=20), nullable=True))
    op.create_check_constraint(CHECK_NAME, TABLE, "relation IN ('NEW','ADDON','REPAY')")
    op.create_index(INDEX_NAME, TABLE, ['channel', 'place_order_status', 'created_at'])

    # 백필: 이미 수집된 건도 화면 필터에 잡혀야 한다(안 하면 전부 '모름'으로 남는다).
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        f"SELECT id, raw_snapshot FROM {TABLE} WHERE raw_snapshot IS NOT NULL"
    )).fetchall()
    updates = []
    for row in rows:
        status = _place_status(row[1])
        if status:
            updates.append({'row_id': row[0], 'status': status[:20]})
    for start in range(0, len(updates), BATCH):
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET place_order_status = :status WHERE id = :row_id"),
            updates[start:start + BATCH],
        )


def downgrade() -> None:
    """생성 역순 제거. 사람이 고른 관계 판정이 사라진다(무손실 아님)."""
    op.drop_index(INDEX_NAME, table_name=TABLE)
    op.drop_constraint(CHECK_NAME, TABLE, type_='check')
    op.drop_column(TABLE, 'place_order_status')
    op.drop_column(TABLE, 'relation')
