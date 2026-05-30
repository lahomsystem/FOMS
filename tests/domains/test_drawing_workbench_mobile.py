"""P0-02 — drawing workbench mobile card thumb + filter offcanvas."""

from datetime import date
from unittest.mock import MagicMock

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.drawing_workbench_display import (
    drawing_thumb_enabled,
    resolve_row_thumbnail_url,
)
from models import Order, User


def _login_drawing_admin(client):
    user = User(
        username="drawing_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="DRAWING",
        name="Drawing Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _drawing_order(structured_data=None):
    sd = {
        "parties": {"customer": {"name": "모바일 도면 고객"}, "manager": {"name": "담당A"}},
        "workflow": {"stage": "DRAWING"},
        "drawing": {"status": "IN_PROGRESS"},
        "drawing_current_files": [
            {
                "key": "drawings/test-plan.png",
                "filename": "test-plan.png",
                "view_url": "/api/files/view/drawings/test-plan.png",
            }
        ],
        "drawing_transfer_history": [],
        "drawing_assignees": [],
    }
    if structured_data:
        sd.update(structured_data)
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="모바일 도면",
        phone="010-1111-2222",
        address="Seoul",
        product="북박이",
        status="DRAWING",
        manager_name="담당A",
        is_erp_order=True,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_drawing_thumb_enabled_respects_env(monkeypatch):
    monkeypatch.delenv("FOMS_V3_DRAWING_THUMB_ENABLED", raising=False)
    assert drawing_thumb_enabled() is False
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    assert drawing_thumb_enabled() is True


def test_resolve_row_thumbnail_prefers_view_url(monkeypatch):
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    db = MagicMock()
    files = [{"key": "k1.png", "filename": "k1.png", "view_url": "/api/files/view/k1.png"}]
    assert resolve_row_thumbnail_url(1, files, db) == "/api/files/view/k1.png"
    db.query.assert_not_called()


def test_resolve_row_thumbnail_uses_attachment_thumb_key(monkeypatch):
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    attachment = MagicMock()
    attachment.thumbnail_key = "thumbs/k1.png"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = attachment
    files = [{"key": "k1.png", "filename": "k1.png"}]
    url = resolve_row_thumbnail_url(42, files, db)
    assert url == "/api/files/view/thumbs/k1.png"


def test_drawing_workbench_mobile_markup_with_v2_and_thumb(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order()

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "erp-drawing-mobile-controls" in body
    assert "erp-drawing-mobile-filter-drawer" in body
    assert "erp-drawing-mobile-card__thumb" in body
    assert "erp-drawing-mobile-list" in body
    assert "foms-drawing-mobile-card.css" in body
    assert "erp-pro-card__header--filter d-none d-lg-block" in body


def test_drawing_workbench_thumb_hidden_when_flag_off(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "false")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order()

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "erp-drawing-mobile-card__thumb" not in body
