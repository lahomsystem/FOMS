from types import SimpleNamespace

from db import db_session
from models import Order, OrderScheduleDate
from foms.services.map_snapshot import build_measurement_snapshot
from foms.services.measurement_manager_colors import MEASUREMENT_MANAGER_PALETTE


def _make_order(order_id, lat, lng, address, customer_name, manager_name="이시영"):
    return SimpleNamespace(
        id=order_id,
        customer_name="ERP Order",
        phone="000-0000-0000",
        address="-",
        product="ERP Order",
        notes="",
        status="MEASURE",
        received_date="2026-03-31",
        measurement_date="2026-03-31",
        measurement_time="오전",
        scheduled_date="2026-04-01",
        completion_date=None,
        manager_name=manager_name,
        lat=lat,
        lng=lng,
        geocode_status=None,
        is_erp_order=True,
        is_regional=False,
        is_self_measurement=False,
        structured_data={
            "parties": {
                "customer": {
                    "name": customer_name,
                    "phone": "010-2562-9522",
                },
                "manager": {
                    "name": manager_name,
                },
            },
            "site": {
                "address_full": address,
            },
            "items": [
                {
                    "product_name": "주방 외5조",
                }
            ],
            "schedule": {
                "measurement": {
                    "date": "2026-03-31",
                    "time": "오전",
                }
            },
        },
    )


def test_build_measurement_snapshot_marks_duplicate_locations_and_addresses():
    orders = [
        _make_order(101, 37.5000001, 127.0000001, "서울시 강남구 테헤란로 1", "윤인선", manager_name="이성민(서서울)"),
        _make_order(102, 37.5000001, 127.0000001, "서울시 강남구 테헤란로 1", "김나래", manager_name="최진호"),
        _make_order(103, 37.5005000, 127.0005000, "서울시 강남구 테헤란로 1", "박성준", manager_name="안종훈"),
    ]

    snapshot = build_measurement_snapshot(
        orders,
        measurement_manager_options=[
            {"name": "이성민(서서울)", "sort_order": 1},
            {"name": "최진호", "sort_order": 2},
            {"name": "안종훈", "sort_order": 3},
        ],
    )
    markers = {item["id"]: item for item in snapshot["markers"]}
    rows = {item["id"]: item for item in snapshot["orders"]}

    assert markers[101]["is_duplicate_location"] is True
    assert markers[102]["is_duplicate_location"] is True
    assert markers[101]["duplicate_location_group_size"] == 2
    assert markers[102]["duplicate_location_group_size"] == 2
    assert markers[103]["is_duplicate_location"] is False
    assert markers[103]["duplicate_location_group_size"] == 1

    assert markers[101]["is_duplicate_address"] is True
    assert markers[102]["is_duplicate_address"] is True
    assert markers[103]["is_duplicate_address"] is True
    assert markers[101]["duplicate_address_group_size"] == 3
    assert markers[102]["duplicate_address_group_size"] == 3
    assert markers[103]["duplicate_address_group_size"] == 3

    assert markers[101]["marker_render_hint"] == "pastel_pink"
    assert markers[102]["marker_render_hint"] == "pastel_pink"
    assert markers[103]["marker_render_hint"] == "pastel_pink"

    assert rows[101]["marker_render_hint"] == "pastel_pink"
    assert rows[102]["marker_render_hint"] == "pastel_pink"
    assert rows[103]["marker_render_hint"] == "pastel_pink"

    assert markers[101]["latitude"] == markers[102]["latitude"]
    assert markers[101]["longitude"] == markers[102]["longitude"]
    assert markers[101]["customer_name"] == "윤인선"
    assert markers[102]["customer_name"] == "김나래"
    assert markers[103]["customer_name"] == "박성준"
    assert markers[101]["manager_name"] == "이성민(서서울)"
    assert markers[101]["manager_bg_color"] == MEASUREMENT_MANAGER_PALETTE[0]
    assert markers[102]["manager_bg_color"] == MEASUREMENT_MANAGER_PALETTE[1]
    assert rows[103]["manager_bg_color"] == MEASUREMENT_MANAGER_PALETTE[2]
    assert rows[103]["manager_text_color"] == "#000000"


def test_build_measurement_snapshot_keeps_non_duplicate_hint_stable():
    orders = [
        _make_order(201, 37.6, 127.1, "서울시 송파구 올림픽로 1", "최수진", manager_name=""),
    ]

    snapshot = build_measurement_snapshot(orders, measurement_manager_options=[])
    marker = snapshot["markers"][0]
    row = snapshot["orders"][0]

    assert marker["is_duplicate_location"] is False
    assert marker["is_duplicate_address"] is False
    assert marker["marker_render_hint"] == "status"
    assert row["marker_render_hint"] == "status"
    assert marker["manager_bg_color"] == "#CCCCCC"
    assert marker["manager_bg_source"] == "fallback"


def test_build_measurement_map_query_supports_sqlite_normalized_schedule_dates(app):
    from foms.services.map_snapshot import build_measurement_map_query

    order = Order(
        received_date="2026-03-31",
        customer_name="SQLite 지도 QA",
        phone="010-0000-0000",
        address="서울시 강남구 테헤란로 99",
        product="붙박이장",
        status="MEASURE",
        manager_name="이시영",
        measurement_date="2026-03-31",
        is_erp_order=True,
        structured_data={
            "parties": {
                "customer": {"name": "SQLite 지도 QA", "phone": "010-0000-0000"},
                "manager": {"name": "이시영"},
            },
            "site": {"address_full": "서울시 강남구 테헤란로 99"},
            "schedule": {"measurement": {"date": "2026-03-31", "time": "오전"}},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="measurement",
            date="2026 03 31",
            source="sqlite_test",
        )
    )
    db_session.commit()

    rows = build_measurement_map_query(
        db_session,
        "2026-03-31",
        "",
        "",
        "measurement",
        limit=10,
    ).all()

    assert [item.id for item in rows] == [order.id]


def test_measurement_map_api_supports_sqlite_normalized_schedule_dates(client, login):
    order = Order(
        received_date="2026-03-31",
        customer_name="SQLite 지도 API",
        phone="010-9999-0000",
        address="서울시 강남구 테헤란로 100",
        product="붙박이장",
        status="MEASURE",
        manager_name="이시영",
        measurement_date="2026-03-31",
        lat=37.501,
        lng=127.039,
        geocode_status="success",
        is_erp_order=True,
        structured_data={
            "parties": {
                "customer": {"name": "SQLite 지도 API", "phone": "010-9999-0000"},
                "manager": {"name": "이시영"},
            },
            "site": {"address_full": "서울시 강남구 테헤란로 100"},
            "schedule": {"measurement": {"date": "2026-03-31", "time": "오후"}},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="measurement",
            date="2026 03 31",
            source="sqlite_api_test",
        )
    )
    db_session.commit()

    response = login.get("/api/map_data?dashboard=measurement&date=2026-03-31")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert [item["id"] for item in payload["orders"]] == [order.id]
    assert [item["id"] for item in payload["markers"]] == [order.id]
