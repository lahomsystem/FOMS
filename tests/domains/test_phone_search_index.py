"""Tests for phone digit normalization and indexed search (P1-02)."""

from types import SimpleNamespace

from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.phone_search import (
    extract_phone_digit_query,
    is_phone_digit_query,
    normalize_phone_digits,
)


def test_normalize_phone_digits_strips_formatting() -> None:
    assert normalize_phone_digits("010-2690-2242") == "01026902242"
    assert normalize_phone_digits("  ") is None


def test_normalize_phone_digits_truncates_to_column_limit() -> None:
    long_raw = "0" * 80
    assert normalize_phone_digits(long_raw) == "0" * 64


def test_normalize_phone_digits_keeps_multi_phone_digits() -> None:
    """전화번호 2개를 한 칸에 적은 주문(숫자 22자)은 잘리지 않는다."""
    raw = "010-8935-0264(고객), 010-5875-1125(팀장)"
    digits = normalize_phone_digits(raw)
    assert digits == "0108935026401058751125"
    assert len(digits) == 22
    assert digits.endswith("1125")


def test_is_phone_digit_query_requires_digit_heavy_input() -> None:
    assert is_phone_digit_query("0102690") is True
    assert is_phone_digit_query("010-2690-2242") is True
    assert is_phone_digit_query("고명옥") is False
    assert extract_phone_digit_query("010 고명") is None


def test_sync_erp_flat_columns_sets_phone_digits() -> None:
    order = SimpleNamespace(
        is_erp_order=True,
        phone="010-1111-2222",
        manager_name="",
        erp_measurement_date=None,
        erp_construction_date=None,
        erp_stage_code=None,
        erp_urgent=False,
        erp_drawing_updated_at=None,
        erp_stage_updated_at=None,
        erp_owner_team_code=None,
        erp_phone_digits=None,
        payment_amount=0,
    )
    structured_data = {
        "parties": {"customer": {"phone": "010-2690-2242"}},
        "workflow": {"stage": "RECEIVED"},
    }

    sync_erp_flat_columns(order, structured_data)

    assert order.erp_phone_digits == "01026902242"


def test_unified_search_finds_customer_by_phone_digits(app) -> None:
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order, User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User(
            username="phone_search_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Phone Search User",
        )
        db_session.add(user)
        db_session.commit()

        order = Order(
            received_date="2026-05-30",
            customer_name="고명옥",
            phone="010-2690-2242",
            address="Seoul",
            product="거실장",
            status="RECEIVED",
            is_erp_order=True,
            erp_phone_digits="01026902242",
            structured_data={
                "parties": {"customer": {"name": "고명옥", "phone": "010-2690-2242"}}
            },
        )
        db_session.add(order)
        db_session.commit()

        by_suffix = search_unified(db_session, "26902242")
        assert by_suffix["customer"]
        assert by_suffix["customer"][0]["order_id"] == order.id

        by_formatted = search_unified(db_session, "010-2690")
        assert by_formatted["customer"]


def test_sync_erp_flat_columns_keeps_second_phone_digits() -> None:
    """다전화 주문의 파생 컬럼이 두 번째 번호 뒷자리까지 담는다."""
    order = SimpleNamespace(
        is_erp_order=True,
        phone="010-8935-0264(고객), 010-5875-1125(팀장)",
        manager_name="",
        erp_measurement_date=None,
        erp_construction_date=None,
        erp_stage_code=None,
        erp_urgent=False,
        erp_drawing_updated_at=None,
        erp_stage_updated_at=None,
        erp_owner_team_code=None,
        erp_phone_digits=None,
        payment_amount=0,
    )
    structured_data = {
        "parties": {"customer": {"phone": "010-8935-0264(고객), 010-5875-1125(팀장)"}},
        "workflow": {"stage": "RECEIVED"},
    }

    sync_erp_flat_columns(order, structured_data)

    assert order.erp_phone_digits == "0108935026401058751125"


def test_unified_search_finds_order_by_second_phone_number(app) -> None:
    """두 번째 번호(팀장·세입자) 뒷 4자리로도 통합 검색이 걸린다."""
    from db import db_session
    from foms.services.erp_sync_columns import sync_erp_flat_columns as _sync
    from foms.services.foms_unified_search import search_unified
    from models import Order, User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User(
            username="phone_multi_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Phone Multi User",
        )
        db_session.add(user)
        db_session.commit()

        raw_phone = "010-8935-0264(고객), 010-5875-1125(팀장)"
        structured_data = {
            "parties": {"customer": {"name": "다전화고객", "phone": raw_phone}},
            "workflow": {"stage": "RECEIVED"},
        }
        order = Order(
            received_date="2026-09-02",
            customer_name="다전화고객",
            phone=raw_phone,
            address="Seoul",
            product="거실장",
            status="RECEIVED",
            is_erp_order=True,
            structured_data=structured_data,
        )
        _sync(order, structured_data)
        db_session.add(order)
        db_session.commit()

        assert order.erp_phone_digits == "0108935026401058751125"

        by_second_suffix = search_unified(db_session, "1125")
        assert by_second_suffix["customer"]
        assert order.id in {row["order_id"] for row in by_second_suffix["customer"]}

        by_second_full = search_unified(db_session, "010-5875-1125")
        assert order.id in {row["order_id"] for row in by_second_full["customer"]}

        by_first = search_unified(db_session, "89350264")
        assert order.id in {row["order_id"] for row in by_first["customer"]}


def test_phonewide_01_sqlite_repair_uses_structured_data_first() -> None:
    """SQLite 분기도 structured_data 전화 원문을 먼저 보고 절단을 푼다."""
    import importlib.util
    import json
    from pathlib import Path

    from sqlalchemy import create_engine, text

    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "phonewide_01_repair_from_structured_phone.py"
    )
    spec = importlib.util.spec_from_file_location("phonewide_01_mig_unit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE orders (id INTEGER PRIMARY KEY, phone TEXT, "
                "structured_data TEXT, erp_phone_digits TEXT)"
            )
        )
        rows = [
            # sd 에만 정본이 있는 절단 행.
            (1, "000-0000-0000", "010-3501-5810 / 010-6411-0925", "01035015810010641109"),
            # phone 컬럼만 있는 절단 행(phonewide_00 이 이미 잡는 모양).
            (2, "010-8935-0264, 010-5875-1125", None, "01089350264010587511"),
            # 음성 대조군 — 20자지만 소스 전체가 20자를 넘지 않는다.
            (3, "010-2690-2242", "010-2690-2242", "01026902242"),
            # 음성 대조군 — 20자인데 소스의 앞 20자와 다르다(정본 불일치).
            (4, "010-1111-2222, 010-3333-4444", None, "99999999999999999999"),
        ]
        for order_id, phone, sd_phone, digits in rows:
            sd = (
                json.dumps({"parties": {"customer": {"phone": sd_phone}}})
                if sd_phone is not None
                else None
            )
            conn.execute(
                text(
                    "INSERT INTO orders (id, phone, structured_data, erp_phone_digits) "
                    "VALUES (:i, :p, :sd, :d)"
                ),
                {"i": order_id, "p": phone, "sd": sd, "d": digits},
            )

        repaired = module._repair_truncated_sqlite(conn)
        stored = dict(
            conn.execute(text("SELECT id, erp_phone_digits FROM orders")).fetchall()
        )

    assert repaired == 2
    assert stored[1] == "0103501581001064110925"
    assert stored[2] == "0108935026401058751125"
    assert stored[3] == "01026902242"
    assert stored[4] == "99999999999999999999"
