from werkzeug.security import generate_password_hash

from db import db_session
from models import User


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
        assert body.count("/erp/api/notifications/badge") == 1
        assert "window.FOMSNotificationBadge" in body
        assert "setInterval(loadNotificationBadge, 60000)" not in body
        assert body.count("loadNotificationBadge(true);") == expected_badge_refresh_calls[path]
        if path == "/erp/dashboard":
            assert "js/orders/erp-dashboard-entry.js" in body
        assert "refreshErpNotificationUI({ reason: 'socket-connect' });" in body
        assert "refreshErpNotificationUI({ force: true, reason: 'erp-notification' });" in body
