"""상담 AI 평가 API · 화면(설계서 2026-11-14-foms-graft 3.15 · D209 — T16) — 답 꼴 · 돌리기 · 설정 · 'AI 시험' 칸 자리.

완료 기준:
- ``POST /api/ai-staff/evals/run``: 처음(상한 0) 409 '돈 상한을 먼저 넣어 주세요.' · 묶음 0 이면 409 · 설정 뒤 202 + RQ ``default`` 에
  줄 일 하나 · 도는 중에 또 누르면 409 · 큐가 없으면 503(남은 줄이 단추를 막지 않는다 — web 에서 대신 돌리지 않는다).
- ``POST /api/ai-staff/evals/settings``: 저장 → ``GET /api/ai-staff/cs`` 의 ``evals.settings`` 에 보인다 · 틀린 값 400(칸 이름) · 그대로.
- ``GET /api/ai-staff/cs`` 만 ``evals`` 칸(줄 셋 · 틀린 차례 · 마지막 시험 · 도는 중)을 싣는다 — 다른 직원 답에는 없다.
- 화면: 'AI 시험' 자리(``data-ds-agents-evals``) 안에 조각 · ADMIN 만 돌리기 · 설정 주소와 칸 · 스크립트(defer · 내용 지문 핀) · CSS.
  MANAGER 화면에는 돌리기 · 설정이 없다. 새 파일 ``style="`` 0 · JS 300줄 아래 · ``innerHTML`` · ``fetch(`` 없음 · CSS 는 ``.fb-`` 머리.
- 스위치 끔: 쓰기 둘 · 읽기 모두 404, 설정 · 결과 줄을 만들지 않는다(지금과 같음).
합성 계정만 · 큐는 가짜(바깥 호출 없음).
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.ai_staff import evals
from foms.services.graft_flags import FLAGS
from models import SystemSetting, User
from tests.support.brain_screen_support import world

ROOT = Path(__file__).resolve().parents[2]
BASE = "/api/ai-staff"
NEW_FILES = ("templates/brain/ds/partials/agents_evals.html", "static/js/brain/ds/ds-agents-evals.js")
CSS = "static/css/contexts/brain/ds/brain-ds-agents-evals.css"
GOOD = {"cap_usd": "4", "past_size": 2, "risk_size": 1, "past_target_pct": 50}


class FakeQueue:
    """RQ ``Queue`` 흉내 — 넣은 것만 적는다(Redis 없음)."""

    name = "default"

    def __init__(self):
        self.calls = []

    def enqueue(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def _off_all(monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)


def _on(monkeypatch):
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "1")
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_COHORT", "all")


@pytest.fixture
def queue(monkeypatch):
    fake = FakeQueue()
    monkeypatch.setattr(evals, "get_rq_queue", lambda: fake)
    return fake


@pytest.fixture
def client(app, monkeypatch, queue):
    _off_all(monkeypatch)
    _on(monkeypatch)
    admin = User(username="ea_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                 is_active=True)
    db_session.add(admin)
    db_session.commit()
    test_client = app.test_client()
    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
    return test_client


def _body(resp, status):
    assert resp.status_code == status, resp.get_data(as_text=True)
    assert resp.headers["Cache-Control"] == "private, no-store"
    body = resp.get_json()
    assert set(body) == {"success", "data", "error"}
    return body


def _evals(client):
    return _body(client.get(f"{BASE}/cs"), 200)["data"]["evals"]


def test_run_is_refused_until_an_admin_sets_the_cap(client, queue):
    body = _body(client.post(f"{BASE}/evals/run", json={}), 409)
    assert body["success"] is False and body["error"] == "돈 상한을 먼저 넣어 주세요."
    assert body["data"]["code"] == "EVAL_NO_CAP" and queue.calls == []
    view = _evals(client)
    assert view["blocked"] == {"code": "EVAL_NO_CAP", "message": "돈 상한을 먼저 넣어 주세요."}
    assert view["settings"] == {"cap_usd": "0", "past_size": 0, "risk_size": 0, "past_target_pct": 0}
    _body(client.post(f"{BASE}/evals/settings", json={"cap_usd": "4"}), 200)
    sizes = _body(client.post(f"{BASE}/evals/run", json={}), 409)
    assert sizes["data"]["code"] == "EVAL_NO_SIZE" and sizes["error"] == "묶음 크기를 먼저 넣어 주세요."
    assert db_session.get(SystemSetting, evals.RESULTS_KEY) is None


def test_settings_then_run_queues_one_job_and_a_second_press_is_busy(client, queue):
    saved = _body(client.post(f"{BASE}/evals/settings", json=GOOD), 200)["data"]
    assert saved == GOOD
    first = _body(client.post(f"{BASE}/evals/run", json={}), 202)
    assert first["data"] == {"run": 1}
    assert queue.calls == [((evals.JOB_PATH, 1), {"job_id": "ai_staff_eval_1", "job_timeout": evals.JOB_TIMEOUT})]
    again = _body(client.post(f"{BASE}/evals/run", json={}), 409)
    assert again["data"]["code"] == "EVAL_BUSY" and again["error"] == "시험이 이미 도는 중이에요."
    assert len(queue.calls) == 1
    view = _evals(client)
    assert view["running"] is True and view["last"]["status_label"] == "줄 서는 중" and view["settings"] == GOOD
    assert [row["key"] for row in view["rows"]] == ["past", "risk", "cq"]
    assert view["rows"][0]["verdict"] == {"text": "아직", "tone": "warning"}  # 아직 숫자를 낸 시험이 없다


@pytest.mark.parametrize("payload", [
    {"cap_usd": "-1"}, {"cap_usd": "abc"}, {"cap_usd": True}, {"cap_usd": "0.0000001"}, {"past_size": -1},
    {"past_size": 3.5}, {"past_size": "3"}, {"risk_size": evals.MAX_SET + 1}, {"past_target_pct": 101},
    {"unknown": 1}, {}, [],
])
def test_bad_settings_are_rejected_and_nothing_changes(client, payload):
    body = _body(client.post(f"{BASE}/evals/settings", json=payload), 400)
    assert body["data"]["code"] == "EVAL_SHAPE" and body["error"] == "값이 맞지 않아요 — 다시 넣어 주세요."
    assert db_session.get(SystemSetting, evals.SETTINGS_KEY) is None


def test_queue_down_is_503_and_does_not_block_the_next_press(client, queue, monkeypatch):
    _body(client.post(f"{BASE}/evals/settings", json=GOOD), 200)
    monkeypatch.setattr(evals, "get_rq_queue", lambda: None)
    down = _body(client.post(f"{BASE}/evals/run", json={}), 503)
    assert down["data"] == {"code": "EVAL_QUEUE"} and down["error"] == "지금은 시험을 돌릴 수 없어요. 잠시 뒤 다시 해 주세요."
    last = _evals(client)["last"]
    assert last["status"] == evals.FAILED and last["reason"] == "줄이 없음"
    monkeypatch.setattr(evals, "get_rq_queue", lambda: queue)
    assert _body(client.post(f"{BASE}/evals/run", json={}), 202)["data"] == {"run": 2}


def test_only_the_cs_detail_carries_evals(client):
    assert "evals" in _body(client.get(f"{BASE}/cs"), 200)["data"]
    for key in ("ops", "ask", "drawing", "schedule"):
        assert "evals" not in _body(client.get(f"{BASE}/{key}"), 200)["data"], key


def _page(app, user_id):
    test_client = app.test_client()
    with test_client.session_transaction() as sess:
        sess["user_id"] = user_id
    resp = test_client.get("/brain?tab=agents")
    return resp.status_code, resp.get_data(as_text=True)


def test_the_screen_places_the_evals_block_admin_only_controls(app, monkeypatch):
    _off_all(monkeypatch)
    _on(monkeypatch)
    ids = {name: user.id for name, user in world(db_session).items()}
    status, body = _page(app, ids["admin"])
    assert status == 200
    place = re.search(r"data-ds-agents-evals>(.*?)</section>", body, re.S)
    assert place and "data-ds-evals " in place.group(1)  # 조각이 'AI 시험' 자리 안에 있다
    assert 'data-detail-url="/api/ai-staff/cs"' in body
    assert 'data-run-url="/api/ai-staff/evals/run"' in body and 'data-settings-url="/api/ai-staff/evals/settings"' in body
    assert "data-ds-evals-form" in body and "data-ds-agents-actions" in body
    scripts = re.findall(r'<script src="([^"]*ds-agents-evals\.js[^"]*)" defer></script>', body)
    assert len(scripts) == 1 and "?v=" in scripts[0]  # 내용 지문 핀(asset_url)
    assert re.search(r'href="[^"]*brain-ds-agents-evals\.css\?v=[^"]+"', body)
    assert 'style="' not in body and "배포를 막아요" not in body  # 없는 문지기는 쓰지 않는다
    status, manager = _page(app, ids["cs_mgr"])
    assert status == 200 and "data-ds-evals " in manager
    assert "data-run-url" not in manager and "data-settings-url" not in manager and "data-ds-evals-form" not in manager


def test_new_files_have_no_inline_style_and_stay_small():
    for name in NEW_FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert 'style="' not in text, name
        if name.endswith(".js"):
            assert len(text.splitlines()) < 300, name
            assert "innerHTML" not in text and "fetch(" not in text, name  # 글은 textContent · 요청은 brain-dom.js
            assert "__FOMS_DS_EVALS_BOUND" in text and "visibilitychange" in text and "pagehide" in text
    css = re.sub(r"/\*.*?\*/", "", (ROOT / CSS).read_text(encoding="utf-8"), flags=re.S)  # 설명 글은 빼고
    groups = [g.strip() for g in re.findall(r"([^{}]+)\{", css) if not g.strip().startswith("@")]
    assert groups  # 대조군 — 선택자를 하나도 못 읽으면 이 시험은 빈 시험이다
    for group in groups:
        for selector in group.split(","):
            assert selector.strip().startswith((".fb-evals", ".f-app .fb-evals")), selector


def test_switch_off_is_today(app, monkeypatch, queue):
    _off_all(monkeypatch)
    admin = User(username="ea_off_admin", password="x", role="ADMIN", name="합성", is_active=True)
    db_session.add(admin)
    db_session.commit()
    test_client = app.test_client()
    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
    assert test_client.post(f"{BASE}/evals/settings", json=GOOD).status_code == 404
    assert test_client.post(f"{BASE}/evals/run", json={}).status_code == 404
    assert test_client.get(f"{BASE}/cs").status_code == 404
    assert db_session.get(SystemSetting, evals.SETTINGS_KEY) is None
    assert db_session.get(SystemSetting, evals.RESULTS_KEY) is None and queue.calls == []
    page = test_client.get("/brain?tab=agents").get_data(as_text=True)
    assert "data-ds-evals" not in page and "ds-agents-evals.js" not in page
