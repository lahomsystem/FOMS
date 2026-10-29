"""Company isolation across ERP tabs, financial populations and query budgets."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import event

from db import db_session
from models import PartnerOrg
from foms.services.datetime_kst import get_today_kst
from tests.domains.test_settlement_aggregation import _money, _seed_order


@pytest.fixture
def scoped_orders(auth_client):
    """Seed matching stages for two companies and an internal control population."""
    orgs = [PartnerOrg(name=f"SCOPE-COMPANY-{i}") for i in range(2)]
    db_session.add_all(orgs)
    db_session.flush()
    today = get_today_kst().isoformat()
    result = []
    for company in [*orgs, None]:
        group = []
        name = company.name if company else "INTERNAL"
        for stage in ("MEASURE", "DRAWING", "PRODUCTION", "CONSTRUCTION", "AS_RECEIVED", "COMPLETED"):
            row = _seed_order(completion=today, status=stage, stage=stage,
                              customer_name=f"{name}-{stage}", sd=_money(1000, 100), commit=False)
            row.partner_org_id = company.id if company else None
            row.created_at = dt.datetime.now()
            row.structured_data = {**row.structured_data, "workflow": {"stage": stage},
                                   "parties": {"customer": {"name": row.customer_name, "phone": row.phone}},
                                   "schedule": {"measurement": {"date": today}, "construction": {"date": today}},
                                   "items": [{"name": "가상붙박이장", "product_name": "가상붙박이장", "price": 1000}]}
            group.append(row)
        result.append(group)
    db_session.flush()
    db_session.commit()
    return [org.id for org in orgs], [[row.id for row in group] for group in result]


@pytest.mark.parametrize("path", [
    "/erp/dashboard", "/erp/measurement", "/erp/drawing-workbench", "/erp/production/dashboard",
    "/erp/shipment", "/erp/as", "/erp/construction/dashboard",
    "/erp/history/?from_dashboard=1",
])
def test_each_tab_filters_rows_and_rejects_foreign_focus(auth_client, scoped_orders, monkeypatch, path):
    from importlib import import_module

    modules = {"/erp/dashboard": "orders.dashboard", "/erp/measurement": "measurement.dashboard",
               "/erp/drawing-workbench": "drawing.workbench", "/erp/production/dashboard": "production.dashboard",
               "/erp/shipment": "shipment.dashboard", "/erp/construction/dashboard": "construction.dashboard",
               "/erp/history/?from_dashboard=1": "orders.history"}
    cached = {}

    def cache(key, ttl, compute, **kwargs):
        if key not in cached:
            cached[key] = compute()
        return cached[key]

    if path in modules:
        monkeypatch.setattr(import_module(f"foms.web.{modules[path]}"), "get_or_compute_dashboard_slice", cache)
    orgs, ids = scoped_orders
    sep = "&" if "?" in path else "?"
    response = auth_client.get(f"{path}{sep}partner_org={orgs[0]}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "SCOPE-COMPANY-0-" in body, path
    assert "SCOPE-COMPANY-1-" not in body, path
    assert "INTERNAL-" not in body, path
    body = auth_client.get(f"{path}{sep}focus_order={ids[1][0]}").get_data(as_text=True)
    assert "SCOPE-COMPANY-1-" not in body and "INTERNAL-" not in body
    body = auth_client.get(f"{path}{sep}partner_org={orgs[1]}").get_data(as_text=True)
    assert "SCOPE-COMPANY-1-" in body
    assert "SCOPE-COMPANY-0-" not in body and "INTERNAL-" not in body
    # An ordinary tab link carries the persisted selection without URL propagation.
    body = auth_client.get(path).get_data(as_text=True)
    assert "SCOPE-COMPANY-0-" not in body and "INTERNAL-" not in body


def test_completion_api_and_csv_use_cookie_scope(auth_client, scoped_orders):
    orgs, ids = scoped_orders
    auth_client.get(f"/erp/completion?partner_org={orgs[0]}")
    response = auth_client.get(f"/api/orders/completion?focus_order={ids[1][-1]}")
    assert response.status_code == 200
    assert not response.get_json()["orders"]
    rows = auth_client.get("/api/orders/completion").get_json()["orders"]
    assert {row["id"] for row in rows} <= set(ids[0])
    assert rows
    response = auth_client.get("/erp/completion/export.csv")
    assert response.status_code == 200 and response.mimetype == "text/csv"
    csv = response.get_data(as_text=True)
    assert "SCOPE-COMPANY-0-" in csv
    assert "SCOPE-COMPANY-1-" not in csv and "INTERNAL-" not in csv


@pytest.mark.parametrize("service", ["aggregate", "rows", "products"])
def test_financial_queries_scope_before_projection_without_extra_queries(auth_client, scoped_orders, service):
    from foms.services.settlement_aggregation import aggregate_settlement
    from foms.services.settlement_rows import list_settlement_rows
    from foms.services.settlement_products import aggregate_products

    orgs, ids = scoped_orders
    calls = {"aggregate": aggregate_settlement, "rows": list_settlement_rows, "products": aggregate_products}
    statements = []
    engine = db_session.get_bind()
    month = get_today_kst().strftime("%Y-%m")
    kwargs = {"month_from": month, "month_to": month} if service == "aggregate" else {}

    def record(conn, cursor, sql, parameters, context, executemany):
        statements.append(sql)

    event.listen(engine, "before_cursor_execute", record)
    try:
        off = calls[service](db_session, **kwargs)
        off_count = len(statements)
        statements.clear()
        on = calls[service](db_session, partner_org=str(orgs[0]), **kwargs)
        assert len(statements) == off_count
        orders_sql = [sql for sql in statements if "FROM orders" in sql]
        assert orders_sql and all("orders.partner_org_id =" in sql for sql in orders_sql)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    if service == "aggregate":
        assert sum(row["count"] for row in off["stages"]) > 0
        assert sum(row["count"] for row in on["stages"]) * 3 == sum(row["count"] for row in off["stages"])
        assert sum(row["amount"] for row in on["stages"]) * 3 == sum(row["amount"] for row in off["stages"])
    elif service == "rows":
        assert on["total_count"] * 3 == off["total_count"]
        assert {row["order_id"] for row in on["rows"]} <= set(ids[0])
    else:
        assert on["allocation_check"]["orders"] * 3 == off["allocation_check"]["orders"]


@pytest.mark.parametrize("path", ["/api/settlement/aggregates", "/api/settlement/rows", "/api/settlement/products"])
def test_financial_endpoints_forward_persisted_company(auth_client, scoped_orders, monkeypatch, path):
    from foms.api.cs import settlement

    orgs, _ = scoped_orders
    seen = []
    for name in ("aggregate_settlement", "list_settlement_rows", "aggregate_products"):
        monkeypatch.setattr(settlement, name, lambda *a, **kw: seen.append(kw["partner_org"]) or {})
    auth_client.get(f"/erp/settlement?partner_org={orgs[0]}")
    assert auth_client.get(path).status_code == 200
    assert seen == [str(orgs[0])]


def test_mobile_menu_reuses_company_query_and_channel_totals_do_not_leak(auth_client, scoped_orders):
    from bs4 import BeautifulSoup

    orgs, _ = scoped_orders
    response = auth_client.get(f"/erp/settlement?partner_org={orgs[0]}")
    soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")
    assert soup.select_one("[data-partner-channel-notice]")
    assert not soup.select_one('[data-settlement-tab="channel"]')
    assert auth_client.get("/api/settlement/channel").status_code == 400
    assert auth_client.get("/api/settlement/channel/export.csv").status_code == 400
    auth_client.get("/erp/settlement?partner_org=")
    assert auth_client.get("/api/settlement/channel").status_code == 200


@pytest.mark.parametrize("path", ["/erp/measurement", "/erp/completion", "/erp/settlement"])
def test_mobile_filter_preserves_controls_and_does_not_query_orgs_in_fragments(auth_client, scoped_orders, monkeypatch, path):
    from bs4 import BeautifulSoup
    from models import User

    orgs, _ = scoped_orders
    user = db_session.query(User).filter_by(username="testadmin").one()
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    sql = []
    engine = db_session.get_bind()

    def record(conn, cursor, statement, parameters, context, executemany):
        if "FROM partner_orgs" in statement:
            sql.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = auth_client.get(f"{path}?partner_org={orgs[0]}")
        assert len(sql) == 1
        soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")
        header = soup.select_one(".erp-mobile-shell-header")
        assert header and header.select_one('[data-foms-partner-open][aria-pressed="true"]')
        for selector in ("[data-foms-urgent-open]", "[data-foms-mytasks-toggle]", "[data-foms-search-open]", "[data-foms-notif-open]"):
            assert header.select_one(selector)
        sql.clear()
        response = auth_client.get(f"{path}?view=fragment", headers={"X-FOMS-ERP-SHELL": "1"})
        assert response.status_code == 200
        assert not sql
    finally:
        event.remove(engine, "before_cursor_execute", record)


@pytest.mark.parametrize("path", [
    "/erp/dashboard", "/erp/measurement", "/erp/drawing-workbench", "/erp/production/dashboard",
    "/erp/shipment", "/erp/as", "/erp/construction/dashboard", "/erp/completion", "/erp/history/",
])
def test_company_filter_does_not_add_database_round_trips(auth_client, scoped_orders, path):
    orgs, _ = scoped_orders
    engine = db_session.get_bind()
    statements = []

    def record(conn, cursor, sql, parameters, context, executemany):
        if sql.lstrip().upper().startswith("SELECT"):
            statements.append(sql)

    event.listen(engine, "before_cursor_execute", record)
    try:
        counts = []
        for company in ("", str(orgs[0])):
            statements.clear()
            params = {"partner_org": company, "view": "fragment", "from_dashboard": "1"}
            if path == "/erp/history/":
                params["q"] = "SCOPE"
            response = auth_client.get(path, query_string=params,
                                       headers={"X-FOMS-ERP-SHELL": "1"})
            assert response.status_code == 200
            counts.append(len(statements))
        assert counts[1] <= counts[0], (path, counts)
    finally:
        event.remove(engine, "before_cursor_execute", record)
