"""P1-02: unified search service + overlay wiring."""

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]


def test_chosung_query_detection() -> None:
    from foms.services.foms_unified_search import is_chosung_query

    assert is_chosung_query("ㄱㅁㅇ") is True
    assert is_chosung_query("고명") is False


def test_matches_query_chosung_prefix() -> None:
    from foms.services.foms_unified_search import matches_query

    assert matches_query("고명옥", "ㄱㅁㅇ") is True
    assert matches_query("고명옥", "ㄱㅅ") is False


def test_search_overlay_template_contract() -> None:
    overlay = (ROOT / "templates/partials/shared/foms_search_overlay.html").read_text(
        encoding="utf-8"
    )
    assert 'id="foms-search-overlay"' in overlay
    assert "hx-trigger" in overlay
    assert "delay:200ms" in overlay
    assert "data-foms-search-open" not in overlay
    header = (ROOT / "templates/partials/shared/erp_mobile_shell_header.html").read_text(
        encoding="utf-8"
    )
    assert "data-foms-search-open" in header
    shell = (ROOT / "templates/partials/shared/erp_mobile_shell.html").read_text(
        encoding="utf-8"
    )
    assert "foms_search_overlay.html" in shell
    assert "js/foms/search.js" in shell


def test_search_assets_imported() -> None:
    erp_pro = (ROOT / "static/css/foundation/erp-pro.css").read_text(encoding="utf-8")
    js = (ROOT / "static/js/foms/search.js").read_text(encoding="utf-8")
    assert "foms-search-overlay.css" in erp_pro
    assert "foms.search.recent.v1" in js
    assert "ArrowDown" in js


def test_unified_search_finds_customer(app) -> None:
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order, User

    with app.app_context():
        user = User(
            username="search_overlay_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Search User",
        )
        db_session.add(user)
        db_session.commit()

        order = Order(
            received_date="2026-05-30",
            customer_name="고명옥",
            phone="010-2690-2242",
            address="Seoul",
            product="거실장",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "고명옥", "phone": "010-2690-2242"}}
            },
        )
        db_session.add(order)
        db_session.commit()

        by_name = search_unified(db_session, "고명")
        assert by_name["customer"]
        by_chosung = search_unified(db_session, "ㄱㅁㅇ")
        assert by_chosung["customer"]


def test_search_api_json(client, app) -> None:
    from db import db_session
    from models import User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User(
            username="search_api_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="API User",
        )
        db_session.add(user)
        db_session.commit()

    client.post(
        "/login",
        data={"username": "search_api_user", "password": "admin"},
        follow_redirects=True,
    )
    response = client.get("/api/foms/search?q=고명&group=customer")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "customer" in payload["data"]


def test_search_fragment_route(client, app) -> None:
    from db import db_session
    from models import User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User(
            username="search_frag_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Frag User",
        )
        db_session.add(user)
        db_session.commit()

    client.post(
        "/login",
        data={"username": "search_frag_user", "password": "admin"},
        follow_redirects=True,
    )
    response = client.get("/api/foms/search/fragment?q=test&group=all")
    assert response.status_code == 200
    assert "foms-search-overlay" in response.get_data(as_text=True)
