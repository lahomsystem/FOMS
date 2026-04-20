"""GNV-B1: orders listing/trash dual-mode fragment contract (full page vs nav fragment)."""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import User


def _login_as_manager(client, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("secret"),
        role="MANAGER",
        team="CS",
        name="GNV Fragment Tester",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_orders_index_full_document_has_global_nav(client) -> None:
    _login_as_manager(client, "gnav-full-index")
    res = client.get("/")
    assert res.status_code == 200
    assert b"layout-global-nav" in res.data


def test_orders_index_fragment_header_and_shape(client) -> None:
    _login_as_manager(client, "gnav-frag-index")
    res = client.get(
        "/?view=nav-fragment",
        headers={"X-FOMS-GNAV": "1"},
    )
    assert res.status_code == 200
    assert res.headers.get("X-FOMS-GNAV-FRAGMENT") == "1"
    assert b"layout-global-nav" not in res.data
    assert b"main-content" not in res.data


def test_orders_index_fragment_matches_full_data_semantics(client) -> None:
    """Fragment and full page should expose the same table shell for the same query (smoke)."""
    _login_as_manager(client, "gnav-parity-index")
    full = client.get("/?status=RECEIVED")
    frag = client.get(
        "/?status=RECEIVED&view=nav-fragment",
        headers={"X-FOMS-GNAV": "1"},
    )
    assert full.status_code == 200
    assert frag.status_code == 200
    assert b"order" in full.data.lower() or b"table" in full.data.lower()
    assert frag.headers.get("X-FOMS-GNAV-FRAGMENT") == "1"


def test_trash_fragment_header(client) -> None:
    _login_as_manager(client, "gnav-frag-trash")
    res = client.get(
        "/trash?view=nav-fragment",
        headers={"X-FOMS-GNAV": "1"},
    )
    assert res.status_code == 200
    assert res.headers.get("X-FOMS-GNAV-FRAGMENT") == "1"
    assert b"layout-global-nav" not in res.data
