"""P1 completion gate: flag matrix, KV rollout manifest, UX route smoke."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tools/design/p1_kv_rollout_manifest.json"
MARKERS = (
    "foms_kv",
    "foms-kv-list",
    "foms_order_contact_kv",
    "render_queue_card",
    "foms-kv-rollout",
    "kv_row",
)


@pytest.mark.parametrize(
    ("flag", "default"),
    [
        ("FOMS_WIZARD_NEW_ORDER_ENABLED", False),
        ("FOMS_INLINE_EDIT_ENABLED", False),
        ("FOMS_TABLET_SPLIT_VIEW_ENABLED", False),
        ("ERP_MOBILE_V2_ENABLED", False),
    ],
)
def test_p1_flags_default_off(monkeypatch: pytest.MonkeyPatch, flag: str, default: bool) -> None:
    from foms.services.feature_flags import env_bool

    monkeypatch.delenv(flag, raising=False)
    assert env_bool(flag, default=default) is default


@pytest.mark.parametrize(
    "wizard,inline,split",
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, True, True),
    ],
)
def test_p1_flag_combination_api_gating(
    client,
    app,
    monkeypatch: pytest.MonkeyPatch,
    wizard: bool,
    inline: bool,
    split: bool,
) -> None:
    from db import db_session
    from models import Order, User

    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true" if wizard else "false")
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "true" if inline else "false")
    monkeypatch.setenv("FOMS_TABLET_SPLIT_VIEW_ENABLED", "true" if split else "false")
    if split:
        monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")

    with app.app_context():
        user = User(
            username="p1_matrix_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Matrix",
        )
        db_session.add(user)
        db_session.flush()
        if split:
            monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
        order = Order(
            received_date="2026-05-30",
            customer_name="M",
            phone="010-0000-0000",
            address="Seoul",
            product="P",
            is_erp_order=True,
            structured_data={"items": [{"product_name": "P", "color": "w"}]},
            structured_updated_at=__import__("datetime").datetime.now(),
        )
        db_session.add(order)
        db_session.commit()
        order_id = order.id

    client.post("/login", data={"username": "p1_matrix_user", "password": "admin"}, follow_redirects=True)

    draft = client.get("/api/erp/order-draft?key=new.off")
    assert draft.status_code == (200 if wizard else 403)

    patch = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        json={"field": "items.0.color", "value": "x"},
        headers={"Content-Type": "application/json"},
    )
    assert patch.status_code == (200 if inline else 403)

    dash = client.get("/erp/dashboard")
    assert dash.status_code == 200
    body = dash.get_data(as_text=True)
    if split:
        assert "foms-split-shell" in body
    else:
        assert "foms-split-shell" not in body


def test_p1_kv_rollout_manifest_coverage() -> None:
    paths = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(paths) == 15
    missing: list[str] = []
    for rel in paths:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if not any(marker in text for marker in MARKERS):
            missing.append(rel)
    assert not missing, f"KV rollout marker missing: {missing}"


def test_p1_spec_artifacts_exist() -> None:
    required = [
        "static/css/components/foms-product-item.css",
        "static/js/foms/product-item.js",
        "static/js/foms/kv-copy.js",
        "static/js/foms/inline-edit.js",
        "static/js/foms/wizard.js",
        "static/js/foms/split-shell.js",
        "templates/macros/foms_kv.html",
        "templates/macros/foms_product_item.html",
        "templates/partials/shared/foms_split_shell.html",
        "templates/orders/wizard/wizard_shell.html",
    ]
    for rel in required:
        assert (ROOT / rel).is_file(), rel


def test_wizard_route_gated(client, app, monkeypatch: pytest.MonkeyPatch) -> None:
    from db import db_session
    from models import User

    with app.app_context():
        db_session.add(
            User(
                username="wiz_gate",
                password=generate_password_hash("admin"),
                role="ADMIN",
                team="CS",
                name="W",
            )
        )
        db_session.commit()
    client.post("/login", data={"username": "wiz_gate", "password": "admin"}, follow_redirects=True)

    monkeypatch.delenv("FOMS_WIZARD_NEW_ORDER_ENABLED", raising=False)
    legacy = client.get("/add")
    assert "foms-wizard-root" not in legacy.get_data(as_text=True)

    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")
    wizard = client.get("/add?wizard=1")
    assert "foms-wizard-root" in wizard.get_data(as_text=True)
