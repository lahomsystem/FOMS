"""SEC-LOG-TIME-00: security_logs 정렬 인덱스 (감사 화면 기본 조회 Seq Scan 제거)

Revision ID: seclog_time_00
Revises: accesslog_detail_00
Create Date: 2026-08-08

관리자 감사 화면(``foms/web/admin/audit.py`` ``security_logs()``)의 기본 조회는
``ORDER BY timestamp DESC, id DESC`` + 전체 ``count(*)`` 인데, ``security_logs`` 에는
timestamp 를 **선행 컬럼으로 갖는 인덱스가 없다**:

* ``ix_security_logs_target`` — 선행이 ``target_type`` 이라 이 정렬에 못 쓴다.
* ``ix_security_logs_message_trgm`` — GIN, ``message`` 자유 검색 전용.

그래서 매 페이지가 Seq Scan + Sort 다. 실측 24,572행(20.64 MB)에서는 아직 수 ms 지만,
보존기간 권고안(보안 3년)과 승격 후 증가율(95행/일 추정)이면 10만행대가 되고 감사 화면이
급격히 나빠진다(``docs/plans/2026-08-07-audit-retention-analysis.md`` §서두가 지목한 병목).

``(timestamp, id)`` 복합 btree 하나로 정렬 tie-break 까지 해결된다. DESC 는 PostgreSQL 이
backward index scan 으로 처리하므로 DESC 인덱스를 따로 만들지 않는다.

``CONCURRENTLY`` 는 쓰지 않는다 — alembic 이 마이그레이션을 트랜잭션 안에서 실행하므로
불가능하고, 2만행대에서 ``CREATE INDEX`` 락은 1초 미만이다.

**``models.py`` 의 ``SecurityLog.__table_args__`` 와 이름·컬럼 순서가 완전히 같아야 한다** —
create_all 레인과 alembic 레인이 다른 스키마가 되면 체인 왕복 테스트가 red 로 잡는다.

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(테이블/컬럼명 리터럴).
``downgrade()`` 는 인덱스만 되돌린다(데이터 손실 0 — 인덱스는 질의 계획에만 영향).
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'seclog_time_00'
down_revision: Union[str, None] = 'accesslog_detail_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'security_logs'
TIME_INDEX = 'ix_security_logs_timestamp_id'


def upgrade() -> None:
    """감사 화면 기본 조회용 ``(timestamp, id)`` 복합 인덱스 추가."""
    op.create_index(TIME_INDEX, TABLE, ['timestamp', 'id'])


def downgrade() -> None:
    """인덱스 제거(데이터 무영향)."""
    op.drop_index(TIME_INDEX, table_name=TABLE)
