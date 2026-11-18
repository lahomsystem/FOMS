"""문장으로 고치기 API 권한 · 스위치 · CSRF(설계서 2026-11-18 7절 '볼 수 없는 사람은 404' · 11절 표 · D247).

- 스위치(``brain_change_request`` · ``brain_ui``)가 꺼졌으면 **모든 길이 404** — 관리자도. 켜졌어도 관리자 · 층 승인자 밖(다른 팀
  팀장 · 직원 · 보기만 · 꺼진 계정)은 404, 로그인 안 함 401. 상태 변화 0.
- 남의 묶음은 없는 묶음과 같은 404(관리자는 본다 · 되돌린다). 넣은 사람은 로그인 사용자에서만.
- 쓰기는 공용 CSRF 가드 뒤(토큰 없으면 403 · 묶음 줄 0).
- 11절 일곱 길이 답 꼴 ``{success, data, error}`` 로 돈다(대조군 — 같은 사람 · 스위치 켬).
합성 계정 · 합성 지식 · 가짜 AI 만.
"""

from __future__ import annotations

import os

import pytest
from itsdangerous import URLSafeSerializer
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChangeRequest
from foms.services.brain.store import current_object
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY
from tests.domains.test_brain_change_request import NEW_TEXT, OLD_TEXT, SENTENCE, answer_text, flags_on, upd, world
from tests.support.brain_chat_support import FakeClient

BASE = "/api/brain/change-requests"


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


@pytest.fixture
def ids(app, monkeypatch):
    people = world(db_session)
    fake = FakeClient(lambda _p: answer_text(updates=[upd("common/rule/assign", text=NEW_TEXT)],
                                             questions=["시공일은 누가 맞추나요?"]))
    fake.close = lambda: None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key")
    import foms.services.cs_agent.brain as cs_brain

    monkeypatch.setattr(cs_brain, "_default_client", lambda: fake)
    return {name: user.id for name, user in people.items()}


def _count():
    return db_session.scalar(select(func.count()).select_from(BrainChangeRequest))


def _paths(number):
    return [("post", BASE, {"text": SENTENCE}), ("get", BASE, None), ("get", f"{BASE}/{number}", None),
            ("post", f"{BASE}/{number}/answer", {"text": "출고 담당이 맞춰요"}),
            ("post", f"{BASE}/{number}/apply", {"skip": []}), ("post", f"{BASE}/{number}/discard", {}),
            ("post", f"{BASE}/{number}/revert", {})]


def _call(client, method, path, body):
    return client.post(path, json=body) if method == "post" else client.get(path)


def test_switch_off_hides_every_route_even_for_admin(app, ids, monkeypatch):
    for env in ("FOMS_GRAFT_BRAIN_UI", "FOMS_GRAFT_BRAIN_CHANGE_REQUEST"):
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
    admin = _client(app, ids["admin"])
    for method, path, body in _paths(1):
        resp = _call(admin, method, path, body)
        assert resp.status_code == 404, path
        assert resp.get_json() == {"success": False, "data": None, "error": "찾을 수 없습니다."}
    flags_on(monkeypatch)
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "0")  # 기대는 스위치(brain_ui)가 꺼져도 없다
    assert _call(admin, "get", BASE, None).status_code == 404
    assert _count() == 0


@pytest.mark.parametrize("name", ["sales_mgr", "cs_staff", "viewer", "off_admin"])
def test_people_who_cannot_use_it_get_404_and_nothing_changes(app, ids, monkeypatch, name):
    flags_on(monkeypatch)
    client = _client(app, ids[name])
    want = (401, 404) if name == "off_admin" else (404,)  # 꺼진 계정은 로그인 층이 먼저 막는다(401)
    for method, path, body in _paths(1):
        assert _call(client, method, path, body).status_code in want, (name, path)
    assert _count() == 0
    assert _client(app, None).post(BASE, json={"text": SENTENCE}).status_code == 401


def test_the_seven_routes_and_someone_elses_bundle(app, ids, monkeypatch):
    flags_on(monkeypatch)
    lead, admin = _client(app, ids["dr_mgr"]), _client(app, ids["admin"])
    made = admin.post(BASE, json={"text": SENTENCE, "created_by": ids["dr_mgr"]})
    assert made.status_code == 200 and made.get_json()["success"] is True
    data = made.get_json()["data"]
    assert data["status"] == "ready" and data["mine"] is True and data["questions"] == ["시공일은 누가 맞추나요?"]
    number = data["id"]
    assert db_session.get(BrainChangeRequest, number).created_by == ids["admin"]  # 본문의 사람 칸은 읽지 않는다
    for method, path, body in _paths(number)[2:]:  # 팀장에게 관리자의 묶음은 없는 것과 같다
        assert _call(lead, method, path, body).status_code == 404, path
    assert lead.get(BASE).get_json()["data"]["total"] == 0
    assert admin.get(f"{BASE}/{number}").get_json()["data"]["lines"][0]["key"] == "common/rule/assign"
    answered = admin.post(f"{BASE}/{number}/answer", json={"text": "출고 담당이 맞춰요"})
    assert answered.status_code == 200 and answered.get_json()["data"]["answers"][0]["answer"] == "출고 담당이 맞춰요"
    bad = admin.post(f"{BASE}/{number}/apply", json={"skip": "1"})
    assert bad.status_code == 400 and bad.get_json()["data"] == {"code": "shape"}
    applied = admin.post(f"{BASE}/{number}/apply", json={"skip": []})
    assert applied.status_code == 200 and applied.get_json()["data"]["status"] == "applied"
    assert admin.post(f"{BASE}/{number}/discard", json={}).status_code == 409  # 반영 뒤엔 버리지 않는다
    reverted = admin.post(f"{BASE}/{number}/revert", json={})
    assert reverted.status_code == 200 and reverted.get_json()["data"]["status"] == "reverted"
    db_session.expire_all()
    assert current_object(db_session, "common/rule/assign").text == OLD_TEXT
    listed = admin.get(f"{BASE}?page=1").get_json()["data"]
    assert listed["total"] == 1 and listed["items"][0]["id"] == number and listed["items"][0]["status"] == "reverted"


def test_admin_reverts_a_team_leads_bundle_but_cannot_apply_it(app, ids, monkeypatch):
    flags_on(monkeypatch)
    lead, admin = _client(app, ids["dr_mgr"]), _client(app, ids["admin"])
    number = lead.post(BASE, json={"text": SENTENCE}).get_json()["data"]["id"]
    assert admin.post(f"{BASE}/{number}/apply", json={}).status_code == 404  # 이대로 고치기는 넣은 사람만
    assert admin.get(f"{BASE}/{number}").get_json()["data"]["mine"] is False


def test_writes_need_a_csrf_token(app, ids, monkeypatch):
    flags_on(monkeypatch)
    client = _client(app, ids["admin"])
    app.config["WRITE_GUARD_ENABLED"] = True
    try:
        blocked = client.post(BASE, json={"text": SENTENCE})
        assert blocked.status_code == 403 and blocked.headers.get("X-Write-Guard") == "blocked"
        assert _count() == 0
        assert client.get(BASE).status_code == 200  # 읽기는 토큰 없이
        seed = os.urandom(16).hex()
        with client.session_transaction() as sess:
            sess[_CSRF_SESSION_KEY] = seed
        token = URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)
        passed = client.post(BASE, json={"text": SENTENCE}, headers={"X-CSRF-Token": token})
        assert passed.status_code == 200
    finally:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    assert _count() == 1


def test_mask_leak_and_shape_answers(app, ids, monkeypatch):
    flags_on(monkeypatch)
    import foms.services.brain.change_request as cr

    client = _client(app, ids["admin"])
    empty = client.post(BASE, json={"text": ""})
    assert empty.status_code == 400 and empty.get_json()["data"] == {"code": "shape"}
    monkeypatch.setattr(cr, "mask", lambda text: text)
    leak = client.post(BASE, json={"text": "연락처 010-2345-6789 도면 담당"})
    assert leak.status_code == 400 and leak.get_json()["data"] == {"code": "mask"}
    assert "010" not in leak.get_data(as_text=True) and _count() == 0
