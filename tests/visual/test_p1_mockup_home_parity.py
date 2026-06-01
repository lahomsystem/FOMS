"""P1 §6.2 home dashboard parity — app-like queue, no chip rows, chunk endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]


def _login_admin(client) -> User:
    user = User(
        username="p1_home_parity_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="홈 Parity Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_home_mobile_v2_body_removes_chip_rows() -> None:
    """Dashboard mobile v2 no longer exposes filter/sort chip strips."""
    body = (ROOT / "templates/orders/partials/dashboard_mobile_v2_body.html").read_text(encoding="utf-8")
    filter_sheet = (ROOT / "templates/orders/partials/dashboard_mobile_filter_sheet.html").read_text(encoding="utf-8")
    for token in ("foms-mobile-queue-list", "data-foms-mobile-queue-scroll", "foms-shell-fab"):
        assert token in body
    for token in ("data-foms-mobile-filter-open", "foms-mobile-filter-sheet", 'name="sort"'):
        assert token in filter_sheet
    for removed in ("오늘 (", "담당:", "foms-chip-strip", 'aria-label="정렬"'):
        assert removed not in body


def test_home_mobile_v2_chunk_partial_exists() -> None:
    """Infinite scroll chunk partial is separated for mobile_chunk=1."""
    chunk = (ROOT / "templates/orders/partials/dashboard_mobile_v2_chunk.html").read_text(encoding="utf-8")
    assert "data-foms-mobile-queue-chunk" in chunk


def test_dashboard_mobile_chunk_endpoint(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mobile_chunk=1 returns queue chunk HTML only."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/dashboard?mobile_chunk=1&page=1")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "data-foms-mobile-queue-chunk" in html
    assert "foms-mobile-v2-dashboard" not in html


def test_dashboard_today_filter_query_still_loads_without_chips(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy today=1 query remains accepted even though chips are removed."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/dashboard?today=1")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "foms-mobile-v2-dashboard" in html
    assert 'aria-label="필터"' not in html
