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
    app_shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(
        encoding="utf-8"
    )
    shell = (ROOT / "templates/partials/shared/erp_mobile_shell.html").read_text(
        encoding="utf-8"
    )
    assert "foms_app_shell.html" in shell
    assert "foms_search_overlay.html" in app_shell
    assert "js/foms/search.js" in app_shell


def test_search_assets_imported() -> None:
    surfaces = (ROOT / "static/css/foundation/foms-mobile-surfaces.css").read_text(encoding="utf-8")
    js = (ROOT / "static/js/foms/search.js").read_text(encoding="utf-8")
    app_shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(encoding="utf-8")
    assert "foms-search-overlay.css" in surfaces
    assert "foms.search.recent.v1" in js
    assert "ArrowDown" in js
    assert "navigateToResult" in js
    assert "mobile-queue-focus.js" in app_shell


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
        href = by_name["customer"][0]["href"]
        assert f"focus_order={order.id}" in href
        assert "open=erp-order" not in href
        assert "view=queue" in href or "/erp/" in href
        by_chosung = search_unified(db_session, "ㄱㅁㅇ")
        assert by_chosung["customer"]


def test_unified_search_drawing_href_uses_workbench(app) -> None:
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        order = Order(
            received_date="2026-05-30",
            customer_name="도면고객",
            phone="010-1111-2222",
            address="Seoul",
            product="붙박이",
            status="DRAWING",
            erp_stage_code="DRAWING",
            is_erp_order=True,
            blueprint_image_url="https://example.com/plan.png",
            structured_data={
                "parties": {"customer": {"name": "도면고객"}},
                "workflow": {"stage": "DRAWING"},
            },
        )
        db_session.add(order)
        db_session.commit()

        hits = search_unified(db_session, "도면고객", group="drawing")
        assert hits["drawing"]
        href = hits["drawing"][0]["href"]
        assert href.startswith("/erp/drawing-workbench?")
        assert f"focus_order={order.id}" in href
        assert "open=erp-order" not in href


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
    body = response.get_data(as_text=True)
    assert "foms-search-overlay" in body or "foms-search-overlay__empty" in body
    partial = (ROOT / "templates/partials/shared/foms_search_results_partial.html").read_text(
        encoding="utf-8"
    )
    assert "data-foms-erp-no-shell" in partial
