from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]


def _login_erp_admin(client):
    user = User(
        username="notification_badge_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Notification Badge Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_erp_pages_use_single_notification_badge_fetch(client):
    _login_erp_admin(client)

    layout_scripts = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(
        encoding="utf-8"
    )
    layout_head = (ROOT / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    chat_js = (ROOT / "static/js/runtime/layout-scripts-chat.js").read_text(encoding="utf-8")
    head_init_js = (ROOT / "static/js/runtime/layout-head-init.js").read_text(encoding="utf-8")

    # Shared badge fetch lives in deferred layout-shared.bundle.js (not inline HTML).
    assert "js/runtime/layout-shared.bundle.js" in layout_scripts
    assert "js/runtime/layout-scripts-chat.js" not in layout_scripts
    assert chat_js.count("/erp/api/notifications/badge") == 1
    assert "window.FOMSNotificationBadge" in chat_js
    assert "setInterval(loadNotificationBadge, 60000)" not in chat_js
    assert "js/runtime/layout-head-init.js" not in layout_head
    assert "js/runtime/layout-shared.bundle.js" in layout_scripts
    assert "refreshErpNotificationUI({ reason: 'socket-connect' });" in head_init_js
    assert "refreshErpNotificationUI({ force: true, reason: 'erp-notification' });" in head_init_js

    # Orders ERP dashboard: no inline `loadNotificationBadge(true);` — badge UI is wired from
    # `erp-dashboard-entry.js`, which loads `dashboard-notifications.js` (not a literal script
    # tag in HTML). Production/construction dashboards still inline two eager refreshes.
    expected_badge_refresh_calls = {
        "/erp/dashboard": 0,
        "/erp/construction/dashboard": 2,
        "/erp/production/dashboard": 2,
    }

    for path in ("/erp/dashboard", "/erp/construction/dashboard", "/erp/production/dashboard"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert body.count("loadNotificationBadge(true);") == expected_badge_refresh_calls[path]
        if path == "/erp/dashboard":
            assert "js/orders/erp-dashboard-entry.js" in body
