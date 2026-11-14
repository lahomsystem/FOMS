"""새 회사 지식 화면 권한(설계서 2026-11-14-foms-graft 5.2) — 스위치를 켜도 권한 규칙은 한 글자도 안 바뀐다.

- 여는 사람(켜진 ADMIN · CS/DRAWING/PRODUCTION 팀 MANAGER): 새 화면 200 — AI 직원 탭(``?tab=agents``)도.
- 못 여는 사람(다른 팀 MANAGER · STAFF · VIEWER): 새 화면 · AI 직원 탭 모두 **404**, 지식 글 한 글자도 없음.
- 협력사: 없는 주소와 똑같은 답. 로그인 안 함: 로그인으로. 꺼진 ADMIN: 로그인으로.
- 스위치가 켜진 사람 목록 밖이면 옛 화면(대조군).
- AI 직원 판정: 화면을 못 여는 사람(``None``) · ADMIN · MANAGER 가 아닌 Viewer 는 거짓.
합성 계정 · 합성 항목만.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.graft_flags import FLAGS
from foms.web.brain import _agents_open
from models import PartnerOrg, User
from tests.support.brain_screen_support import world

PAGES = ("/brain", "/brain?tab=inbox", "/brain?tab=recheck", "/brain?tab=releases", "/brain?tab=table",
         "/brain?tab=map", "/brain?tab=onto", "/brain?tab=agents", "/brain/items/common/door")
SECRET_NAMES = ("여닫이 문짝", "문짝 재량 규칙", "문짝 맞춤 규칙")


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


@pytest.fixture
def people(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "1")
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_COHORT", "all")
    who = world(db_session)
    org = PartnerOrg(name="합성 협력사")
    db_session.add(org)
    db_session.commit()
    partner = User(username="bds_partner", password="x", name="합성", role="PARTNER", team=None, is_active=True,
                   partner_org_id=org.id)
    db_session.add(partner)
    db_session.commit()
    who["partner"] = partner
    return {name: user.id for name, user in who.items()}


@pytest.mark.parametrize("name", ["admin", "cs_mgr", "dr_mgr", "pr_mgr"])
def test_openers_get_the_new_screens_including_agents(app, people, name):
    client = _client(app, people[name])
    for path in PAGES:
        resp = client.get(path)
        assert resp.status_code == 200, (name, path)
        assert "data-ds-shell" in resp.get_data(as_text=True), (name, path)


@pytest.mark.parametrize("name", ["sales_mgr", "cs_staff", "viewer"])
def test_other_internal_roles_get_404_on_every_new_screen(app, people, name):
    client = _client(app, people[name])
    for path in PAGES:
        resp = client.get(path)
        assert resp.status_code == 404, (name, path)
        body = resp.get_data(as_text=True)
        assert "data-ds-shell" not in body and not any(s in body for s in SECRET_NAMES), (name, path)


def test_partner_signed_out_and_switched_off_admin(app, people):
    partner = _client(app, people["partner"])
    missing = partner.get("/brain-no-such-page")
    for path in PAGES:
        resp = partner.get(path)
        assert resp.status_code == missing.status_code != 200, path
        assert resp.headers.get("Location") == missing.headers.get("Location"), path
    for client in (app.test_client(), _client(app, people["off_admin"])):
        for path in ("/brain", "/brain?tab=agents"):
            resp = client.get(path)
            assert resp.status_code == 302 and "/login" in resp.headers["Location"], path


def test_outside_the_cohort_keeps_the_old_screen(app, people, monkeypatch):
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_COHORT", str(people["cs_mgr"]))
    old = _client(app, people["dr_mgr"]).get("/brain?tab=agents").get_data(as_text=True)
    new = _client(app, people["cs_mgr"]).get("/brain?tab=agents").get_data(as_text=True)
    assert "data-brain-page" in old and "data-ds-shell" not in old
    assert "data-ds-shell" in new and 'data-ds-section="agents"' in new


def test_agents_tab_rule():
    assert _agents_open(None) is False
    assert _agents_open(SimpleNamespace(is_admin=True, role="ADMIN")) is True
    assert _agents_open(SimpleNamespace(is_admin=False, role="MANAGER")) is True
    assert _agents_open(SimpleNamespace(is_admin=False, role="STAFF")) is False
