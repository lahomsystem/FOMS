from db import db_session
from models import Order


def _add_erp_order(customer_name: str) -> Order:
    order = Order(
        received_date="2026-05-12",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울시 테스트구 검색로 1",
        product="슬라이딩",
        status="RECEIVED",
        is_erp_order=True,
        erp_stage_code="MEASURE",
        structured_data={
            "workflow": {"stage": "MEASURE"},
            "parties": {"customer": {"name": customer_name}},
            "site": {"address_full": "서울시 테스트구 검색로 1"},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_dashboard_search_zero_results_redirects_to_history(login):
    response = login.get("/erp/dashboard?q=missing")

    assert response.status_code == 302
    assert response.location.endswith("/erp/history/?q=missing&from_dashboard=1")


def test_dashboard_search_existing_result_stays_on_dashboard(login):
    _add_erp_order("existing customer")

    response = login.get("/erp/dashboard?q=existing")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "existing customer" in body


def test_dashboard_search_with_operations_filter_does_not_redirect(login):
    response = login.get("/erp/dashboard?q=missing&mine=1")

    assert response.status_code == 200


def test_dashboard_fragment_redirect_returns_history_fragment_and_canonical_url(login):
    response = login.get(
        "/erp/dashboard?q=missing&view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.headers["X-FOMS-ERP-FRAGMENT"] == "1"
    assert response.headers["X-FOMS-Canonical-URL"] == "/erp/history/?q=missing&from_dashboard=1"
    assert "ERP 대시보드에서 현재 운영 주문을 찾지 못해 과거 이력 검색으로 이동했습니다." in body


def test_history_banner_renders_only_when_from_dashboard(login):
    redirected = login.get("/erp/history/?q=missing&from_dashboard=1")
    normal = login.get("/erp/history/?q=missing")

    assert "현재 운영 주문을 찾지 못해" in redirected.get_data(as_text=True)
    assert "현재 운영 주문을 찾지 못해" not in normal.get_data(as_text=True)
