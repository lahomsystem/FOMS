"""ACCESS-LOG-DETAIL-00: access_logs 구조화 payload 컬럼 + 주문 축 인덱스

Revision ID: accesslog_detail_00
Revises: auditlife_00
Create Date: 2026-08-08

T12 파일 열람 화면의 주문 필터는 ``additional_data`` 가 JSON **문자열**(Text)이라
``LIKE '%"order_id": 12,%'`` 로 물을 수밖에 없었다. 인덱스를 못 타는 것도 문제지만,
구분자(``,``/``}``)를 손으로 붙여 접두 오탐(주문 12 ↔ 123)을 막는 계약 자체가 취약하다.

이 마이그레이션은 T8 ``seclog_struct_00`` 이 ``security_logs`` 에서 쓴 방식을 그대로 따라
**질의 가능한 사본**을 additive 로 만든다:

* ``detail`` — 구조화 payload(JSONB on PostgreSQL). ``additional_data`` 원문은 **보존**한다.
  승격 롤백 시 구버전 코드가 읽을 값이 남아야 하고, 감사 원장은 형식 변경으로 값을 잃으면
  안 된다.
* ``ix_access_logs_detail_order_id`` — ``((detail ->> 'order_id')::integer)`` 표현식 인덱스.
  ORM 이 PG 에서 내는 비교식(``CAST((detail ->> 'order_id') AS INTEGER)``)과 **같은 모양**
  이어야 계획기가 매칭한다. PostgreSQL 전용이라 다른 dialect 에서는 만들지 않는다
  (SQLite 는 같은 비교를 ``JSON_EXTRACT`` 로 내므로 이 인덱스가 무의미하다).

백필 범위는 **파일 접근 3종(FILE_VIEW/FILE_PRESIGNED/FILE_DOWNLOAD)뿐**이다. ``access_logs``
에는 T6 이전 구현이 남긴 구 형식 행이 다수 섞여 있고(스테이징 실측 121행 중 119행), 그
payload 에는 고객명·연락처 같은 PII 가 들어 있다 — 그것을 질의 가능한 JSONB 컬럼으로
옮기면 PII 노출면이 넓어진다. 구 형식 행은 ``detail`` NULL 로 남고 원문은 그대로다.

백필은 SQL 캐스트가 아니라 **Python 파싱**으로 한다. ``additional_data`` 는 과거 writer 가
자유 형식으로 쓴 컬럼이라 ``::jsonb`` 일괄 캐스트는 비-JSON 행 한 건에 마이그레이션 전체가
파산한다. 파싱 실패 행은 건너뛰고 원문을 남긴다(감사 원장은 지우지 않는다).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(테이블/컬럼명 리터럴).
``downgrade()`` 는 인덱스 → 컬럼 순으로 되돌린다 — ``additional_data`` 원문이 그대로 있으므로
데이터 손실 0 의 완전 가역 변경이다.
"""
from typing import Any, Sequence, Union

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'accesslog_detail_00'
down_revision: Union[str, None] = 'auditlife_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'access_logs'
DETAIL_COLUMN = 'detail'
ORDER_INDEX = 'ix_access_logs_detail_order_id'
# ``models.py`` 의 Index 표현식과 문자 그대로 같아야 한다(create_all 레인 정합).
ORDER_INDEX_EXPRESSION = "((detail ->> 'order_id')::integer)"
# 백필 대상 — writer(``record_file_access``)가 쓰는 파일 접근 3종만.
FILE_ACCESS_ACTIONS = ('FILE_VIEW', 'FILE_PRESIGNED', 'FILE_DOWNLOAD')
# models.JSONColumn 과 같은 형태를 리터럴로 재현한다(모델 import 금지 — 상수 동결).
_JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')

_access_logs = sa.table(
    TABLE,
    sa.column('id', sa.Integer),
    sa.column('action', sa.String),
    sa.column('additional_data', sa.Text),
    sa.column(DETAIL_COLUMN, _JSON_TYPE),
)


def _backfill_detail(bind: sa.engine.Connection) -> int:
    """파일 접근 3종 행의 ``additional_data`` 를 파싱해 ``detail`` 에 채운다.

    :param bind: 마이그레이션 커넥션.
    :return: 실제로 채운 행 수(파싱 실패·dict 아님·빈 값은 건너뛴다).
    """
    rows = bind.execute(
        sa.select(_access_logs.c.id, _access_logs.c.additional_data).where(
            _access_logs.c.action.in_(FILE_ACCESS_ACTIONS)
        )
    ).fetchall()

    filled = 0
    for row_id, raw in rows:
        if not raw:
            continue
        try:
            parsed: Any = json.loads(raw)
        except (TypeError, ValueError):
            continue  # 자유 형식 원문은 Text 컬럼에 그대로 남는다
        if not isinstance(parsed, dict):
            continue
        bind.execute(
            _access_logs.update()
            .where(_access_logs.c.id == row_id)
            .values(**{DETAIL_COLUMN: parsed})
        )
        filled += 1
    return filled


def upgrade() -> None:
    """``detail`` JSONB 컬럼 추가 → 파일 접근 행 백필 → 주문 축 표현식 인덱스(PG 전용)."""
    op.add_column(TABLE, sa.Column(DETAIL_COLUMN, _JSON_TYPE, nullable=True))

    bind = op.get_bind()
    _backfill_detail(bind)

    # 표현식 인덱스는 PostgreSQL 전용 — 백필 뒤에 만든다(비어 있는 인덱스를 채우는 것보다
    # 싸고, 백필이 실패하면 인덱스도 만들지 않는다).
    if bind.dialect.name == 'postgresql':
        op.execute(
            f'CREATE INDEX {ORDER_INDEX} ON {TABLE} ({ORDER_INDEX_EXPRESSION})'
        )


def downgrade() -> None:
    """생성 역순으로 인덱스 → ``detail`` 컬럼 제거(``additional_data`` 원문은 보존)."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(f'DROP INDEX IF EXISTS {ORDER_INDEX}')
    op.drop_column(TABLE, DETAIL_COLUMN)
