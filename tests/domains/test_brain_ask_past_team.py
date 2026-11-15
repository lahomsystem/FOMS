"""물어보기 점검 2차(w2-17 · w2-18 · w2-19 · D233) — 가린 물음 칸 · 지난 질문 다시 보기 · 모름 답의 [○○팀에 묻기].

- 새 화면(``brain_ui``) 답 값: 가린 질문 · 가린 갈래와 수 · 찾은 지식 수 · 팀에 묻기 · 빈 지식에 올라감 — 원문(전화)은 어디에도 없다.
  두 스위치가 꺼진 사람의 답 값에는 새 칸이 없다(옛 화면 그대로).
- ``GET /api/brain/chat/questions/<번호>``: 다시 묻지 않는다(모델 부름 · 기록 · 하루 수 그대로). 내 질문만 — 남의 질문은 ADMIN 도 404.
  그 질문의 팀 묻기 알림을 받은 사람은 읽는다(피드백 칸 없음).
- ``POST …/ask-team``: 그 팀의 켜진 직원(물어보기를 여는 사람 · 묻는 사람 빼고)에게 FOMS 안 알림 한 줄씩, 같은 질문은 한 번만.
  남의 질문 404 · 모름이 아니거나 팀이 아닌 답 409.
합성 계정 · 합성 지식 · 가짜 모델만(바깥 호출 없음).
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainQuestion
from foms.services.brain.chat_answer import ask
from foms.services.brain.chat_settings import read_chat_settings
from foms.services.brain.chat_team_ask import BRAIN_ASK_TEAM_TYPE, team_ask_link
from foms.services.graft_flags import FLAGS
from models import Notification, User
from tests.support.brain_chat_support import FakeClient, chat_on, chat_world, reply
from tests.support.brain_support import person

PHONE = "010" + "5550" + "1234"  # 합성 휴대폰(실행 때 만든다)
QUESTION = f"슬라이딩 문 깊이 알려 주세요 손님 번호 {PHONE}"


@pytest.fixture
def ids(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    people = chat_world(db_session, stage="all")
    people["dr_staff"] = person(db_session, "bc_dr_staff", role="STAFF", team="DRAWING")
    people["dr_off"] = person(db_session, "bc_dr_off", role="STAFF", team="DRAWING", active=False)
    db_session.commit()
    return {name: user.id for name, user in people.items()}


def _brain_ui(monkeypatch):
    monkeypatch.setenv(f"{FLAGS['brain_ui']}_ENABLED", "1")
    monkeypatch.setenv(f"{FLAGS['brain_ui']}_COHORT", "all")


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _unknown(team="DRAWING"):
    return FakeClient(lambda _p: reply(unknown=True, ask_team=team, layer="drawing", confidence="low"))


def _ask(user_id, fake, question=QUESTION):
    data = ask(db_session, db_session.get(User, user_id), question, client=fake)
    db_session.commit()
    return data


def test_new_screen_answer_has_masked_question_kinds_count_and_team(ids, monkeypatch):
    _brain_ui(monkeypatch)
    data = _ask(ids["staff"], _unknown())
    assert data["unknown"] is True and PHONE not in json.dumps(data, ensure_ascii=False)  # 원문은 답 값 어디에도 없다
    assert "[전화]" in data["question"] and data["masked"] == [{"label": "전화", "n": 1}] and data["masked_count"] == 1
    assert data["found"] >= 1 and data["team"] == "DRAWING" and data["team_label"] == "도면팀" and data["team_sent"] is False
    assert data["gap"] is False  # 빈 지식 묶기가 꺼져 있으면 '빈 지식에 올렸어요'를 말하지 않는다
    row = db_session.get(BrainQuestion, data["id"])
    assert PHONE not in row.masked_question  # 기록도 가린 글


def test_gap_line_only_when_weekly_gaps_are_on(ids, monkeypatch):
    _brain_ui(monkeypatch)
    cfg = read_chat_settings(db_session)
    chat_on(db_session, stage="all", gap_enabled=True, per_person_daily=cfg.get("per_person_daily"))
    assert _ask(ids["staff"], _unknown())["gap"] is True
    owner = _ask(ids["staff"], _unknown("owner"))
    assert owner["gap"] is True and owner["team"] is None and owner["team_label"] == ""  # 사장님은 팀이 아니다 — 단추 없음


def test_old_screen_answer_keeps_its_fields(ids):
    data = _ask(ids["staff"], _unknown())
    assert not {"question", "masked", "masked_count", "found", "team", "gap"} & set(data)


def test_past_question_is_shown_again_without_asking_and_only_to_the_asker(app, ids, monkeypatch):
    _brain_ui(monkeypatch)
    fake = FakeClient(lambda _p: reply(answer="슬라이딩 문 장의 몸통 깊이는 합성 규격 650mm 입니다.",
                                       evidence_ids=["common/sliding"], unknown=False, confidence="high"))
    data = _ask(ids["staff"], fake)
    calls, rows = len(fake.calls), db_session.scalar(select(func.count()).select_from(BrainQuestion))
    resp = _client(app, ids["staff"]).get(f"/api/brain/chat/questions/{data['id']}")
    past = resp.get_json()["data"]
    assert resp.status_code == 200 and past["mine"] is True and past["question"] == data["question"]
    assert past["answer"] == data["answer"] and [c["key"] for c in past["evidence"]] == ["common/sliding"]
    assert past["evidence"][0]["name"] == "슬라이딩 깊이" and PHONE not in json.dumps(past, ensure_ascii=False)
    assert len(fake.calls) == calls and db_session.scalar(select(func.count()).select_from(BrainQuestion)) == rows
    state = _client(app, ids["staff"]).get("/api/brain/chat/state").get_json()["data"]
    assert state["left_today"] == int(read_chat_settings(db_session).get("per_person_daily")) - 1  # 다시 보기는 수를 안 쓴다
    for other in ("cs_mgr", "admin"):  # 남의 질문 — ADMIN 도 못 본다(없는 질문과 같은 답)
        assert _client(app, ids[other]).get(f"/api/brain/chat/questions/{data['id']}").status_code == 404
    assert _client(app, ids["staff"]).get("/api/brain/chat/questions/999999").status_code == 404


def test_past_question_is_hidden_when_the_new_screen_is_off(app, ids):
    data = _ask(ids["staff"], _unknown())
    assert _client(app, ids["staff"]).get(f"/api/brain/chat/questions/{data['id']}").status_code == 404


def test_ask_team_sends_one_foms_notification_per_team_member_once(app, ids, monkeypatch):
    _brain_ui(monkeypatch)
    data = _ask(ids["staff"], _unknown())
    staff = _client(app, ids["staff"])
    resp = staff.post(f"/api/brain/chat/questions/{data['id']}/ask-team", json={})
    body = resp.get_json()
    assert resp.status_code == 200 and body["data"]["sent"] == 2 and body["data"]["already"] is False
    notes = db_session.execute(select(Notification).where(Notification.notification_type == BRAIN_ASK_TEAM_TYPE)).scalars().all()
    assert sorted(n.target_user_id for n in notes) == sorted([ids["dr_mgr"], ids["dr_staff"]])  # 꺼진 계정 · 다른 팀 · 나 빼고
    assert all(n.target_type == "USER" and n.order_id is None for n in notes)
    assert {team_ask_link(n.message) for n in notes} == {f"/brain/ask?question={data['id']}"}
    assert all("[전화]" in n.message and PHONE not in n.message for n in notes)  # 가린 글만
    again = staff.post(f"/api/brain/chat/questions/{data['id']}/ask-team", json={}).get_json()["data"]
    assert again["already"] is True and again["sent"] == 0
    assert db_session.scalar(select(func.count()).select_from(Notification)
                             .where(Notification.notification_type == BRAIN_ASK_TEAM_TYPE)) == 2  # 같은 질문은 한 번만
    mine = staff.get(f"/api/brain/chat/questions/{data['id']}").get_json()["data"]
    assert mine["team_sent"] is True  # 다시 열어도 '보냈어요'
    got = _client(app, ids["dr_mgr"]).get(f"/api/brain/chat/questions/{data['id']}")
    assert got.status_code == 200 and got.get_json()["data"]["mine"] is False and got.get_json()["data"]["feedback"] is None
    assert _client(app, ids["cs_mgr"]).get(f"/api/brain/chat/questions/{data['id']}").status_code == 404


def test_ask_team_refuses_other_people_and_answers_without_a_team(app, ids, monkeypatch):
    _brain_ui(monkeypatch)
    data = _ask(ids["staff"], _unknown())
    assert _client(app, ids["cs_mgr"]).post(f"/api/brain/chat/questions/{data['id']}/ask-team", json={}).status_code == 404
    owner = _ask(ids["staff"], _unknown("owner"))
    resp = _client(app, ids["staff"]).post(f"/api/brain/chat/questions/{owner['id']}/ask-team", json={})
    assert resp.status_code == 409 and resp.get_json()["data"]["code"] == "no_team"
    assert db_session.scalar(select(func.count()).select_from(Notification)
                             .where(Notification.notification_type == BRAIN_ASK_TEAM_TYPE)) == 0
