"""상담 AI 평가 권한(설계서 2026-11-14-foms-graft 3.15 · 3.10 · 7절 — T16) — 돌리기 · 설정은 ADMIN 만, 결과는 화면을 여는 MANAGER 도,
돈 칸은 ADMIN 만, 그 밖 404.

- 돌리기 · 설정: 화면을 여는 MANAGER · 직원 · 보기만 404(설정 · 결과 줄 · 감사 줄 · 줄 일 0) · 협력사는 앞 문지기 403 · 로그인 안 함 ·
  꺼진 ADMIN 401. ADMIN 만 202 · 200 + 감사 줄(번호 · 수 · 칸 이름만).
- 결과 읽기(``GET /api/ai-staff/cs`` 의 ``evals``): MANAGER 는 줄 · 틀린 차례 · 마지막 시험(돈 없음)만 — 설정 · 돌리기 칸 · 돈 열쇠 없음.
- 쓰기 둘은 공용 CSRF · Origin 가드 뒤(토큰 없으면 403 · 상태 변화 0)이고 두 길 목록에 ``ADMIN_OPS`` 로 실려 있다.
합성 계정만 · 큐는 가짜.
"""

from __future__ import annotations

import os

import pytest
from itsdangerous import URLSafeSerializer

from db import db_session
from foms.services.ai_staff import evals
from foms.services.graft_flags import FLAGS
from foms.services.orders.order_mutation_policy import load_policy_manifest
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY, load_write_guard_manifest
from models import PartnerOrg, SecurityLog, SystemSetting, User
from tests.support.brain_screen_support import people

BASE = "/api/ai-staff"
GOOD = {"cap_usd": "4", "past_size": 2, "risk_size": 1, "past_target_pct": 50}
WRITES = {"ai_staff_api.ai_staff_evals_run": "/api/ai-staff/evals/run",
          "ai_staff_api.ai_staff_evals_settings": "/api/ai-staff/evals/settings"}


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
    partner = User(username="ev_partner", password="x", name="합성", role="PARTNER", team=None, is_active=True,
                   partner_org_id=org.id)
    db_session.add(partner)
    db_session.commit()
    users["partner"] = partner
    return {name: user.id for name, user in users.items()}


@pytest.fixture
def queue(monkeypatch):
    calls = []
    monkeypatch.setattr(evals, "get_rq_queue",
                        lambda: type("Q", (), {"enqueue": staticmethod(lambda *a, **k: calls.append((a, k)))})())
    return calls


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


def _nothing_written():
    assert db_session.get(SystemSetting, evals.SETTINGS_KEY) is None
    assert db_session.get(SystemSetting, evals.RESULTS_KEY) is None
    assert db_session.query(SecurityLog).filter(
        SecurityLog.action.in_((evals.AUDIT_SETTINGS, evals.AUDIT_RUN))).count() == 0


@pytest.mark.parametrize("name,status", [("cs_mgr", 404), ("dr_mgr", 404), ("sales_mgr", 404), ("cs_staff", 404),
                                         ("viewer", 404), ("partner", 403), ("off_admin", 401), (None, 401)])
def test_only_admin_runs_and_saves(app, who, queue, name, status):
    client = _client(app, who[name] if name else None)
    for path, body in ((f"{BASE}/evals/settings", GOOD), (f"{BASE}/evals/run", {})):
        resp = client.post(path, json=body)
        assert resp.status_code == status, (name, path, resp.status_code)
        text = resp.get_data(as_text=True)
        assert "돈 상한" not in text and "cap_usd" not in text
    _nothing_written()
    assert queue == []


def test_admin_runs_and_saves_with_audit_lines(app, who, queue):
    client = _client(app, who["admin"])
    assert client.post(f"{BASE}/evals/settings", json=GOOD).status_code == 200
    assert client.post(f"{BASE}/evals/run", json={}).status_code == 202
    assert len(queue) == 1
    saved = db_session.query(SecurityLog).filter(SecurityLog.action == evals.AUDIT_SETTINGS).one()
    assert saved.user_id == who["admin"] and saved.detail == {"changes": {
        "cap_usd": ["0", "4"], "past_size": [0, 2], "risk_size": [0, 1], "past_target_pct": [0, 50]}}
    run = db_session.query(SecurityLog).filter(SecurityLog.action == evals.AUDIT_RUN).one()
    assert run.user_id == who["admin"] and run.detail == {"run": 1, "past_size": 2, "risk_size": 1}
    assert evals.latest_results(db_session)[0]["actor_id"] == who["admin"]


@pytest.mark.parametrize("name", ["cs_mgr", "dr_mgr", "pr_mgr"])
def test_manager_reads_results_without_money_or_controls(app, who, queue, name):
    admin = _client(app, who["admin"])
    admin.post(f"{BASE}/evals/settings", json=GOOD)
    admin.post(f"{BASE}/evals/run", json={})
    mine = _client(app, who[name]).get(f"{BASE}/cs").get_json()["data"]["evals"]
    assert set(mine) == {"rows", "failures", "last", "running"}
    assert "cost" not in mine["last"] and mine["running"] is True
    full = admin.get(f"{BASE}/cs").get_json()["data"]["evals"]
    assert full["can_run"] is True and full["settings"] == GOOD and "cost" in full["last"]


@pytest.mark.parametrize("name", ["sales_mgr", "cs_staff", "viewer"])
def test_others_cannot_read_results(app, who, name):
    resp = _client(app, who[name]).get(f"{BASE}/cs")
    assert resp.status_code == 404 and "evals" not in resp.get_data(as_text=True)


def test_writes_need_a_csrf_token(app, who, queue):
    client = _client(app, who["admin"])
    app.config["WRITE_GUARD_ENABLED"] = True
    try:
        for path, body in ((f"{BASE}/evals/settings", GOOD), (f"{BASE}/evals/run", {})):
            blocked = client.post(path, json=body)
            assert blocked.status_code == 403 and blocked.headers.get("X-Write-Guard") == "blocked", path
        _nothing_written()
        seed = os.urandom(16).hex()
        with client.session_transaction() as sess:
            sess[_CSRF_SESSION_KEY] = seed
        token = URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)
        assert client.post(f"{BASE}/evals/settings", json=GOOD, headers={"X-CSRF-Token": token}).status_code == 200
    finally:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    assert queue == []


def test_write_routes_are_listed_as_admin_ops(app):
    policy, guard = load_policy_manifest()["routes"], load_write_guard_manifest()["routes"]
    for endpoint, rule in WRITES.items():
        assert policy[endpoint] == {"mode": "guard", "policy_id": "ADMIN_OPS", "rule": rule}, endpoint
        assert guard[endpoint] == {"mode": "guard", "rule": rule}, endpoint
    staff_writes = {r.endpoint for r in app.url_map.iter_rules()
                    if r.endpoint.startswith("ai_staff_api.") and r.methods - {"GET", "HEAD", "OPTIONS"}}
    assert staff_writes == {*WRITES, "ai_staff_api.ai_staff_levels"}  # 쓰기 길은 이 셋뿐 — 모두 목록에 있다
    assert all(endpoint in policy and endpoint in guard for endpoint in staff_writes)
