"""P0-04: ERP construction dashboard mobile card (v1.1 badge + drawing/measurement thumbs)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.construction_dashboard_display import (
    construction_stage_badge_modifier,
    construction_thumb_enabled,
    enrich_construction_mobile_rows,
)
from models import Order, OrderAttachment, User


def _login_as_admin(client):
    user = User(
        username="erp_construction_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CONSTRUCTION",
        name="ERP Construction Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_construction_order(**kwargs):
    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    sd = kwargs.pop("structured_data", {}) or {}
    workflow = sd.get("workflow") or {}
    if "stage" not in workflow:
        workflow = {**workflow, "stage": kwargs.pop("workflow_stage", "CONSTRUCTION")}
    sd["workflow"] = workflow
    order = Order(
        received_date=today,
        customer_name=kwargs.get("customer_name", "시공 모바일 고객"),
        phone="010-3333-4444",
        address="Seoul",
        product="붙박이장",
        status=kwargs.get("status", "CONSTRUCTION"),
        manager_name=kwargs.get("manager_name", "Bob"),
        is_erp_order=True,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_construction_stage_badge_modifier_completed():
    assert construction_stage_badge_modifier("시공완료") == "--completed"


def test_construction_stage_badge_modifier_in_progress():
    assert construction_stage_badge_modifier("시공중") == "--construction"
    assert construction_stage_badge_modifier("시공대기") == "--construction"


def test_construction_thumb_enabled_respects_env(monkeypatch):
    monkeypatch.delenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", raising=False)
    assert construction_thumb_enabled() is False
    assert construction_thumb_enabled(mobile_v2_active=True) is True
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "true")
    assert construction_thumb_enabled() is True


@patch("foms.services.construction_dashboard_display.build_file_view_url", return_value="/files/const-thumb")
def test_enrich_construction_mobile_rows_from_structured_files(mock_url, monkeypatch):
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "true")
    rows = [
        {
            "id": 99,
            "stage": "시공중",
            "structured_data": {
                "drawing_current_files": [
                    {"key": "drawings/a.png", "filename": "a.png"},
                ]
            },
        }
    ]
    enrich_construction_mobile_rows(rows, MagicMock())

    assert rows[0]["stage_badge_modifier"] == "--construction"
    assert rows[0]["construction_thumb_active"] is True
    assert rows[0]["thumbnail_url"] == "/files/const-thumb"
    assert rows[0]["attachment_previews"] == ["/files/const-thumb"]
    mock_url.assert_called_once_with("drawings/a.png")


def test_enrich_construction_mobile_rows_skips_thumb_when_disabled(monkeypatch):
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "false")
    rows = [{"id": 1, "stage": "시공완료", "structured_data": {}}]
    enrich_construction_mobile_rows(rows, MagicMock())

    assert rows[0]["stage_badge_modifier"] == "--completed"
    assert rows[0]["construction_thumb_active"] is False
    assert rows[0]["thumbnail_url"] is None
    assert rows[0]["attachment_previews"] == []


@patch("foms.services.construction_dashboard_display.build_file_view_url", return_value="/files/att-thumb")
def test_enrich_construction_mobile_rows_attachment_fallback(mock_url, monkeypatch, app):
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "true")
    order = _create_construction_order()
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="measure.jpg",
            file_type="image",
            category="measurement",
            file_size=10,
            storage_key="const/measure.jpg",
        )
    )
    db_session.commit()

    rows = [{"id": order.id, "stage": "시공대기", "structured_data": {}}]
    enrich_construction_mobile_rows(rows, db_session)

    assert rows[0]["thumbnail_url"] == "/files/att-thumb"
    mock_url.assert_called_once_with("const/measure.jpg")


def test_construction_dashboard_mobile_wiring_contract():
    root = Path(__file__).resolve().parents[2]
    queue_src = (root / "templates/construction/partials/mobile_queue.html").read_text(
        encoding="utf-8"
    )
    macro_src = (root / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(
        encoding="utf-8"
    )

    # 모바일 v2 큐는 홈과 동일한 깔끔한 queue-card-v2를 쓰고 시공 배지를 명시 전달한다.
    assert "render_queue_card_v2" in queue_src
    assert "shared/erp_mobile_queue_card_v2.html" in queue_src
    assert "--construction" in queue_src
    # v2 카드는 badge override(modifier)를 stage 배지에 반영한다.
    assert "foms-stage-badge{{ badge_mod }}" in macro_src


def test_construction_dashboard_renders_v11_badge(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "false")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    # CONSTRUCTION team forces mine_only; manager must match logged-in user (dashboard.py L50-58).
    _create_construction_order(
        customer_name="시공 v11 배지",
        manager_name=user.name,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION", "history": [{"note": "시공 시작"}]},
            "parties": {"manager": {"name": user.name}},
        },
    )

    response = client.get("/erp/construction/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-erp-mobile-v2="true"' in body
    assert "foms-stage-badge foms-stage-badge--construction" in body
    assert "erp-construction-mobile-card__thumb-grid" not in body
