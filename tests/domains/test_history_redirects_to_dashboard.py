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


def test_unified_search_landing_stays_on_history(auth_client):
    db_session.add(Order(customer_name="통합검색착지", phone="010-0000-0001",
                         address="서울", product="장", received_date="2026-09-30",
                         status="RECEIVED", is_erp_order=True,
                         structured_data={"parties": {"customer": {"name": "통합검색착지"}}}))
    db_session.commit()
    resp = auth_client.get("/erp/history/?q=통합검색착지&from_search=1")
    assert resp.status_code == 200


def test_dashboard_search_links_older_history_orders(auth_client):
    """대시보드 범위 밖(완료 60일+) 주문이 있으면 '과거 이력에 N건 더' 링크를 보인다."""
    import datetime

    old = datetime.datetime.now() - datetime.timedelta(days=400)
    db_session.add(Order(customer_name="더보기고객", phone="010-0000-0002",
                         address="서울", product="장", received_date="2026-09-30",
                         status="RECEIVED", is_erp_order=True,
                         structured_data={"parties": {"customer": {"name": "더보기고객"}}}))
    db_session.add(Order(customer_name="더보기고객", phone="010-0000-0003",
                         address="서울", product="장", received_date="2025-08-18",
                         status="COMPLETED", is_erp_order=True, erp_stage_code="COMPLETED",
                         erp_stage_updated_at=old, created_at=old,
                         structured_data={"parties": {"customer": {"name": "더보기고객"}}}))
    db_session.commit()
    body = auth_client.get("/erp/dashboard?q=더보기고객&from_history=1").get_data(as_text=True)
    assert "data-erp-history-more" in body
    assert "과거 이력에 1건 더" in body
    assert "from_dashboard=1" in body


def test_dashboard_search_no_link_when_all_on_dashboard(auth_client):
    db_session.add(Order(customer_name="전부대시보드", phone="010-0000-0004",
                         address="서울", product="장", received_date="2026-09-30",
                         status="RECEIVED", is_erp_order=True,
                         structured_data={"parties": {"customer": {"name": "전부대시보드"}}}))
    db_session.commit()
    body = auth_client.get("/erp/dashboard?q=전부대시보드").get_data(as_text=True)
    assert "data-erp-history-more" not in body
