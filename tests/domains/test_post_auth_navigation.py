"""Post-auth landing + persistent session contract for mobile ERP home."""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import User

IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _create_user(username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, username: str = "admin", password: str = "admin", **kwargs):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        **kwargs,
    )


def test_mobile_login_lands_on_erp_dashboard(client, app, monkeypatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")
    _create_user("mobile_login_user")
    response = _login(
        client,
        username="mobile_login_user",
        follow_redirects=False,
        headers={"User-Agent": IPHONE_UA},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/erp/dashboard")


def test_desktop_login_stays_on_legacy_home(client, app) -> None:
    _create_user("desktop_login_user")
    response = _login(
        client,
        username="desktop_login_user",
        follow_redirects=False,
        headers={"User-Agent": DESKTOP_UA},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_mobile_root_redirects_to_erp_dashboard(client, app, monkeypatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")
    user = _create_user("mobile_root_user")
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    response = client.get("/", follow_redirects=False, headers={"User-Agent": IPHONE_UA})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/erp/dashboard")


def test_pwa_start_url_mobile_app_query_redirects_home(client, app, monkeypatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")
    user = _create_user("pwa_home_user")
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    response = client.get(
        "/?mobile_app=1",
        follow_redirects=False,
        headers={"User-Agent": DESKTOP_UA},
    )
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/erp/dashboard")


def test_login_sets_persistent_session_cookie(client, app) -> None:
    _create_user("persistent_session_user")
    response = _login(
        client,
        username="persistent_session_user",
        follow_redirects=False,
    )
    set_cookie = response.headers.get("Set-Cookie", "")
    assert "session_staging=" in set_cookie
    assert "Expires=" in set_cookie or "Max-Age=" in set_cookie
