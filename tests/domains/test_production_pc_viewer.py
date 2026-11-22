"""PC 생산 화면 = 보기 전용 첫 화면 — 설계서 docs/specs/2026-11-21-production-pc-viewer_SPEC.md §4 · §5 · §6 · §7 · §11(1단계).

- 기기 문: PC(마우스, ``foms_ptr=fine``)는 쓰기 단추 · 쓰기 JS 를 **서버가 그리지 않는다**. 쓰기 = 쓰기 팀(관리자 · 생산팀,
  ``can_write_production``) and (태블릿 ``coarse`` or [고치기] 켬). 쿠키 없는 첫 요청도 안 그린다.
- [고치기] = 관리자 · 생산팀만(§13 결정 1), 쿠키 ``foms_prod_edit=<켠 시각>`` 2시간 안일 때만 켬. CS · 영업은 쿠키를 심어도 무시.
- [확인했어요] 는 개인 확인 기록이라 기기와 상관없이 보는 사람 모두에게(PC 보기 전용 포함, §13 결정 5).
- PC 꼴: ERP 둘째 줄 메뉴 · 모든 줄 맨 앞 시공일 칸 · 공정 칸 누가 · 언제 마우스 글 · 늦음 줄. 태블릿 · 폰 출력에는 하나도 없다.
대조군: 같은 사람 · 같은 주문의 태블릿 응답.
"""
from __future__ import annotations

import datetime
import re
import time
from itertools import count
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.production.late_rule import production_late_level
from foms.services.production.pc_view import EDIT_COOKIE, EDIT_TTL_SECONDS, production_screen_flags
from foms.services.production.write_access import can_write_production
from models import Order, User
from tests.domains.test_production_home_changes import _date_changed
from tests.domains.test_production_home_changes import _order as _changed_order
from tests.support.production_home_step_panel_seed import HOME, add_order, get_html, set_cookies

ROOT = Path(__file__).resolve().parents[2]
PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
TABLET = {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}
TABS = ("", "?tab=steps", "?tab=changes", "?tab=all")
#: 쓰기 표식 — 공정 [끝] · 작업 시트 단추 · 판 [끝] · 시트 공정 칸 · [불량]
WRITE = ("data-foms-home-step-done", "data-tablet-sheet-action", "data-foms-step-finish", "data-foms-sheet-step=",
         "data-foms-sheet-defect-toggle")
ACK = 'data-kanban-action="change-ack"'
PC_ONLY = ("data-tip=", "data-foms-pc-due", "foms-prod-home is-pc", "pc.css?v=", "foms-production-edit.js", 'class="fpc-',
           '<nav class="erp-pro-nav"', "data-foms-home-board")
_seq = count(1)


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _login(client, who: str) -> User:
    team, role = {"admin": ("CS", "ADMIN"), "prod": ("PRODUCTION", "STAFF"), "cs": ("CS", "STAFF"),
                  "sales": ("SALES", "STAFF"), "drawing": ("DRAWING", "STAFF")}[who]
    user = User(username=f"pcv_{who}_{next(_seq)}", password=generate_password_hash("pw"), role=role, team=team,
                name=f"{who}사람", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return user


def _edit(client, issued: float | str | None) -> None:
    client.delete_cookie(EDIT_COOKIE, domain="localhost", path="/erp/production")
    if issued is not None:
        value = issued if isinstance(issued, str) else str(int(issued))
        client.set_cookie(EDIT_COOKIE, value, domain="localhost", path="/erp/production")


def _no_date_order(name: str) -> Order:
    sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
          "items": [{"product_name": "붙박이장"}], "schedule": {"construction": {"date": ""}}}
    order = Order(received_date=get_today_kst().isoformat(), customer_name=name, phone="010-0000-0000", address="가짜시",
                  product="장", status="PRODUCTION", is_erp_order=True, structured_data=sd, erp_stage_code="PRODUCTION",
                  erp_construction_date="")
    db_session.add(order)
    db_session.commit()
    return order


def _seed() -> dict[str, Order]:
    """재단 중(내일) · 엣지 중(모레, 재단 김재단 끝) · 보류 · 제작 대기 · 시공일 바뀐 주문 · 시공일 없음 · 여러 시공일."""
    orders = {
        "cut": add_order("가재단", 1),
        "edge": add_order("나엣지", 2, done=("cut",)),
        "hold": add_order("다보류", 5, done=("cut",), hold="자재 기다림"),
        "wait": add_order("라대기", 1, run=False),
        "nodate": _no_date_order("바없음"),
    }
    changed = _changed_order("PRODUCTION", "마바뀜", 4, run=True)
    _date_changed(changed, datetime.timedelta(hours=2), None)
    orders["changed"] = changed
    multi = add_order("사여럿", 6)
    sd = dict(multi.structured_data)
    first = (get_today_kst() + datetime.timedelta(days=6)).isoformat()
    later = (get_today_kst() + datetime.timedelta(days=9)).isoformat()
    sd["schedule"] = {"construction": {"date": f"{first}, {later}"}}
    multi.structured_data = sd
    db_session.commit()
    orders["multi"] = multi
    return orders


def _sheet(order: Order) -> str:
    return f"/erp/production/sheet/{order.id}"


def _all_pages(client, orders) -> dict[str, str]:
    pages = {tab or "date": get_html(client, HOME + tab) for tab in TABS}
    pages["sheet"] = get_html(client, _sheet(orders["edge"]))
    return pages


# --------------------------------------------------------------------------- #
# 권한 · 기기 판정 한 곳
# --------------------------------------------------------------------------- #
class _Req:
    def __init__(self, **cookies):
        self.cookies = cookies


class _U:
    def __init__(self, role="STAFF", team=None, partner_org_id=None):
        self.role, self.team, self.partner_org_id = role, team, partner_org_id


def test_쓰기_팀은_관리자와_생산팀만() -> None:
    assert can_write_production(_U("ADMIN", "CS")) and can_write_production(_U(team="PRODUCTION"))
    for user in (_U(team="CS"), _U(team="SALES"), _U(team="DRAWING"), _U(team="CONSTRUCTION"), _U(team="SHIPMENT"),
                 _U(team=None), _U("ADMIN", partner_org_id=3), _U(team="PRODUCTION", partner_org_id=3), None):
        assert not can_write_production(user)


def test_화면_판정_표() -> None:
    now = 1_800_000_000
    admin, prod, cs = _U("ADMIN", "CS"), _U(team="PRODUCTION"), _U(team="CS")
    fresh = str(now - 60)
    # PC 보기 전용 — 쓰기 없음, [확인했어요]는 보는 사람 모두(§13 결정 5, 기기 무관), [고치기]는 쓰기 팀만
    assert production_screen_flags(admin, _Req(foms_ptr="fine"), now) == {
        "pc_view": True, "can_act": False, "can_ack": True, "edit_on": False, "edit_toggle": True, "edit_now": now,
        "write_omitted": False}
    for ptr in ("fine", "coarse", "", "weird"):
        for user in (cs, _U(team="SALES"), _U(team="DRAWING"), _U(team="SHIPMENT"), prod):
            assert production_screen_flags(user, _Req(foms_ptr=ptr), now)["can_ack"] is True, (ptr, user.team)
        # 음성 대조 — 생산 화면을 못 보는 사람(팀 없음 · 협력사 · 조회 전용)은 없다
        for user in (_U(team=None), _U(team="CS", partner_org_id=3), _U("VIEWER", "CS")):
            assert production_screen_flags(user, _Req(foms_ptr=ptr), now)["can_ack"] is False, (ptr, user.role)
    # [고치기] 켬 — 쓰기 팀 + PC + 2시간 안
    for user in (admin, prod):
        flags = production_screen_flags(user, _Req(foms_ptr="fine", foms_prod_edit=fresh), now)
        assert flags["edit_on"] and flags["can_act"]
    for value in (str(now - EDIT_TTL_SECONDS), str(now - EDIT_TTL_SECONDS - 1), str(now + 600), "abc", "", "-5"):
        assert not production_screen_flags(admin, _Req(foms_ptr="fine", foms_prod_edit=value), now)["can_act"], value
    assert production_screen_flags(admin, _Req(foms_ptr="fine", foms_prod_edit=str(now - EDIT_TTL_SECONDS + 1)), now)["can_act"]
    flags = production_screen_flags(cs, _Req(foms_ptr="fine", foms_prod_edit=fresh), now)
    assert not flags["edit_on"] and not flags["can_act"] and not flags["edit_toggle"]
    # 태블릿(coarse) = 쓰기 팀이면 지금처럼, [고치기] 없음 · 쿠키 없음(첫 요청)은 안 그림(§4)
    assert production_screen_flags(prod, _Req(foms_ptr="coarse"), now)["can_act"] is True
    assert production_screen_flags(cs, _Req(foms_ptr="coarse"), now)["can_act"] is False
    assert production_screen_flags(prod, _Req(foms_ptr="coarse", foms_prod_edit=fresh), now)["edit_toggle"] is False
    for req in (_Req(), _Req(foms_ptr="weird")):
        flags = production_screen_flags(prod, req, now)
        assert not flags["pc_view"] and not flags["can_act"] and not flags["edit_toggle"]
        # 쓰기 팀인데 기기를 몰라 뺐다 → 표식(터치 기기면 쿠키가 심긴 뒤 다시 받는다, §12)
        assert flags["write_omitted"] is True
        assert production_screen_flags(cs, req, now)["write_omitted"] is False
    for ptr in ("fine", "coarse"):
        assert production_screen_flags(prod, _Req(foms_ptr=ptr, foms_prod_edit=fresh), now)["write_omitted"] is False


# --------------------------------------------------------------------------- #
# PC 보기 전용 — 응답에 쓰기 표식 0
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("who", ["admin", "prod", "cs", "sales"])
def test_PC_보기_전용은_쓰기_단추와_쓰기_JS_가_없다(client, cohort, who) -> None:
    orders = _seed()
    _login(client, who)
    set_cookies(client, PC)
    writer = who in ("admin", "prod")
    for name, html in _all_pages(client, orders).items():
        for mark in WRITE:
            assert mark not in html, (who, name, mark)
        assert "foms-reason-sheet.js" not in html and "foms-admin-override.js" not in html, (who, name)
        assert ("보기 전용" in html) and ("data-foms-pc-editband" not in html), (who, name)
        assert ('data-foms-prod-edit="on"' in html) is writer, (who, name)
        assert ("foms-production-edit.js" in html) is writer, (who, name)
    pages = _all_pages(client, orders)
    # [확인했어요]는 PC 보기 전용에서도 보는 사람 모두(§13 결정 5) — CS · 영업도 있다(그 배선 JS 만 같이)
    assert ACK in pages["?tab=changes"] and "tablet-domain-sheets.js" in pages["?tab=changes"], who
    for name in ("date", "?tab=steps", "?tab=all"):
        assert "tablet-domain-sheets.js" not in pages[name], name


def test_PC_보기_전용_작업_시트는_공정_칸을_보기만으로_그린다(client, cohort) -> None:
    orders = _seed()
    _login(client, "admin")
    set_cookies(client, PC)
    html = get_html(client, _sheet(orders["edge"]))
    steps = html.split('aria-label="공정"', 1)[1].split("</section>", 1)[0]
    assert steps.count('<div class="foms-prod-page__step is-view') == 4 and "<button" not in steps
    assert 'class="foms-prod-page__foot"' not in html
    # 머리 시공일 = 첫 화면 ① 칸과 같은 글(M/D (요일) · D-n)
    due = re.search(r'<span class="foms-prod-page__due fpc-sheet-due is-[a-z]+" data-foms-pc-due>시공 ([^<]+?)( · <b>([^<]+)</b>)?</span>', html)
    day = get_today_kst() + datetime.timedelta(days=2)
    assert due and due.group(1) == f"{day.month}/{day.day} ({'월화수목금토일'[day.weekday()]})" and due.group(3) == "D-2"


# --------------------------------------------------------------------------- #
# [고치기] — 관리자 · 생산팀 + 2시간 안 쿠키
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("who", ["admin", "prod"])
def test_고치기_켬이면_태블릿과_같은_쓰기_단추(client, cohort, who) -> None:
    orders = _seed()
    _login(client, who)
    set_cookies(client, PC)
    _edit(client, time.time() - 60)
    steps = get_html(client, HOME + "?tab=steps")
    assert "data-foms-pc-editband" in steps and "고치는 중이에요 — 누르면 바로 저장돼요" in steps
    assert 'data-foms-prod-edit="off"' in steps and "보기 전용" not in steps
    # 재단 줄: 가재단(재단 중) — 같은 [끝] 계약(data-foms-home-step-done · POST /production/steps, foms-production-home.js)
    assert f'data-foms-home-step-done data-order-id="{orders["cut"].id}" data-step-key="cut"' in steps
    # 보류 줄은 [끝] 대신 보류 글
    assert f'data-order-id="{orders["hold"].id}" data-step-key=' not in steps and "보류 중 · 자재 기다림" in steps
    sheet = get_html(client, _sheet(orders["edge"]))
    for mark in ('data-tablet-sheet-action="production-cancel"', 'data-tablet-sheet-action="production-hold"',
                 'data-foms-sheet-step="cut"', "data-foms-sheet-defect-toggle", "tablet-domain-sheets.js",
                 "foms-reason-sheet.js"):
        assert mark in sheet, mark
    assert "data-foms-pc-editband" in sheet


@pytest.mark.parametrize("issued", [lambda: time.time() - EDIT_TTL_SECONDS - 5, lambda: time.time() + 3600, lambda: "nope"])
def test_고치기_쿠키가_2시간_지났거나_이상하면_보기_전용(client, cohort, issued) -> None:
    orders = _seed()
    _login(client, "admin")
    set_cookies(client, PC)
    _edit(client, issued())
    for name, html in _all_pages(client, orders).items():
        assert not any(mark in html for mark in WRITE), name
        assert "data-foms-pc-editband" not in html and 'data-foms-prod-edit="on"' in html, name


@pytest.mark.parametrize("who", ["cs", "sales"])
def test_CS_영업은_고치기가_없고_쿠키를_심어도_보기만(client, cohort, who) -> None:
    orders = _seed()
    _login(client, who)
    set_cookies(client, PC)
    _edit(client, time.time() - 60)
    pages = _all_pages(client, orders)
    for name, html in pages.items():
        assert not any(mark in html for mark in WRITE), name
        assert "data-foms-prod-edit" not in html and "data-foms-pc-editband" not in html, name
    assert ACK in pages["?tab=changes"]  # [확인했어요]는 쿠키와 상관없이 그대로(§13 결정 5)


# --------------------------------------------------------------------------- #
# 태블릿 · 쿠키 없음
# --------------------------------------------------------------------------- #
def test_태블릿_쓰기_팀은_지금_그대로_CS_는_단추가_없다(client, cohort) -> None:
    orders = _seed()
    _login(client, "prod")
    set_cookies(client, TABLET)
    _edit(client, time.time() - 60)  # 태블릿에서는 [고치기]가 없고 쿠키도 상관없다
    steps = get_html(client, HOME + "?tab=steps")
    assert "data-foms-home-step-done" in steps or "data-foms-step-finish" in steps
    pages = _all_pages(client, orders)
    assert 'data-tablet-sheet-action="production-cancel"' in pages["sheet"] and ACK in pages["?tab=changes"]
    for name, html in pages.items():
        for mark in PC_ONLY + ("data-foms-prod-edit", "보기 전용"):
            assert mark not in html, (name, mark)
    _login(client, "cs")
    pages = _all_pages(client, orders)
    for name, html in pages.items():
        assert not any(mark in html for mark in WRITE), name
    assert ACK in pages["?tab=changes"]  # CS 는 쓰기 단추가 없어도 [확인했어요]는 있다(§13 결정 5)


@pytest.mark.parametrize("cookies", [PC, TABLET, None])
def test_확인했어요는_보는_사람_모두에게_기기_무관(client, cohort, cookies) -> None:
    """도면팀(2단계에 보기를 연 팀)도 PC · 태블릿 · 쿠키 없음 모두 [확인했어요]가 있고, 누르면 200 — 쓰기 단추는 없다."""
    orders = _seed()
    _login(client, "drawing")
    set_cookies(client, cookies)
    changes = get_html(client, HOME + "?tab=changes")
    cards = changes.count("data-foms-home-inbox=")
    assert cards and changes.count(ACK) == cards and "tablet-domain-sheets.js" in changes
    assert not any(mark in get_html(client, HOME + "?tab=steps") for mark in WRITE)
    resp = client.post(f"/api/orders/{orders['changed'].id}/production/change-ack", json={})
    assert resp.status_code == 200 and resp.get_json()["success"] is True


def test_쿠키_없는_첫_요청은_쓰기_단추를_안_그리고_PC_꼴도_아니다(client, cohort) -> None:
    orders = _seed()
    _login(client, "prod")
    set_cookies(client, None)
    for name, html in _all_pages(client, orders).items():
        assert not any(mark in html for mark in WRITE), name
        assert not any(mark in html for mark in PC_ONLY), name


WRITE_MARK = "<template data-foms-write-omitted></template>"


@pytest.mark.parametrize(("who", "cookies", "want"), [
    ("prod", None, 1), ("admin", None, 1), ("prod", {"foms_ptr": "weird"}, 1),  # 쓰기 팀 + 기기 모름 → 표식
    ("cs", None, 0), ("sales", None, 0),  # 보기 팀은 다시 받아도 단추가 없다 — 표식 없음
    ("prod", PC, 0), ("prod", TABLET, 0), ("admin", PC, 0),  # 기기를 알면 표식 없음
])
def test_쿠키_없는_첫_요청의_쓰기_팀만_단추_자리에_되돌림_표식(client, cohort, who, cookies, want) -> None:
    """사이트 데이터를 지운 공장 태블릿(사장님 11-21): 첫 화면에 단추 대신 표식 + 되돌림 스크립트 — 터치 기기면 다시 받는다."""
    orders = _seed()
    _login(client, who)
    set_cookies(client, cookies)
    steps = get_html(client, HOME + "?tab=steps")
    sheet = get_html(client, _sheet(orders["edge"]))
    assert steps.count(WRITE_MARK) == want and sheet.count(WRITE_MARK) == want, (who, cookies)
    for html in (steps, sheet):
        assert ("js/runtime/foms-wide-surface-recover.js?v=" in html) is bool(want)
        if want:
            assert not any(mark in html for mark in WRITE)  # 표식 자리 = 단추를 뺀 자리
    # 셸 조각(레일 · 아래 메뉴로 온 '내 공정')도 같은 몸통이라 같은 표식
    frag = get_html(client, HOME + "?tab=steps&view=fragment", headers={"X-FOMS-ERP-SHELL": "1"})
    assert frag.count(WRITE_MARK) == want
    # 쓰기 단추가 없는 탭(날짜 · 바뀐 것 · 찾기)은 다시 받을 까닭이 없다
    for tab in ("", "?tab=changes", "?tab=all"):
        assert WRITE_MARK not in get_html(client, HOME + tab), tab


def test_되돌림_JS_는_터치_기기에서만_쓰기_표식을_다시_받는다() -> None:
    js = (ROOT / "static/js/runtime/foms-wide-surface-recover.js").read_text(encoding="utf-8")
    assert len(js.splitlines()) <= 300
    assert "var COARSE_MQ = '(pointer: coarse)';" in js and "var WRITE_OMITTED_SELECTOR = '[data-foms-write-omitted]';" in js
    assert "(touchDevice() && !!document.querySelector(WRITE_OMITTED_SELECTOR))" in js
    # 터치 판정 = 쿠키를 심는 부트와 같은 함수(키보드 커버 태블릿도 터치, 11-22) · 포인터 식이 바뀌면 다시 본다
    assert "window.__fomsPointerHint() === 'coarse'" in js and "[coarseMql, onPointerChange], [anyCoarseMql, onPointerChange]" in js
    assert "if (!omittedNow()) {" in js and "if (reloadedRecently(guard, key)) {" in js  # 되풀이 막음(같은 길)
    # 쿠키를 심는 부트와 같은 식 — 터치면 이 화면에서 이미 foms_ptr=coarse 가 심겨 있다
    head = (ROOT / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    assert "window.__fomsPointerHint = sync;" in head and "var primary = window.matchMedia('(pointer: coarse)');" in head
    # 두 표식이 같은 파일 · 같은 핀 · 같은 run-once 열쇠(한 화면에 같이 있어도 한 번만 묶인다)
    pins = []
    for tpl in ("templates/production/partials/write_omitted_marker.html", "templates/partials/shared/wide_surface_omitted_marker.html"):
        tag = re.search(r"<script[^>]*foms-wide-surface-recover\.js[^>]*>", (ROOT / tpl).read_text(encoding="utf-8")).group(0)
        assert " defer" in tag and 'data-foms-run-once="wide-surface-recover"' in tag, tpl
        pins.append(re.search(r"\?v=(\w+)", tag).group(1))
    assert pins[0] == pins[1], pins


# --------------------------------------------------------------------------- #
# PC 꼴 — 둘째 줄 메뉴 · [보드 →] · 시공일 칸 · 누가 · 언제 · 늦음
# --------------------------------------------------------------------------- #
def test_PC_에는_ERP_둘째_줄_메뉴_하나와_보드_길(client, cohort) -> None:
    _seed()
    _login(client, "cs")
    set_cookies(client, PC)
    for tab in TABS:
        html = get_html(client, HOME + tab)
        assert html.count('<nav class="erp-pro-nav"') == 1, tab
        nav = html.split('<nav class="erp-pro-nav"', 1)[1].split("</nav>", 1)[0]
        assert re.search(r'class="erp-pro-nav-item active"\s+href="/erp/production/', nav), tab
        assert 'data-foms-home-board data-foms-erp-no-shell="1" href="/erp/production/dashboard"' in html, tab
    # 셸 조각(view=fragment + 셸 머리글)도 같은 몸통이라 같은 메뉴(parity)
    frag = get_html(client, HOME + "?view=fragment", headers={"X-FOMS-ERP-SHELL": "1"})
    assert frag.count('<nav class="erp-pro-nav"') == 1 and "pc.css?v=" in frag


def test_모든_탭의_모든_줄에_시공일_칸(client, cohort) -> None:
    orders = _seed()
    _login(client, "admin")
    set_cookies(client, PC)
    found = get_html(client, HOME + "?tab=all")
    rows = found.count("data-foms-home-job ")
    assert rows >= len(orders) and found.count("data-foms-pc-due") == rows
    nodate = found.split(f'data-foms-home-dayrow="{orders["nodate"].id}"', 1)[1].split('<div class="fpc-r', 1)[0]
    assert '<span class="fpc-due is-none" data-foms-pc-due><b>시공일 없음</b></span>' in nodate
    # 바뀐 시공일: 새 날 크게 그대로 + '← 옛 날' 작게(이벤트 11/10 → 11/12)
    changed = found.split(f'data-foms-home-dayrow="{orders["changed"].id}"', 1)[1].split('<div class="fpc-r', 1)[0]
    assert "<em>← 11/10</em>" in changed
    # 여러 시공일: 가장 가까운 날 + 외 n
    multi = found.split(f'data-foms-home-dayrow="{orders["multi"].id}"', 1)[1].split('<div class="fpc-r', 1)[0]
    assert "<span>D-6</span><small>외 1</small>" in multi
    steps = get_html(client, HOME + "?tab=steps")
    lines = steps.count("data-foms-home-qrow=") + steps.split('data-foms-home-stepq="', 1)[1].count('<div class="fpc-r')
    assert lines and steps.count("data-foms-pc-due") == lines
    changes = get_html(client, HOME + "?tab=changes")
    cards = changes.count("data-foms-home-inbox=")
    assert cards and changes.count("data-foms-pc-due") == cards
    for off in (1, 2):
        key = (get_today_kst() + datetime.timedelta(days=off)).isoformat()
        pane = get_html(client, HOME + f"?view=day&day={key}")
        assert pane.count("data-foms-home-dayrow=") == pane.count("data-foms-pc-due") > 0, key


def test_공정_칸_누가_언제는_PC_에만(client, cohort) -> None:
    orders = _seed()
    _login(client, "prod")
    set_cookies(client, PC)
    key = (get_today_kst() + datetime.timedelta(days=2)).isoformat()
    pane = get_html(client, HOME + f"?view=day&day={key}")
    row = pane.split(f'data-foms-home-dayrow="{orders["edge"].id}"', 1)[1].split('<div class="fpc-r', 1)[0]
    # 시드: 재단 김재단 2026-11-21T00:12Z = KST 11/21 09:12, 회차 시작 2026-11-20 23:40Z = KST 11/21 08:40
    assert 'data-tip="재단 끝 · 김재단 · 11/21 09:12" tabindex="0" aria-label="재단 끝 · 김재단 · 11/21 09:12"' in row
    assert '<span class="fpc-s__m">김재단 11/21</span>' in row
    assert 'data-tip="엣지 · 지금 여기(아직)"' in row and 'data-tip="조립 · 아직"' in row
    assert 'data-tip="제작 시작 11/21 08:40"' in row
    set_cookies(client, TABLET)
    tablet = get_html(client, HOME + f"?view=day&day={key}")
    assert "data-tip=" not in tablet and "김재단" not in tablet


def test_늦은_줄은_띠와_까닭_한_줄(client, cohort) -> None:
    orders = _seed()
    _login(client, "admin")
    set_cookies(client, PC)
    found = get_html(client, HOME + "?tab=all")
    # 내일 시공 + 제작 대기 = 일하는 날 0~1 ≤ 2 → 요일과 상관없이 늦음
    wait = found.split(f'data-foms-home-dayrow="{orders["wait"].id}"', 1)[0].rsplit("<div ", 1)[1]
    assert "is-late" in wait
    assert "<small>늦음 — 내일 시공, 아직 시작 전</small>" in found
    # 다른 줄은 같은 함수의 답과 같은 꼴(요일에 따라 빠듯 · 늦음 · 없음)
    today = get_today_kst()
    for name in ("cut", "edge", "hold"):
        order = orders[name]
        head = found.split(f'data-foms-home-dayrow="{order.id}"', 1)[0].rsplit("<div ", 1)[1]
        row = {"home_stage": {"cut": "재단 중", "edge": "엣지 중", "hold": "보류"}[name],
               "home_view": "prod", "construction_date": order.erp_construction_date, "hold_active": name == "hold",
               "home_has_run": True, "home_steps": [{"key": k, "label": l, "done": (name != "cut" and k == "cut")}
                                                    for k, l in (("cut", "재단"), ("edge", "엣지"), ("assemble", "조립"), ("inspect", "검수"))]}
        level = production_late_level(row, today)
        assert (f"is-{level}" in head) if level else ("is-late" not in head and "is-tight" not in head), name


# --------------------------------------------------------------------------- #
# 정적 파일 계약 — pc.css · [고치기] JS
# --------------------------------------------------------------------------- #
def test_pc_css_는_PC_응답에서만_싣고_글자는_배율을_따른다() -> None:
    css = (ROOT / "static/css/contexts/production/pc.css").read_text(encoding="utf-8")
    sizes = re.findall(r"font-size:\s*([^;}]+)", css)
    assert sizes and all(re.fullmatch(r"calc\((\d+)px \* var\(--foms-fs, 1\)\)", s.strip()) for s in sizes), sizes
    assert min(int(re.search(r"(\d+)px", s).group(1)) for s in sizes) >= 13
    # 늦음 · 빠듯: 6px 띠 + 연한 바탕(빨강 · 주황 — 무채색 아님)
    assert ".fpc-r.is-late, .fpc-q.is-late { background: var(--fpc-danger-50); border-color: var(--fpc-danger-line); box-shadow: inset 6px 0 0 var(--fpc-danger); }" in css
    assert ".fpc-r.is-tight, .fpc-q.is-tight { background: var(--fpc-warn-50); border-color: var(--fpc-warn-soft); box-shadow: inset 6px 0 0 var(--fpc-warn-line); }" in css
    # 여섯 칸 = 목업 값, 아주 넓은 칸(1,500px)은 공정이 더 갖고 칸 안 글
    assert "grid-template-columns: 8.5rem 7rem minmax(14rem, 1.3fr) minmax(19rem, 2fr) minmax(7.5rem, .8fr) 5rem;" in css
    assert "@container fpc (min-width: 1500px)" in css and ".fpc-s__m { display: block; }" in css
    users = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "templates").rglob("*.html")
                   if "production/pc.css" in p.read_text(encoding="utf-8"))
    assert users == ["templates/production/partials/home_styles.html", "templates/production/sheet.html"]


def test_고치기_JS_는_세션_쿠키_한_경로_새_API_없음() -> None:
    js = (ROOT / "static/js/production/foms-production-edit.js").read_text(encoding="utf-8")
    assert len(js.splitlines()) <= 300
    assert "var NAME = 'foms_prod_edit';" in js and "var PATH = '/erp/production';" in js and ";SameSite=Lax" in js
    # 켤 때는 만료 없음(세션 쿠키), 끌 때만 max-age=0. fetch · XHR 없음
    assert js.count("max-age") == 1 and "NAME + '=;max-age=0'" in js and "expires" not in js
    assert "fetch(" not in js and "XMLHttpRequest" not in js and "data-foms-prod-edit-now" in js


# --------------------------------------------------------------------------- #
# 바로가기 order= — PC 줄도 태블릿처럼 테두리(설계서 §9-10)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("param", ["order", "focus_order"])
def test_PC_바로가기_주문은_그_날_장과_줄_테두리(client, cohort, param) -> None:
    orders = _seed()
    _login(client, "cs")
    set_cookies(client, PC)
    target = orders["hold"]  # 닷새 뒤 — 오늘 장이 아니다
    day = (get_today_kst() + datetime.timedelta(days=5)).isoformat()
    html = get_html(client, HOME + f"?{param}={target.id}")
    assert f'data-foms-home-daypane="{day}"' in html
    focused = re.findall(r'<div class="fpc-r[^"]*\bis-focus\b[^"]*" data-foms-home-dayrow="(\d+)"', html)
    assert focused and set(focused) == {str(target.id)}, focused
    # 음성 대조 — order= 가 없으면 테두리 없음, 같은 사람 태블릿은 옛 줄(fph-dr) 테두리 그대로
    assert "is-focus" not in get_html(client, HOME + f"?day={day}")
    set_cookies(client, TABLET)
    tablet = get_html(client, HOME + f"?{param}={target.id}")
    assert re.search(r'<a class="fph-dr[^"]*\bis-focus\b', tablet) and 'class="fpc-r' not in tablet


def test_pc_css_바로가기_테두리는_태블릿과_같은_꼴이고_핀을_올렸다() -> None:
    css = (ROOT / "static/css/contexts/production/pc.css").read_text(encoding="utf-8")
    rule = ".fpc-r.is-focus, .fpc-q.is-focus { outline: 3px solid var(--fpc-brand); outline-offset: 2px; }"
    assert rule in css and css.index(rule) > css.index(".fpc-r.is-chg, .fpc-q.is-chg {")  # 바뀜 테두리보다 뒤(이긴다)
    home = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".fph-dr.is-focus, .fph-wi.is-focus { outline: 3px solid var(--fph-brand); outline-offset: 2px; }" in home
    assert re.search(r"--fpc-brand:\s*#5a67d8;", css) and re.search(r"--fph-brand:\s*#5a67d8;", home)  # 같은 색
    for tpl in ("templates/production/partials/home_styles.html", "templates/production/sheet.html"):
        assert "pc.css') }}?v=20261122b" in (ROOT / tpl).read_text(encoding="utf-8"), tpl
