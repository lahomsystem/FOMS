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
    chunk_src = (root / "templates/production/partials/mobile_queue_chunk.html").read_text(encoding="utf-8")
    assert "data-foms-mobile-queue-scroll" in queue_src
    assert "data-foms-mobile-queue-sentinel" in queue_src
    assert "production/partials/mobile_queue_chunk.html" in queue_src
    assert "render_queue_card_v2" in chunk_src
    assert "data-foms-mobile-queue-chunk" in chunk_src
    assert "--production" in chunk_src


def test_production_mobile_queue_infinite_scroll_pagination(client, monkeypatch):
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
    assert "data-foms-mobile-queue-scroll" in body
    assert 'data-total-pages="2"' in body
    assert 'data-next-page="2"' in body
    assert "data-foms-mobile-queue-sentinel" in body
    assert "50 / 전체 60건" in body

    chunk = client.get("/erp/production/dashboard?mobile_chunk=1&page=2")
    assert chunk.status_code == 200
    chunk_body = chunk.get_data(as_text=True)
    assert "data-foms-mobile-queue-chunk" in chunk_body
    assert 'data-next-page="0"' in chunk_body
    assert "data-foms-mobile-queue-scroll" not in chunk_body
    assert "60 / 전체 60건" in chunk_body
