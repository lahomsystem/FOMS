"""P1-05~07 contract tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_split_shell_templates() -> None:
    shell = (ROOT / "templates/partials/shared/foms_split_shell.html").read_text(encoding="utf-8")
    assert "data-foms-split-shell" in shell
    assert "foms_master_list.html" in shell
    css = (ROOT / "static/css/foundation/foms-split-view.css").read_text(encoding="utf-8")
    assert "1024px" in css
    js = (ROOT / "static/js/foms/split-shell.js").read_text(encoding="utf-8")
    assert "data-foms-master-card" in js


def test_token_alias_bridge() -> None:
    tokens = (ROOT / "static/css/foundation/erp-pro/01-intro-tokens.css").read_text(encoding="utf-8")
    assert 'url("../foms-tokens.css")' in tokens
    assert "--foms-bridge-erp-primary: var(--erp-primary)" in tokens


def test_foms_kv_macro_deeplinks() -> None:
    macro = (ROOT / "templates/macros/foms_kv.html").read_text(encoding="utf-8")
    assert "tel:" in macro
    assert "map.kakao.com" in macro
    assert "mailto:" in macro


def test_wizard_alpine_validation_and_multi_product() -> None:
    shell = (ROOT / "templates/orders/wizard/wizard_shell.html").read_text(encoding="utf-8")
    assert 'x-data="fomsWizardValidation"' in shell
    step1 = (ROOT / "templates/orders/wizard/step1_basic.html").read_text(encoding="utf-8")
    assert "foms-wizard__error" in step1
    step2 = (ROOT / "templates/orders/wizard/step2_products.html").read_text(encoding="utf-8")
    assert "foms-wizard-add-product" in step2
    js = (ROOT / "static/js/foms/wizard.js").read_text(encoding="utf-8")
    assert "cloneProductCard" in js
    assert "applyAlpineErrors" in js
    css = (ROOT / "static/css/foundation/erp-pro.css").read_text(encoding="utf-8")
    assert "foms-kv-row.css" in css


def test_build_split_master_cards() -> None:
    from foms.services.foms_split_view import build_split_master_cards

    cards = build_split_master_cards(
        [{"id": 1, "customer_name": "A", "product": "장"}],
        active_order_id=1,
    )
    assert cards[0]["active"] is True
    assert "/api/foms/fragment/order/1/edit" in cards[0]["detail_href"]
