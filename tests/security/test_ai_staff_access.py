"""AI 직원 API 권한(설계서 2026-11-14-foms-graft 3.10 · 7절) — 읽기: ADMIN + 회사 지식 화면을 여는 MANAGER, 비용 칸은 ADMIN 만,
수준 고치기는 ADMIN 만, 그 밖 404.

- 여는 사람(ADMIN · CS/DRAWING/PRODUCTION MANAGER): 목록 · 자세히 200. MANAGER 답에는 비용 열쇠가 없고 고치기 칸이 거짓.
- 못 여는 사람(다른 팀 MANAGER · STAFF · VIEWER): 404, 직원 이름 한 글자도 없음. 협력사: 앞 문지기 403(답에 값 없음).
  꺼진 ADMIN · 로그인 안 함: 401.
- 새 화면 스위치 끔(또는 사람 목록 밖): ADMIN 도 404(지금은 없는 길).
- 수준 고치기: MANAGER · STAFF 404 · 표 그대로 · 감사 줄 없음.
합성 계정만.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.ai_staff.levels import AUDIT_LEVELS_SAVED
from foms.services.ai_staff.registry import SETTINGS_KEY
from foms.services.ai_staff.views import staff_viewer
from foms.services.graft_flags import FLAGS
from models import PartnerOrg, SecurityLog, SystemSetting, User
from tests.support.brain_screen_support import people

BASE = "/api/ai-staff"
READS = (BASE, f"{BASE}/cs", f"{BASE}/ops")


@pytest.fixture
def who(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "1")
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_COHORT", "all")
    users = people(db_session)
    org = PartnerOrg(name="합성 협력사")
    db_session.add(org)
    db_session.commit()
    partner = User(username="as_partner", password="x", name="합성", role="PARTNER", team=None, is_active=True,
                   partner_org_id=org.id)
    db_session.add(partner)
    db_session.commit()
    users["partner"] = partner
    return {name: user.id for name, user in users.items()}


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


@pytest.mark.parametrize("name", ["admin", "cs_mgr", "dr_mgr", "pr_mgr"])
def test_openers_read_and_only_admin_sees_cost(app, who, name):
    client = _client(app, who[name])
    for path in READS:
        resp = client.get(path)
        assert resp.status_code == 200, (name, path)
        assert resp.headers["Cache-Control"] == "private, no-store"
    data = client.get(f"{BASE}/cs").get_json()["data"]
    assert ("cost" in data["usage"]) is (name == "admin")
    assert data["can_edit"] is (name == "admin")
    assert all(row["choices"] == [] for row in data["duties"]) is (name != "admin")


@pytest.mark.parametrize("name", ["sales_mgr", "cs_staff", "viewer", "partner"])
def test_others_get_nothing(app, who, name):
    client = _client(app, who[name])
    for path in READS:
        resp = client.get(path)
        assert resp.status_code == (403 if name == "partner" else 404), (name, path, resp.status_code)  # 협력사는 앞 문지기
        text = resp.get_data(as_text=True)
        assert "상담 AI" not in text and "운영 AI" not in text


@pytest.mark.parametrize("name", ["off_admin", None])
def test_logged_out_or_disabled_is_401(app, who, name):
    resp = _client(app, who[name] if name else None).get(BASE)
    assert resp.status_code == 401, resp.status_code
    assert "상담 AI" not in resp.get_data(as_text=True)


@pytest.mark.parametrize("cohort", [None, "999999"])
def test_switch_off_hides_the_api_even_from_admin(app, who, monkeypatch, cohort):
    if cohort:
        monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_COHORT", cohort)
    else:
        monkeypatch.delenv("FOMS_GRAFT_BRAIN_UI_ENABLED", raising=False)
    client = _client(app, who["admin"])
    for path in (*READS, f"{BASE}/levels"):
        resp = client.post(path, json={"levels": {"ops": {"advance_stage": 1}}}) if path.endswith("/levels") \
            else client.get(path)
        assert resp.status_code == 404, (path, resp.status_code)
    assert db_session.get(SystemSetting, SETTINGS_KEY) is None


@pytest.mark.parametrize("name", ["cs_mgr", "dr_mgr", "cs_staff", "viewer"])
def test_only_admin_saves_levels(app, who, name):
    resp = _client(app, who[name]).post(f"{BASE}/levels", json={"levels": {"ops": {"advance_stage": 1}}})
    assert resp.status_code == 404 and resp.get_json()["data"] is None
    assert db_session.get(SystemSetting, SETTINGS_KEY) is None
    assert db_session.query(SecurityLog).filter(SecurityLog.action == AUDIT_LEVELS_SAVED).count() == 0
    ok = _client(app, who["admin"]).post(f"{BASE}/levels", json={"levels": {"ops": {"advance_stage": 1}}})
    assert ok.status_code == 200
    log = db_session.query(SecurityLog).filter(SecurityLog.action == AUDIT_LEVELS_SAVED).one()
    assert log.user_id == who["admin"] and log.detail == {"changes": {"ops.advance_stage": [0, 1]}}


def test_staff_viewer_rule(app, who):
    users = {name: db_session.get(User, user_id) for name, user_id in who.items()}
    assert staff_viewer(None) is None
    assert staff_viewer(users["admin"]) is not None and staff_viewer(users["cs_mgr"]) is not None
    for name in ("sales_mgr", "cs_staff", "viewer", "partner", "off_admin"):
        assert staff_viewer(users[name]) is None, name
