"""Contract: order edit (/edit/<id>) joins the erp-mobile-v2 shell cohort.

Mobile queue cards open the ERP order via /edit/<id>?open=erp-order, so that page
must wear the foms mobile shell chrome (header + bottom nav + mobile CSS bundle)
for the cohort, mirroring orders/mobile_order_detail.html. Desktop (>=992px) keeps
the legacy chrome via CSS media queries (not asserted here; this is a render
contract for the markup + CSS-bundle gate).
"""
from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User, Order


def _login_admin(client) -> User:
    user = User(
        username="edit_shell_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Edit Shell Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_erp_order() -> Order:
    order = Order(
        received_date=datetime.date.today().isoformat(),
        customer_name="Edit Shell Customer",
        phone="010-0000-1111",
        address="서울시 검증",
        product="검증 제품",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_edit_has_mobile_shell_for_cohort(client, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _make_erp_order()

    resp = client.get(f"/edit/{order.id}?open=erp-order")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # body cohort class -> mobile CSS media rules apply (legacy chrome hidden)
    assert "erp-mobile-v2-layout" in html
    # the mobile shell chrome wrapper + foms header
    assert 'data-erp-mobile-v2="true"' in html
    assert "erp-mobile-shell-header" in html
    assert "주문 수정" in html
    # the mobile shell CSS bundle (styles the foms header grid + sticky) must load
    assert "foms-mobile-surfaces.css" in html


def test_edit_no_shell_when_cohort_off(client, monkeypatch: pytest.MonkeyPatch) -> None:
    _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "")
    order = _make_erp_order()

    resp = client.get(f"/edit/{order.id}?open=erp-order")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "erp-mobile-v2-layout" not in html
    assert "erp-mobile-shell-header" not in html
    assert "foms-mobile-surfaces.css" not in html
