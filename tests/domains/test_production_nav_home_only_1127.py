"""옛 생산 보드 없애기 ③ 길 바꾸기(설계서 2026-11-27 옛 보드 없애기 §5-1 · §0-1 — 넘겨주기 없음).

* 어느 계정이든(관리자 · 보는 팀 · 팀 없는 직원 · 협력사 · 사용자 없음 · 켜진 프리랜서) 메뉴 '생산' · 주문 링크 · 레일 = 첫 화면.
* 돌아가기 열쇠 ``erp_production_dashboard`` 는 옛 링크에 실려 올 수 있어 글자만 받고 첫 화면 endpoint 로 보낸다 — 옛 보드
  endpoint 를 ``url_for`` 로 부르는 곳은 없다(④ 가 라우트를 지운다).
* 새 화면 템플릿 · 셸 JS · 협력사 거르기 목록(파이썬 · JS 둘)에 옛 보드 주소가 0.

켜진 프리랜서의 메뉴 항목(``freelancer_menu.py``)과 첫 화면에서 '내 주문만' 보는 것은 조각 ① 시험 몫이다. 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.production.home_access import PRODUCTION_HOME_PATH
from foms.services.production.nav_target import (
    PRODUCTION_HOME_ENDPOINT,
    production_nav_href,
    production_order_href,
    production_order_link,
)
from tests.support.production_access_support import PEOPLE, make_user, ns

ROOT = Path(__file__).resolve().parents[2]
OLD_BOARD_PATH = "/erp/production/dashboard"
OLD_BOARD_ENDPOINT = "erp_production_dashboard"
OLD_SHEET = ("erp_production_tablet_sheet", "/erp/production/tablet-sheet")

#: 누구든 — 보는 팀 표 전부 + 팀 없음 · 협력사 · 사용자 없음.
EVERYONE = [ns(role, team) for _n, role, team, _w, _v in PEOPLE] + [
    ns("STAFF", None),
    ns("STAFF", "PRODUCTION", partner_org_id=3),
    ns("PARTNER", None, partner_org_id=3),
    None,
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 메뉴 · 주문 링크 · 레일 = 첫 화면
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("user", EVERYONE, ids=lambda u: "none" if u is None else f"{u.role}-{u.team}-{u.partner_org_id}")
def test_어느_계정이든_메뉴_생산과_주문_링크는_첫_화면(user) -> None:
    from foms.services.foms_split_view import build_split_side_items, build_tablet_rail_items

    assert production_nav_href(user) == PRODUCTION_HOME_PATH
    assert production_order_link(12, user) == (PRODUCTION_HOME_ENDPOINT, {"order": 12})
    assert production_order_href(12, user) == f"{PRODUCTION_HOME_PATH}?order=12"
    for items in (build_tablet_rail_items(user, "/erp/shipment"), build_split_side_items(user)):
        hrefs = [it["href"] for it in items if it["id"] == "production"]
        assert hrefs in ([], [PRODUCTION_HOME_PATH]), hrefs  # 시공팀처럼 생산 칸이 없는 레일도 있다
        assert all(OLD_BOARD_PATH not in str(it["href"]) for it in items)


def test_켜진_프리랜서도_메뉴_생산과_주문_링크는_첫_화면(app) -> None:
    """예전엔 켜진 프리랜서만 옛 보드(``focus_order=``)로 갔다. 판정이 요청 안에서 설정을 읽던 갈래가 없어진 것을 요청 안에서 본다."""
    from flask import g

    from foms.services.erp_order_deeplink import build_order_queue_focus_href, resolve_edit_return_back_endpoint
    from foms.services.orders.board_state_display import build_board_state
    from foms.services.sales_commission.settings import load_settings, save_freelancer

    fl = make_user("nav1127_freelancer", "STAFF", "SALES")
    save_freelancer(db_session, fl.id, {"match_name": "가짜프리길", "start_month": "2020-01", "tax_type": "NONE",
                                        "active": True}, base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    person = ns("STAFF", "SALES")
    person.id = fl.id
    order = SimpleNamespace(id=31, erp_stage_code="PRODUCTION", status="PRODUCTION", structured_data={})
    with app.test_request_context("/"):
        g.current_user = person
        assert production_nav_href(person) == PRODUCTION_HOME_PATH
        assert production_order_href(31, person) == f"{PRODUCTION_HOME_PATH}?order=31"
        assert build_order_queue_focus_href(order, search_query="가짜") == f"{PRODUCTION_HOME_PATH}?order=31"
        assert resolve_edit_return_back_endpoint(OLD_BOARD_ENDPOINT) == PRODUCTION_HOME_ENDPOINT
        state = build_board_state(order, {}, "PRODUCTION")
        assert (state["link_endpoint"], state["link_params"]) == (PRODUCTION_HOME_ENDPOINT, {"order": 31})


# --------------------------------------------------------------------------- #
# 돌아가기 열쇠 — 옛 글자는 받고 첫 화면으로
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("user", EVERYONE, ids=lambda u: "none" if u is None else f"{u.role}-{u.team}-{u.partner_org_id}")
def test_돌아가기_열쇠_옛_보드_글자는_누구든_첫_화면(app, user) -> None:
    from flask import g

    from foms.services.erp_order_deeplink import build_order_queue_focus_href, resolve_edit_return_back_endpoint

    order = SimpleNamespace(id=8, erp_stage_code="PRODUCTION", status="PRODUCTION", structured_data={})
    with app.test_request_context("/"):
        g.current_user = user
        assert resolve_edit_return_back_endpoint(OLD_BOARD_ENDPOINT) == PRODUCTION_HOME_ENDPOINT
        assert build_order_queue_focus_href(order) == f"{PRODUCTION_HOME_PATH}?order=8"
        # 음성 대조 — 다른 열쇠 · 모르는 열쇠는 그대로
        assert resolve_edit_return_back_endpoint("erp_shipment_dashboard") == "erp_shipment_page.erp_shipment_dashboard"
        assert resolve_edit_return_back_endpoint("모르는열쇠") == "erp_dashboard.erp_dashboard"


def test_돌아가기_열쇠는_실제_endpoint_로_주소가_된다(app) -> None:
    from flask import url_for

    from foms.services.erp_order_deeplink import resolve_edit_return_back_endpoint

    with app.test_request_context("/"):
        assert url_for(resolve_edit_return_back_endpoint(OLD_BOARD_ENDPOINT)) == PRODUCTION_HOME_PATH


def test_길_모듈에_옛_보드_endpoint_부르기가_없다() -> None:
    """열쇠 글자(사전의 키)만 남고, 옛 보드 endpoint 를 값 · ``url_for`` 로 쓰는 곳은 없다 — ④ 가 endpoint 를 지워도 안 깨진다."""
    deeplink = _read("foms/services/erp_order_deeplink.py")
    assert deeplink.count(f'"{OLD_BOARD_ENDPOINT}"') == 1 and f'"{OLD_BOARD_ENDPOINT}": PRODUCTION_HOME_ENDPOINT' in deeplink
    assert f"erp_production_page.{OLD_BOARD_ENDPOINT}" not in deeplink and OLD_BOARD_PATH not in deeplink
    nav = _read("foms/services/production/nav_target.py")
    assert OLD_BOARD_ENDPOINT not in nav and OLD_BOARD_PATH not in nav and "focus_order" not in nav
    for rel in ("foms/services/production/nav_target.py", "foms/services/erp_order_deeplink.py",
                "foms/services/foms_split_view.py", "foms/services/orders/board_state_display.py"):
        assert not re.search(r"url_for\([^)]*erp_production_(dashboard|tablet_sheet)", _read(rel)), rel


# --------------------------------------------------------------------------- #
# 화면 · JS · 협력사 거르기 목록에 보드 주소 0
# --------------------------------------------------------------------------- #
#: 새 생산 화면(첫 화면 · 작업 시트 · 인쇄)과 공용 메뉴 템플릿 — 옛 보드 전용 템플릿(④ 가 지움)은 뺀다.
NEW_SCREEN_TEMPLATES = sorted(
    {p.relative_to(ROOT).as_posix() for p in (ROOT / "templates/production/partials").glob("home_*.html")}
    | {"templates/production/home.html", "templates/production/sheet.html", "templates/production/print_sheet.html",
       "templates/production/partials/notif_bell.html", "templates/production/partials/sheet_step_confirm.html",
       "templates/partials/shared/erp_sub_nav.html", "templates/partials/shared/erp_mobile_shell.html",
       "templates/partials/shared/layout_nav.html"})


@pytest.mark.parametrize("rel", NEW_SCREEN_TEMPLATES)
def test_새_화면_템플릿에_옛_보드_길이_없다(rel) -> None:
    src = _read(rel)
    for needle in (OLD_BOARD_PATH, OLD_BOARD_ENDPOINT, *OLD_SHEET, "data-foms-home-board", "fpc-board"):
        assert needle not in src, (rel, needle)


def test_PC_보드_링크_조각과_CSS_규칙이_없다() -> None:
    assert not (ROOT / "templates/production/partials/home_pc_board_link.html").exists()
    css = _read("static/css/contexts/production/pc.css")
    assert "fpc-board" not in css
    # 지운 규칙이 기기에 닿게 pc.css 를 싣는 두 곳 핀을 같이 올렸다
    for rel in ("templates/production/partials/home_styles.html", "templates/production/sheet.html"):
        assert "pc.css') }}?v=20261127h" in _read(rel), rel


def test_셸_JS에_옛_보드_하위_조각이_없다() -> None:
    js = _read("static/js/runtime/erp-shell.js")
    assert "LEGACY_SWAP_PATHS" not in js and OLD_BOARD_PATH not in js
    assert "js/runtime/erp-shell.js') }}?v=20261127h" in _read("templates/partials/shared/layout_scripts.html")


def test_협력사_거르기_목록_둘에_옛_보드가_없고_서로_같다() -> None:
    from foms.services.common.partner_order_filter import PARTNER_FILTER_PATHS

    assert OLD_BOARD_PATH not in PARTNER_FILTER_PATHS and PRODUCTION_HOME_PATH in PARTNER_FILTER_PATHS
    js = _read("static/js/foms/partner-order-filter.js")
    block = js.split("var paths = [", 1)[1].split("];", 1)[0]
    js_paths = set(re.findall(r"'([^']+)'", block))
    assert js_paths == set(PARTNER_FILTER_PATHS)  # 파이썬 · JS 사본이 어긋나지 않는다
    assert OLD_BOARD_PATH not in js


def test_화면에서_메뉴_생산은_첫_화면이고_옛_보드_주소가_없다(client) -> None:
    """실제 응답: 팀 없는 직원(예전엔 옛 보드로 가던 사람)과 CS(대조군) 모두 PC 둘째 줄 메뉴 '생산' = 첫 화면."""
    from tests.support.production_access_support import login

    pattern = r'<a class="erp-pro-nav-item[^"]*"\s+href="([^"]+)">\s*<i class="fas fa-industry">'
    for name, team in (("nav1127_noteam", None), ("nav1127_cs", "CS")):
        login(client, make_user(name, "STAFF", team))
        html = client.get("/erp/measurement").get_data(as_text=True)
        assert re.findall(pattern, html) == [PRODUCTION_HOME_PATH], team
        assert OLD_BOARD_PATH not in html, team
