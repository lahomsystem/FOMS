"""생산 화면 2단계 — 누가 보나 · 메뉴 · 바로가기(설계서 2026-11-21-production-pc-viewer §9 · §10 R1 · §11 · §13 결정 5).

* 보기(§9-1): 도면 · 시공 · 출고 팀도 첫 화면 · 작업 시트 200. 협력사 403.
* 메뉴 · 바로가기(§9-2~9-11): PC 둘째 줄 메뉴 · 폰 아래 메뉴 · 레일 · 9탭 계약 · 폰 알림 · 검색 · 주문 목록 · 돌아가기 열쇠 ·
  협력사 거르기 · 첫 화면 ``order=``. 옛 생산 보드는 2026-11-27 없앴다(옛 보드 없애기 설계서 §5-1) — 누구든 첫 화면으로 간다.
  팀 없는 직원 · 켜진 프리랜서가 첫 화면에서 무엇을 보는지는 각자 시험(test_production_teamless_view · test_freelancer_production_home).

모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.common import erp_navigation_contract as enc
from foms.services.datetime_kst import get_today_kst
from foms.services.production.home_access import PRODUCTION_HOME_PATH, can_view_production_home
from foms.services.production.nav_target import production_nav_href, production_order_href
from models import PartnerOrg
from tests.support.production_access_support import PEOPLE, login, make_order, make_user, ns

#: 옛 생산 보드 주소 — 어디에도 링크로 남지 않아야 한다(2026-11-27).
OLD_BOARD_PATH = "/erp/production/dashboard"


@pytest.mark.parametrize("name,role,team,write,view", PEOPLE)
def test_view_matrix(name, role, team, write, view):
    assert can_view_production_home(ns(role, team)) is view, name
    assert can_view_production_home(ns("PARTNER", team, partner_org_id=7)) is False, name


# --------------------------------------------------------------------------- #
# 보기 — 첫 화면 · 작업 시트
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("team", ["DRAWING", "CONSTRUCTION", "SHIPMENT", "CS", "SALES", "PRODUCTION"])
def test_view_teams_open_home_and_sheet(client, team):
    user = make_user(f"pv_{team.lower()}", "STAFF", team)
    login(client, user)
    order_id = make_order("가짜보기고객", construction=get_today_kst().isoformat()).id
    for tab in ("", "?tab=steps", "?tab=changes", "?tab=all"):
        assert client.get(PRODUCTION_HOME_PATH + tab).status_code == 200, (team, tab)
    assert client.get(f"/erp/production/sheet/{order_id}").status_code == 200, team


def test_teamless_staff_views_home_partner_and_other_team_cannot(client):
    """팀 없는 직원은 보기만(설계서 옛 생산 보드 없애기 §4, 2026-11-27 — 자세한 시험 test_production_teamless_view.py)."""
    user = make_user("pv_noteam", "STAFF", None)
    login(client, user)
    assert client.get(PRODUCTION_HOME_PATH).status_code == 200
    login(client, make_user("pv_other_team", "STAFF", "WAREHOUSE"))  # 목록 밖 팀 글자는 넓히지 않는다
    assert client.get(PRODUCTION_HOME_PATH).status_code == 403
    org = PartnerOrg(name="가짜협력사보기")
    db_session.add(org)
    db_session.commit()
    partner = make_user("pv_partner", "PARTNER", None, partner_org_id=org.id)
    login(client, partner)
    assert client.get(PRODUCTION_HOME_PATH).status_code != 200


# --------------------------------------------------------------------------- #
# 메뉴 · 바로가기 주소
# --------------------------------------------------------------------------- #
def test_nav_target_is_home_for_everyone():
    """옛 보드 없애기(2026-11-27 §5-1): 볼 수 있든 없든 · 사용자가 없든 메뉴 · 주문 링크는 첫 화면."""
    for _name, role, team, _write, _view in PEOPLE:
        assert production_nav_href(ns(role, team)) == PRODUCTION_HOME_PATH, (role, team)
        assert production_order_href(5, ns(role, team)) == f"{PRODUCTION_HOME_PATH}?order=5"
    assert production_nav_href(None) == PRODUCTION_HOME_PATH
    assert production_order_href(5, None) == f"{PRODUCTION_HOME_PATH}?order=5"


def test_nine_tab_contract_production_is_home():
    idx = enc.ERP_TAB_IDS.index("production")
    assert enc.ERP_PRIMARY_NAV_PATHS[idx] == PRODUCTION_HOME_PATH
    assert enc.ERP_FRAGMENT_READY_PATHS[idx] == PRODUCTION_HOME_PATH
    assert enc.ERP_PATH_TO_TAB_ID[PRODUCTION_HOME_PATH] == "production"
    assert OLD_BOARD_PATH not in enc.ERP_PRIMARY_NAV_PATHS


def _nav_production_hrefs(html: str) -> list[str]:
    import re

    return re.findall(r'<a class="erp-pro-nav-item[^"]*"\s+href="([^"]+)">\s*<i class="fas fa-industry">', html)


@pytest.mark.parametrize("team", ["CS", "SALES", "PRODUCTION", "DRAWING", "SHIPMENT", "CONSTRUCTION"])
def test_pc_sub_nav_production_points_to_home(client, team):
    """PC 둘째 줄 메뉴의 생산 = 첫 화면. 시공팀도 생산 칸이 있다(§13 결정 5)."""
    user = make_user(f"nav_{team.lower()}", "STAFF", team)
    login(client, user)
    html = client.get("/erp/shipment").get_data(as_text=True)
    assert _nav_production_hrefs(html) == [PRODUCTION_HOME_PATH], team


def test_pc_sub_nav_teamless_staff_points_to_home(client):
    """팀 없는 직원도 메뉴 '생산' = 첫 화면(옛 보드 없애기 §4 · §5-1 — 예전엔 옛 보드)."""
    user = make_user("nav_noteam", "STAFF", None)
    login(client, user)
    html = client.get("/erp/shipment").get_data(as_text=True)
    assert _nav_production_hrefs(html) == [PRODUCTION_HOME_PATH]
    assert OLD_BOARD_PATH not in html


def test_phone_menu_production_points_to_home(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = make_user("nav_phone_cs", "STAFF", "CS")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    login(client, user)
    html = client.get("/erp/shipment").get_data(as_text=True)
    assert f'href="{PRODUCTION_HOME_PATH}"' in html
    assert OLD_BOARD_PATH not in html


def test_push_deep_link_opens_changes_tab():
    from foms.services.notifications.push_sender import _deep_link
    from models import Notification

    notif = Notification(order_id=1, notification_type="PRODUCTION_ORDER_CHANGED", target_type="TEAM",
                         target_team="CS", title="t", message="m")
    assert _deep_link(notif) == "/erp/production/home?tab=changes"


def test_search_focus_link_and_return_key(app):
    from flask import g

    from foms.services.erp_order_deeplink import build_order_queue_focus_href, resolve_edit_return_back_endpoint

    order = SimpleNamespace(id=42, erp_stage_code="PRODUCTION", status="PRODUCTION", structured_data={})
    with app.test_request_context("/"):
        g.current_user = ns("STAFF", "DRAWING")
        assert build_order_queue_focus_href(order, search_query="가짜") == "/erp/production/home?order=42"
        assert resolve_edit_return_back_endpoint("erp_production_dashboard") == "erp_production_page.erp_production_home"
        # 첫 화면을 못 보던 사람(팀 없음)도 이제 첫 화면 — 옛 열쇠 글자는 받아서 첫 화면으로(2026-11-27)
        g.current_user = ns("STAFF", None)
        assert build_order_queue_focus_href(order, search_query="가짜") == "/erp/production/home?order=42"
        assert resolve_edit_return_back_endpoint("erp_production_dashboard") == "erp_production_page.erp_production_home"
        g.current_user = ns("STAFF", "WAREHOUSE")  # 목록 밖 팀 글자도 주소는 첫 화면(볼 수 있는지는 첫 화면 문지기가 본다)
        assert build_order_queue_focus_href(order, search_query="가짜") == "/erp/production/home?order=42"


def test_board_state_link_opens_production_home(app):
    from foms.services.orders.board_state_display import build_board_state

    order = SimpleNamespace(id=77)
    state = build_board_state(order, {}, "PRODUCTION", viewer=ns("STAFF", "CS"))
    assert state["link_label"] == "생산 화면 열기"
    assert (state["link_endpoint"], state["link_params"]) == ("erp_production_page.erp_production_home", {"order": 77})
    teamless = build_board_state(order, {}, "PRODUCTION", viewer=ns("STAFF", None))
    assert (teamless["link_endpoint"], teamless["link_params"]) == ("erp_production_page.erp_production_home", {"order": 77})


def test_partner_filter_applies_to_home():
    from foms.services.common.partner_order_filter import PARTNER_FILTER_PATHS

    assert PRODUCTION_HOME_PATH in PARTNER_FILTER_PATHS
    assert OLD_BOARD_PATH not in PARTNER_FILTER_PATHS


# --------------------------------------------------------------------------- #
# 첫 화면 order= — 그 주문의 날 장 · 줄 테두리
# --------------------------------------------------------------------------- #
def test_home_order_param_picks_that_day_and_outlines_row(client):
    user = make_user("focus_prod", "STAFF", "PRODUCTION")
    login(client, user)
    later = (get_today_kst() + timedelta(days=5)).isoformat()
    first = (get_today_kst() + timedelta(days=1)).isoformat()  # 처음 여는 장 = 내일(띠의 날 줄은 내일부터, 사장님 2026-11-25)
    make_order("가짜내일고객", construction=first)
    target = make_order("가짜닷새뒤고객", construction=later)
    plain = client.get(PRODUCTION_HOME_PATH).get_data(as_text=True)
    assert f'data-foms-home-daypane="{first}"' in plain and "is-focus" not in plain
    for param in ("order", "focus_order"):
        html = client.get(f"{PRODUCTION_HOME_PATH}?{param}={target.id}").get_data(as_text=True)
        assert f'data-foms-home-daypane="{later}"' in html, param
        assert "is-focus" in html, param
    # 고른 날(day=)이 있으면 그 날이 이긴다
    html = client.get(f"{PRODUCTION_HOME_PATH}?order={target.id}&day={first}").get_data(as_text=True)
    assert f'data-foms-home-daypane="{first}"' in html


def test_home_days_focus_unknown_order_keeps_auto():
    from foms.services.production_home_days import production_home_days

    today = date(2026, 11, 23)
    rows = [{"id": 1, "construction_date": "2026-11-25", "home_view": "prod", "home_stage": "제작 대기", "home_steps": []}]
    days = production_home_days(rows, today, None, focus_order=999)
    assert days["auto"] is True and days["focus"] is None
    days = production_home_days(rows, today, None, focus_order=1)
    assert days["selected"] == "2026-11-25" and days["auto"] is False and days["focus"] == 1
    assert rows[0]["home_focus"] is True


# --------------------------------------------------------------------------- #
# 켜진 프리랜서 — 메뉴 · 주문 링크도 첫 화면(2026-11-27 옛 보드 없애기 §5-1). 첫 화면에서 '내 주문만' 보는 것과
# 문지기는 tests/security/test_freelancer_production_home.py 몫이다.
# --------------------------------------------------------------------------- #
def test_enabled_freelancer_nav_is_home(app, client):
    from flask import g

    from foms.services.sales_commission.settings import load_settings, save_freelancer

    fl = make_user("pv_freelancer", "STAFF", "SALES")
    save_freelancer(db_session, fl.id, {"match_name": "가짜프리생산", "start_month": "2020-01", "tax_type": "NONE",
                                        "active": True}, base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    person = ns("STAFF", "SALES")
    person.id = fl.id
    with app.test_request_context("/"):
        g.current_user = person
        assert production_nav_href(person) == PRODUCTION_HOME_PATH
        assert production_order_href(9, person) == f"{PRODUCTION_HOME_PATH}?order=9"
    login(client, fl)
    order_id = make_order().id
    assert client.post(f"/api/orders/{order_id}/production/start", json={}).status_code in (403, 404)
