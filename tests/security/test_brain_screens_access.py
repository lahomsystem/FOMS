"""'회사 지식' 화면 · API 권한(설계서 2026-11-02-haud-master-brain 7.5 · 11절 '화면 권한 시험(ADMIN · 승인자 밖 404)' · D101).

- 여는 사람: 켜진 ADMIN · CS/DRAWING/PRODUCTION 팀 MANAGER → 200(대조군).
- 못 여는 사람: 다른 팀 MANAGER · STAFF · VIEWER · 꺼진 ADMIN → **404**(화면 · API 모두, 있는지도 알리지 않는다).
- PARTNER: 협력사 문지기가 이 핸들러 앞에서 막는다 — **없는 주소와 똑같은 답**이고 brain 글은 한 글자도 없다. 문지기를 지나도
  (판정 함수) 열 수 없다.
- 로그인 안 함: API 401 · 화면은 로그인으로. 읽기 블루프린트에는 쓰기 동작이 없다(POST 405) — 쓰기(제안 · 결정 · 되돌리기)는
  따로 블루프린트(``brain_review_api``)이고 권한 · CSRF 시험은 ``test_brain_review_access.py``.
합성 계정 · 합성 항목만.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain.access import can_open_screen, screen_viewer
from models import PartnerOrg, User
from tests.support.brain_screen_support import world

PAGES = ("/brain", "/brain?tab=map", "/brain?tab=onto", "/brain/items/common/door")
APIS = ("/api/brain/search?q=%EB%AC%B8%EC%A7%9D", "/api/brain/table?type=build_rule", "/api/brain/items/common/door",
        "/api/brain/type-map", "/api/brain/releases", "/api/brain/releases/1",
        "/api/brain/around?key=common/door&depth=2", "/api/brain/points", "/api/brain/quality",  # ⑤-4 이웃 찾기 · 뇌 보기
        "/api/brain/ontology", "/api/brain/ontology/types/product_line")  # 온톨로지 탭(설계서 2026-11-12 7절)
SECRET_NAMES = ("여닫이 문짝", "문짝 재량 규칙", "문짝 맞춤 규칙")


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


@pytest.fixture
def people(app):
    who = world(db_session)
    org = PartnerOrg(name="합성 협력사")
    db_session.add(org)
    db_session.commit()
    partner = User(username="bs_partner", password="x", name="합성", role="PARTNER", team=None, is_active=True,
                   partner_org_id=org.id)
    db_session.add(partner)
    db_session.commit()
    who["partner"] = partner
    return {name: user.id for name, user in who.items()}  # 요청마다 세션이 닫혀 객체 대신 번호


@pytest.mark.parametrize("name", ["admin", "cs_mgr", "dr_mgr", "pr_mgr"])
def test_admin_and_layer_approver_managers_open_every_screen_and_api(app, people, name):
    client = _client(app, people[name])
    for path in PAGES + APIS:
        assert client.get(path).status_code == 200, (name, path)


@pytest.mark.parametrize("name", ["sales_mgr", "cs_staff", "viewer"])
def test_other_internal_roles_get_404_everywhere(app, people, name):
    client = _client(app, people[name])
    for path in PAGES + APIS:
        resp = client.get(path)
        assert resp.status_code == 404, (name, path)
        body = resp.get_data(as_text=True)
        assert not any(secret in body for secret in SECRET_NAMES), (name, path)
    api = client.get("/api/brain/type-map").get_json()
    assert api == {"success": False, "data": None, "error": "찾을 수 없습니다."}


def test_switched_off_admin_cannot_open(app, people):
    client = _client(app, people["off_admin"])
    page = client.get("/brain")
    assert page.status_code == 302 and "/login" in page.headers["Location"]
    assert client.get("/api/brain/type-map").status_code in (401, 404)


def test_partner_gets_the_same_answer_as_a_missing_address_and_no_brain_text(app, people):
    client = _client(app, people["partner"])
    missing_api = client.get("/api/brain/no-such-endpoint")
    for path in APIS:
        resp = client.get(path)
        assert resp.status_code == missing_api.status_code and resp.status_code != 200, path
        assert resp.get_json() == missing_api.get_json(), path
        assert not any(secret in resp.get_data(as_text=True) for secret in SECRET_NAMES)
    missing_page = client.get("/brain-no-such-page")
    for path in PAGES:
        resp = client.get(path)
        assert resp.status_code == missing_page.status_code and resp.status_code != 200, path
        assert resp.headers.get("Location") == missing_page.headers.get("Location"), path
    # 문지기를 지나도(판정 함수) 협력사 계정은 열 수 없다 — 화면 · API 의 404 판정과 같은 함수
    partner = db_session.get(User, people["partner"])
    assert screen_viewer(partner) is None and not can_open_screen(partner)


def test_signed_out_gets_401_on_api_and_login_on_pages(app, people):
    client = app.test_client()
    for path in APIS:
        resp = client.get(path)
        assert resp.status_code == 401, path
        assert resp.get_json()["success"] is False
    page = client.get("/brain")
    assert page.status_code == 302 and "/login" in page.headers["Location"]


def test_hidden_item_answers_exactly_like_a_missing_item(app, people):
    client = _client(app, people["cs_mgr"])
    hidden = client.get("/api/brain/items/common/discount")
    missing = client.get("/api/brain/items/common/nothing")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.get_json() == missing.get_json()
    assert client.get("/brain/items/common/discount").status_code == 404
    assert _client(app, people["admin"]).get("/api/brain/items/common/discount").status_code == 200  # 대조군


def test_read_blueprints_have_no_write_routes(app, people):
    client = _client(app, people["admin"])
    for path in ("/api/brain/search", "/api/brain/table", "/api/brain/items/common/door", "/api/brain/releases"):
        assert client.post(path, json={}).status_code in (403, 405), path  # 쓰기 가드(CSRF) 또는 없는 동작
    brain_rules = [r for r in app.url_map.iter_rules() if r.endpoint.startswith(("brain_api.", "brain_web."))]
    assert brain_rules and all(r.methods <= {"GET", "HEAD", "OPTIONS"} for r in brain_rules)


def test_bad_table_values_are_400_only_for_people_who_may_open(app, people):
    assert _client(app, people["admin"]).get("/api/brain/table?type=spec&layer=kitchen").status_code == 400
    assert _client(app, people["cs_staff"]).get("/api/brain/table?type=spec&layer=kitchen").status_code == 404


def test_menu_entry_shows_only_for_people_who_may_open(app, people):
    shown = _client(app, people["cs_mgr"]).get("/notices").get_data(as_text=True)
    hidden = _client(app, people["cs_staff"]).get("/notices").get_data(as_text=True)
    assert "data-foms-nav-brain" in shown and 'href="/brain"' in shown
    assert "data-foms-nav-brain" not in hidden and 'href="/brain"' not in hidden
    assert "data-foms-nav-brain" not in _client(app, people["sales_mgr"]).get("/notices").get_data(as_text=True)
