"""생산팀 계정 태블릿 왼쪽 세로 메뉴 = 도면 · 생산 · 출고 · AS · 시공 다섯(사장님 2026-11-27).

폰 아래 메뉴 · 더보기 · PC 메뉴 · 다른 팀 · 관리자는 그대로. 빠진 화면은 주소로 직접 열린다.
"""

from __future__ import annotations

import re

from tests.domains.test_production_multi_parts import _get, _tablet, _user, cohort  # noqa: F401
from tests.support.production_part_claim_seed import login

FIVE = ["도면", "생산", "출고", "AS", "시공"]
FULL = ["대시보드", "실측", "도면", "생산", "출고", "AS", "시공", "완료", "이력", "계산기"]


def _rail_titles(html: str) -> list[str]:
    rail = html[html.index('<nav class="foms-tablet-rail"'):]
    menu = rail.split('<div class="foms-tablet-rail__menu">', 1)[1].split("</div>", 1)[0]
    return re.findall(r'<a\s+class="foms-tablet-rail__item[^"]*"[^>]*?title="([^"]+)"', menu, flags=re.S)


def _bottom_labels(html: str) -> list[str]:
    nav = html.split('<nav class="erp-mobile-bottom-nav"', 1)[1].split("</nav>", 1)[0]
    return re.findall(r"<span>([^<]+)</span>", nav)


def _drawer_labels(html: str) -> list[str]:
    drawer = html.split('id="erp-mobile-menu-drawer"', 1)[1]
    return re.findall(r'erp-mobile-menu-drawer__label">([^<]+)<', drawer)


def _phone(client, who) -> None:
    login(client, who)
    client.set_cookie("foms_scr", "844", domain="localhost")


def test_생산팀_태블릿_레일은_다섯만_차례대로(client, cohort):  # noqa: F811
    _tablet(client, _user("김재단"))
    assert _rail_titles(_get(client, "/erp/production/home")) == FIVE


def test_빠진_화면에_들어가_있어도_레일은_다섯_강조_없음(client, cohort):  # noqa: F811
    _tablet(client, _user("김재단"))
    html = _get(client, "/erp/dashboard")
    assert _rail_titles(html) == FIVE
    rail = html[html.index('<nav class="foms-tablet-rail"'):].split("</nav>", 1)[0]
    assert "is-active" not in rail.split('foms-tablet-rail__spacer', 1)[0]
    # 대조군: 있는 칸 화면이면 그 칸이 강조
    ship = _get(client, "/erp/shipment")
    assert re.search(r'foms-tablet-rail__item is-active"[^>]*?title="출고"', ship, flags=re.S)


def test_빠진_화면도_주소로_열린다(client, cohort):  # noqa: F811
    _tablet(client, _user("김재단"))
    for path in ("/erp/dashboard", "/erp/measurement", "/erp/completion", "/erp/history"):
        resp = client.get(path, follow_redirects=True)
        assert resp.status_code == 200, (path, resp.status_code)


def test_다른_팀과_관리자_레일은_그대로(client, cohort):  # noqa: F811
    for who in (_user("영업", team="SALES"), _user("관리자", team="CS", role="ADMIN"),
                _user("협력", team="PRODUCTION", role="ADMIN")):
        _tablet(client, who)
        assert _rail_titles(_get(client, "/erp/shipment")) == FULL, who


def test_폰_아래_메뉴와_더보기는_그대로(client, cohort):  # noqa: F811
    _phone(client, _user("김재단"))
    html = _get(client, "/erp/shipment")
    assert _bottom_labels(html)[:4] == ["생산", "출고", "시공", "대시보드"]
    assert _drawer_labels(html)[:9] == ["대시보드", "실측", "도면", "생산", "출고", "AS", "시공", "완료", "이력"]
