"""FCOMM-01 3단계 겹 5 메뉴: 켜진 프리랜서에게는 문지기 허용 목록 안 메뉴만 보인다 (플랜 T17 B).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 겹 5(메뉴) · §6.5.

* 폰 아래 탭 · "더보기" 서랍 · 태블릿 레일 · PC 위 메뉴 · 사용자 메뉴 · ERP 서브 내비를 실제 화면으로 그려, 그 안의
  **모든** 링크(href)와 폼(action)의 endpoint 가 허용 목록 안이고 그 방법이 열려 있는지 본다.
* 음성 대조군: 같은 검사기를 프리랜서 아닌 영업 직원 화면에 돌리면 허용 목록 밖 링크를 찾아야 한다(검사기가 살아 있다).
* 막힌 문으로 가는 머리 단추(통합 검색 · 협력사 거르기)와 실측 판 지도 · 이력 검색 링크는 숨긴다. 셸 미리 받기는
  내 메뉴 화면만 받는다(스테이징 QA 결함 2 · 3).
* 프리랜서 아닌 영업 직원 · 관리자 화면은 그대로다 — 늘 보던 항목이 그대로 있다. (바이트 단위 비교는 작업 때 바꾸기 전 ·
  뒤 화면 30개로 했다. 시험에는 항목 목록으로 남긴다 — 다른 작업이 화면을 바꿔도 이 시험이 깨지지 않게.)
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from flask import g, url_for

from foms.services.auth.freelancer_menu import FREELANCER_MENU
from foms.services.auth.freelancer_scope import FREELANCER_ALLOWED_ENDPOINTS, is_freelancer_request_allowed
from foms.services.foms_split_view import build_split_side_items
from tests.domains.test_auth_finance import _login, _make_user
from tests.security.test_freelancer_edit_guards import _freelancer

_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
_PAGES = ("/erp/dashboard", "/erp/measurement")
_STAGE_LABELS = ["대시보드", "실측", "도면", "생산", "출고", "AS", "시공", "완료", "이력"]
#: D27 — 프리랜서 메뉴는 문지기가 여는 화면만(판 화면 묶음이 열리면 저절로 나타난다).
_FL_MENU = [(item_id, label) for item_id, label, endpoint, _icon in FREELANCER_MENU
            if endpoint in FREELANCER_ALLOWED_ENDPOINTS]
_FL_IDS = [item_id for item_id, _label in _FL_MENU]
_FL_LABELS = [label for _item_id, label in _FL_MENU]


# --------------------------------------------------------------------------
# 그리기 · 자르기
# --------------------------------------------------------------------------
def _render(app, monkeypatch, user, path: str, *, mobile: bool) -> str:
    if mobile:
        monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
        monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    else:
        monkeypatch.delenv("ERP_MOBILE_V2_ENABLED", raising=False)
        monkeypatch.delenv("FOMS_V3_SHELL_COHORT", raising=False)
    client = app.test_client()
    _login(client, user)
    resp = client.get(path, headers={"User-Agent": _MOBILE_UA} if mobile else {})
    assert resp.status_code == 200, (path, resp.status_code)
    return resp.get_data(as_text=True)


def _cut(html: str, start: str, end: str) -> str:
    """``start`` 가 처음 나오는 곳부터 그 뒤 첫 ``end`` 까지. 없으면 빈 글."""
    i = html.find(start)
    if i < 0:
        return ""
    j = html.find(end, i)
    return html[i:j + len(end)] if j >= 0 else html[i:]


def _drawer(html: str) -> str:
    i = html.find('id="erp-mobile-menu-drawer"')
    if i < 0:
        return ""
    j = html.find("</nav>", html.find("erp-mobile-menu-drawer__account-links", i))
    return html[i:j + len("</nav>")]


def _mobile_regions(html: str) -> dict[str, str]:
    return {
        "bottom_nav": _cut(html, '<nav class="erp-mobile-bottom-nav"', "</nav>"),
        "drawer": _drawer(html),
        "tablet_rail": _cut(html, '<nav class="foms-tablet-rail"', "</nav>"),
    }


def _desktop_regions(html: str) -> dict[str, str]:
    return {
        "global_nav": _cut(html, '<nav class="layout-global-nav', "</nav>"),
        "user_menu": _cut(html, 'aria-labelledby="userDropdown"', "</ul>"),
        "erp_sub_nav": _cut(html, '<nav class="erp-pro-nav"', "</nav>"),
    }


def _targets(region: str) -> list[tuple[str, str]]:
    """(방법, 경로) — 링크는 GET, 폼은 POST. 화면 안 이동(#) · 스크립트 링크는 뺀다."""
    out = [("GET", h) for h in re.findall(r'\shref="([^"]*)"', region)]
    out += [("POST", a) for a in re.findall(r'<form[^>]*\saction="([^"]*)"', region)]
    return [(m, html_lib.unescape(p)) for m, p in out if p and not p.startswith(("#", "javascript:"))]


def _outside_allowlist(app, regions: dict[str, str]) -> list[tuple[str, str, str, str]]:
    adapter = app.url_map.bind("localhost")
    bad = []
    for name, region in regions.items():
        for method, target in _targets(region):
            try:
                endpoint, _args = adapter.match(urlsplit(target).path, method=method)
            except Exception:  # noqa: BLE001 — 없는 주소도 "허용 밖"으로 센다
                endpoint = None
            if not is_freelancer_request_allowed(endpoint, method):
                bad.append((name, method, target, str(endpoint)))
    return bad


def _labels(region: str, cls: str) -> list[str]:
    return re.findall(rf'<span class="{cls}">([^<]+)</span>', region)


# --------------------------------------------------------------------------
# 프리랜서 — 허용 목록 안 링크만
# --------------------------------------------------------------------------
def test_menu_catalog_keeps_base_items_and_only_shows_allowed():
    assert {"dashboard", "measurement", "my_commission"} <= set(_FL_IDS)
    assert _FL_IDS[0] == "dashboard" and _FL_IDS[-1] == "my_commission"


@pytest.mark.parametrize("path", [*_PAGES, "/erp/my-commission"])
def test_freelancer_mobile_menus_only_link_allowed_endpoints(app, monkeypatch, path):
    fl = _freelancer()
    regions = _mobile_regions(_render(app, monkeypatch, fl, path, mobile=True))
    assert regions["bottom_nav"] and regions["drawer"], "폰 셸이 안 그려졌다"
    assert _outside_allowlist(app, regions) == []
    # 아래 탭(D30): 회사 영업과 같은 탭 + 내 수수료 · 계산기 · 더보기.
    assert re.findall(r'data-foms-nav-id="(\w+)"', regions["bottom_nav"]) == [
        "dashboard", "measurement", "drawing_workbench", "shipment", "my_commission"]
    assert "계산기" in regions["bottom_nav"] and "더보기" in regions["bottom_nav"]
    # 서랍: 문지기가 여는 판 화면(PC 메뉴와 같은 셋, 계산기는 탭에) + 내 정보 · 공지사항 · 로그아웃. 네이버 수집 없음.
    assert _labels(regions["drawer"], "erp-mobile-menu-drawer__label") == [
        label for label in _FL_LABELS if label != "견적 계산기"]
    assert _labels(regions["drawer"], "erp-mobile-menu-drawer__label") == [*_STAGE_LABELS, "내 수수료"]
    assert "네이버 수집" not in regions["drawer"]
    assert re.findall(r"<span>([^<]+)</span>", _cut(regions["drawer"], "erp-mobile-menu-drawer__account-links", "</nav>")) \
        == ["내 정보", "공지사항", "로그아웃"]
    # 태블릿 레일(/erp 전 화면): PC 메뉴와 같은 셋(견적 계산기 포함) + 알림.
    assert _labels(regions["tablet_rail"], "foms-tablet-rail__label") == [*_FL_LABELS, "알림"]


@pytest.mark.parametrize("path", _PAGES)
def test_freelancer_desktop_menus_only_link_allowed_endpoints(app, monkeypatch, path):
    fl = _freelancer()
    regions = _desktop_regions(_render(app, monkeypatch, fl, path, mobile=False))
    assert all(regions.values()), [k for k, v in regions.items() if not v]
    assert _outside_allowlist(app, regions) == []
    # 링크 글로 본다(주석에도 "WDCalculator" · "채팅" 이 있다)
    for absent in ("</i> WDCalculator", "</i> 채팅", "네이버 수집", "휴지통", "전체 주문"):
        assert absent not in regions["global_nav"], absent
    assert "내 변경 로그" not in regions["user_menu"]
    assert 'href="/profile"' in regions["user_menu"] and "공지사항" in regions["user_menu"]
    assert re.findall(r"<span>([^<]+)</span>", regions["erp_sub_nav"]) == _FL_LABELS


def test_tablet_rail_items_for_freelancer(app, monkeypatch):
    """태블릿 레일(build_split_side_items)도 PC 메뉴와 같은 셋."""
    fl = _freelancer()
    with app.test_request_context("/erp/measurement"):
        g.current_user = fl
        items = build_split_side_items(fl, active_id="measurement")
    assert [i["id"] for i in items] == _FL_IDS
    assert [i["id"] for i in items if i["active"]] == ["measurement"]


# --------------------------------------------------------------------------
# 대조군 — 프리랜서 아닌 계정은 늘 보던 그대로
# --------------------------------------------------------------------------
def test_checker_finds_blocked_links_for_normal_sales(app, monkeypatch):
    """음성 대조군: 보통 영업 직원 화면에는 허용 목록 밖 링크가 있다 — 검사기가 실제로 잡는다."""
    _freelancer()
    user = _make_user("STAFF", "SALES")
    mobile = _outside_allowlist(app, _mobile_regions(_render(app, monkeypatch, user, "/erp/dashboard", mobile=True)))
    desktop = _outside_allowlist(app, _desktop_regions(_render(app, monkeypatch, user, "/erp/dashboard", mobile=False)))
    # D27 로 판 화면이 열리며 아래 탭의 링크는 모두 허용 목록 안이 됐다 — 서랍(네이버 수집 등)은 아직 밖이다.
    assert "drawer" in {name for name, *_ in mobile}
    assert {"global_nav", "user_menu"} <= {name for name, *_ in desktop}  # ERP 서브 내비는 D27 로 모두 열림


def test_normal_sales_mobile_menus_unchanged(app, monkeypatch):
    _freelancer()  # 설정 줄이 있어도 지정되지 않은 사람은 그대로
    user = _make_user("STAFF", "SALES")
    regions = _mobile_regions(_render(app, monkeypatch, user, "/erp/dashboard", mobile=True))
    assert re.findall(r'data-foms-nav-id="(\w+)"', regions["bottom_nav"]) == [
        "dashboard", "measurement", "drawing_workbench", "shipment"]
    assert "계산기" in regions["bottom_nav"] and "더보기" in regions["bottom_nav"]
    assert _labels(regions["drawer"], "erp-mobile-menu-drawer__label") == [*_STAGE_LABELS, "네이버 수집"]
    assert "my-commission" not in regions["drawer"]
    assert _labels(regions["tablet_rail"], "foms-tablet-rail__label") == [*_STAGE_LABELS, "계산기", "알림"]


@pytest.mark.parametrize("role,team", [("STAFF", "SALES"), ("ADMIN", None)])
def test_normal_desktop_menus_unchanged(app, monkeypatch, role, team):
    _freelancer()
    user = _make_user(role, team)
    regions = _desktop_regions(_render(app, monkeypatch, user, "/erp/dashboard", mobile=False))
    for present in ("</i> WDCalculator", "</i> 채팅", "</i> ERP 대시보드", "전체 주문"):
        assert present in regions["global_nav"], present
    assert "내 변경 로그" in regions["user_menu"]
    sub = re.findall(r"<span>([^<]+)</span>", regions["erp_sub_nav"])
    assert sub[:4] == ["대시보드", "실측", "도면작업실", "생산"] and sub[-1] == "과거 이력 검색"
    assert "내 수수료" not in sub


# --------------------------------------------------------------------------
# 머리 단추 · 실측 판 링크 — 막힌 문으로 가는 것은 숨긴다(스테이징 QA 결함 2)
# --------------------------------------------------------------------------
# (표식, 이름) — 통합 검색(단추 · 검색 창, 입력이 /api/foms/search/fragment 를 부른다), 협력사 거르기
# (폰 단추 · PC 목록 — 협력사 이름이 실린다), 실측 판 지도(PC · 폰 칩 · 태블릿 — 지도 화면으로 넘긴다),
# 실측 판 "모든 날짜에서 찾기"(이력 검색).
_HIDDEN_FOR_FREELANCER = (
    ("data-foms-search-open", "폰 통합 검색 단추"),
    ('id="foms-search-overlay"', "통합 검색 창"),
    ("data-foms-partner-open", "폰 협력사 거르기 단추"),
    ("global-partner-filter-btn", "PC 협력사 거르기 목록"),
    ("open_map=1", "실측 판 지도 링크"),
    ("foms-tablet-measure-list__map", "태블릿 실측 지도 단추"),
    ("모든 날짜에서 찾기", "실측 판 이력 검색 링크"),
)
_MEASURE_SEARCH = "/erp/measurement?q=x"


@pytest.mark.parametrize("mobile", [True, False])
@pytest.mark.parametrize("path", ["/erp/dashboard", _MEASURE_SEARCH])
def test_freelancer_hides_blocked_header_buttons(app, monkeypatch, path, mobile):
    html = _render(app, monkeypatch, _freelancer(), path, mobile=mobile)
    assert [name for marker, name in _HIDDEN_FOR_FREELANCER if marker in html] == []
    # 남는 것: 긴급 호출 · 알림(허용 목록 안)
    assert "data-foms-urgent-open" in html and "data-foms-notif-open" in html


def test_normal_sales_keeps_header_buttons(app, monkeypatch):
    """대조군: 프리랜서 아닌 영업 직원 화면에는 전부 그대로 있다(바꾸기 전 · 뒤 바이트 비교는 작업 때 18화면으로 했다)."""
    _freelancer()
    user = _make_user("STAFF", "SALES")
    mobile = _render(app, monkeypatch, user, _MEASURE_SEARCH, mobile=True)
    desktop = _render(app, monkeypatch, user, _MEASURE_SEARCH, mobile=False)
    assert [name for marker, name in _HIDDEN_FOR_FREELANCER if marker not in mobile] == []
    assert "global-partner-filter-btn" in desktop and "open_map=1" in desktop


# --------------------------------------------------------------------------
# 실측 판 담당자 거르기 — 실측 담당자 명단(직원 이름)은 프리랜서에게 안 보인다(스테이징 T18 남은 것 3)
# --------------------------------------------------------------------------
_FAKE_MEASURER = "가짜실측담당명단"


def _seed_measurer_roster(monkeypatch) -> None:
    import foms.web.measurement.dashboard as measurement_dashboard
    from foms.services.erp_shipment_settings import load_erp_shipment_settings

    def _with_roster():
        settings = dict(load_erp_shipment_settings())
        settings["measurement_manager"] = [{"name": _FAKE_MEASURER, "sort_order": 1}]
        return settings

    monkeypatch.setattr(measurement_dashboard, "load_erp_shipment_settings", _with_roster)


def test_freelancer_measurement_board_hides_manager_roster(app, monkeypatch):
    _seed_measurer_roster(monkeypatch)
    html = _render(app, monkeypatch, _freelancer(), "/erp/measurement", mobile=False)
    assert 'name="manager_filter"' not in html
    assert _FAKE_MEASURER not in html
    assert 'name="date_from"' in html  # 같은 거르기 줄의 나머지는 그대로(빈 화면으로 통과하는 것이 아니다)


@pytest.mark.parametrize("role,team", [("STAFF", "SALES"), ("ADMIN", None)])
def test_staff_measurement_board_keeps_manager_roster(app, monkeypatch, role, team):
    """대조군: 프리랜서 아닌 영업 직원 · 관리자는 담당자 거르기와 명단을 그대로 본다."""
    _freelancer()
    _seed_measurer_roster(monkeypatch)
    html = _render(app, monkeypatch, _make_user(role, team), "/erp/measurement", mobile=False)
    assert 'name="manager_filter"' in html
    assert f'<option value="{_FAKE_MEASURER}" >{_FAKE_MEASURER}</option>' in html


# --------------------------------------------------------------------------
# 셸 미리 받기 — 내 메뉴 화면만(스테이징 QA 결함 3)
# --------------------------------------------------------------------------
_PREFETCH_ATTR = re.compile(r'erp-shell\.js\?v=[^"]+" data-foms-prefetch-allow="([^"]*)" defer')
_SIM_JS = Path(__file__).resolve().parents[2] / "tests" / "support" / "erp_shell_heartbeat_schedule_node_checks.js"


def _simulate_prefetch(allow: str | None, current: list[str]) -> list[dict]:
    """erp-shell.js 를 가짜 창 · 가짜 시계로 한 시간 돌려 미리 받은 경로를 센다(하트비트 시험과 같은 도구)."""
    node = shutil.which("node")
    assert node, "node must be on PATH"
    env = {**os.environ, "FOMS_SIM_CURRENT": ",".join(current)}
    env.pop("FOMS_SIM_PREFETCH_ALLOW", None)
    if allow is not None:
        env["FOMS_SIM_PREFETCH_ALLOW"] = allow
    proc = subprocess.run([node, str(_SIM_JS)], capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("mobile", [True, False])
def test_freelancer_prefetch_allow_lists_own_menu(app, monkeypatch, mobile):
    html = _render(app, monkeypatch, _freelancer(), "/erp/dashboard", mobile=mobile)
    with app.test_request_context("/"):
        expected = " ".join(url_for(endpoint) for item_id, _label, endpoint, _icon in FREELANCER_MENU if item_id in _FL_IDS)
    assert _PREFETCH_ATTR.findall(html) == [expected]
    assert "/erp/my-commission" in expected and "/erp/settlement" not in expected


@pytest.mark.parametrize("role,team", [("STAFF", "SALES"), ("ADMIN", None)])
def test_normal_staff_prefetch_unrestricted(app, monkeypatch, role, team):
    _freelancer()
    html = _render(app, monkeypatch, _make_user(role, team), "/erp/dashboard", mobile=False)
    assert "data-foms-prefetch-allow" not in html
    assert "js/runtime/erp-shell.js?v=" in html


def test_shell_prefetches_only_allowed_paths():
    """켜진 프리랜서 목록이면 도면 · 생산 · 출고 … 를 한 번도 받지 않는다. 목록이 없으면(보통 직원) 아홉 탭을 다 받는다."""
    allow = "/erp/dashboard /erp/measurement /erp/my-commission"
    for run in _simulate_prefetch(allow, ["/erp/dashboard", "/erp/my-commission"]):
        assert set(run["perPath"]) <= {"/erp/dashboard", "/erp/measurement"}, run
        assert run["perPath"].get("/erp/measurement"), run  # 허용 경로는 계속 미리 받는다
    staff = _simulate_prefetch(None, ["/erp/dashboard"])[0]["perPath"]
    assert {"/erp/drawing-workbench", "/erp/production/dashboard", "/erp/shipment", "/erp/history/"} <= set(staff)
