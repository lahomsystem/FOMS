"""접목판 ERP 읽기 API 권한(설계서 2026-11-14-foms-graft 3.7 · 3.8 · 7절) — 새 읽기 길 넷.

- ``GET /api/brain/chat/history``: 로그인 안 함 401 · 물어보기를 못 여는 사람 404 · 스위치가 꺼진 사람은 없는 주소와 같은
  답(지금과 같다) · 켠 사람은 **내 질문만**(남의 질문 · 묻는 사람 번호 · 답 글 없음).
- ``GET /api/brain/items/<키>/usage``: 켠 사람만 쓰인 곳 · 화면을 못 여는 사람 404 · 로그인 안 함 401 · 숨은 항목은 없는 항목과
  같은 답 · 꺼진 사람은 지금 길(키가 ``…/usage`` 로 끝나는 항목 카드) 그대로.
- ``GET /api/brain/ontology`` 의 ``erp`` 칸 · ``GET /api/brain/ontology/erp/<종류>``: 켠 사람만(꺼진 사람은 없는 주소와 같은 답).
- 협력사는 없는 주소와 같은 답. 모든 답은 ``Cache-Control: private, no-store``.
합성 계정 · 합성 항목만.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.persistence.brain.models import BrainQuestion
from foms.services.brain.usage_events import record_uses
from foms.services.datetime_kst import now_utc_naive
from foms.services.graft_flags import FLAGS
from models import PartnerOrg, User
from tests.support.brain_chat_support import chat_on
from tests.support.brain_screen_support import world
from tests.support.brain_support import create

NOT_FOUND = {"success": False, "data": None, "error": "찾을 수 없습니다."}
LONG = "슬라이딩 문 깊이는 얼마예요? " * 6


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)


def _on(monkeypatch, short="erp_read", cohort="all"):
    monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
    monkeypatch.setenv(f"{FLAGS[short]}_COHORT", cohort)


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


@pytest.fixture
def ids(app):
    who = world(db_session)
    create(db_session, who["admin"], "common/usage", name="쓰임 이름 항목")  # 키가 '/usage' 로 끝나는 항목(지금 길)
    org = PartnerOrg(name="합성 협력사")
    db_session.add(org)
    db_session.flush()
    who["partner"] = User(username="gr_partner", password="x", name="합성", role="PARTNER", is_active=True,
                          partner_org_id=org.id)
    db_session.add(who["partner"])
    now = now_utc_naive()
    for asker, text, minutes in ((who["admin"], LONG, 5), (who["admin"], "어제 물은 합성 질문", 60 * 24 + 5),
                                 (who["cs_mgr"], "남이 물은 합성 질문", 3), (who["admin"], "열흘 전 합성 질문", 60 * 240)):
        db_session.add(BrainQuestion(asked_at=now - datetime.timedelta(minutes=minutes), asker_id=asker.id,
                                     masked_question=text, answer="합성 답", unknown=text.startswith("어제"),
                                     ask_team="DRAWING" if text.startswith("어제") else None, confidence="high"))
    db_session.flush()
    first = db_session.query(BrainQuestion).filter_by(masked_question=LONG).one()
    record_uses(db_session, ["erp:order/4101"], "chatbot", "question", first.id, now)
    record_uses(db_session, ["common/fit"], "chatbot", "question", first.id, now)
    db_session.commit()
    chat_on(db_session, stage="leads")
    return {name: user.id for name, user in who.items()}


# ── 내 질문 목록 ─────────────────────────────────────────────────────────
def test_history_needs_a_switch_and_shows_only_my_questions(app, ids, monkeypatch):
    admin = _client(app, ids["admin"])
    off, missing = admin.get("/api/brain/chat/history"), admin.get("/api/brain/chat/no-such-endpoint")
    assert off.status_code == missing.status_code == 404 and off.get_data() == missing.get_data()  # 꺼짐 = 없는 주소
    _on(monkeypatch)
    resp = admin.get("/api/brain/chat/history")
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "private, no-store"
    data = resp.get_json()["data"]
    texts = [row["text"] for row in data["today"] + data["week"]]
    assert "남이 물은 합성 질문" not in texts and "열흘 전 합성 질문" not in texts
    assert data["today"][0]["text"] == LONG[:60] + "…"  # 가린 글 앞 60자
    first = data["today"][0]
    assert first["erp"] is True and first["unknown"] is False and first["certainty_label"] == "높음"
    assert set(first) == {"id", "text", "unknown", "erp", "certainty", "certainty_label", "ask_team", "ask_label",
                          "asked_at"}  # 묻는 사람 번호 · 답 글 없음
    yesterday = next(row for row in data["today"] + data["week"] if row["text"] == "어제 물은 합성 질문")
    assert yesterday["unknown"] is True and yesterday["erp"] is False and yesterday["ask_label"] == "도면팀"
    mine = _client(app, ids["cs_mgr"]).get("/api/brain/chat/history").get_json()["data"]
    assert [row["text"] for row in mine["today"] + mine["week"]] == ["남이 물은 합성 질문"]  # 대조군: 그 사람 것만


def test_history_doors_for_other_people(app, ids, monkeypatch):
    _on(monkeypatch, "brain_ui")  # 새 화면 스위치만 켜도 열린다
    assert _client(app, ids["admin"]).get("/api/brain/chat/history").status_code == 200
    assert _client(app, None).get("/api/brain/chat/history").status_code == 401
    assert _client(app, ids["cs_staff"]).get("/api/brain/chat/history").status_code == 404  # 단계 밖
    partner = _client(app, ids["partner"])
    missing = partner.get("/api/brain/no-such-endpoint")
    resp = partner.get("/api/brain/chat/history")
    assert resp.status_code == missing.status_code != 200 and resp.get_json() == missing.get_json()


# ── 쓰인 곳 ──────────────────────────────────────────────────────────────
def test_usage_is_behind_the_switch_and_keeps_todays_card_path(app, ids, monkeypatch):
    admin = _client(app, ids["admin"])
    off = admin.get("/api/brain/items/common/fit/usage")
    today = admin.get("/api/brain/items/common/fit/usage-nothing")  # 꺼짐 = 지금 카드 길(그런 키는 없다)
    assert off.status_code == 404 and off.get_json() == today.get_json() == NOT_FOUND
    card_off = admin.get("/api/brain/items/common/usage")
    assert card_off.status_code == 200 and card_off.get_json()["data"]["item"]["key"] == "common/usage"
    _on(monkeypatch)
    resp = admin.get("/api/brain/items/common/fit/usage")
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "private, no-store"
    data = resp.get_json()["data"]
    assert data["days"] == 14 and data["by_reader"]["chatbot"] == 1
    assert data["recent"][0]["agent_label"] == "지식 물어보기" and data["recent"][0]["text"] == LONG[:60] + "…"
    card_on = admin.get("/api/brain/items/common/usage")  # 켜도 '/usage' 로 끝나는 항목 카드는 그대로 열린다
    assert card_on.status_code == 200 and card_on.get_json()["data"]["item"]["key"] == "common/usage"


def test_usage_doors(app, ids, monkeypatch):
    _on(monkeypatch)
    assert _client(app, None).get("/api/brain/items/common/fit/usage").status_code == 401
    staff = _client(app, ids["cs_staff"]).get("/api/brain/items/common/fit/usage")
    assert staff.status_code == 404 and staff.get_json() == NOT_FOUND  # 화면을 못 여는 사람
    cs = _client(app, ids["cs_mgr"])
    hidden, missing = cs.get("/api/brain/items/common/discount/usage"), cs.get("/api/brain/items/common/nothing/usage")
    assert hidden.status_code == missing.status_code == 404 and hidden.get_json() == missing.get_json()
    assert _client(app, ids["admin"]).get("/api/brain/items/common/discount/usage").status_code == 200  # 대조군
    partner = _client(app, ids["partner"])
    assert partner.get("/api/brain/items/common/fit/usage").get_json() == partner.get("/api/brain/no-such").get_json()


# ── 온톨로지 ERP 칸 ──────────────────────────────────────────────────────
def test_ontology_erp_field_and_detail_only_when_on(app, ids, monkeypatch):
    admin = _client(app, ids["admin"])
    off = admin.get("/api/brain/ontology").get_json()["data"]
    assert "erp" not in off and "covered_before" not in off["cq"]
    off_detail, missing = admin.get("/api/brain/ontology/erp/order"), admin.get("/api/brain/no-such-endpoint")
    assert off_detail.status_code == 404 and off_detail.get_data() == missing.get_data()  # 꺼짐 = 없는 주소
    _on(monkeypatch)
    on = admin.get("/api/brain/ontology").get_json()["data"]
    assert len(on["erp"]["types"]) == 10 and on["cq"]["covered_before"] == off["cq"]["covered"]
    detail = admin.get("/api/brain/ontology/erp/order")
    assert detail.status_code == 200 and detail.get_json()["data"]["type"] == "erp:order"
    assert detail.headers["Cache-Control"] == "private, no-store"
    unknown = admin.get("/api/brain/ontology/erp/no_such")
    assert unknown.status_code == 404 and unknown.get_json() == NOT_FOUND
    assert _client(app, ids["cs_staff"]).get("/api/brain/ontology/erp/order").status_code == 404
    assert _client(app, None).get("/api/brain/ontology/erp/order").status_code == 401
    _on(monkeypatch, cohort=str(ids["cs_mgr"]))  # 목록 밖 ADMIN 은 꺼진 사람과 같다
    assert "erp" not in admin.get("/api/brain/ontology").get_json()["data"]
    assert "erp" in _client(app, ids["cs_mgr"]).get("/api/brain/ontology").get_json()["data"]
