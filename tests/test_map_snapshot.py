from types import SimpleNamespace

from services.map_snapshot import build_measurement_snapshot


def _make_order(order_id, lat, lng, address, customer_name, manager_name="이시영"):
    return SimpleNamespace(
        id=order_id,
        customer_name="ERP Beta",
        phone="000-0000-0000",
        address="-",
        product="ERP Beta",
        notes="",
        status="MEASURE",
        received_date="2026-03-31",
        measurement_date="2026-03-31",
        measurement_time="오전",
        scheduled_date="2026-04-01",
        completion_date=None,
        manager_name="ERP Beta",
        lat=lat,
        lng=lng,
        geocode_status=None,
        is_erp_beta=True,
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
        _make_order(101, 37.5000001, 127.0000001, "서울시 강남구 테헤란로 1", "윤인선"),
        _make_order(102, 37.5000001, 127.0000001, "서울시 강남구 테헤란로 1", "김나래"),
        _make_order(103, 37.5005000, 127.0005000, "서울시 강남구 테헤란로 1", "박성준"),
    ]

    snapshot = build_measurement_snapshot(orders)
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


def test_build_measurement_snapshot_keeps_non_duplicate_hint_stable():
    orders = [
        _make_order(201, 37.6, 127.1, "서울시 송파구 올림픽로 1", "최수진"),
    ]

    snapshot = build_measurement_snapshot(orders)
    marker = snapshot["markers"][0]
    row = snapshot["orders"][0]

    assert marker["is_duplicate_location"] is False
    assert marker["is_duplicate_address"] is False
    assert marker["marker_render_hint"] == "status"
    assert row["marker_render_hint"] == "status"
