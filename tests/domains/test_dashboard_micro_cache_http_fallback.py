"""DMC-B6: Redis 없이도 ERP dashboard 라우트가 캐시 우회로 200 응답."""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

from foms.services.common import dashboard_cache as dc


@pytest.fixture(autouse=True)
def _reset_cache_runtime():
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_erp_admin(client):
    user = User(
        username="dmc_b6_http_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="DMC B6 Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_erp_dashboard_measurement_shipment_200_without_redis_url(client, monkeypatch):
    """Flag on + REDIS_URL 없음 → bypass, 요청 실패 없음 (계획 fail-open)."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    for path in ("/erp/dashboard", "/erp/measurement", "/erp/shipment"):
        response = client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"
