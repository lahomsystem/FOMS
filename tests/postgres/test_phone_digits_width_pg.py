"""PHONEWIDE-01: erp_phone_digits 폭 확대 + 절단 복구 계약 (PGTEST-00 lane).

SQLite 는 ``VARCHAR`` 길이를 강제하지 않아 절단이 로컬에서 재현되지 않는다. 실 PostgreSQL
에서만 확인되는 두 가지를 못박는다.

* 모델 스키마의 ``erp_phone_digits`` 폭이 64 라 22~23자 숫자열이 절단 없이 저장된다.
* 마이그레이션 ``phonewide_00`` 의 복구 SQL 이 **절단된 행만** 고치고, 진짜 20자 행과
  정본이 어긋난 행은 건드리지 않는다. downgrade 는 되자르고 폭을 20 으로 되돌린다.

``FOMS_TEST_DATABASE_URL``(또는 PG* env) 미설정이면 lane 자체가 skip 된다(conftest).
"""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import pytest
from sqlalchemy.exc import DataError
from sqlalchemy.orm import sessionmaker

from models import Order

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = _REPO_ROOT / "migrations" / "versions" / "phonewide_00_widen_erp_phone_digits.py"
_MIGRATION_01_PATH = (
    _REPO_ROOT / "migrations" / "versions" / "phonewide_01_repair_from_structured_phone.py"
)

_WIDE_DDL = "ALTER TABLE orders ALTER COLUMN erp_phone_digits TYPE VARCHAR(64)"
_NARROW_DDL = "ALTER TABLE orders ALTER COLUMN erp_phone_digits TYPE VARCHAR(20)"
_DOWNGRADE_TRIM = (
    "UPDATE orders SET erp_phone_digits = LEFT(erp_phone_digits, 20) "
    "WHERE erp_phone_digits IS NOT NULL AND length(erp_phone_digits) > 20"
)


def _load_module(name: str, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_migration():
    """Import the phonewide_00 migration module by file path."""
    return _load_module("phonewide_00_mig", _MIGRATION_PATH)


def _load_migration_01():
    """Import the phonewide_01 migration module by file path."""
    return _load_module("phonewide_01_mig", _MIGRATION_01_PATH)


def _column_width(conn) -> int:
    return conn.exec_driver_sql(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_name = 'orders' AND column_name = 'erp_phone_digits'"
    ).scalar()


def _insert_order(conn, *, phone: str, digits: str, sd_phone: str | None = None) -> int:
    """검사용 주문 1건을 직접 INSERT 하고 id 를 돌려준다."""
    structured = (
        json.dumps({"parties": {"customer": {"phone": sd_phone}}}, ensure_ascii=False)
        if sd_phone is not None
        else None
    )
    return conn.exec_driver_sql(
        "INSERT INTO orders (received_date, customer_name, phone, address, product, "
        "status, is_erp_order, structured_schema_version, structured_data, erp_phone_digits) "
        "VALUES ('2026-09-02', %(name)s, %(phone)s, '서울', '거실장', 'RECEIVED', true, 1, "
        "CAST(%(sd)s AS jsonb), %(d)s) "
        "RETURNING id",
        {
            "name": f"폭검사_{int(time.time() * 1000) % 1000000}",
            "phone": phone,
            "sd": structured,
            "d": digits,
        },
    ).scalar()


# --------------------------------------------------------------------------- #
# 모델 스키마 폭
# --------------------------------------------------------------------------- #


def test_model_declares_wide_phone_digits_column() -> None:
    """models 의 erp_phone_digits 폭이 정규화 상한과 같은 64 다."""
    from foms.services.phone_search import _MAX_PHONE_DIGITS

    assert Order.__table__.c.erp_phone_digits.type.length == 64
    assert _MAX_PHONE_DIGITS == 64


def test_migration_revises_current_head_and_is_reversible() -> None:
    """phonewide_00 은 단일 head 위에 얹히고 downgrade 가 비어 있지 않다."""
    import inspect

    module = _load_migration()
    assert module.revision == "phonewide_00"
    assert module.down_revision == "merge_naverbf_share"
    source = inspect.getsource(module.downgrade)
    assert "VARCHAR(20)" in source
    # 상수 동결: 과거/현재 마이그레이션은 models 를 live import 하지 않는다.
    file_text = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert "import models" not in file_text
    assert "from models" not in file_text


# --------------------------------------------------------------------------- #
# PostgreSQL lane
# --------------------------------------------------------------------------- #


def test_multi_phone_digits_survive_round_trip(pg_engine) -> None:
    """22자 숫자열이 절단 없이 저장/조회된다(폭 64 확인 포함)."""
    with pg_engine.connect() as conn:
        ac = conn.execution_options(isolation_level="AUTOCOMMIT")
        ac.exec_driver_sql(_WIDE_DDL)
        assert _column_width(ac) == 64

    digits = "0108935026401058751125"
    session = sessionmaker(bind=pg_engine)()
    try:
        order = Order(
            received_date="2026-09-02",
            customer_name="다전화고객",
            phone="010-8935-0264(고객), 010-5875-1125(팀장)",
            address="서울",
            product="거실장",
            status="RECEIVED",
            is_erp_order=True,
            erp_phone_digits=digits,
        )
        session.add(order)
        session.commit()
        order_id = order.id
        session.expunge_all()

        stored = session.get(Order, order_id).erp_phone_digits
        assert stored == digits
        assert len(stored) == 22
    finally:
        session.close()


def test_repair_sql_fixes_only_truncated_rows(pg_engine) -> None:
    """복구 SQL 은 절단 행만 고치고, 진짜 20자·정본 불일치 행은 그대로 둔다."""
    module = _load_migration()

    with pg_engine.connect() as conn:
        ac = conn.execution_options(isolation_level="AUTOCOMMIT")
        ac.exec_driver_sql(_WIDE_DDL)

        # 1) 절단 행: phone 숫자열 22자, 파생값은 앞 20자만.
        truncated_id = _insert_order(
            ac,
            phone="010-8935-0264(고객), 010-5875-1125(팀장)",
            digits="01089350264010587511",
        )
        # 2) 음성 대조군 A — 진짜 20자(phone 숫자열도 정확히 20자).
        exact_id = _insert_order(
            ac, phone="02-1234-5678, 02-1234-5678", digits="02123456780212345678"
        )
        # 3) 음성 대조군 B — 20자지만 phone 전체 숫자열의 접두사가 아니다(정본 불일치).
        mismatch_id = _insert_order(
            ac,
            phone="010-1111-2222, 010-3333-4444",
            digits="99999999999999999999",
        )
        # 4) 음성 대조군 C — 20자 미만(평범한 단일 번호).
        short_id = _insert_order(ac, phone="010-2690-2242", digits="01026902242")

        repaired = ac.exec_driver_sql(module._PG_REPAIR_SQL).rowcount

        def _digits_of(order_id: int) -> str:
            return ac.exec_driver_sql(
                "SELECT erp_phone_digits FROM orders WHERE id = %(i)s", {"i": order_id}
            ).scalar()

        assert repaired == 1
        assert _digits_of(truncated_id) == "0108935026401058751125"
        assert _digits_of(exact_id) == "02123456780212345678"
        assert _digits_of(mismatch_id) == "99999999999999999999"
        assert _digits_of(short_id) == "01026902242"

        # 재실행해도 더 고칠 것이 없다(멱등).
        assert ac.exec_driver_sql(module._PG_REPAIR_SQL).rowcount == 0

        for order_id in (truncated_id, exact_id, mismatch_id, short_id):
            ac.exec_driver_sql("DELETE FROM orders WHERE id = %(i)s", {"i": order_id})


def test_downgrade_narrows_column_after_trimming(pg_engine) -> None:
    """downgrade 는 값을 20자로 되자른 뒤에야 폭을 좁힌다(ALTER 실패 없음)."""
    with pg_engine.connect() as conn:
        ac = conn.execution_options(isolation_level="AUTOCOMMIT")
        ac.exec_driver_sql(_WIDE_DDL)
        wide_id = _insert_order(
            ac,
            phone="010-8935-0264(고객), 010-5875-1125(팀장)",
            digits="0108935026401058751125",
        )

        ac.exec_driver_sql(_DOWNGRADE_TRIM)
        ac.exec_driver_sql(_NARROW_DDL)

        assert _column_width(ac) == 20
        assert ac.exec_driver_sql(
            "SELECT erp_phone_digits FROM orders WHERE id = %(i)s", {"i": wide_id}
        ).scalar() == "01089350264010587511"

        # 좁은 폭에서는 22자 저장이 아예 거부된다 — SQLite 로는 못 보는 축(길이 미강제).
        with pytest.raises(DataError):
            _insert_order(
                ac,
                phone="010-8935-0264(고객), 010-5875-1125(팀장)",
                digits="0108935026401058751125",
            )

        # upgrade 로 되돌려 lane 을 모델 스키마와 같은 상태로 남긴다.
        ac.exec_driver_sql(_WIDE_DDL)
        assert _column_width(ac) == 64
        ac.exec_driver_sql("DELETE FROM orders WHERE id = %(i)s", {"i": wide_id})


def test_phonewide_01_repairs_rows_whose_source_is_structured_data(pg_engine) -> None:
    """phone 컬럼이 자리표시자여도 structured_data 전화 원문으로 절단을 푼다.

    스테이징 실측(2026-09-02): phonewide_00 적용 뒤 남은 20자 4건이 모두 이 모양이었다
    (phone='000-0000-0000' 또는 두 번호 중 하나만, 정본은 sd 쪽).
    """
    mig00 = _load_migration()
    mig01 = _load_migration_01()

    with pg_engine.connect() as conn:
        ac = conn.execution_options(isolation_level="AUTOCOMMIT")
        ac.exec_driver_sql(_WIDE_DDL)

        # sd 에만 정본이 있는 절단 행 — phone 은 자리표시자.
        sd_only_id = _insert_order(
            ac,
            phone="000-0000-0000",
            sd_phone="010-3501-5810 / 010-6411-0925",
            digits="01035015810010641109",
        )
        # phone 이 두 번호 중 하나만 담은 절단 행.
        partial_phone_id = _insert_order(
            ac,
            phone="010-5217-7125",
            sd_phone="010-6899-7125(실측) / 010-5217-7125(상담)",
            digits="01068997125010521771",
        )
        # 음성 대조군 — sd 도 phone 도 20자를 넘지 않는다.
        control_id = _insert_order(
            ac, phone="010-2690-2242", sd_phone="010-2690-2242", digits="01026902242"
        )

        def _digits_of(order_id: int) -> str:
            return ac.exec_driver_sql(
                "SELECT erp_phone_digits FROM orders WHERE id = %(i)s", {"i": order_id}
            ).scalar()

        # phonewide_00 은 phone 컬럼만 보므로 이 행들을 못 고친다(간극 재현).
        ac.exec_driver_sql(mig00._PG_REPAIR_SQL)
        assert _digits_of(sd_only_id) == "01035015810010641109"
        assert _digits_of(partial_phone_id) == "01068997125010521771"

        ac.exec_driver_sql(mig01._PG_REPAIR_SQL)
        assert _digits_of(sd_only_id) == "0103501581001064110925"
        assert _digits_of(partial_phone_id) == "0106899712501052177125"
        assert _digits_of(control_id) == "01026902242"

        # 멱등: 다시 돌려도 값이 변하지 않는다.
        ac.exec_driver_sql(mig01._PG_REPAIR_SQL)
        assert _digits_of(sd_only_id) == "0103501581001064110925"

        for order_id in (sd_only_id, partial_phone_id, control_id):
            ac.exec_driver_sql("DELETE FROM orders WHERE id = %(i)s", {"i": order_id})


def test_phonewide_01_revises_phonewide_00_and_freezes_constants() -> None:
    """후속 마이그레이션은 phonewide_00 위에 얹히고 models 를 import 하지 않는다."""
    module = _load_migration_01()
    assert module.revision == "phonewide_01"
    assert module.down_revision == "phonewide_00"
    file_text = _MIGRATION_01_PATH.read_text(encoding="utf-8")
    assert "import models" not in file_text
    assert "from models" not in file_text
