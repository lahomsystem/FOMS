"""메뉴 '회사 지식' 줄 — 물어보기를 여는 직원에게도 보인다(점검 F28 · 사장님 D99 3단계 '내부 직원 전부').

- 화면을 여는 사람(ADMIN · 층 승인자 팀 MANAGER)은 지금처럼 늘 보인다.
- 화면을 못 여는 내부 직원은 물어보기 화면을 열 수 있을 때만(:func:`foms.services.brain.chat_access.page_viewer` 와 같은
  판정): 단계 'all' + 켬이면 STAFF · VIEWER · 다른 팀 MANAGER, 'leads' 면 MANAGER 만, 'admin' · 끔이면 아무도.
- 바깥 역할(PARTNER) · 꺼진 계정 · 로그인 안 함은 어느 단계에서도 없다. 켜진 프리랜서도 없다(문지기 허용 목록 밖 —
  대조군: 같은 단계의 프리랜서 아닌 영업 직원은 보인다).
- 휴대폰 서랍(``erp_mobile_menu_drawer.html`` 계정 칸 — 휴대폰에선 PC 머리줄이 숨는다)도 같은 판정 · 같은 사람.
- 메뉴 줄 주소는 그대로 ``/brain`` — 물어보기만 여는 직원은 ``/brain`` 이 ``/brain/ask`` 로 보낸다(눌렀을 때 닿는 곳).
- 메뉴 판정은 설정 없이 알 수 있는 사람에게 설정을 묻지 않는다 — 모든 (사람 × 단계 × 켬/끔)에서 ``page_viewer`` 와 답이 같다.
합성 계정 · 합성 설정만.
"""

from __future__ import annotations

import re

import pytest
from flask import g

from db import db_session
from foms.services.brain.chat_access import page_open_without_settings, page_viewer
from foms.services.brain.chat_settings import STAGES, read_chat_settings
from foms.web.brain import brain_nav_allowed
from models import User
from tests.domains.test_auth_finance import _make_user
from tests.security.test_freelancer_edit_guards import _freelancer
from tests.support.brain_chat_support import chat_on, chat_people

NAV_MARK = "data-foms-nav-brain"
_MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
              "Version/17.0 Mobile/15E148 Safari/604.1")
#: 휴대폰 셸 조각(탭 바꾸기) — 서랍이 실린다.
PHONE_FRAGMENT = ("/erp/dashboard?view=fragment", {"X-FOMS-ERP-SHELL": "1", "User-Agent": _MOBILE_UA})
INSIDERS = ("admin", "cs_mgr", "dr_mgr", "sales_mgr", "staff", "viewer")
#: (켬, 단계) → 메뉴 줄이 보일 사람. 화면을 여는 셋(admin · cs_mgr · dr_mgr)은 늘.
EXPECTED = {
    (True, "all"): {"admin", "cs_mgr", "dr_mgr", "sales_mgr", "staff", "viewer"},
    (True, "leads"): {"admin", "cs_mgr", "dr_mgr", "sales_mgr"},
    (True, "admin"): {"admin", "cs_mgr", "dr_mgr"},
    (False, "all"): {"admin", "cs_mgr", "dr_mgr"},
}


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


@pytest.fixture
def ids(app):
    people = chat_people(db_session)
    db_session.commit()
    return {name: user.id for name, user in people.items()}  # 요청마다 세션이 닫혀 객체 대신 번호


@pytest.fixture
def phone(monkeypatch):
    """휴대폰 셸(모바일 v2 · 모두 코호트)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _drawer_account(app, user_id) -> str:
    """휴대폰 서랍 계정 칸(내 정보 · 공지사항 · … · 로그아웃)."""
    path, headers = PHONE_FRAGMENT
    resp = _client(app, user_id).get(path, headers=headers)
    assert resp.status_code == 200, (user_id, resp.status_code)
    html = resp.get_data(as_text=True)
    start = html.find("erp-mobile-menu-drawer__account-links")
    assert start >= 0, "휴대폰 서랍이 안 그려졌다 — 대조"
    return html[start:html.find("</nav>", start)]


def _drawer_labels(region: str) -> list[str]:
    return re.findall(r"<span>([^<]+)</span>", region)


def _menu_shown(app, user_id) -> bool:
    resp = _client(app, user_id).get("/notices")
    assert resp.status_code == 200, (user_id, resp.status_code)
    body = resp.get_data(as_text=True)
    assert "userDropdown" in body  # 대조: 메뉴(내 이름 펼침)를 실제로 그렸다
    return NAV_MARK in body


@pytest.mark.parametrize("enabled,stage", sorted(EXPECTED))
def test_menu_entry_follows_the_ask_stage(app, ids, enabled, stage):
    chat_on(db_session, enabled=enabled, stage=stage)
    shown = {name for name in INSIDERS if _menu_shown(app, ids[name])}
    assert shown == EXPECTED[(enabled, stage)], (enabled, stage, shown)


def test_menu_entry_keeps_the_same_address_and_lands_on_the_ask_page(app, ids):
    chat_on(db_session, stage="all")
    client = _client(app, ids["staff"])
    body = client.get("/notices").get_data(as_text=True)
    assert NAV_MARK in body and 'href="/brain"' in body
    first = client.get("/brain")
    assert first.status_code == 302 and first.headers["Location"].endswith("/brain/ask")
    page = client.get("/brain/ask")
    assert page.status_code == 200 and "data-brain-ask" in page.get_data(as_text=True)


def test_outsiders_never_get_the_entry_at_any_stage(app, ids):
    partner = db_session.get(User, ids["partner"])
    off = db_session.get(User, ids["off"])
    for stage in STAGES:
        chat_on(db_session, stage=stage)
        with app.test_request_context("/notices"):
            for who in (partner, off, None):
                g.current_user = who
                assert brain_nav_allowed() is False, (stage, getattr(who, "username", None))


def test_switched_on_freelancer_does_not_get_the_entry(app, ids):
    chat_on(db_session, stage="all")
    freelancer_id = _freelancer().id
    sales_staff_id = _make_user("STAFF", "SALES").id  # 대조군: 프리랜서 아닌 영업 직원
    assert _menu_shown(app, sales_staff_id) is True
    assert _menu_shown(app, freelancer_id) is False


def test_shortcut_answers_match_the_full_judgement_for_everyone(app, ids):
    """설정 없이 답한 사람은 어느 설정에서든 ``page_viewer`` 와 같은 답이다(짧은 길이 판정을 바꾸지 않는다)."""
    people = {name: db_session.get(User, uid) for name, uid in ids.items()}
    people["nobody"] = None
    asked = set()
    for enabled in (True, False):
        for stage in STAGES:
            chat_on(db_session, enabled=enabled, stage=stage)
            cfg = read_chat_settings(db_session)
            for name, user in people.items():
                full = page_viewer(user, cfg) is not None
                short = page_open_without_settings(user)
                if short is None:
                    asked.add(name)
                else:
                    assert short is full, (enabled, stage, name)
    # 설정을 봐야 아는 사람은 화면을 못 여는 내부 직원뿐이다(층 승인자 MANAGER 도 물어보기는 단계에 달렸다)
    assert asked == {"cs_mgr", "dr_mgr", "sales_mgr", "staff", "viewer"}


@pytest.mark.parametrize("enabled,stage", sorted(EXPECTED))
def test_phone_drawer_entry_follows_the_same_judgement(app, ids, phone, enabled, stage):
    chat_on(db_session, enabled=enabled, stage=stage)
    shown = {name for name in INSIDERS if NAV_MARK in _drawer_account(app, ids[name])}
    assert shown == EXPECTED[(enabled, stage)], (enabled, stage, shown)


def test_phone_drawer_entry_sits_after_notices_with_the_same_markup(app, ids, phone):
    chat_on(db_session, stage="all")
    staff = _drawer_account(app, ids["staff"])
    assert _drawer_labels(staff) == ["내 정보", "공지사항", "회사 지식", "로그아웃"]
    assert ('<a class="erp-mobile-menu-drawer__account-link" href="/brain" data-foms-nav-brain>' in staff
            and '<i class="fas fa-brain" aria-hidden="true"></i><span>회사 지식</span>' in staff)
    assert _drawer_labels(_drawer_account(app, ids["admin"])) == ["내 정보", "공지사항", "회사 지식", "관리자", "로그아웃"]
    chat_on(db_session, stage="admin")  # 대조: 못 여는 직원은 예전 그대로
    assert _drawer_labels(_drawer_account(app, ids["staff"])) == ["내 정보", "공지사항", "로그아웃"]


def test_switched_on_freelancer_phone_drawer_has_no_entry(app, ids, phone):
    chat_on(db_session, stage="all")
    freelancer_id = _freelancer().id
    sales_staff_id = _make_user("STAFF", "SALES").id  # 대조군: 프리랜서 아닌 영업 직원
    assert NAV_MARK in _drawer_account(app, sales_staff_id)
    assert _drawer_labels(_drawer_account(app, freelancer_id)) == ["내 정보", "공지사항", "로그아웃"]
