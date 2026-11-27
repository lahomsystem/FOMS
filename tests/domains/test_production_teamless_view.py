"""팀 없는 직원 계정 — 생산 첫 화면을 **보기만**(설계서 옛 생산 보드 없애기 §4 · §7-3, 사장님 2026-11-27 "새 화면을 보기만 열어 주기").

* 팀 값이 빈(``None`` · 빈 글 · 공백) 직원: 첫 화면 탭 다섯 · 작업 시트 · 인쇄 200, 생산 쓰기 여덟 403, [확인했어요](change-ack) 403,
  응답에 쓰기 · 확인 표식 0. 메뉴 '생산' 주소는 첫 화면을 볼 수 있는 곳(주소 글은 길 바꾸기 조각이 정한다 — 여기서는 고정하지 않는다).
* 음성 대조: 협력사는 못 본다 · 팀 있는 CS 는 [확인했어요]가 있다 · 관리자(팀 없음)는 지금처럼 전부 된다 · 목록 밖 팀 글자는 못 본다.

모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import datetime
import re
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.production.home_access import (
    PRODUCTION_HOME_PATH,
    can_view_production_home,
    can_view_production_home_as_team,
)
from foms.services.production.part_access import part_view_mode
from foms.services.production.write_access import can_ack_production_change, can_write_production
from models import OrderEvent, PartnerOrg
from tests.domains.test_production_home_changes import _date_changed
from tests.domains.test_production_home_changes import _order as _changed_order
from tests.support.production_access_support import ACK_PATH, WRITE_ENDPOINTS, login, make_user
from tests.support.production_home_step_panel_seed import add_order, set_cookies

PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
TABLET = {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "800"}
#: 첫 화면 탭 다섯 — 날짜(첫 화면) · 남은 공정 · 바뀐 것 · 찾기 · 도면 카드(태블릿 판, 그 밖 기기는 날짜로 돌아감)
TABS = ("", "?tab=steps", "?tab=changes", "?tab=all", "?tab=parts")
#: 쓰기 표식 — 공정 [끝] · 작업 시트 단추 · 판 [끝] · 시트 공정 칸 · [불량]
WRITE_MARKS = ("data-tablet-sheet-action", "data-foms-home-step-done", "data-foms-step-finish", "data-foms-sheet-step=",
               "data-foms-sheet-defect-toggle")
ACK_MARK = 'data-kanban-action="change-ack"'
TEAMLESS = (None, "", "   ")


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _ns(role: str, team, *, partner_org_id=None):
    return SimpleNamespace(id=990002, role=role, team=team, partner_org_id=partner_org_id, is_active=True,
                           name="가짜", production_part=None, production_lead=None)


def _seed() -> SimpleNamespace:
    """도면 1장 재단 중(내일) 주문 · 시공일이 바뀐 주문(바뀐 것 탭에 [확인했어요] 줄이 생긴다)."""
    cut = add_order("가짜팀없음재단", 1, pngs=1)
    changed = _changed_order("PRODUCTION", "가짜팀없음바뀜", 4, run=True)
    _date_changed(changed, datetime.timedelta(hours=2), None)
    return SimpleNamespace(cut=cut.id, changed=changed.id)  # 번호만(요청이 끝나면 세션이 닫혀 ORM 객체는 못 읽는다)


def _pages(client, seed) -> dict[str, str]:
    pages = {}
    for tab in TABS:
        resp = client.get(PRODUCTION_HOME_PATH + tab)
        assert resp.status_code == 200, (tab, resp.status_code)
        pages[tab or "date"] = resp.get_data(as_text=True)
    for kind in ("sheet", "print"):
        for name, order_id in (("cut", seed.cut), ("changed", seed.changed)):
            resp = client.get(f"/erp/production/{kind}/{order_id}")
            assert resp.status_code == 200, (kind, name, resp.status_code)
            pages[f"{kind}:{name}"] = resp.get_data(as_text=True)
    return pages


def _ack_events(order_id: int) -> int:
    return db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_CHANGE_ACK").count()


# --------------------------------------------------------------------------- #
# 1. 판정 — 보기는 열고 쓰기 · 확인은 닫는다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("team", TEAMLESS)
@pytest.mark.parametrize("role", ["STAFF", "MANAGER"])
def test_teamless_staff_view_only_rules(role, team):
    person = _ns(role, team)
    assert can_view_production_home(person) is True
    assert can_view_production_home_as_team(person) is False
    assert can_write_production(person) is False
    assert can_ack_production_change(person) is False
    assert part_view_mode(person) == "readonly"  # 도면 카드 판은 CS · 영업처럼 보기만(§0-1 의 4)
    # 파트 · 반장 칸이 (옛 값으로) 남아 있어도 생산팀이 아니면 파트 쓰기 모드가 되지 않는다
    person.production_part, person.production_parts, person.production_lead = "cut", ["cut"], True
    assert part_view_mode(person) == "readonly"
    assert can_write_production(person) is False


def test_negative_controls_rules():
    # 협력사(팀 없음 · 팀 있음 모두) · 역할이 협력사인 계정 · 목록 밖 팀 글자 · 로그인 없음은 못 본다
    for person in (_ns("PARTNER", None, partner_org_id=7), _ns("STAFF", None, partner_org_id=7),
                   _ns("PARTNER", None), _ns("STAFF", "WAREHOUSE"), _ns("MANAGER", "UNKNOWN")):
        assert can_view_production_home(person) is False, person
        assert can_ack_production_change(person) is False, person
    assert can_view_production_home(None) is False
    # 관리자(팀 없음)는 지금처럼 보기 · 쓰기 · 확인 모두
    admin = _ns("ADMIN", None)
    assert can_view_production_home(admin) and can_write_production(admin) and can_ack_production_change(admin)
    # 지금 사람들의 확인 답은 그대로(관리자 · CS · 회계 별칭 · 영업 · 실측 별칭 · 생산 · 도면 · 시공 · 출고 = 참)
    for team in ("CS", "ACCOUNTING", "SALES", "MEASURE", "PRODUCTION", "DRAWING", "CONSTRUCTION", "SHIPMENT"):
        assert can_ack_production_change(_ns("STAFF", team)) is True, team
        assert can_view_production_home(_ns("STAFF", team)) is True, team


def test_active_freelancer_keeps_ack_like_company_sales(app):
    """켜진 프리랜서는 팀이 영업이라 회사 영업처럼 [확인했어요]가 있다(§0-1 의 2, D27) — 팀 없는 계정 규칙이 건드리지 않는다."""
    from flask import g

    from foms.services.auth.freelancer_scope import is_freelancer_user
    from foms.services.sales_commission.settings import load_settings, save_freelancer

    user = make_user("tl_freelancer", "STAFF", "SALES")
    save_freelancer(db_session, user.id, {"match_name": "가짜팀없음프리", "start_month": "2020-01", "tax_type": "NONE",
                                          "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    with app.test_request_context("/"):
        g.current_user = user
        assert is_freelancer_user(user) is True  # 대조: 정말 켜진 프리랜서다
        assert can_ack_production_change(user) is True
        assert can_view_production_home_as_team(user) is True


# --------------------------------------------------------------------------- #
# 2. HTTP — 팀 없는 직원은 보기만
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cookies", [PC, TABLET, PHONE, None], ids=["pc", "tablet", "phone", "nocookie"])
def test_teamless_staff_sees_pages_without_write_or_ack_marks(client, cohort, cookies):
    seed = _seed()
    login(client, make_user("tl_view_staff", "STAFF", None))
    set_cookies(client, cookies)
    pages = _pages(client, seed)
    for name, html in pages.items():
        for mark in WRITE_MARKS + (ACK_MARK,):
            assert mark not in html, (name, mark)
    # 보기는 된다 — 주문 이름이 첫 화면 · 시트에 보인다
    assert "가짜팀없음재단" in pages["?tab=all"] and "가짜팀없음바뀜" in pages["?tab=all"]
    assert "가짜팀없음바뀜" in pages["?tab=changes"]
    assert "가짜팀없음재단" in pages["sheet:cut"]


@pytest.mark.parametrize("team", TEAMLESS)
def test_teamless_staff_write_eight_and_change_ack_are_403(client, team):
    seed = _seed()
    login(client, make_user(f"tl_write_{len(team or '')}_{team is None}", "STAFF", team))
    order_id = seed.cut
    before = db_session.query(OrderEvent).filter_by(order_id=order_id).count()
    for path, body in WRITE_ENDPOINTS:
        resp = client.post(f"/api/orders/{order_id}/production/{path}", json=body)
        assert resp.status_code == 403, (path, resp.status_code)
        assert resp.get_json()["success"] is False
    resp = client.post(f"/api/orders/{seed.changed}/production/{ACK_PATH}", json={})
    assert resp.status_code == 403 and resp.get_json()["success"] is False
    assert _ack_events(seed.changed) == 0
    db_session.expire_all()
    assert db_session.query(OrderEvent).filter_by(order_id=order_id).count() == before


def test_teamless_staff_read_apis_open(client):
    """같이 열리는 읽기 길(§4): 도면 카드 바뀐 기록 · 30초 받아 오기 · PC 도면 창 — 보기만, 쓰기 POST 는 따로 막힌다."""
    seed = _seed()
    login(client, make_user("tl_read_api", "STAFF", None))
    oid = seed.cut
    assert client.get("/api/production/part-history", query_string={"order_id": oid}).status_code == 200
    assert client.get("/api/production/part-marks", query_string={"order_ids": str(oid), "since": "2000-01-01T00:00:00"}).status_code == 200
    assert client.get("/api/production/part-sheet", query_string={"order_id": oid, "part": "cut"}).status_code == 200
    # 도면 표시 쓰기는 생산팀 · 관리자만 — 팀 없는 계정은 여전히 막힌다
    key = "orders/x/drawing/가짜팀없음재단_0.png"  # add_order 가 심는 도면 1장
    resp = client.post("/api/production/part-marks", json={"order_id": oid, "drawing_key": key, "part": "cut",
                                                            "action": "take", "seen": "none"})
    assert resp.status_code == 403, (resp.status_code, resp.get_json())


def _nav_production_hrefs(html: str) -> list[str]:
    return re.findall(r'<a class="erp-pro-nav-item[^"]*"\s+href="([^"]+)">\s*<i class="fas fa-industry">', html)


def test_teamless_staff_menu_production_opens_a_page_they_can_see(client):
    """메뉴 '생산' 주소(지금 ``nav_target`` 이 주는 값)를 누르면 볼 수 있는 화면이 열린다 — 주소 글은 고정하지 않는다."""
    login(client, make_user("tl_menu", "STAFF", None))
    hrefs = _nav_production_hrefs(client.get("/erp/shipment").get_data(as_text=True))
    assert len(hrefs) == 1, hrefs
    resp = client.get(hrefs[0], follow_redirects=True)
    assert resp.status_code == 200, (hrefs[0], resp.status_code)
    assert client.get(PRODUCTION_HOME_PATH).status_code == 200


# --------------------------------------------------------------------------- #
# 3. 음성 대조 — 협력사 · 팀 있는 CS · 관리자(팀 없음) · 목록 밖 팀
# --------------------------------------------------------------------------- #
def test_partner_cannot_open_production_pages(client):
    seed = _seed()
    org = PartnerOrg(name="가짜협력사팀없음")
    db_session.add(org)
    db_session.commit()
    login(client, make_user("tl_partner", "PARTNER", None, partner_org_id=org.id))
    for path in (PRODUCTION_HOME_PATH, f"/erp/production/sheet/{seed.cut}", f"/erp/production/print/{seed.cut}"):
        resp = client.get(path)
        assert resp.status_code in (302, 403), (path, resp.status_code)
        assert "가짜팀없음재단" not in resp.get_data(as_text=True), path
    assert client.post(f"/api/orders/{seed.changed}/production/{ACK_PATH}", json={}).status_code == 403


def test_other_team_letters_stay_closed(client):
    """목록 밖 팀 글자는 넓히지 않는다(§4 · §13)."""
    _seed()
    login(client, make_user("tl_other_team", "STAFF", "WAREHOUSE"))
    assert client.get(PRODUCTION_HOME_PATH).status_code == 403


@pytest.mark.parametrize("cookies", [PC, TABLET], ids=["pc", "tablet"])
def test_cs_with_team_keeps_ack_button(client, cohort, cookies):
    seed = _seed()
    login(client, make_user("tl_cs", "STAFF", "CS"))
    set_cookies(client, cookies)
    changes = client.get(PRODUCTION_HOME_PATH + "?tab=changes").get_data(as_text=True)
    assert ACK_MARK in changes
    resp = client.post(f"/api/orders/{seed.changed}/production/{ACK_PATH}", json={})
    assert resp.status_code == 200 and _ack_events(seed.changed) == 1


def test_teamless_admin_keeps_everything(client, cohort):
    seed = _seed()
    login(client, make_user("tl_admin", "ADMIN", None))
    set_cookies(client, TABLET)
    pages = _pages(client, seed)
    assert ACK_MARK in pages["?tab=changes"]
    assert any(mark in pages["?tab=steps"] or mark in pages["sheet:cut"] for mark in WRITE_MARKS)
    resp = client.post(f"/api/orders/{seed.changed}/production/{ACK_PATH}", json={})
    assert resp.status_code == 200 and _ack_events(seed.changed) == 1
    resp = client.post(f"/api/orders/{seed.cut}/production/hold", json={"active": True, "reason": "가짜 사유"})
    assert resp.status_code != 403, resp.get_json()
