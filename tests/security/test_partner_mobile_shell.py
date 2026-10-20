"""PARTNER-FOMS 4-1: 협력사 휴대폰 틀 — 우리 위 줄 · 아래 탭 5개 · 더보기 시트.

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.1 · §16.
"""
from __future__ import annotations

import re
from pathlib import Path

from db import db_session
from models import User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_confirm,
    world,
)

_TABS = re.compile(r'data-pp-nav="(\w+)"')


def _html(app, user_id, path) -> str:
    resp = _client(app, db_session.get(User, user_id)).get(path)
    assert resp.status_code == 200, path
    return resp.get_data(as_text=True)


def _active(html: str) -> list[str]:
    return re.findall(r'erp-mobile-bottom-nav__item is-active" href="[^"]*" data-pp-nav="(\w+)"', html)


def test_mobile_chrome_has_our_shell_parts_and_five_tabs(app, world):
    html = _html(app, world["partner_a"], "/partner")
    assert 'class="erp-mobile-shell pp-shell" data-erp-mobile-v2="true"' in html
    assert "erp-mobile-v2-layout" in html and "erp-mobile-shell-chrome" in html
    assert "erp-mobile-shell-header foms-shell-header" in html
    assert _TABS.findall(html) == ["orders", "turn", "new", "done"]
    assert 'data-pp-sheet-open="ppMoreSheet"' in html and 'id="ppMoreSheet"' in html  # 다섯째 = 더보기
    assert _active(html) == ["orders"]
    # PC 머리줄 · 메뉴 줄은 휴대폰에서 우리 규칙으로 숨는다.
    assert html.count("foms-shell-desktop-only") == 2
    # 알림 칸은 PC 와 휴대폰에 하나씩, 판은 공용 조각.
    assert html.count("data-pp-push-panel") == 2
    # 내부 메뉴 · 긴급 호출 · 검색은 싣지 않는다.
    for absent in ("erp-mobile-menu-drawer", "data-foms-urgent-open", "data-foms-search-open"):
        assert absent not in html


def test_active_tab_follows_screen(app, world):
    assert _active(_html(app, world["partner_a"], "/partner?turn=1")) == ["turn"]
    assert _active(_html(app, world["partner_a"], "/partner?stage=완료")) == ["done"]
    new = _html(app, world["partner_a"], "/partner/orders/new")
    assert _active(new) == ["new"]
    assert 'erp-mobile-shell-header__home foms-icon-btn" href="/partner"' in new
    assert "foms-shell-title\">새 주문<" in new


def test_order_screen_title_back_and_turn_badge(app, world):
    resp = _create(app, world["partner_a"])
    order_id = resp.get_json()["data"]["order_id"]
    _to_confirm(order_id)
    html = _html(app, world["partner_a"], f"/partner/orders/{order_id}")
    assert f'foms-shell-title">주문 #{order_id}<' in html
    assert 'erp-mobile-shell-header__home foms-icon-btn" href="/partner"' in html
    assert re.search(r'data-pp-nav="turn"[^>]*>.*?erp-mobile-bottom-nav__badge[^>]*>1<', html, re.S)
    home = _html(app, world["partner_a"], "/partner")
    assert "erp-mobile-shell-header__home" not in home  # 목록은 뒤로 단추 없음


def test_mobile_surfaces_pin_matches_staff_layout():
    staff = Path("templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    partner = Path("templates/partner/layout.html").read_text(encoding="utf-8")
    pin = re.search(r"foms-mobile-surfaces\.css'\) \}\}\?v=(\w+)", staff).group(1)
    assert f"foms-mobile-surfaces.css') }}}}?v={pin}" in partner
