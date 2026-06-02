"""Contracts for the mobile-v2 ERP order edit form."""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]

CRITICAL_ERP_IDS = {
    "erp-order",
    "erp-order-config",
    "erp-order-bootstrap",
    "erp-order-measurement-panel",
    "erp-received-date",
    "erp-received-time",
    "erp-urgent-flag",
    "erp-urgent-reason",
    "erp-self-measurement",
    "erp-customer-name",
    "erp-customer-phone",
    "erp-manual-phone-input",
    "erp-phone-note",
    "erp-orderer-direct",
    "erp-orderer-select",
    "erp-orderer",
    "erp-manager",
    "erp-construction-workers",
    "erp-workflow-stage",
    "erp-notes",
    "erp-address",
    "erp-address-search-btn",
    "erp-address-note",
    "erp-measurement-date",
    "erp-measurement-date-open",
    "erp-construction-date",
    "erp-construction-date-open",
    "erp-measurement-time",
    "erp-measurement-time-select",
    "erp-construction-time",
    "erp-construction-time-select",
    "erp-measurement-note",
    "erp-items",
    "erp-add-item-btn",
    "erp-items-total",
    "erp-deposit-amount",
    "erp-deposit-section",
    "erp-remaining-amount",
    "erp-remaining-section",
    "erp-status-text",
    "erp-channeltalk-push-btn",
    "erp-gen-text-btn",
    "erp-conversion-text",
    "erp-copy-text-btn",
    "erp-save-btn",
    "erp-load-btn",
    "erp-draft-banner",
    "erp-draft-order-id",
    "erp-draft-edit-link",
    "erp-attachments-input",
    "erp-attachments-upload-btn",
    "erp-attachments-gallery",
    "erp-attachments-category",
    "erp-attachments-progress",
    "erp-attachments-progress-bar",
    "erp-attachments-status",
    "erp-attachment-preview-body",
    "erp-attachment-preview-download",
    "erp-address-modal-query",
    "erp-address-modal-detail",
    "erp-address-modal-search-btn",
    "erp-address-modal-results",
    "erp-address-modal-status",
    "erp-address-modal-apply-btn",
    "erp-collapse-phone-note",
    "erp-collapse-address-note",
    "erp-collapse-address-note-btn",
    "erp-collapse-measure-note",
}

MOBILE_OMITTED_ERP_IDS = {
    "erp-channeltalk-push-btn",
    "erp-gen-text-btn",
    "erp-conversion-text",
    "erp-copy-text-btn",
}

MOBILE_ONLY_ERP_IDS = {
    "erp-urgent-reason-field",
    "erp-received-time-select",
    "erp-received-time-control",
    "erp-measurement-time-control",
    "erp-construction-time-control",
    "erp-order-measurement-panel-toggle",
    "erp-order-measurement-panel-collapse",
    "erp-attachment-preview-item-select",
    "erp-attachment-preview-unlink",
    "erp-attachment-preview-delete",
}

PARENT_ERP_IDS = {"erp-order-config", "erp-order-bootstrap", "erp-order-tab"}


def _template_ids(rel: str) -> set[str]:
    html = (ROOT / rel).read_text(encoding="utf-8")
    return set(re.findall(r"""id=["']([^"']+)["']""", html))


def _login_admin(client, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP Mobile Form Admin",
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
        customer_name="ERP Mobile Customer",
        phone="010-0000-2222",
        address="서울시 모바일",
        product="모바일 제품",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _erp_form_html(html: str) -> str:
    start = html.index('id="erp-form"')
    end = html.index('id="erp-estimate"', start)
    return html[start:end]


def test_mobile_template_preserves_critical_erp_ids() -> None:
    legacy_ids = _template_ids("templates/orders/partials/erp_order_tab.html")
    mobile_ids = _template_ids("templates/orders/partials/erp_order_tab_mobile.html")
    parent_ids = _template_ids("templates/orders/partials/edit_order_body.html")

    assert PARENT_ERP_IDS <= parent_ids
    assert CRITICAL_ERP_IDS - PARENT_ERP_IDS <= legacy_ids
    assert sorted(
        ((CRITICAL_ERP_IDS - PARENT_ERP_IDS) - MOBILE_OMITTED_ERP_IDS) - mobile_ids
    ) == []
    assert MOBILE_OMITTED_ERP_IDS <= legacy_ids
    assert sorted(MOBILE_OMITTED_ERP_IDS & mobile_ids) == []
    assert MOBILE_ONLY_ERP_IDS <= mobile_ids


def test_mobile_surfaces_import_form_field_css() -> None:
    bundle = (ROOT / "static/css/foundation/foms-mobile-surfaces.css").read_text(
        encoding="utf-8"
    )
    assert "foms-form-field.css" in bundle


def test_edit_erp_order_uses_mobile_form_for_cohort(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _login_admin(client, "erp_mobile_form_on")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _make_erp_order()

    resp = client.get(f"/edit/{order.id}?open=erp-order")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    erp_form = _erp_form_html(html)

    assert "foms-mobile-surfaces.css" in html
    assert "erp_order_tab_mobile.html" not in html
    assert "foms-input" in erp_form
    assert "field__label" in erp_form
    assert "form-control form-control-sm" not in erp_form
    assert "erp-mobile-time-inline" in erp_form
    assert 'id="erp-urgent-reason-field"' in erp_form
    assert "erp-received-time-select" in erp_form
    assert "erp-order-measurement-panel-collapse" in erp_form
    assert "계약 텍스트" not in erp_form


def test_edit_erp_order_keeps_legacy_form_when_cohort_off(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_admin(client, "erp_mobile_form_off")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "")
    order = _make_erp_order()

    resp = client.get(f"/edit/{order.id}?open=erp-order")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    erp_form = _erp_form_html(html)

    assert "foms-mobile-surfaces.css" not in html
    assert "form-control form-control-sm" in erp_form
    assert "foms-input" not in erp_form
