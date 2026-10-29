"""Partner preference and company search: actual list/summary/history regressions."""
import datetime
import re

import pytest
from flask import request

from db import db_session
from models import Order, PartnerOrg
from foms.services.common.partner_order_filter import partner_filter_value


@pytest.fixture
def partner_orders(auth_client):
    """Seed two companies, an internal order and an old completion; return IDs."""
    org = PartnerOrg(name="필터라운즈")
    other = PartnerOrg(name="필터다른회사")
    db_session.add_all([org, other])
    db_session.flush()
    rows = []
    for index in range(5):
        rows.append(Order(
            customer_name=f"필터고객{index}", phone="010-0000-0000", address="가상주소",
            product="가상제품", received_date="2026-10-29", is_erp_order=True,
            status="MEASURE" if index == 0 else "DRAWING",
            erp_stage_code="MEASURE" if index == 0 else "DRAWING", partner_org_id=org.id,
            structured_data={"parties": {"orderer": {"name": org.name}, "customer": {"name": f"필터고객{index}"}}},
        ))
    rows.extend([
        Order(customer_name="필터다른고객", phone="010-0000-0000", address="가상주소", product="가상제품",
              received_date="2026-10-29", is_erp_order=True, status="DRAWING", erp_stage_code="DRAWING",
              partner_org_id=other.id, structured_data={"parties": {"orderer": {"name": other.name}}}),
        Order(customer_name="필터내부고객", phone="010-0000-0000", address="가상주소", product="가상제품",
              received_date="2026-10-29", is_erp_order=True, status="DRAWING", erp_stage_code="DRAWING",
              structured_data={"parties": {"orderer": {"name": org.name}, "manager": {"name": org.name}}}),
    ])
    db_session.add_all(rows)
    db_session.commit()
    return org.id, other.id, [row.id for row in rows]


def _ids(body: str) -> set[int]:
    """Return order IDs rendered in the desktop work queue/history."""
    return {int(value) for value in re.findall(r'data-order-id="(\d+)"', body)}


@pytest.mark.parametrize("raw,expected", [("", ""), ("all", "all"), ("1", "1"),
                                               ("99999999999999", "-1"), ("junk", "-1"), ("0", "-1")])
def test_selection_normalizes_without_widening(app, raw, expected):
    with app.test_request_context("/erp/dashboard", query_string={"partner_org": raw}):
        assert partner_filter_value(request) == expected


def test_company_search_finds_all_five_current_orders(auth_client, partner_orders):
    org, _, ids = partner_orders
    body = auth_client.get("/erp/dashboard?q=필터라운즈").get_data(as_text=True)
    assert _ids(body) == set(ids[:5])
    assert "data-erp-history-more" not in body
    assert "global-partner-filter-btn" in body
    assert f"partner_org={org}" in body


@pytest.mark.parametrize("path", ["/erp/dashboard?view=fragment", "/erp/history/?view=fragment"])
def test_company_scope_and_focus_cannot_leak_other_orders(auth_client, partner_orders, path):
    org, _, ids = partner_orders
    response = auth_client.get(f"{path}&partner_org={org}&focus_order={ids[5]}", headers={"X-FOMS-ERP-SHELL": "1"})
    assert response.status_code == 200
    assert response.headers["X-FOMS-ERP-FRAGMENT"] == "1"
    assert _ids(response.get_data(as_text=True)) == set(ids[:5])


def test_all_partners_cookie_clear_and_invalid_id(auth_client, partner_orders):
    org, _, ids = partner_orders
    first = auth_client.get(f"/erp/dashboard?partner_org={org}")
    assert "foms_partner_org=" in first.headers.get("Set-Cookie", "")
    assert _ids(auth_client.get("/erp/dashboard").get_data(as_text=True)) == set(ids[:5])
    assert _ids(auth_client.get("/erp/dashboard?partner_org=all").get_data(as_text=True)) == set(ids[:6])
    assert not _ids(auth_client.get("/erp/dashboard?partner_org=123456789").get_data(as_text=True))
    assert _ids(auth_client.get("/erp/dashboard?partner_org=").get_data(as_text=True)) == set(ids)


def test_listing_search_respects_company_preference(auth_client, partner_orders):
    org, _, _ = partner_orders
    auth_client.get(f"/erp/dashboard?partner_org={org}")
    body = auth_client.get("/?q=필터").get_data(as_text=True)
    assert "필터고객0" in body
    assert "필터다른고객" not in body and "필터내부고객" not in body


@pytest.mark.parametrize("missing_stage_timestamp", [False, True])
def test_history_more_only_counts_actual_outside_population(auth_client, partner_orders, missing_stage_timestamp):
    org, _, ids = partner_orders
    old = datetime.datetime.now() - datetime.timedelta(days=400)
    db_session.add(Order(customer_name="필터과거고객", phone="010-0000-0000", address="가상주소", product="가상제품",
                         received_date="2025-01-01", is_erp_order=True, status="COMPLETED", erp_stage_code="COMPLETED",
                         erp_stage_updated_at=None if missing_stage_timestamp else old,
                         structured_updated_at=None, created_at=old, partner_org_id=org,
                         structured_data={"parties": {"orderer": {"name": "필터라운즈"}}}))
    db_session.commit()
    body = auth_client.get(f"/erp/dashboard?q=필터라운즈&partner_org={org}").get_data(as_text=True)
    assert _ids(body) == set(ids[:5])
    assert "전체 이력에 1건 더" in body
    assert f"partner_org={org}" in re.search(r'href="([^"]+)" data-erp-history-more', body).group(1)


def test_history_redirect_preserves_explicit_company(auth_client, partner_orders):
    org, _, _ = partner_orders
    response = auth_client.get(f"/erp/history/?q=필터라운즈&partner_org={org}")
    assert response.status_code == 302
    assert f"partner_org={org}" in response.headers["Location"]


def test_company_search_intersects_stage(auth_client, partner_orders):
    org, _, ids = partner_orders
    body = auth_client.get(f"/erp/dashboard?q=필터라운즈&partner_org={org}&stage=도면").get_data(as_text=True)
    assert _ids(body) == set(ids[1:5])


@pytest.mark.parametrize("module,path", [
    ("foms.web.orders.dashboard", "/erp/dashboard"),
    ("foms.web.orders.history", "/erp/history/?from_dashboard=1"),
])
def test_cached_results_are_partitioned_by_company(auth_client, partner_orders, monkeypatch, module, path):
    from importlib import import_module

    org, other, ids = partner_orders
    cached = {}

    def cache(key, ttl, compute, **kwargs):
        if key not in cached:
            cached[key] = compute()
        return cached[key]

    monkeypatch.setattr(import_module(module), "get_or_compute_dashboard_slice", cache)
    sep = "&" if "?" in path else "?"
    body = auth_client.get(f"{path}{sep}partner_org={org}").get_data(as_text=True)
    keys = set(cached)
    assert _ids(body) == set(ids[:5])
    body = auth_client.get(f"{path}{sep}partner_org={other}").get_data(as_text=True)
    assert _ids(body) == {ids[5]}
    assert set(cached) - keys


def test_history_shadow_key_includes_cookie_scope(app, monkeypatch):
    from flask import make_response
    from types import SimpleNamespace
    from foms.web.orders import history

    captured = []
    monkeypatch.setattr(history, "is_shadow_revalidation_enabled", lambda: True)
    monkeypatch.setattr(history, "wants_erp_shell_tab_body", lambda req: True)
    monkeypatch.setattr(history, "build_fragment_version_key", lambda **kw: captured.append(kw) or None)
    for company in ("1", "2"):
        with app.test_request_context("/erp/history/", headers={"Cookie": f"foms_partner_org={company}"}):
            history._observe_fragment_version(make_response("body"), SimpleNamespace(id=1), False)
    assert captured[0]["route_id"] != captured[1]["route_id"]
