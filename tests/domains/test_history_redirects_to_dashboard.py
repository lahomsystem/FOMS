"""과거 이력 검색: ERP 대시보드에 결과가 있으면 대시보드 결과로 보낸다."""

from db import db_session
from models import Order


def test_history_search_redirects_to_dashboard_when_dashboard_has_hits(auth_client):
    db_session.add(Order(customer_name="이력대시보드이동", phone="010-0000-0000",
                         address="서울", product="장", received_date="2026-09-30",
                         status="RECEIVED", is_erp_order=True,
                         structured_data={"parties": {"customer": {"name": "이력대시보드이동"}}}))
    db_session.commit()
    resp = auth_client.get("/erp/history/?q=이력대시보드이동")
    assert resp.status_code == 302
    assert "/erp/dashboard" in resp.headers["Location"]
    assert "from_history=1" in resp.headers["Location"]


def test_history_search_stays_when_dashboard_empty(auth_client):
    resp = auth_client.get("/erp/history/?q=없는고객검색어XYZ")
    assert resp.status_code == 200


def test_history_from_dashboard_does_not_bounce_back(auth_client):
    resp = auth_client.get("/erp/history/?q=없는고객검색어XYZ&from_dashboard=1")
    assert resp.status_code == 200
