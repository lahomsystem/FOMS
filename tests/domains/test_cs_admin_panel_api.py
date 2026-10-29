"""AI 상담팀원 관리 패널(설계서 16.1 · 단계 1) — 화면 · JSON API: ADMIN 만(401 · 403) · 쓰기는 CSRF · 정책 가드 ·
스위치 왕복(누가 · 언제) · 설정 저장(버전 대조 · 통째 거절 · 잠긴 칸 400) · 하루 상한은 WORKER 하트비트 값(web env 아님) ·
기록 탭 재료 · 저장 성공 글. 손님 글이 없는 합성 값만 쓴다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from itsdangerous import URLSafeSerializer
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.cs_agent import brain, loop, panel, turns
from foms.services.cs_agent import brain_spend as bs
from foms.services.cs_agent import settings as st
from foms.services.datetime_kst import now_utc_naive
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY
from models import SecurityLog, SideEffectWorkerHeartbeat, SystemSetting, SystemSettingReceipt, User

ROOT = Path(__file__).resolve().parents[2]
API = "/api/admin/cs-agent"
TEMPLATES = ("templates/admin/cs_agent.html", "templates/admin/partials/cs_agent_switch.html",
             "templates/admin/partials/cs_agent_brain.html", "templates/admin/partials/cs_agent_records.html")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "5")


def login(client, role="ADMIN", name="합성 관리자"):
    user = User(username=f"cs-panel-{role.lower()}", password=generate_password_hash("pw"), role=role, team="CS",
                name=name, is_active=True)
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, user.username, role
    return uid


@pytest.fixture
def flag(app):
    """설정 깃발(WRITE_GUARD_ENABLED · AUTH_POLICY_ENABLED)을 시험 동안만 켜고 되돌린다."""
    saved = {}

    def turn_on(name):
        saved.setdefault(name, app.config.get(name, saved))
        app.config[name] = True

    yield turn_on
    for name, value in saved.items():
        if value is saved:
            app.config.pop(name, None)
        else:
            app.config[name] = value


def worker_beat(cap):
    db_session.merge(SideEffectWorkerHeartbeat(worker_kind="CS_LOOP", last_heartbeat_at=now_utc_naive(),
                                               metadata_json={"outcome": "ok", bs.HEARTBEAT_CAP_KEY: cap}))
    db_session.commit()


def receipts(policy):
    db_session.expire_all()
    return db_session.query(SystemSettingReceipt).filter_by(policy_id=policy).order_by(SystemSettingReceipt.id).all()


def switch_value():
    db_session.expire_all()
    row = db_session.get(SystemSetting, loop.SWITCH_KEY)
    return None if row is None else row.setting_value


# ── 권한 ─────────────────────────────────────────────────────────────────
def test_anonymous_gets_401_and_non_admin_gets_403_json_and_nothing_is_written(client, env):
    assert client.get(f"{API}/state").status_code == 401
    login(client, role="STAFF")
    for method, path, body in (("get", "/state", None), ("post", "/switch/loop", {"on": False}),
                               ("post", "/switch/draft", {"mode": "memo"}),
                               ("post", "/settings", {"values": {"draft_effort": "max"}, "expected_version": 0})):
        resp = getattr(client, method)(f"{API}{path}", json=body)
        data = resp.get_json()
        assert (resp.status_code, data["success"], data["data"]) == (403, False, None), path
    assert switch_value() is None and receipts(panel.SWITCH_POLICY_ID) == receipts(st.POLICY_ID) == []
    page = client.get("/admin/cs-agent")
    assert page.status_code == 302  # 화면은 ADMIN 아니면 홈으로(기존 role_required 규약)


def test_admin_reads_the_state_with_defaults(client, env):
    login(client)
    resp = client.get(f"{API}/state")
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "private, no-store"
    data = resp.get_json()["data"]
    assert (data["switch"]["loop"], data["switch"]["draft"], data["settings"]["version"]) == ("on", "off", 0)
    assert [f["name"] for f in data["settings"]["fields"]] == [f.name for f in st.FIELDS]
    assert data["caps"] == {"worker": None, "worker_state": "unknown", "worker_seen": None, "panel": None,
                            "effective": None}  # web env(5)는 보지 않는다 — WORKER 하트비트가 아직 없다
    assert {f["name"] for f in data["settings"]["fields"] if f["locked"]} == st.LOCKED_FIELDS
    assert data["records"]["spend"]["usd"] == "0" and data["records"]["turns"]["total"] == 0
    assert data["records"]["heartbeat"]["at"] is None and data["changes"] == []


# ── 스위치 왕복 ──────────────────────────────────────────────────────────
def test_emergency_stop_round_trip_records_who_and_when(client, env):
    admin = login(client, name="합성 사장")
    stop = client.post(f"{API}/switch/loop", json={"on": False})
    assert stop.status_code == 200 and stop.get_json()["data"]["changed"] is True
    assert loop.read_switch(db_session) is False
    state = stop.get_json()["data"]["state"]["switch"]
    assert state["loop"] == "off" and state["loop_changed"]["by"] == "합성 사장"
    assert state["loop_changed"]["source"] == "panel"
    [receipt] = receipts(panel.SWITCH_POLICY_ID)
    assert receipt.actor_user_id == admin and receipt.response_body["data"]["at"] == switch_value()["changed_at"]
    assert db_session.query(SecurityLog).filter_by(action="CS_AGENT_SWITCH", user_id=admin).count() == 1
    again = client.post(f"{API}/switch/loop", json={"on": False})
    assert again.get_json()["data"]["changed"] is False and len(receipts(panel.SWITCH_POLICY_ID)) == 1  # 같은 값
    assert client.post(f"{API}/switch/loop", json={"on": True}).status_code == 200
    assert loop.read_switch(db_session) is True and len(receipts(panel.SWITCH_POLICY_ID)) == 2
    assert client.post(f"{API}/switch/loop", json={"on": "false"}).status_code == 400  # 글자 'false' 는 안 받는다
    loop.set_switch(db_session, on=False)  # 화면 밖(스크립트)에서 바꿈 — 기록이 없다
    outside = client.get(f"{API}/state").get_json()["data"]["switch"]["loop_changed"]
    assert (outside["source"], outside["by"]) == ("other", None)


def test_draft_switch_round_trip_keeps_the_loop_field(client, env):
    login(client)
    loop.set_switch(db_session, on=True)
    resp = client.post(f"{API}/switch/draft", json={"mode": "store"})
    assert resp.status_code == 200 and turns.draft_mode(db_session) == "store"
    value = switch_value()
    assert (value["loop"], value["draft_reason"]) == ("on", panel.PANEL_REASON)  # 다른 칸은 그대로
    changed = resp.get_json()["data"]["state"]["switch"]["draft_changed"]
    assert changed["source"] == "panel" and changed["by"] == "합성 관리자"
    for bad in ({"mode": "public"}, {"mode": None}, {}):
        assert client.post(f"{API}/switch/draft", json=bad).status_code == 400
    assert turns.draft_mode(db_session) == "store" and len(receipts(panel.SWITCH_POLICY_ID)) == 1
    assert client.post(f"{API}/switch/draft", json={"mode": "off"}).status_code == 200
    history = client.get(f"{API}/state").get_json()["data"]["changes"]
    assert [row["detail"] for row in history] == ["저장만 → 끔", "끔 → 저장만"]  # 새 것부터


# ── 설정 저장 ────────────────────────────────────────────────────────────
def test_settings_save_conflict_and_invalid_over_http(client, env):
    login(client)
    ok = client.post(f"{API}/settings", json={"values": {"draft_model": "claude-haiku-5-5"}, "expected_version": 0})
    assert ok.status_code == 200 and ok.get_json()["data"]["version"] == 1
    assert st.read_settings(db_session).model_for("draft") == "claude-haiku-5-5"
    stale = client.post(f"{API}/settings", json={"values": {"draft_effort": "max"}, "expected_version": 0})
    assert stale.status_code == 409 and stale.get_json()["data"] == {"current_version": 1}
    bad = client.post(f"{API}/settings", json={"values": {"draft_model": "claude-fable-5-1", "draft_effort": "max"},
                                               "expected_version": 1})
    assert bad.status_code == 400 and bad.get_json()["data"] == {"fields": ["draft_model"]}
    assert "claude-fable-5-1" not in bad.get_data(as_text=True)
    for body in ({"values": {"draft_effort": "max"}}, {"values": {"draft_effort": "max"}, "expected_version": "1"},
                 {"values": {"draft_effort": "max"}, "expected_version": True}):
        assert client.post(f"{API}/settings", json=body).status_code == 400
    same = client.post(f"{API}/settings", json={"values": {"draft_model": "claude-haiku-5-5"}, "expected_version": 1})
    assert same.status_code == 400 and same.get_json()["error"] == "바뀐 칸이 없습니다."
    assert st.read_settings(db_session).version == 1 and len(receipts(st.POLICY_ID)) == 1
    detail = client.get(f"{API}/state").get_json()["data"]["changes"][0]["detail"]
    assert detail == "초안 모델 Opus 5.5 → Haiku 5.5"


def test_a_locked_field_change_is_a_400_and_nothing_is_saved(client, env):
    login(client)
    locked = client.post(f"{API}/settings", json={"values": {"draft_effort": "max", "max_wait_business_days": 2},
                                                  "expected_version": 0})
    body = locked.get_json()
    assert locked.status_code == 400 and body["data"] == {"fields": ["max_wait_business_days"], "locked": True}
    assert "다음 단계" in body["error"] and db_session.get(SystemSetting, st.SETTINGS_KEY) is None
    same = client.post(f"{API}/settings", json={"values": {"draft_effort": "max", "max_wait_business_days": 1},
                                                "expected_version": 0})
    assert same.status_code == 200 and same.get_json()["data"]["changed"] == ["draft_effort"]  # 값 그대로면 받는다


def test_the_save_ceiling_and_the_shown_cap_come_from_the_worker(client, env, monkeypatch):
    login(client)
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "1")  # web env 는 보지 않는다(음성 대조)
    worker_beat("5")
    over = client.post(f"{API}/settings", json={"values": {"daily_cap_usd_panel": "5.01"}, "expected_version": 0})
    assert over.status_code == 400 and over.get_json()["data"] == {"fields": ["daily_cap_usd_panel"]}
    ok = client.post(f"{API}/settings", json={"values": {"daily_cap_usd_panel": "3"}, "expected_version": 0})
    caps = ok.get_json()["data"]["state"]["caps"]
    assert (caps["worker"], caps["worker_state"], caps["panel"], caps["effective"]) == ("5", "ok", "3.00", "3.00")


# ── CSRF · 정책 가드 ─────────────────────────────────────────────────────
def test_writes_need_a_csrf_token_reads_do_not(client, app, env, flag):
    flag("WRITE_GUARD_ENABLED")
    login(client)
    blocked = client.post(f"{API}/switch/loop", json={"on": False})
    assert blocked.status_code == 403 and blocked.headers.get("X-Write-Guard") == "blocked"
    assert loop.read_switch(db_session) is True and receipts(panel.SWITCH_POLICY_ID) == []
    assert client.get(f"{API}/state").status_code == 200  # 읽기는 토큰 없이
    seed = os.urandom(16).hex()
    with client.session_transaction() as sess:
        sess[_CSRF_SESSION_KEY] = seed
    token = URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)
    passed = client.post(f"{API}/switch/loop", json={"on": False}, headers={"X-CSRF-Token": token})
    assert passed.status_code == 200 and loop.read_switch(db_session) is False


def test_the_policy_guard_lets_only_admins_write(client, env, flag):
    flag("AUTH_POLICY_ENABLED")
    login(client, role="MANAGER")  # ADMIN_OPS — 매니저도 안 된다
    denied = client.post(f"{API}/switch/draft", json={"mode": "store"})
    assert denied.status_code == 403 and denied.headers.get("X-Auth-Policy") == "denied"
    assert turns.draft_mode(db_session) == "off"


# ── 화면 ─────────────────────────────────────────────────────────────────
def test_the_page_renders_three_tabs_for_an_admin(client, env):
    login(client)
    loop.set_switch(db_session, on=False)
    html = client.get("/admin/cs-agent").get_data(as_text=True)
    for needle in ("data-cs-agent-panel", "cs-tab-switch", "cs-tab-brain", "cs-tab-records", "감시 루프 멈춤",
                   "다시 켜기", "js/admin/cs-agent-panel.js", "/api/admin/cs-agent/settings", 'data-version="0"',
                   'data-setting="draft_model"', 'value="claude-haiku-5-5"', "WORKER 상한 확인 안 됨",
                   "상한을 올리면 다음 바퀴부터 다시", "비상 정지는 PC 시범 메모도 멈춥니다 · 초안 끔은 서버 초안만 멈춥니다",
                   "만들던 초안은 메모 없이 저장만 합니다"):
        assert needle in html, needle
    assert "이미 도는 바퀴는 끝까지 돕니다" not in html  # 바퀴 도중 끄기(R8) 뒤로 틀린 글
    assert "claude-fable" not in html and "env 천장 $5" not in html  # 고를 수 없는 모델 · web env 는 화면에 없다
    worker_beat("7")
    html = client.get("/admin/cs-agent").get_data(as_text=True)
    assert "WORKER env 천장 $7" in html and 'max="7"' in html
    admin_menu = (ROOT / "templates/admin/admin.html").read_text(encoding="utf-8")
    assert "url_for('admin.cs_agent_panel')" in admin_menu


def test_locked_fields_render_disabled_with_a_next_step_badge(client, env):
    login(client)
    html = client.get("/admin/cs-agent").get_data(as_text=True)
    for name in st.FIELD_BY_NAME:
        start = html.index(f'data-setting="{name}"')
        tag = html[html.rindex("<", 0, start):html.index(">", start)]
        assert ("disabled" in tag) == (name in st.LOCKED_FIELDS), name  # 고칠 수 있는 칸은 그대로 켜져 있다
    assert html.count("다음 단계</span>") >= len(st.LOCKED_FIELDS)


def test_templates_and_script_follow_the_frontend_rules():
    for rel in TEMPLATES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert 'style="' not in text and "<script>" not in text and "onclick" not in text, rel
    script = (ROOT / "static/js/admin/cs-agent-panel.js").read_text(encoding="utf-8")
    assert ".innerHTML" not in script and "jQuery" not in script and "$(" not in script
    assert "__FOMS_CS_AGENT_PANEL_BOUND" in script and "data.success" in script
    assert len(script.splitlines()) < 300
    assert "if (input.disabled) return;" in script  # 잠긴 칸은 보내지 않는다
    for call in ("sessionStorage.setItem", "sessionStorage.getItem", "sessionStorage.removeItem"):
        at = script.index(call)  # 저장소는 try 안에서만 쓴다 — 바로 앞 try 가 바로 앞 catch 보다 뒤에 있다
        assert script.rindex("try {", 0, at) > script.rfind("catch (", 0, at), call
    assert "showFlash();" in script  # 다시 읽은 뒤 저장 성공 글을 한 번 보인다
