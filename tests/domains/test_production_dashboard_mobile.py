"""생산 대시보드 모바일 큐 무한스크롤 회귀 (시공과 동일 패턴)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_plain_admin(client):
    user = User(
        username="erp_production_pager_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team=None,
        name="ERP Production Pager Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_production_mobile_queue_wiring_contract():
    root = Path(__file__).resolve().parents[2]
    queue_src = (root / "templates/production/partials/mobile_queue.html").read_text(encoding="utf-8")
    pc_grid = (root / "templates/production/partials/filters_grid.html").read_text(encoding="utf-8")
    pc_scripts = (root / "templates/production/partials/scripts.html").read_text(encoding="utf-8")
    # PC식 번호 페이저(무한스크롤 아님)
    assert "render_mobile_pager" in queue_src
    assert "render_queue_card_v2" in queue_src
    assert "--production" in queue_src
    assert "data-foms-mobile-queue-scroll" not in queue_src
    assert "data-foms-mobile-queue-sentinel" not in queue_src
    # PC workflow baseline: start is in the grid, complete is in the detail flow.
    assert 'data-action="startProduction"' in pc_grid
    assert "completeProduction" in pc_scripts
    # Mobile must expose both PC-critical production actions by stage.
    assert 'data_action\': \'startProduction\'' in queue_src
    assert 'data_action\': \'completeProduction\'' in queue_src
    assert "고객 컨펌 전" in queue_src


def test_production_mobile_queue_numbered_pagination(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    today = date.today().strftime("%Y-%m-%d")
    for i in range(60):
        db_session.add(
            Order(
                received_date=today,
                customer_name=f"생산 페이저 {i}",
                phone="010-0000-0000",
                address="Seoul",
                product="붙박이장",
                status="PRODUCTION",
                manager_name="Bob",
                is_erp_order=True,
                structured_data={"workflow": {"stage": "생산"}},
            )
        )
    db_session.commit()

    page1 = client.get("/erp/production/dashboard")
    assert page1.status_code == 200
    body = page1.get_data(as_text=True)
    assert "foms-mobile-pager" in body
    assert "page=2" in body
    assert "data-foms-mobile-queue-scroll" not in body
    assert "50 / 전체 60건" in body

    page2 = client.get("/erp/production/dashboard?page=2")
    assert page2.status_code == 200
    body2 = page2.get_data(as_text=True)
    assert "foms-mobile-pager" in body2
    assert "60 / 전체 60건" in body2
    assert "page=1" in body2


def test_production_mobile_queue_renders_complete_and_edit_for_in_progress(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    today = date.today().strftime("%Y-%m-%d")
    db_session.add(
        Order(
            received_date=today,
            customer_name="제작중 모바일 고객",
            phone="010-0000-0000",
            address="Seoul",
            product="붙박이장",
            status="PRODUCTION",
            manager_name="Bob",
            is_erp_order=True,
            structured_data={"workflow": {"stage": "생산"}},
        )
    )
    db_session.commit()

    response = client.get("/erp/production/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-action="completeProduction"' in body
    assert "제작 완료" in body
    assert "?open=erp-order" in body
