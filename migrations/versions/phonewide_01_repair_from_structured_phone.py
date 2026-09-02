"""PHONEWIDE-02: erp_phone_digits 절단 복구를 structured_data 전화 원문까지 넓힌다

Revision ID: phonewide_01
Revises: phonewide_00
Create Date: 2026-09-02

``phonewide_00`` 은 ``phone`` 컬럼만 소스로 보고 절단 행을 재계산했다. 스테이징 반영 후
남은 행을 세어 보니 4건이 여전히 20자였고, 그 4건은 **정본이 ``structured_data`` 쪽에만
있는** 주문이었다.

```
#3246 phone='000-0000-0000'  sd='010-3501-5810 / 010-6411-0925'  col='01035015810010641109'
#3792 phone='010-5217-7125'  sd='010-6899-7125(실측) / 010-5217-7125(상담)'
```

라이브 파생(``foms.services.erp_sync_columns.sync_erp_flat_columns``)은
``parties.customer.phone`` 을 먼저 보고 없을 때만 ``phone`` 컬럼으로 내려간다. 복구도 같은
우선순위를 써야 한다 — ``phone`` 이 자리표시자(``000-0000-0000``)이거나 두 번호 중 하나만
담고 있으면 ``phonewide_00`` 의 술어가 그 행을 통째로 놓친다.

범위는 그대로 **증명 가능한 절단 행**으로만 좁힌다: 현재 값이 정확히 20자이고, 파생 소스의
전체 숫자열이 20자를 넘으며, 그 앞 20자가 현재 값과 같은 행. ``phonewide_00`` 이 이미 고친
행은 20자가 아니라 대상에서 빠지므로 두 마이그레이션을 겹쳐 돌려도 안전하다(멱등).

상수 동결: ``models`` 를 import 하지 않는다.
"""
from typing import Sequence, Union

import logging
import re

from alembic import op
from sqlalchemy import text

revision: str = 'phonewide_01'
down_revision: Union[str, None] = 'phonewide_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_log = logging.getLogger("alembic.runtime.migration")

_DIGIT_RE = re.compile(r"[^0-9]")
_OLD_MAX_DIGITS = 20
_NEW_MAX_DIGITS = 64

# 파생 소스 우선순위: structured_data.parties.customer.phone -> orders.phone
# (sync_erp_flat_columns 와 같은 순서). 두 값 모두에서 숫자만 뽑아 앞선 것을 쓴다.
_SOURCE_DIGITS_SQL = """
COALESCE(
    NULLIF(regexp_replace(
        COALESCE(structured_data #>> '{parties,customer,phone}', ''), '[^0-9]', '', 'g'), ''),
    NULLIF(regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g'), '')
)
"""

_PG_REPAIR_SQL = f"""
UPDATE orders AS o
   SET erp_phone_digits = LEFT(d.full_digits, 64)
  FROM (
        SELECT id, {_SOURCE_DIGITS_SQL} AS full_digits
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
    """SQLite/CI: JSON 경로·regexp_replace 부재 — 파이썬으로 같은 술어를 적용한다."""
    import json

    rows = conn.execute(
        text(
            "SELECT id, phone, structured_data, erp_phone_digits FROM orders "
            "WHERE erp_phone_digits IS NOT NULL AND length(erp_phone_digits) = 20"
        )
    ).fetchall()
    repaired = 0
    for row in rows:
        sd = row.structured_data
        if isinstance(sd, str):
            try:
                sd = json.loads(sd)
            except ValueError:
                sd = None
        sd_phone = None
        if isinstance(sd, dict):
            parties = sd.get("parties")
            customer = parties.get("customer") if isinstance(parties, dict) else None
            if isinstance(customer, dict):
                sd_phone = customer.get("phone")
        full = _digits(sd_phone) or _digits(row.phone)
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
    """structured_data 전화 원문까지 소스로 삼아 남은 절단 행을 재계산한다."""
    conn = op.get_bind()
    if _is_postgresql(conn):
        result = conn.execute(text(_PG_REPAIR_SQL))
        _log.info("[PHONEWIDE-02] structured_data 소스 절단 복구 %s행", result.rowcount)
    else:
        repaired = _repair_truncated_sqlite(conn)
        _log.info("[PHONEWIDE-02] structured_data 소스 절단 복구 %s행 (sqlite)", repaired)


def downgrade() -> None:
    """데이터 복구 전용 — 되돌릴 것이 없다(값을 다시 자르는 것은 손실이라 하지 않는다).

    컬럼 폭 되돌리기는 ``phonewide_00`` 의 downgrade 가 담당한다.
    """
    pass
