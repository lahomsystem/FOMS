"""AUDIT-LOG T6: access_logs 조회 인덱스 (파일 접근 기록 부활)

Revision ID: access_log_00
Revises: attach_life_00
Create Date: 2026-08-06

``access_logs`` 는 writer 0 건의 사문 테이블이었다(스펙 §2). T6 이 파일 라우트 3곳
(view/presigned/download)에서 이 테이블에 쓰기 시작하면 **행이 계속 늘어나는 감사 원장**이
된다. 조회 화면은 만들지 않고 SQL 전용으로 쓰기로 했으므로(스펙 §3-1 한계 명시), 실제로
돌 질의 2종에만 인덱스를 붙인다:

* ``ix_access_logs_user_id_timestamp`` — "이 사용자가 최근 무슨 파일을 봤나"
  (``WHERE user_id = ? ORDER BY timestamp DESC``). 사고 조사의 기본 질의다.
* ``ix_access_logs_timestamp`` — 기간 조회 + T9 retention purge 의 keyset 스캔
  (``WHERE timestamp < ? ORDER BY timestamp``). 단독 timestamp 인덱스가 없으면 purge 가
  매 배치마다 Seq Scan 을 돈다.

**models.py 는 건드리지 않는다**(T6 파일 경계 — 기존 스키마 그대로 사용). 따라서
``Base.metadata.create_all`` 로 스키마를 만드는 레인(pytest·PG 테스트 레인)에는 이 인덱스가
없고, 실 DB 에는 이 마이그레이션으로만 생긴다. 인덱스는 질의 계획에만 영향을 주고 결과에는
영향이 없으므로 이 드리프트는 무해하다 — 그래도 ``tests/postgres/test_file_access_log_pg.py``
가 이 마이그레이션을 실제로 upgrade→downgrade→upgrade 돌려 DDL 을 증명한다.

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(테이블/컬럼명 리터럴).
``downgrade()`` 는 생성 역순으로 두 인덱스를 되돌린다(데이터 손실 없음).
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'access_log_00'
down_revision: Union[str, None] = 'attach_life_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'access_logs'
USER_TIME_INDEX = 'ix_access_logs_user_id_timestamp'
TIME_INDEX = 'ix_access_logs_timestamp'


def upgrade() -> None:
    """감사 조회용 인덱스 2개 추가 (사용자별 최근 접근 · 기간/purge keyset)."""
    op.create_index(USER_TIME_INDEX, TABLE, ['user_id', 'timestamp'])
    op.create_index(TIME_INDEX, TABLE, ['timestamp'])


def downgrade() -> None:
    """생성 역순으로 인덱스 제거."""
    op.drop_index(TIME_INDEX, table_name=TABLE)
    op.drop_index(USER_TIME_INDEX, table_name=TABLE)
