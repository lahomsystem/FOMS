"""Contracts for the mobile-v2 ERP order edit form."""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User
from tests.visual.conftest import VISUAL_ADMIN_PASSWORD, VISUAL_ADMIN_USERNAME

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
    "erp-regional-order",
    "erp-regional-construction-type-field",
    "erp-regional-construction-type",
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

DESKTOP_OMITTED_ERP_IDS = {
    "erp-load-btn",
}

MOBILE_ONLY_ERP_IDS = {
    "erp-urgent-reason-field",
    "erp-received-time-select",
    "erp-received-time-control",
    "erp-measurement-time-control",
    "erp-construction-time-control",
    "erp-order-measurement-panel-toggle",
    "erp-order-measurement-panel-collapse",
    "erp-mobile-collapse-received-toggle",
    "erp-mobile-collapse-received-body",
    "erp-mobile-collapse-order-toggle",
    "erp-mobile-collapse-order-body",
    "erp-mobile-collapse-attachments-toggle",
    "erp-mobile-collapse-attachments-body",
    "erp-attachment-preview-item-select",
    "erp-attachment-preview-unlink",
    "erp-attachment-preview-delete",
}

PARENT_ERP_IDS = {"erp-order-config", "erp-order-bootstrap", "erp-order-tab"}


_INCLUDE_RE = re.compile(r"""{%\s*include\s+['"]([^'"]+)['"]""")


def _template_ids(rel: str, _seen: frozenset[str] | None = None) -> set[str]:
    """Collect element ids from a template and one level of {% include %} (recursive)."""
    if _seen is None:
        _seen = frozenset()
    if rel in _seen:
        return set()
    html = (ROOT / rel).read_text(encoding="utf-8")
    ids = set(re.findall(r"""id=["']([^"']+)["']""", html))
    for include_ref in _INCLUDE_RE.findall(html):
        inc_rel = include_ref if include_ref.startswith("templates/") else f"templates/{include_ref}"
        inc_path = ROOT / inc_rel
        if inc_path.is_file():
            ids |= _template_ids(inc_rel.replace("\\", "/"), _seen | {rel})
    return ids


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


_ERP_FORM_END_MARKER = "<!-- ERP 주소 검색 모달 -->"


def _erp_form_html(html: str) -> str:
    start = html.index('id="erp-form"')
    end = html.index(_ERP_FORM_END_MARKER, start)
    return html[start:end]


def _erp_form_html_in_mount(html: str, mount_id: str) -> str:
    mount_start = html.index(f'id="{mount_id}"')
    mount_chunk = html[mount_start:]
    form_start = mount_chunk.index('id="erp-form"')
    form_end = mount_chunk.index(_ERP_FORM_END_MARKER, form_start)
    return mount_chunk[form_start:form_end]


def test_mobile_template_preserves_critical_erp_ids() -> None:
    legacy_ids = _template_ids("templates/orders/partials/erp_order_tab.html")
    mobile_ids = _template_ids("templates/orders/partials/erp_order_tab_mobile.html")
    edit_body_ids = _template_ids("templates/orders/partials/edit_order_body.html")
    parent_ids = _template_ids("templates/orders/partials/edit_order_body.html")

    legacy_surface_ids = legacy_ids | edit_body_ids
    mobile_surface_ids = mobile_ids | edit_body_ids

    assert PARENT_ERP_IDS <= parent_ids
    assert (CRITICAL_ERP_IDS - PARENT_ERP_IDS - DESKTOP_OMITTED_ERP_IDS) <= legacy_surface_ids
    assert sorted(
        ((CRITICAL_ERP_IDS - PARENT_ERP_IDS) - MOBILE_OMITTED_ERP_IDS) - mobile_surface_ids
    ) == []
    assert MOBILE_OMITTED_ERP_IDS <= legacy_surface_ids
    assert sorted(MOBILE_OMITTED_ERP_IDS & mobile_ids) == []
    assert MOBILE_ONLY_ERP_IDS <= mobile_surface_ids


def test_mobile_surfaces_import_form_field_css() -> None:
    bundle = (ROOT / "static/css/foundation/foms-mobile-surfaces.css").read_text(
        encoding="utf-8"
    )
    assert "foms-form-field.css" in bundle


def test_mobile_erp_form_uses_foms_select_not_legacy_bootstrap_select() -> None:
    """ERP form pane uses foms-select atoms; legacy form-select stays out of the form body."""
    mobile = (
        ROOT / "templates" / "orders" / "partials" / "erp_order_tab_mobile.html"
    ).read_text(encoding="utf-8")
    erp_form = _erp_form_html(mobile)

    assert "foms-select" in erp_form
    assert "form-select" not in erp_form
    assert 'id="erp-workflow-stage"' in erp_form


def test_edit_erp_order_ships_responsive_form_mounts_for_cohort(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _login_admin(client, "erp_mobile_form_on")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _make_erp_order()

    resp = client.get(f"/edit/{order.id}?open=erp-order")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    legacy_form = _erp_form_html_in_mount(html, "erp-order-form-legacy")
    mobile_form = _erp_form_html_in_mount(html, "erp-order-form-mobile")

    assert "foms-mobile-surfaces.css" in html
    assert 'id="erp-order-form-legacy"' in html
    assert 'id="erp-order-form-mobile"' in html
    assert "matchMedia" in html
    assert "erp_order_tab_mobile.html" not in html
    assert "form-control form-control-sm" in legacy_form
    assert "foms-input" not in legacy_form
    assert "foms-input" in mobile_form
    assert "field__label" in mobile_form
    assert "form-control form-control-sm" not in mobile_form
    assert "erp-mobile-time-inline" in mobile_form
    assert 'id="erp-urgent-reason-field"' in mobile_form
    assert "erp-received-time-select" in mobile_form
    assert "erp-order-measurement-panel-collapse" in mobile_form
    assert "계약 텍스트" not in mobile_form
    assert 'id="erp-mobile-collapse-received-toggle"' in mobile_form
    assert 'aria-expanded="false"' in mobile_form
    assert 'id="erp-mobile-collapse-received-body"' in mobile_form
    assert 'class="collapse"' in mobile_form
    assert 'id="erp-mobile-collapse-order-toggle"' in mobile_form
    assert 'id="erp-mobile-collapse-attachments-toggle"' in mobile_form
    assert 'aria-expanded="true"' in mobile_form
    assert "현장 스펙" in mobile_form
    assert "사진/동영상 추가" in mobile_form
    assert 'class="collapse show"' in mobile_form
    assert "erp-mobile-pre-sticky-footer" in mobile_form


def test_mobile_erp_form_sections_use_field_priority_collapse_defaults() -> None:
    """접수·발주는 접고, 현장 사진/동영상은 바로 보이게 둔다."""
    mobile = (
        ROOT / "templates" / "orders" / "partials" / "erp_order_tab_mobile.html"
    ).read_text(encoding="utf-8")

    for toggle_id, body_id in (
        ("erp-mobile-collapse-received-toggle", "erp-mobile-collapse-received-body"),
        ("erp-mobile-collapse-order-toggle", "erp-mobile-collapse-order-body"),
    ):
        toggle_idx = mobile.index(f'id="{toggle_id}"')
        body_marker = f'id="{body_id}"'
        body_idx = mobile.index(body_marker)
        toggle_chunk = mobile[toggle_idx:body_idx]
        assert 'aria-expanded="false"' in toggle_chunk
        assert 'data-bs-toggle="collapse"' in toggle_chunk
        assert f'data-bs-target="#{body_id}"' in toggle_chunk
        body_open = mobile[body_idx - 40:body_idx + len(body_marker) + 20]
        assert 'class="collapse"' in body_open
        assert " show" not in body_open.split(">", 1)[0]

    attachments_toggle_idx = mobile.index('id="erp-mobile-collapse-attachments-toggle"')
    attachments_body_idx = mobile.index('id="erp-mobile-collapse-attachments-body"')
    attachments_toggle = mobile[attachments_toggle_idx:attachments_body_idx]
    attachments_body_open = mobile[attachments_body_idx - 40:attachments_body_idx + 80]
    assert 'aria-expanded="true"' in attachments_toggle
    assert 'class="collapse show"' in attachments_body_open


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


@pytest.mark.skipif(
    "sqlite:///tests/visual/" not in os.environ.get("DATABASE_URL", "").replace("\\", "/"),
    reason="Playwright edit smoke requires DATABASE_URL=sqlite:///tests/visual/visual_local.sqlite",
)
def test_edit_erp_order_mobile_field_persona_smoke(
    page,
    visual_live_server_erp_v2,
    monkeypatch: pytest.MonkeyPatch,
    visual_cohort_user_id: str,
) -> None:
    """실측 담당자 모바일 폭에서 현장 스펙/사진 입력이 첫 작업권에 렌더된다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", visual_cohort_user_id)
    order = Order(
        received_date=datetime.date.today().isoformat(),
        customer_name="현장실측 고객",
        phone="010-3981-0000",
        address="서울시 현장",
        product="ㄷ자 시스템행거",
        is_erp_order=True,
        structured_data={
            "parties": {
                "customer": {"name": "현장실측 고객", "phone": "010-3981-0000"},
                "manager": {"name": "한용희 부장"},
            },
            "site": {"address_full": "서울시 현장"},
            "workflow": {"stage": "MEASURE"},
            "items": [
                {
                    "product_name": "ㄷ자 시스템행거",
                    "spec": "5700(2402+1864+1638)*400*2300",
                    "spec_rows": [
                        {
                            "spec_width": "5700(2402+1864+1638)",
                            "spec_depth": "400",
                            "spec_height": "2300",
                        }
                    ],
                    "internal": "사진참조",
                    "color": "한솔시에라오크",
                    "option_detail": "리프트업도어,밥솥장,서랍장,블룸레일*4",
                    "handle": "내림도어, 목찬넬",
                    "misc": "주방",
                    "price": 7000000,
                }
            ],
        },
    )
    db_session.add(order)
    db_session.commit()

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{visual_live_server_erp_v2}/login", wait_until="networkidle")
    page.fill('input[name="username"]', VISUAL_ADMIN_USERNAME)
    page.fill('input[name="password"]', VISUAL_ADMIN_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    page.goto(f"{visual_live_server_erp_v2}/edit/{order.id}?open=erp-order", wait_until="networkidle")

    body_class = page.locator("body").get_attribute("class") or ""
    assert "erp-mobile-v2-layout" in body_class
    assert page.locator("#erp-order-form-mobile").is_visible()
    page.wait_for_selector('#erp-order-form-mobile textarea[data-erp="spec"]')

    mobile_text = page.locator("#erp-order-form-mobile").inner_text()
    assert mobile_text.index("현장 스펙") < mobile_text.index("발주")
    assert mobile_text.index("사진/동영상") < mobile_text.index("발주")
    assert page.locator('#erp-order-form-mobile textarea[data-erp="spec"]').input_value() == (
        "5700(2402+1864+1638)*400*2300"
    )
    assert page.locator("#erp-attachments-upload-btn").is_visible()
