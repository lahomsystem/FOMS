"""PHONEWIDE-01: erp_phone_digits 20자 절단 해소 (VARCHAR(20) -> VARCHAR(64))

Revision ID: phonewide_00
Revises: merge_naverbf_share
Create Date: 2026-09-02

전화번호를 여러 개 적은 주문("010-8935-0264(고객), 010-5875-1125(팀장)")은 숫자열이
22~23자가 되는데, ``orders.erp_phone_digits`` 가 ``VARCHAR(20)`` 이고
``normalize_phone_digits`` 도 20자에서 잘라 **두 번째 번호의 뒷자리가 소실**됐다.
증상은 그 번호로 통합 검색이 안 걸리는 것(운영 실측 2026-09-02: 정확히 20자 81건,
``phone`` 숫자열 20자 초과 72건, 최대 23자).

이 마이그레이션은 두 가지를 한다.

1. 컬럼 폭을 64로 넓힌다. PostgreSQL 에서 varchar 길이 **증가**는 테이블 재작성도
   인덱스 재빌드도 없다(카탈로그 갱신뿐) — hot ``orders`` 테이블이지만 락 점유가 짧다.
2. 이미 절단된 행만 재계산한다. ``erp_phone_digits`` 는 ``DERIVED_COLUMNS`` 이지만
   그 백필(``foms.services.orders.erp_flat_backfill``)은 부팅 자동이 아니라 OPS approval
   + lease 가 필요한 수동 인프라라, 여기서 풀지 않으면 기존 행은 그대로 남는다.

재계산 범위는 **증명 가능한 절단 행으로만** 좁힌다: 현재 값이 정확히 20자이고,
``phone`` 전체 숫자열이 20자를 넘으며, 그 앞 20자가 현재 값과 같은 행. 진짜 20자짜리는
대상에서 빠지고(값도 동일), 정본이 어긋난 행은 접두사 조건에서 걸러진다(파생 재동기는
이 마이그레이션의 일이 아니다).

소스로 ``phone`` 컬럼을 쓰는 것은 선행 마이그레이션 ``add_erp_phone_digits`` 와 같은
계약이며, 2026-09-01 사고 조사에서 ``phone`` 과 ``structured_data`` 가 서로 같음을 확인했다.

상수 동결: 이 파일은 ``models`` 를 import 하지 않는다(폭 64·20 은 파일 안에 고정).
"""
from typing import Sequence, Union

import logging
import re

from alembic import op
from sqlalchemy import text

revision: str = 'phonewide_00'
down_revision: Union[str, None] = 'merge_naverbf_share'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_log = logging.getLogger("alembic.runtime.migration")

_DIGIT_RE = re.compile(r"[^0-9]")
_OLD_MAX_DIGITS = 20
_NEW_MAX_DIGITS = 64

# 절단 행만 재계산: 현재 20자 + 전체 숫자열이 20자 초과 + 앞 20자가 현재 값과 동일.
_PG_REPAIR_SQL = """
UPDATE orders AS o
   SET erp_phone_digits = LEFT(d.full_digits, 64)
  FROM (
        SELECT id,
               NULLIF(regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g'), '') AS full_digits
          FROM orders
       ) AS d
 WHERE o.id = d.id
   AND o.erp_phone_digits IS NOT NULL
   AND length(o.erp_phone_digits) = 20
   AND d.full_digits IS NOT NULL
   AND length(d.full_digits) > 20
   AND LEFT(d.full_digits, 20) = o.erp_phone_digits
"""


def _is_postgresql(conn) -> bool:
    return getattr(getattr(conn, "dialect", None), "name", None) == "postgresql"


def _digits(raw) -> str:
    """전화 원문에서 숫자만 추출(정규화 함수와 동일 규칙, live import 없이 동결)."""
    return _DIGIT_RE.sub("", str(raw if raw is not None else "").strip())


def _repair_truncated_sqlite(conn) -> int:
    """SQLite/CI: ``regexp_replace`` 부재 — 파이썬으로 같은 술어를 적용한다."""
    rows = conn.execute(
        text(
            "SELECT id, phone, erp_phone_digits FROM orders "
            "WHERE erp_phone_digits IS NOT NULL AND length(erp_phone_digits) = 20"
        )
    ).fetchall()
    repaired = 0
    for row in rows:
        full = _digits(row.phone)
        if len(full) <= _OLD_MAX_DIGITS:
            continue
        if full[:_OLD_MAX_DIGITS] != row.erp_phone_digits:
            continue
        conn.execute(
            text("UPDATE orders SET erp_phone_digits = :digits WHERE id = :id"),
            {"digits": full[:_NEW_MAX_DIGITS], "id": row.id},
        )
        repaired += 1
    return repaired


def upgrade() -> None:
    """컬럼 폭을 64 로 넓히고 절단된 행을 재계산한다."""
    conn = op.get_bind()
    if _is_postgresql(conn):
        op.execute("ALTER TABLE orders ALTER COLUMN erp_phone_digits TYPE VARCHAR(64)")
        result = conn.execute(text(_PG_REPAIR_SQL))
        _log.info("[PHONEWIDE-01] erp_phone_digits 절단 복구 %s행", result.rowcount)
    else:
        # SQLite 는 VARCHAR 길이를 강제하지 않아 타입 변경이 무의미하다(ALTER TYPE 미지원).
        repaired = _repair_truncated_sqlite(conn)
        _log.info("[PHONEWIDE-01] erp_phone_digits 절단 복구 %s행 (sqlite)", repaired)


def downgrade() -> None:
    """값을 20자로 되자른 뒤 컬럼 폭을 20 으로 되돌린다(자른 뒷자리는 복구 불가)."""
    conn = op.get_bind()
    if _is_postgresql(conn):
        op.execute(
            "UPDATE orders SET erp_phone_digits = LEFT(erp_phone_digits, 20) "
            "WHERE erp_phone_digits IS NOT NULL AND length(erp_phone_digits) > 20"
        )
        op.execute("ALTER TABLE orders ALTER COLUMN erp_phone_digits TYPE VARCHAR(20)")
    else:
        conn.execute(
            text(
                "UPDATE orders SET erp_phone_digits = substr(erp_phone_digits, 1, 20) "
                "WHERE erp_phone_digits IS NOT NULL AND length(erp_phone_digits) > 20"
            )
        )
