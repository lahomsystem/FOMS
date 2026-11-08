"""메뉴 '회사 지식' 판정의 질의 수 가드(점검 F28 — 메뉴는 모든 화면에서 그려진다).

물어보기 설정 한 줄(``system_settings`` 의 ``brain_chat_settings``)을

- 화면을 이미 여는 사람(ADMIN · 층 승인자 팀 MANAGER) · 바깥 역할 · 꺼진 계정 · 로그인 안 함은 **읽지 않는다**(0번),
- 그 밖 내부 직원은 **한 요청에 한 번만** 읽는다 — 메뉴를 여러 번 그려도, 물어보기 화면(``/brain/ask``)이 앞에서 이미
  판정했어도(같은 ``flask.g`` 기억).

휴대폰 서랍(``erp_mobile_menu_drawer.html``)도 같은 판정이라 셸 조각(탭 바꾸기) 요청마다 그려진다 — 그 직원 한 명당 조각
요청마다 1번은 받아들인 비용(총괄 결정)이고, ADMIN · 층 승인자 · 바깥 역할 · 켜진 프리랜서는 조각에서도 0번이다.
PC 메뉴와 서랍이 한 화면에 같이 그려져도 1번이다.

설정 줄 말고 다른 질의는 이 판정이 더하지 않는다 — ADMIN · 층 승인자 화면은 이 작업 앞과 질의가 같다(설정 0번 = 새 질의 0).
합성 계정 · 합성 설정만.
"""

from __future__ import annotations

import pytest
from flask import g
from sqlalchemy import event, text

from db import db_session, engine
from foms.services.brain.chat_settings import SETTINGS_KEY
from foms.web.brain import brain_nav_allowed
from models import User
from tests.domains.test_auth_finance import _make_user
from tests.security.test_freelancer_edit_guards import _freelancer
from tests.support.brain_chat_support import chat_on, chat_people

_MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
              "Version/17.0 Mobile/15E148 Safari/604.1")
_FRAGMENT = "/erp/dashboard?view=fragment"
_FRAGMENT_HEADERS = {"X-FOMS-ERP-SHELL": "1", "User-Agent": _MOBILE_UA}


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


def _settings_reads(fn):
    """``fn`` 을 부르는 동안 물어보기 설정 줄을 읽은 문장 수 · 모든 문장 수."""
    reads: list[str] = []
    every: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        every.append(statement)
        if "system_settings" in statement and SETTINGS_KEY in repr(params):
            reads.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    assert every, "SQL 수집이 비었다 — 대조군"
    return result, len(reads)


@pytest.fixture
def ids(app):
    people = chat_people(db_session)
    db_session.commit()
    chat_on(db_session, stage="all")
    return {name: user.id for name, user in people.items()}


@pytest.mark.parametrize("name", ["admin", "cs_mgr", "dr_mgr"])
def test_people_who_open_the_screen_never_read_the_setting(app, ids, name):
    client = _client(app, ids[name])
    client.get("/notices")  # 처음 한 번(캐시 데우기)
    resp, reads = _settings_reads(lambda: client.get("/notices"))
    assert resp.status_code == 200 and "data-foms-nav-brain" in resp.get_data(as_text=True)
    assert reads == 0, name


@pytest.mark.parametrize("name", ["sales_mgr", "staff", "viewer"])
def test_other_staff_read_the_setting_once_per_request(app, ids, name):
    client = _client(app, ids[name])
    client.get("/notices")
    resp, reads = _settings_reads(lambda: client.get("/notices"))
    assert resp.status_code == 200 and "data-foms-nav-brain" in resp.get_data(as_text=True)
    assert reads == 1, name


def test_ask_page_shares_one_read_with_the_menu(app, ids):
    client = _client(app, ids["staff"])
    client.get("/brain/ask")
    resp, reads = _settings_reads(lambda: client.get("/brain/ask"))
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "data-brain-ask" in body and "data-foms-nav-brain" in body
    assert reads == 1


def test_many_menu_calls_in_one_request_read_once_and_outsiders_never(app, ids):
    staff = db_session.get(User, ids["staff"])
    outsiders = [db_session.get(User, ids["partner"]), db_session.get(User, ids["off"]), None]

    def _staff_three_times():
        with app.test_request_context("/notices"):
            g.current_user = staff
            return [brain_nav_allowed() for _ in range(3)]

    answers, reads = _settings_reads(_staff_three_times)
    assert answers == [True, True, True] and reads == 1

    def _outsiders():
        with app.test_request_context("/notices"):
            out = []
            for who in outsiders:
                g.current_user = who
                out.append(brain_nav_allowed())
            db_session.execute(text("SELECT 1"))  # 대조 문장 하나(수집기가 살아 있다)
            return out

    answers, reads = _settings_reads(_outsiders)
    assert answers == [False, False, False] and reads == 0


@pytest.fixture
def phone(monkeypatch):
    """휴대폰 셸(모바일 v2 · 모두 코호트)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _drawer_fragment_reads(app, user_id):
    client = _client(app, user_id)
    client.get(_FRAGMENT, headers=_FRAGMENT_HEADERS)  # 처음 한 번(캐시 데우기)
    return _settings_reads(lambda: client.get(_FRAGMENT, headers=_FRAGMENT_HEADERS))


@pytest.mark.parametrize("name,expected", [("admin", 0), ("cs_mgr", 0), ("dr_mgr", 0),
                                           ("sales_mgr", 1), ("staff", 1), ("viewer", 1)])
def test_phone_drawer_fragment_reads_the_setting_only_for_other_staff(app, ids, phone, name, expected):
    resp, reads = _drawer_fragment_reads(app, ids[name])
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and 'id="erp-mobile-menu-drawer"' in body  # 대조: 서랍을 실제로 그렸다
    assert "data-foms-nav-brain" in body and "userDropdown" not in body  # 조각엔 서랍만(PC 머리줄 없음)
    assert reads == expected, name


def test_phone_drawer_fragment_never_reads_for_freelancer_or_outsider(app, ids, phone):
    freelancer_id = _freelancer().id
    resp, reads = _drawer_fragment_reads(app, freelancer_id)
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and 'id="erp-mobile-menu-drawer"' in body and "data-foms-nav-brain" not in body
    assert reads == 0
    resp, reads = _drawer_fragment_reads(app, ids["partner"])  # 협력사 문지기가 그리기 전에 막는다
    assert resp.status_code != 200 and reads == 0


def test_full_phone_page_with_both_menus_reads_once(app, ids, phone):
    sales_staff_id = _make_user("STAFF", "SALES").id
    for user_id in (ids["staff"], sales_staff_id):
        client = _client(app, user_id)
        client.get("/erp/dashboard", headers={"User-Agent": _MOBILE_UA})
        resp, reads = _settings_reads(lambda: client.get("/erp/dashboard", headers={"User-Agent": _MOBILE_UA}))
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200 and body.count("data-foms-nav-brain") == 2  # PC 메뉴 + 서랍
        assert reads == 1, user_id
