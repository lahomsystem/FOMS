"""회사 지식 물어보기 화면 · API 권한 · CSRF · 설정(설계서 10.1 · 12절 · 13절 2 · D99 — ADMIN 2주 → 팀장 → 직원 전부).

- 여는 단계(``admin`` → ``leads`` → ``all``)대로만 화면 · API 가 열리고 그 밖은 404 — 협력사 · 꺼진 계정은 어느 단계에서도.
- 스위치가 꺼져 있으면 ADMIN 만 화면(설정)을 보고 묻기는 409, 그 밖은 404.
- 쓰기는 공용 CSRF 가드 뒤(토큰 없으면 403 · 기록 0) · 정책 manifest(``BRAIN_ASK`` · 설정은 ``ADMIN_OPS``).
- 설정 저장은 ADMIN 만 · 버전 대조 · 틀린 값 400. 에이전트 도구는 읽기 셋뿐.
합성 계정 · 합성 지식 · 가짜 모델만.
"""

from __future__ import annotations

import os

import pytest
from itsdangerous import URLSafeSerializer
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainQuestion
from foms.services.brain.chat_settings import read_chat_settings
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, load_policy_manifest
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY
from tests.support.brain_chat_support import FakeClient, chat_on, chat_world, reply

WRITES = {"brain_chat_api.brain_chat_ask": "BRAIN_ASK", "brain_chat_api.brain_chat_feedback": "BRAIN_ASK",
          "brain_chat_api.brain_chat_settings_save": "ADMIN_OPS"}


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


@pytest.fixture
def ids(app, monkeypatch):
    people = chat_world(db_session)
    fake = FakeClient(lambda _p: reply(answer="합성 규격 650mm 입니다.", evidence_ids=["common/sliding"], unknown=False))
    fake.close = lambda: None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key")
    import foms.services.cs_agent.brain as cs_brain

    monkeypatch.setattr(cs_brain, "_default_client", lambda: fake)
    return {name: user.id for name, user in people.items()}


def test_stage_setting_gates_the_page_and_the_api(app, ids):
    expected = {"admin": {"admin"}, "leads": {"admin", "cs_mgr", "sales_mgr"},
                "all": {"admin", "cs_mgr", "sales_mgr", "staff", "viewer"}}
    for stage, open_to in expected.items():
        chat_on(db_session, stage=stage)
        for name in ("admin", "cs_mgr", "sales_mgr", "staff", "viewer", "off"):
            client = _client(app, ids[name])
            state = client.get("/api/brain/chat/state")
            page = client.get("/brain/ask")
            if name in open_to:
                assert state.status_code == 200 and state.get_json()["data"]["can_ask"] is True, (stage, name)
                assert page.status_code == 200 and "data-brain-ask" in page.get_data(as_text=True), (stage, name)
            else:
                assert state.status_code in (401, 404) and page.status_code in (302, 404), (stage, name)  # 꺼진 계정 = 로그아웃
                ask = client.post("/api/brain/chat/ask", json={"question": "슬라이딩 깊이"})
                assert ask.status_code in (302, 401, 404), (stage, name)
    staff = _client(app, ids["staff"])
    assert staff.get("/brain").status_code == 302 and staff.get("/brain").headers["Location"].endswith("/brain/ask")
    assert _client(app, None).get("/api/brain/chat/state").status_code == 401


def test_partner_gets_the_same_answer_as_a_missing_address(app, ids):
    chat_on(db_session, stage="all")
    client = _client(app, ids["partner"])
    missing = client.get("/api/brain/no-such-endpoint")
    for path in ("/api/brain/chat/state", "/api/brain/chat/tools"):
        resp = client.get(path)
        assert resp.status_code == missing.status_code != 200 and resp.get_json() == missing.get_json(), path
    page = client.get("/brain/ask")
    assert page.status_code != 200 and page.status_code == client.get("/brain-no-such-page").status_code


def test_ask_and_feedback_over_http_and_switch_off(app, ids):
    admin = _client(app, ids["admin"])
    answered = admin.post("/api/brain/chat/ask", json={"question": "슬라이딩 깊이는?"})
    body = answered.get_json()
    assert answered.status_code == 200 and body["success"] is True and body["error"] is None
    assert body["data"]["evidence"][0]["key"] == "common/sliding" and body["data"]["card_links"] is True
    qid = body["data"]["id"]
    fb = admin.post(f"/api/brain/chat/questions/{qid}/feedback", json={"feedback": "helpful"})
    assert fb.status_code == 200 and db_session.get(BrainQuestion, qid).feedback == "helpful"
    other = _client(app, ids["admin2"]).post(f"/api/brain/chat/questions/{qid}/feedback", json={"feedback": "wrong"})
    assert other.status_code == 404  # 남의 질문은 없는 것과 같은 답
    bad = admin.post(f"/api/brain/chat/questions/{qid}/feedback", json={"feedback": "maybe"})
    assert bad.status_code == 400 and bad.get_json()["success"] is False
    empty = admin.post("/api/brain/chat/ask", json={"question": "  "})
    assert empty.status_code == 400 and empty.get_json()["data"]["code"] == "shape"
    chat_on(db_session, enabled=False)
    off = admin.post("/api/brain/chat/ask", json={"question": "슬라이딩 깊이는?"})
    assert off.status_code == 409 and off.get_json()["data"]["code"] == "off"
    assert admin.get("/api/brain/chat/state").get_json()["data"]["enabled"] is False  # ADMIN 은 설정을 본다
    assert _client(app, ids["cs_mgr"]).get("/api/brain/chat/state").status_code == 404


def test_writes_need_a_csrf_token_and_are_in_the_policy_manifest(app, ids):
    routes = load_policy_manifest()["routes"]
    for endpoint, policy in WRITES.items():
        assert routes[endpoint]["policy_id"] == policy and routes[endpoint]["mode"] == "guard", endpoint
    assert POLICY_REGISTRY["BRAIN_ASK"].viewer is True  # 단계 all 의 VIEWER 도 묻는다 — 단계 판정은 라우트가 다시
    chat_writes = {r.endpoint for r in app.url_map.iter_rules()
                   if r.endpoint.startswith("brain_chat_api.") and r.methods - {"GET", "HEAD", "OPTIONS"}}
    assert chat_writes == set(WRITES)
    client = _client(app, ids["admin"])
    app.config["WRITE_GUARD_ENABLED"] = True
    try:
        blocked = client.post("/api/brain/chat/ask", json={"question": "슬라이딩 깊이는?"})
        assert blocked.status_code == 403 and blocked.headers.get("X-Write-Guard") == "blocked"
        assert db_session.scalar(select(func.count()).select_from(BrainQuestion)) == 0
        seed = os.urandom(16).hex()
        with client.session_transaction() as sess:
            sess[_CSRF_SESSION_KEY] = seed
        token = URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)
        passed = client.post("/api/brain/chat/ask", json={"question": "슬라이딩 깊이는?"}, headers={"X-CSRF-Token": token})
        assert passed.status_code == 200
    finally:
        app.config.pop("WRITE_GUARD_ENABLED", None)


def test_settings_are_admin_only_versioned_and_checked(app, ids):
    admin, cs = _client(app, ids["admin"]), _client(app, ids["cs_mgr"])
    chat_on(db_session, stage="leads")
    assert cs.post("/api/brain/chat/settings", json={"changes": {"stage": "all"}, "version": 1}).status_code == 404
    version = admin.get("/api/brain/chat/state").get_json()["data"]["settings"]["version"]
    saved = admin.post("/api/brain/chat/settings", json={"changes": {"per_person_daily": 5, "stage": "all"},
                                                          "version": version})
    assert saved.status_code == 200 and saved.get_json()["data"]["cap_ready"] is True
    cfg = read_chat_settings(db_session)
    assert (cfg.get("per_person_daily"), cfg.stage, cfg.version) == (5, "all", version + 1)
    stale = admin.post("/api/brain/chat/settings", json={"changes": {"per_person_daily": 6}, "version": version})
    assert stale.status_code == 409
    wrong = admin.post("/api/brain/chat/settings", json={"changes": {"stage": "everyone"}, "version": version + 1})
    assert wrong.status_code == 400 and wrong.get_json()["data"]["fields"] == ["stage"]
    tools = admin.get("/api/brain/chat/tools").get_json()["data"]
    assert {t["name"] for t in tools["agent_tools"]} == {"brain_search_objects", "brain_get_object", "brain_neighbours"}
    assert tools["agent_write_actions"] == [] and tools["chat_offers"][0]["name"] == "propose_edit"


def test_brain_page_shows_the_ask_tab_only_inside_the_stage(app, ids):
    chat_on(db_session, stage="admin")
    admin_page = _client(app, ids["admin"]).get("/brain?tab=ask").get_data(as_text=True)
    assert 'data-brain-tab="ask"' in admin_page and "brain-ask-admin.js" in admin_page and "data-brain-ask" in admin_page
    cs_page = _client(app, ids["cs_mgr"]).get("/brain").get_data(as_text=True)
    assert 'data-brain-tab="ask"' not in cs_page and "brain-ask.js" not in cs_page
    chat_on(db_session, stage="leads")
    cs_page = _client(app, ids["cs_mgr"]).get("/brain").get_data(as_text=True)
    assert 'data-brain-tab="ask"' in cs_page and "brain-ask-admin.js" not in cs_page
