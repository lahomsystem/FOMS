"""P1-03: OrderDraft API + wizard shell wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def wizard_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")


def _login(client, app, username: str = "wizard_api_user") -> None:
    from db import db_session
    from models import User

    with app.app_context():
        if not db_session.query(User).filter_by(username=username).first():
            db_session.add(
                User(
                    username=username,
                    password=generate_password_hash("admin"),
                    role="ADMIN",
                    team="CS",
                    name="Wizard User",
                )
            )
            db_session.commit()
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )


def test_wizard_template_contract() -> None:
    shell = (ROOT / "templates/orders/wizard/wizard_shell.html").read_text(encoding="utf-8")
    assert 'id="foms-wizard-root"' in shell
    assert "data-draft-key" in shell
    assert "step1_basic.html" in shell
    assert "js/foms/draft.js" in shell
    assert "js/foms/wizard.js" in shell
    css = (ROOT / "static/css/components/foms-wizard.css").read_text(encoding="utf-8")
    assert ".foms-wizard" in css
    assert "foms-wizard.css" in shell


def test_order_draft_get_empty(client, app, wizard_enabled) -> None:
    _login(client, app)
    response = client.get("/api/erp/order-draft?key=new.test-empty")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["draft"] is None


def test_order_draft_put_and_get(client, app, wizard_enabled) -> None:
    _login(client, app, "wizard_put_user")
    body = {
        "draft_key": "new.test-put",
        "step": 2,
        "payload": {
            "schema_version": 1,
            "step": 2,
            "data": {"customer_name": "고명옥", "phone": "010-1111-2222", "address": "Seoul"},
        },
    }
    put = client.put(
        "/api/erp/order-draft",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert put.status_code == 200
    put_json = put.get_json()
    assert put_json["success"] is True
    assert put_json["updated_at"]

    get_resp = client.get("/api/erp/order-draft?key=new.test-put")
    assert get_resp.status_code == 200
    got = get_resp.get_json()
    assert got["draft"]["step"] == 2
    assert got["draft"]["payload"]["data"]["customer_name"] == "고명옥"


def test_order_draft_conflict_409(client, app, wizard_enabled) -> None:
    _login(client, app, "wizard_conflict_user")
    key = "new.test-conflict"
    base = {
        "draft_key": key,
        "step": 1,
        "payload": {"schema_version": 1, "step": 1, "data": {"customer_name": "A"}},
    }
    first = client.put(
        "/api/erp/order-draft",
        data=json.dumps(base),
        content_type="application/json",
    )
    updated_at = first.get_json()["updated_at"]

    stale = client.put(
        "/api/erp/order-draft",
        data=json.dumps(
            {
                "draft_key": key,
                "step": 1,
                "payload": {"schema_version": 1, "step": 1, "data": {"customer_name": "B"}},
            }
        ),
        content_type="application/json",
        headers={"X-If-Match": "1999-01-01 00:00:00"},
    )
    assert stale.status_code == 409
    conflict = stale.get_json()
    assert conflict["error"] == "CONFLICT"
    assert conflict["current"]["updated_at"] == updated_at


def test_order_draft_delete(client, app, wizard_enabled) -> None:
    _login(client, app, "wizard_delete_user")
    key = "new.test-delete"
    client.put(
        "/api/erp/order-draft",
        data=json.dumps(
            {
                "draft_key": key,
                "step": 1,
                "payload": {"schema_version": 1, "step": 1, "data": {}},
            }
        ),
        content_type="application/json",
    )
    deleted = client.delete(f"/api/erp/order-draft?key={key}")
    assert deleted.status_code == 200
    assert client.get(f"/api/erp/order-draft?key={key}").get_json()["draft"] is None


def test_order_draft_submit_creates_order(client, app, wizard_enabled) -> None:
    from db import db_session
    from models import Order

    _login(client, app, "wizard_submit_user")
    key = "new.test-submit"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "제출테스트",
            "phone": "010-9999-8888",
            "address": "경기도 성남시",
            "received_date": "2026-05-30",
            "items": [
                {
                    "product_name": "주방장",
                    "spec_rows": [{"spec_width": "3000", "spec_depth": "600", "spec_height": "2300"}],
                }
            ],
            "schedule": {},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.customer_name == "제출테스트"
        assert order.is_erp_order is True
    assert client.get(f"/api/erp/order-draft?key={key}").get_json()["draft"] is None


def test_add_order_renders_wizard_when_flag_on(client, app, wizard_enabled) -> None:
    _login(client, app, "wizard_page_user")
    response = client.get("/add")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-wizard-root" in body
    assert "wizard_shell" not in body  # rendered, not raw path leak required — ok if template name absent


def test_wizard_disabled_returns_403(client, app, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOMS_WIZARD_NEW_ORDER_ENABLED", raising=False)
    _login(client, app, "wizard_off_user")
    response = client.get("/api/erp/order-draft?key=new.off")
    assert response.status_code == 403
