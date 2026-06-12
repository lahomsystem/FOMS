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
    pc_grid = (root / "templates/construction/partials/filters_grid.html").read_text(
        encoding="utf-8"
    )
    macro_src = (root / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(
        encoding="utf-8"
    )

    # 모바일 큐는 queue-card-v2 + PC식 번호 페이저(무한스크롤 아님).
    assert "render_queue_card_v2" in queue_src
    assert "--construction" in queue_src
    assert "render_mobile_pager" in queue_src
    assert "data-foms-mobile-queue-scroll" not in queue_src
    assert "data-foms-mobile-queue-sentinel" not in queue_src
    # v2 카드는 badge override(modifier)를 stage 배지에 반영한다.
    assert "foms-stage-badge{{ badge_mod }}" in macro_src
    # PC workflow baseline: 시공완료는 사진 재업로드와 AS 액션이 병존한다.
    assert 'data-action="reuploadConstructionPhotos"' in pc_grid
    assert 'data-action="openAsAcceptModal"' in pc_grid
    assert 'data-action="openAsReuploadModal"' in pc_grid
    # Mobile must preserve the same critical action set.
    assert "'reuploadConstructionPhotos'" in queue_src
    assert "'openAsAcceptModal'" in queue_src
    assert "'openAsReuploadModal'" in queue_src
    assert "task_actions=task_actions" in queue_src


def _login_plain_admin(client):
    """mine_only 강제(CONSTRUCTION 팀)를 피하려고 팀 없는 ADMIN으로 로그인."""
    user = User(
        username="erp_construction_pager_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team=None,
        name="ERP Construction Pager Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_construction_mobile_queue_numbered_pagination(client, monkeypatch):
    """회귀: 시공 모바일 큐가 50건 초과 시 하단 PC식 번호 페이저로 페이지 이동.

    증상: 무한스크롤은 앞으로만 로딩되고 이전 페이지로 못 돌아감 → 번호 페이저로 교체.
    """
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "false")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    for i in range(60):
        db_session.add(
            Order(
                received_date=today,
                customer_name=f"시공 페이저 {i}",
                phone="010-0000-0000",
                address="Seoul",
                product="붙박이장",
                status="CONSTRUCTION",
                manager_name="Bob",
                is_erp_order=True,
                structured_data={"workflow": {"stage": "CONSTRUCTION"}},
            )
        )
    db_session.commit()

    # 페이지 1: 번호 페이저(2페이지 링크) + 첫 50건, 무한스크롤 배선 없음
    page1 = client.get("/erp/construction/dashboard")
    assert page1.status_code == 200
    body = page1.get_data(as_text=True)
    assert "foms-mobile-pager" in body
    assert "page=2" in body
    assert "data-foms-mobile-queue-scroll" not in body
    assert "data-foms-mobile-queue-sentinel" not in body
    assert "50 / 전체 60건" in body

    # 페이지 2 직접 접근 → 나머지 10건, 페이저로 1페이지 복귀 가능
    page2 = client.get("/erp/construction/dashboard?page=2")
    assert page2.status_code == 200
    body2 = page2.get_data(as_text=True)
    assert "foms-mobile-pager" in body2
    assert "60 / 전체 60건" in body2
    assert 'aria-current="page"' in body2  # 현재 페이지(2) 표시
    assert "page=1" in body2  # 1페이지로 돌아가는 링크


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


def test_construction_mobile_completed_renders_reupload_as_and_edit(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "false")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    _create_construction_order(
        customer_name="시공완료 모바일 고객",
        structured_data={"workflow": {"stage": "COMPLETED"}},
    )

    response = client.get("/erp/construction/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-action="reuploadConstructionPhotos"' in body
    assert 'data-action="openAsAcceptModal"' in body
    assert "?open=erp-order" in body
