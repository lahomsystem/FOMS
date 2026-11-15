"""AI 직원 화면 점검 2차 고침(11-15 — 계획서 2026-11-14-foms-graft-plan '점검 2차' w3-13 ~ w3-20 · D233) — 서버가 내는 값.

완료 기준:
- w3-14 수준 꼬리표 색 갈래가 수준마다 다르다(0 read · 1 draft · 2 propose · 못 함 danger) — 초록(success) · 무채색 없음.
- w3-18 할 일 줄 '새로 붙음'은 판 1 이 원래 직원에게 더한 일만(상담 AI 제안 넷 · 물어보기 주문 읽기). 상담 AI 주문 읽기는 '있음'.
- w3-15 실행 기록 단계마다 상태(끝남 · 건너뜀 · 걸림 · 승인 대기 · 실패) — 훑기의 '건너뜀' 단계 · 실패한 실행의 마지막 단계도.
- w3-16 상담 AI 차례가 근거로 남긴 키가 있을 때만 '손님 · 주문 찾기' · '회사 지식 찾기' 단계(없으면 지어내지 않는다).
- w3-19 실행 기록 '담당'(차례를 보낸 직원 이름)은 ADMIN 에게 · 값이 있을 때만.
- w3-13 아직 도는 시험의 줄 꼬리표는 판정 없이 '도는 중'(끝나면 판정).
- w3-20 물어보기 평가가 돌면 마지막 점수 한 줄이 남고(수만) '지식 물어보기' 자세히의 'AI 시험' 칸에 보인다.
- D233 지시문 보기: ADMIN 만(MANAGER 404) · 직원마다 오는 곳(상담 초안 지시문 · 물어보기 지시문 · 규칙 목록 · 저장소 밖 한 줄) ·
  비밀 · 손님 자료 꼴 없음 · 화면에는 ADMIN 에게만 단추 · 창.
합성 계정 · 합성 차례 · 합성 항목만. 바깥 호출 없음.
"""

from __future__ import annotations

import datetime
import json
import re

import pytest

from db import db_session
from foms.persistence.graft.models import AiAgentRun, ErpActionProposal
from foms.services.ai_staff import ask_eval, evals, evals_view
from foms.services.ai_staff.views import staff_detail, staff_list
from foms.services.brain.scope import viewer_of
from foms.services.brain.usage_events import READER_CS_DRAFT, record_uses
from foms.services.datetime_kst import now_utc_naive
from foms.services.graft_flags import FLAGS
from models import CsAgentTurn, SystemSetting, User
from tests.support.brain_screen_support import world

BASE = "/api/ai-staff"


@pytest.fixture
def staff(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "1")
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_COHORT", "all")
    users = world(db_session)
    db_session.commit()
    return {name: user.id for name, user in users.items()}


def _user(uid):
    return db_session.get(User, uid)


def _client(app, uid):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return client


def _detail(uid, key):
    return staff_detail(db_session, viewer_of(_user(uid)), key, now_utc_naive())


def _turn(**extra):
    turn = CsAgentTurn(brand="LAHOM", chat_id=f"fx{extra.pop('n', 1)}", last_user_message_id="m1",
                       state=extra.pop("state", "posted"), latency_ms=7200, model="claude-sonnet-x", **extra)
    db_session.add(turn)
    db_session.commit()
    return turn


def _steps(user):
    return _detail(user, "cs")["run"]["steps"]


# ── w3-14 · w3-18 ────────────────────────────────────────────────────────
def test_level_tags_have_one_tone_per_level_and_no_green(staff):
    tones = {0: "read", 1: "draft", 2: "propose", None: "danger"}
    for key in ("cs", "ask", "ops", "schedule", "drawing"):
        for row in _detail(staff["admin"], key)["duties"]:
            assert row["tone"] == tones[row["level"]], (key, row["key"])
    tags = {item["key"]: item["tag"] for item in staff_list(db_session, viewer_of(_user(staff["admin"])))["agents"]}
    assert tags["cs"]["tone"] == "draft" and tags["ask"]["tone"] == "read" and tags["ops"]["tone"] == "warning"
    assert len(set(tones.values())) == 4 and "success" not in tones.values()


def test_only_duties_added_in_this_release_say_new(staff):
    cs = {row["key"]: row["new"] for row in _detail(staff["admin"], "cs")["duties"]}
    assert cs == {"cs_draft": False, "erp_read": False, "move_construction": True, "move_measurement": True,
                  "schedule_as_visit": True,  # D235 — 방문 옮기기(AS) 제안도 판 1 뒤에 붙은 일
                  "register_as": True, "add_construction_note": True, "send_measure_alimtalk": False}
    ask = {row["key"]: row["new"] for row in _detail(staff["admin"], "ask")["duties"]}
    assert ask == {"ask_answer": False, "erp_read": True}
    assert not any(row["new"] for row in _detail(staff["admin"], "ops")["duties"])  # 직원 전체가 '시험 중'


# ── w3-15 · w3-16 · w3-19 ────────────────────────────────────────────────
def test_cs_run_step_states_follow_the_turn(staff):
    turn = _turn(handoff=True, check_codes=["date_promise"])
    db_session.add(ErpActionProposal(action="move_construction", proposed_by="agent:cs", order_id=5, params={},
                                     preview=[], reason="합성", evidence=[], level=2, status="open",
                                     dedupe_key="fx:move:5", source_kind="cs_turn", source_ref=str(turn.id),
                                     created_at=now_utc_naive()))
    db_session.commit()
    steps = _steps(staff["admin"])
    assert [(s["what"], s["state"]) for s in steps] == [
        ("손님 글 읽기", "done"), ("초안 쓰기", "skipped"), ("위험 검사", "warn"), ("할 일 제안", "done"),
        ("승인 대기", "wait")]
    assert steps[-1]["detail"] == "1개 · 승인 전에는 안 바뀌어요"


def test_failed_turn_ends_on_a_failed_step(staff):
    _turn(state="failed", error_code="error", check_codes=None)
    steps = _steps(staff["admin"])
    assert [(s["what"], s["state"]) for s in steps] == [("손님 글 읽기", "done"), ("초안 쓰기", "failed")]


def test_evidence_steps_appear_only_when_the_turn_left_keys(staff):
    turn = _turn(check_codes=[])
    whats = [s["what"] for s in _steps(staff["admin"])]
    assert "손님 · 주문 찾기" not in whats and "회사 지식 찾기" not in whats  # 남긴 것이 없으면 지어내지 않는다
    record_uses(db_session, ["common/door", "erp:order/5"], READER_CS_DRAFT, "cs_turn", turn.id, now_utc_naive())
    db_session.commit()
    steps = _steps(staff["admin"])
    assert [s["what"] for s in steps][:4] == ["손님 글 읽기", "손님 · 주문 찾기", "회사 지식 찾기", "초안 쓰기"]
    assert steps[1]["tool"] == "erp.order.find" and steps[1]["detail"] == "주문 #5 · 손님 정보 가림"
    assert steps[2]["tool"] == "knowledge.search" and "여닫이 문짝" in steps[2]["detail"]
    assert all(s["state"] == "done" for s in steps)


def test_run_owner_is_shown_to_admin_only_and_only_when_known(staff):
    sender = User(username="fx_sender", password="x", name="합성 상담원", role="STAFF", team="CS", is_active=True)
    db_session.add(sender)
    db_session.commit()
    _turn(sent_by_user_id=sender.id, check_codes=[])
    assert _detail(staff["admin"], "cs")["run"]["who"] == "합성 상담원"
    assert _detail(staff["cs_mgr"], "cs")["run"]["who"] is None  # 직원 번호 · 이름은 ADMIN 만(R10-28)
    _turn(n=2, check_codes=[])  # 가장 새 차례 — 보낸 사람 없음
    assert _detail(staff["admin"], "cs")["run"]["who"] is None


def test_sweep_skip_steps_and_failed_runs_have_states(staff):
    now = now_utc_naive()
    db_session.add(AiAgentRun(agent="ops", started_at=now, total_ms=10, source_kind="sweep", outcome="done", proposals=0,
                              steps=[{"tool": "erp.order.list", "what": "건너뜀 — O2", "detail": "수준 0 — 제안 안 만듦"},
                                     {"tool": "erp.order.list", "what": "후보 고르기 — O1", "detail": "후보 0개"}]))
    db_session.commit()
    assert [s["state"] for s in _detail(staff["admin"], "ops")["run"]["steps"]] == ["skipped", "done"]
    db_session.add(AiAgentRun(agent="ops", started_at=now + datetime.timedelta(seconds=1), total_ms=10,
                              source_kind="sweep", outcome="failed", proposals=0,
                              steps=[{"tool": "erp.order.list", "what": "후보 고르기 — O1", "detail": "후보 0개"}]))
    db_session.commit()
    assert [s["state"] for s in _detail(staff["admin"], "ops")["run"]["steps"]] == ["failed"]


# ── w3-13 ───────────────────────────────────────────────────────────────
def _eval_run(status, done):
    now = now_utc_naive()
    run = {"id": 3, "status": status, "code": None, "actor_id": 1,
           "started_at": (now - datetime.timedelta(minutes=4)).isoformat(timespec="seconds"),
           "heartbeat_at": now.isoformat(timespec="seconds"),
           "finished_at": None if status == evals.RUNNING else now.isoformat(timespec="seconds"),
           "model": "claude-opus-5-5", "cost_usd": "0.42", "target_pct": 60,
           "past": {"total": 40, "done": done, "passed": round(done * 0.7)},
           "risk": {"total": 12, "done": 0 if status == evals.RUNNING else 12, "bad": 0}, "failures": []}
    row = db_session.get(SystemSetting, "ai_staff_eval_results")
    if row is None:
        db_session.add(SystemSetting(setting_key="ai_staff_eval_results", setting_value={"runs": [run]}))
    else:
        row.setting_value = {"runs": [run]}
    db_session.commit()


def test_running_eval_shows_no_verdict_until_it_ends(staff):
    _eval_run(evals.RUNNING, 17)
    view = evals_view.eval_view(db_session, viewer_of(_user(staff["admin"])), now=now_utc_naive(), erp=False)
    assert view["running"] is True
    assert view["rows"][0]["verdict"] == {"text": "도는 중", "tone": "primary"}
    assert view["rows"][0]["text"].endswith("17/40개 봄") and view["rows"][0]["pct"] == 71
    _eval_run(evals.DONE, 40)
    view = evals_view.eval_view(db_session, viewer_of(_user(staff["admin"])), now=now_utc_naive(), erp=False)
    assert view["rows"][0]["verdict"] == {"text": "통과", "tone": "success"}
    assert view["rows"][1]["verdict"] == {"text": "통과", "tone": "success"}


# ── w3-20 ───────────────────────────────────────────────────────────────
def test_ask_eval_keeps_only_numbers_and_shows_on_the_ask_screen(app, staff):
    client = _client(app, staff["admin"])
    first = client.get(f"{BASE}/ask").get_json()["data"]["evals"]
    assert first["rows"] == [] and first["note"] == ask_eval.NO_RUN_NOTE
    score = {"answerable": 30, "hit": 27, "hit_rate": 0.9, "unanswerable": 10, "unknown_ok": 10, "unsupported": 0,
             "passed": True, "misses": ["q003", "q017", "q021"]}
    ask_eval.record_ask_eval(db_session, score, mode="answer", now=now_utc_naive())
    db_session.commit()
    stored = db_session.get(SystemSetting, ask_eval.ASK_EVAL_KEY).setting_value
    assert set(stored) == {"at", "mode", "answerable", "hit", "unanswerable", "unknown_ok", "unsupported", "passed"}
    view = client.get(f"{BASE}/ask").get_json()["data"]["evals"]
    row = view["rows"][0]
    assert row["label"] == "물어보기 평가 40개" and row["pct"] == 90 and row["verdict"] == {"text": "통과", "tone": "success"}
    assert row["text"] == "맞힘 90% · 기준 80% · 근거 없는 답 0 · 기준 0 · 지식에 없는 질문 '모름' 10/10"
    assert view["last"]["status_label"] == "답까지" and view["note"] == ""
    with pytest.raises(ValueError):
        ask_eval.record_ask_eval(db_session, {**score, "hit": 31}, mode="answer", now=now_utc_naive())


def test_ask_eval_script_records_the_last_score(app, staff, tmp_path):
    from scripts.maintenance import brain_chat_eval
    from tests.support.brain_chat_eval_set import QUESTIONS

    path = tmp_path / "set.json"
    path.write_text(json.dumps(QUESTIONS, ensure_ascii=False), encoding="utf-8")
    brain_chat_eval.main(["--set", str(path), "--retrieval-only", "--no-record"])
    assert ask_eval.read_ask_eval(db_session) is None
    brain_chat_eval.main(["--set", str(path), "--retrieval-only"])
    stored = ask_eval.read_ask_eval(db_session)
    assert stored is not None and stored["mode"] == "retrieval"
    assert (stored["answerable"], stored["unanswerable"]) == (30, 10)


# ── D233 지시문 보기 ─────────────────────────────────────────────────────
_SECRET_SHAPES = (r"sk-ant", r"sk-[A-Za-z0-9]{8}", r"Bearer ", r"api[_-]?key\s*[:=]", r"password", r"\b01[016789]-?\d{3,4}-?\d{4}\b",
                  r"https?://", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")


def test_instructions_come_from_each_agents_own_place_and_hold_no_secrets(app, staff):
    client = _client(app, staff["admin"])
    got = {}
    for key in ("cs", "ask", "ops", "schedule", "drawing"):
        resp = client.get(f"{BASE}/{key}/instructions")
        assert resp.status_code == 200 and resp.headers["Cache-Control"] == "private, no-store", key
        got[key] = resp.get_json()["data"]
    assert got["cs"]["kind"] == "prompt" and "꼭 지킬 것" in got["cs"]["sections"][0]["text"]
    assert got["ask"]["kind"] == "prompt" and "FOMS 회사 지식 물어보기" in got["ask"]["sections"][0]["text"]
    assert "{key}" not in got["ask"]["sections"][1]["text"]
    assert got["ops"]["kind"] == "rules" and re.search(r"^O1 · .+ → '.+' 제안 \(지금 수준 1 초안\)$",
                                                        got["ops"]["sections"][0]["text"], flags=re.M)
    assert got["schedule"]["sections"][0]["text"].startswith("S1 · ")
    assert got["drawing"] == {"key": "drawing", "label": "도면 AI 팀원", "kind": "outside",
                              "note": "도면 AI 팀원의 지시문은 FOMS 저장소 밖의 주 1회 루틴에 있어서 여기서 볼 수 없어요.",
                              "sections": []}
    text = json.dumps(got, ensure_ascii=False)
    for shape in _SECRET_SHAPES:
        assert not re.search(shape, text, flags=re.I), shape
    assert client.get(f"{BASE}/nope/instructions").status_code == 404


def test_instructions_are_admin_only_on_the_api_and_the_screen(app, staff):
    manager = _client(app, staff["cs_mgr"])
    resp = manager.get(f"{BASE}/cs/instructions")
    assert resp.status_code == 404 and "꼭 지킬 것" not in resp.get_data(as_text=True)
    page = manager.get("/brain?tab=agents").get_data(as_text=True)
    for mark in ("data-prompt-url", "data-ds-agents-prompt", "지시문 보기"):
        assert mark not in page, mark
    page = _client(app, staff["admin"]).get("/brain?tab=agents").get_data(as_text=True)
    assert 'data-prompt-url="/api/ai-staff/__KEY__/instructions"' in page
    assert "data-ds-agents-prompt-open" in page and '<dialog class="f-dialog fb-agents-prompt"' in page
    assert page.index("data-ds-agents-prompt-open") < page.index("data-ds-agents-duties")  # 머리 단추 자리
