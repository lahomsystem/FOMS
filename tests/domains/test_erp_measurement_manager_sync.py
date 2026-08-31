from werkzeug.security import generate_password_hash

import datetime

from db import db_session
from models import Order, User


def _login_erp_editor(client):
    user = User(
        username="measurement_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Measurement Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_erp_order(manager_name="Alice"):
    order = Order(
        received_date="2026-03-31",
        customer_name="ERP Order",
        phone="010-1111-2222",
        address="Seoul",
        product="ERP Order",
        status="MEASURE",
        manager_name=manager_name,
        is_erp_order=True,
        structured_data={
            "parties": {
                "customer": {
                    "name": "Customer",
                    "phone": "010-1111-2222",
                },
                "manager": {
                    "name": manager_name,
                },
            }
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def test_measurement_manager_update_syncs_erp_order_fields(client):
    _login_erp_editor(client)
    order_id = _create_erp_order(manager_name="Alice")

    response = client.post(
        f"/api/erp/measurement/update/{order_id}",
        json={"field": "manager", "value": "Mango"},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    order = db_session.query(Order).filter(Order.id == order_id).first()
    assert order is not None
    assert order.manager_name == "Mango"
    assert ((order.structured_data or {}).get("parties") or {}).get("manager", {}).get("name") == "Mango"


def test_measurement_manager_delete_clears_erp_order_fields(client):
    _login_erp_editor(client)
    order_id = _create_erp_order(manager_name="Alice")

    response = client.post(
        f"/api/erp/measurement/update/{order_id}",
        json={"field": "manager", "value": ""},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    order = db_session.query(Order).filter(Order.id == order_id).first()
    assert order is not None
    assert order.manager_name == ""
    assert ((order.structured_data or {}).get("parties") or {}).get("manager", {}).get("name") == ""


def test_measurement_summary_returns_panel_dates(client):
    """Regression: summary must not 500 when accessing g.current_user (mine filter path)."""
    _login_erp_editor(client)
    _create_erp_order(manager_name="Alice")

    response = client.get("/api/erp/measurement/summary")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    panel_dates = payload["panel_dates"]
    assert isinstance(panel_dates, list)
    assert len(panel_dates) == 15
    assert all(
        "date" in row and "count" in row and "count_regional" in row and "count_metro" in row and "cases" in row
        for row in panel_dates
    )

    mine_response = client.get("/api/erp/measurement/summary?mine=1")
    assert mine_response.status_code == 200
    mine_payload = mine_response.get_json()
    assert mine_payload["success"] is True
    assert isinstance(mine_payload["panel_dates"], list)


def test_measurement_summary_segmented_counts(client, monkeypatch):
    """summary API는 날짜별 count_regional/count_metro를 반환한다."""
    import foms.api.measurement.routes as measurement_routes

    monkeypatch.setattr(measurement_routes.measurement_api, "get_today_kst", lambda: datetime.date(2026, 7, 2))
    _login_erp_editor(client)
    target = "2026-07-06"
    regional = Order(
        received_date=target,
        customer_name="지방 summary",
        phone="010-7777-8888",
        address="Busan",
        product="장",
        status="MEASURE",
        is_erp_order=True,
        is_regional=True,
        structured_data={"schedule": {"measurement": {"date": target}}},
    )
    metro = Order(
        received_date=target,
        customer_name="수도권 summary",
        phone="010-9999-0000",
        address="Seoul",
        product="장",
        status="MEASURE",
        is_erp_order=True,
        is_regional=False,
        structured_data={"schedule": {"measurement": {"date": target}}},
    )
    db_session.add_all([regional, metro])
    db_session.commit()

    payload = client.get("/api/erp/measurement/summary").get_json()
    row = next(item for item in payload["panel_dates"] if item["date"] == target)
    assert row["count"] == 2
    assert row["count_regional"] == 1
    assert row["count_metro"] == 1


def test_measurement_manager_update_resolves_numeric_user_id_to_name(client):
    _login_erp_editor(client)
    manager_user = User(
        username="resolved_manager",
        password=generate_password_hash("manager"),
        role="STAFF",
        team="CS",
        name="복구 담당자",
        is_active=True,
    )
    db_session.add(manager_user)
    db_session.commit()
    order_id = _create_erp_order(manager_name="Alice")

    response = client.post(
        f"/api/erp/measurement/update/{order_id}",
        json={"field": "manager", "value": str(manager_user.id)},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    order = db_session.query(Order).filter(Order.id == order_id).first()
    assert order is not None
    assert order.manager_name == "복구 담당자"
    assert ((order.structured_data or {}).get("parties") or {}).get("manager", {}).get("name") == "복구 담당자"


# ==========================================================================
# 실측 미러링 패널 모집단 계약 (2026-09-01 성능 수정)
#
# 이 API 는 주문 편집 화면이 열려 있는 동안 30초마다 호출된다. 예전에는 id 내림차순
# 1,500행을 structured_data 째로 읽고 파이썬에서 날짜를 판정했다 — 운영 창 안 주문이
# 68건인데 매번 1,500행이었다. 지금은 SQL 이 날짜창으로 좁힌다.
# 좁히는 술어가 무엇을 빠뜨리면 패널에서 **조용히** 사라지므로 여기서 잡는다.
# ==========================================================================
def _seed_measurement_order(date_str: str, name: str, **kwargs) -> Order:
    """실측일이 date_str 인 ERP 주문 1건. schedule_dates 는 동기화 리스너가 만든다."""
    order = Order(
        received_date="2026-01-02",
        customer_name=name,
        phone="010-3333-4444",
        address="Seoul",
        product="장",
        status="MEASURE",
        is_erp_order=True,
        structured_data={"schedule": {"measurement": {"date": date_str}}},
        **kwargs,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _panel_names(client, date_str: str) -> set:
    payload = client.get("/api/erp/measurement/summary").get_json()
    row = next(item for item in payload["panel_dates"] if item["date"] == date_str)
    return {case["customer_name"] for case in row["cases"]}


def test_summary_panel_includes_old_order_ids_inside_the_window(client, monkeypatch):
    """**창 안이면 id 가 아무리 오래돼도 포함된다.**

    옛 구현은 `order_by(id.desc()).limit(1500)` 을 **먼저** 걸고 그 다음 파이썬에서
    날짜를 판정해서, 최신 1,500건 밖의 주문에 다가오는 실측일이 있으면 패널에서 조용히
    빠졌다(프로젝트가 아는 '캡 뒤 분류' 함정). 이 테스트가 그 회귀를 막는다.
    """
    import foms.api.measurement.routes as measurement_routes

    monkeypatch.setattr(
        measurement_routes.measurement_api, "get_today_kst", lambda: datetime.date(2026, 7, 2)
    )
    monkeypatch.setattr(measurement_routes, "MEASUREMENT_PANEL_SAFETY_CAP", 3)
    _login_erp_editor(client)

    target = "2026-07-05"
    old = _seed_measurement_order(target, "오래된 주문")
    # 창 밖(과거) 주문을 더 만들어 옛 캡 순서라면 old 가 밀려나게 한다.
    for index in range(5):
        _seed_measurement_order("2026-05-01", f"창 밖 {index}")

    assert "오래된 주문" in _panel_names(client, target), (
        f"id={old.id} 주문이 캡에 밀려 패널에서 빠졌다"
    )


def test_summary_panel_excludes_orders_outside_the_window(client, monkeypatch):
    """창(오늘~+14) 밖 실측일은 패널 모집단에 들어오지 않는다 — 음성 대조군."""
    import foms.api.measurement.routes as measurement_routes

    monkeypatch.setattr(
        measurement_routes.measurement_api, "get_today_kst", lambda: datetime.date(2026, 7, 2)
    )
    _login_erp_editor(client)
    _seed_measurement_order("2026-07-05", "창 안")
    _seed_measurement_order("2026-08-20", "창 밖")

    payload = client.get("/api/erp/measurement/summary").get_json()
    names = {
        case["customer_name"]
        for row in payload["panel_dates"]
        for case in row["cases"]
    }

    assert "창 안" in names
    assert "창 밖" not in names, "창 밖 주문이 패널에 실렸다"


def test_summary_panel_keeps_multi_date_orders_on_every_date(client, monkeypatch):
    """콤마 복수 실측일은 **모든 날짜**에 걸린다(싱크 컬럼은 첫 날짜만 담는다)."""
    import foms.api.measurement.routes as measurement_routes

    monkeypatch.setattr(
        measurement_routes.measurement_api, "get_today_kst", lambda: datetime.date(2026, 7, 2)
    )
    _login_erp_editor(client)
    _seed_measurement_order("2026-07-04, 2026-07-09", "복수 일정")

    assert "복수 일정" in _panel_names(client, "2026-07-04")
    assert "복수 일정" in _panel_names(client, "2026-07-09")


def test_summary_panel_safety_cap_warns_when_it_fires(client, monkeypatch, caplog):
    """폭주 가드가 발동하면 **경고 로그**를 남긴다 — 무음 절단 금지."""
    import foms.api.measurement.routes as measurement_routes

    monkeypatch.setattr(
        measurement_routes.measurement_api, "get_today_kst", lambda: datetime.date(2026, 7, 2)
    )
    monkeypatch.setattr(measurement_routes, "MEASUREMENT_PANEL_SAFETY_CAP", 2)
    _login_erp_editor(client)
    for index in range(3):
        _seed_measurement_order("2026-07-05", f"창 안 {index}")

    with caplog.at_level("WARNING"):
        assert client.get("/api/erp/measurement/summary").status_code == 200

    assert any("safety cap fired" in record.message for record in caplog.records), (
        "캡이 발동했는데 경고 로그가 없다"
    )
