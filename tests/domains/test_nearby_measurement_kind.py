"""`/api/orders/nearby?kind=measurement` 계약 (설계서 §4.1).

기본값(`kind` 미지정)은 시공 경로 그대로이며, 실측 경로는 자가실측·지방·삭제·
과거 실측일을 후보에서 뺀다. 카카오 호출 없이 돌도록 좌표 해석과 계산부를
monkeypatch 한다(`test_orders_boundary_contract.py` 방식).
"""

from werkzeug.security import generate_password_hash

import foms.api.orders.nearby as nearby_module
from db import db_session
from models import Order, OrderScheduleDate, User

REF_DATE = "2026-05-10"
BASE_KEYS = {
    "success",
    "by_distance",
    "by_date",
    "by_combined",
    "search_radius_km",
    "ref_lat",
    "ref_lng",
    "parcel_suggested",
}


def _login_as_admin(client, username: str) -> User:
    """Create an admin user and attach it to the test client session."""
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Nearby Measurement Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_order_id(measurement_date=None, **overrides) -> int:
    """Create one order and return its id (rows are synced by the date-sync listener).

    요청 처리 후 세션이 정리되면 ORM 객체가 detach 되므로 id 만 들고 다닌다.
    """
    payload = {
        "received_date": "2026-04-11",
        "customer_name": "Nearby Measure Tester",
        "phone": "010-3333-4444",
        "address": "서울 강남구 테헤란로 1",
        "product": "Wardrobe",
        "status": "RECEIVED",
        "is_regional": False,
        "is_self_measurement": False,
        "measurement_date": measurement_date,
        "structured_data": {"parties": {"manager": {"name": "김영업"}}},
    }
    payload.update(overrides)
    order = Order(**payload)
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _schedule_rows(order_id: int):
    """Return the measurement schedule rows synced for one order."""
    return (
        db_session.query(OrderScheduleDate)
        .filter(
            OrderScheduleDate.order_id == order_id,
            OrderScheduleDate.kind == "measurement",
        )
        .all()
    )


def _patch_measurement_compute(monkeypatch) -> dict:
    """Replace coordinate resolution + measurement compute; capture loader output."""
    captured: dict = {}

    monkeypatch.setattr(
        nearby_module,
        "resolve_nearby_start_coordinates",
        lambda *args, **kwargs: (37.5, 127.0),
    )

    def fake_compute(**kwargs):
        captured["valid_items"] = kwargs["valid_items"]
        captured["route_timeout_sec"] = kwargs.get("route_timeout_sec")
        items = [dict(item) for item in kwargs["valid_items"]]
        return {
            "success": True,
            "by_distance": items,
            "by_date": list(items),
            "by_combined": list(items),
            "search_radius_km": 30.0,
            "ref_lat": kwargs["start_lat"],
            "ref_lng": kwargs["start_lng"],
        }

    monkeypatch.setattr(nearby_module, "compute_nearby_success_payload", fake_compute)
    return captured


def _get_measurement(client, **params):
    """Call the nearby endpoint with kind=measurement."""
    query = {"address": "서울 강남구 역삼동", "date": REF_DATE, "kind": "measurement"}
    query.update(params)
    return client.get("/api/orders/nearby", query_string=query)


def test_measurement_kind_response_keys_and_item_shape(client, monkeypatch) -> None:
    """실측 응답은 기존 키 + parcel_suggested 이고 item 은 type/manager/time 을 갖는다."""
    _login_as_admin(client, "nearby-measure-keys")
    order_id = _create_order_id(measurement_date="2026-05-12", measurement_time="10:00")
    assert _schedule_rows(order_id), "date-sync 리스너가 실측 일정 행을 만들어야 한다"

    captured = _patch_measurement_compute(monkeypatch)
    response = _get_measurement(client)

    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload.keys()) == BASE_KEYS
    assert payload["parcel_suggested"] is False
    assert captured["route_timeout_sec"] == 3.0

    items = payload["by_distance"]
    assert [item["id"] for item in items] == [order_id]
    item = items[0]
    assert item["type"] == "실측"
    assert item["date"] == "2026-05-12"
    assert item["manager"] == "김영업"
    assert item["time"] == "10:00"
    assert set(item) >= {
        "id",
        "customer_name",
        "address",
        "date",
        "type",
        "manager",
        "time",
    }


def test_measurement_kind_excludes_self_measurement_regional_and_deleted(
    client, monkeypatch
) -> None:
    """자가실측(플래그·상태)·지방·삭제 주문은 실측 후보에서 빠진다."""
    _login_as_admin(client, "nearby-measure-exclusions")
    keep_id = _create_order_id(measurement_date="2026-05-12", customer_name="Keep Me")
    flagged_id = _create_order_id(measurement_date="2026-05-12", is_self_measurement=True)
    by_status_id = _create_order_id(measurement_date="2026-05-12", status="SELF_MEASUREMENT")
    by_status2_id = _create_order_id(measurement_date="2026-05-12", status="SELF_MEASURED")
    regional_id = _create_order_id(measurement_date="2026-05-12", is_regional=True)
    deleted_status_id = _create_order_id(measurement_date="2026-05-12", status="DELETED")
    soft_deleted_id = _create_order_id(
        measurement_date="2026-05-12", deleted_at="2026-05-01 10:00:00"
    )

    _patch_measurement_compute(monkeypatch)
    payload = _get_measurement(client).get_json()

    ids = {item["id"] for item in payload["by_distance"]}
    assert ids == {keep_id}
    for excluded_id in (
        flagged_id,
        by_status_id,
        by_status2_id,
        regional_id,
        deleted_status_id,
        soft_deleted_id,
    ):
        assert excluded_id not in ids


def test_measurement_kind_excludes_past_measurement_dates(client, monkeypatch) -> None:
    """기준일보다 이른 실측일만 가진 주문은 후보가 아니다."""
    _login_as_admin(client, "nearby-measure-past")
    past_id = _create_order_id(measurement_date="2026-04-30")
    future_id = _create_order_id(measurement_date="2026-05-10")

    _patch_measurement_compute(monkeypatch)
    payload = _get_measurement(client).get_json()

    ids = {item["id"] for item in payload["by_distance"]}
    assert ids == {future_id}
    assert past_id not in ids


def test_measurement_kind_excludes_reference_order(client, monkeypatch) -> None:
    """exclude_id 로 넘어온 기준 주문 자신은 후보에서 빠진다."""
    _login_as_admin(client, "nearby-measure-exclude-id")
    self_order_id = _create_order_id(measurement_date="2026-05-12")
    other_id = _create_order_id(measurement_date="2026-05-13")

    _patch_measurement_compute(monkeypatch)
    payload = _get_measurement(client, exclude_id=self_order_id).get_json()

    assert {item["id"] for item in payload["by_distance"]} == {other_id}


def test_measurement_kind_sets_parcel_suggested_when_no_candidates(
    client, monkeypatch
) -> None:
    """후보 3리스트가 모두 비면 택배 전환을 제안한다."""
    _login_as_admin(client, "nearby-measure-parcel")
    _create_order_id(measurement_date="2026-04-01")  # 과거 실측일 → 후보 아님

    _patch_measurement_compute(monkeypatch)
    payload = _get_measurement(client).get_json()

    assert payload["by_distance"] == []
    assert payload["by_date"] == []
    assert payload["by_combined"] == []
    assert payload["parcel_suggested"] is True


def test_default_kind_still_uses_construction_path(client, monkeypatch) -> None:
    """kind 미지정이면 기존 시공 로더·계산부를 그대로 쓴다(계약 불변)."""
    _login_as_admin(client, "nearby-measure-default")
    calls: dict = {}

    monkeypatch.setattr(
        nearby_module,
        "resolve_nearby_start_coordinates",
        lambda *args, **kwargs: (37.5, 127.0),
    )

    def fail_measurement_loader(*args, **kwargs):
        raise AssertionError("기본 경로에서 실측 로더를 부르면 안 된다")

    monkeypatch.setattr(
        nearby_module, "load_measurement_nearby_valid_items", fail_measurement_loader
    )

    def construction_loader(*args, **kwargs):
        calls["loader"] = "construction"
        return []

    monkeypatch.setattr(
        nearby_module, "load_construction_nearby_valid_items", construction_loader
    )

    def fake_construction_compute(**kwargs):
        calls["route_timeout_sec"] = kwargs.get("route_timeout_sec")
        calls["compute"] = "construction"
        return {
            "success": True,
            "by_distance": [],
            "by_date": [],
            "by_combined": [],
            "search_radius_km": 30.0,
            "ref_lat": 37.5,
            "ref_lng": 127.0,
        }

    monkeypatch.setattr(
        nearby_module,
        "compute_construction_nearby_success_payload",
        fake_construction_compute,
    )

    response = client.get(
        "/api/orders/nearby",
        query_string={"address": "서울 강남구 역삼동", "date": REF_DATE},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert calls["loader"] == "construction"
    assert calls["compute"] == "construction"
    assert calls["route_timeout_sec"] is None
    assert payload["parcel_suggested"] is False


def test_explicit_construction_kind_matches_default(client, monkeypatch) -> None:
    """kind=construction 은 기본값과 같은 경로다."""
    _login_as_admin(client, "nearby-measure-explicit-construction")

    monkeypatch.setattr(
        nearby_module,
        "resolve_nearby_start_coordinates",
        lambda *args, **kwargs: (37.5, 127.0),
    )
    monkeypatch.setattr(
        nearby_module, "load_construction_nearby_valid_items", lambda *a, **k: []
    )
    monkeypatch.setattr(
        nearby_module,
        "compute_construction_nearby_success_payload",
        lambda **kwargs: {
            "success": True,
            "by_distance": [],
            "by_date": [],
            "by_combined": [],
            "search_radius_km": 30.0,
            "ref_lat": 37.5,
            "ref_lng": 127.0,
        },
    )

    response = client.get(
        "/api/orders/nearby",
        query_string={
            "address": "서울 강남구 역삼동",
            "date": REF_DATE,
            "kind": "construction",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["parcel_suggested"] is False


def test_unknown_kind_returns_400(client) -> None:
    """지원하지 않는 kind 는 400 + 기존 오류 페이로드 형태."""
    _login_as_admin(client, "nearby-measure-bad-kind")

    response = client.get(
        "/api/orders/nearby",
        query_string={"address": "서울 강남구 역삼동", "kind": "shipping"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "message" in payload
    assert "error" in payload
