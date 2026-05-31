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
