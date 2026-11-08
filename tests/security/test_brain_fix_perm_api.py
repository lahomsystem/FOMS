"""승인 대기 ③(엇갈림 · 물어볼 것 만들기) API 권한(점검 F26 · 사장님 D167 · D152) — 화면에서 숨기는 것만이 아니라 API 길이 막힌다.

층 승인자 MANAGER(상담팀장 · 도면팀장)는 ③ 제안을 목록 · 알림 수 · 화면 탭 수에서 못 보고, 반영 · 거절 · ③ 답(거절 까닭 셋) ·
한꺼번에 승인 모두 없는 제안과 같은 **404**(한꺼번에는 그 줄이 실패로) — 제안은 열린 채. 대조군: ADMIN 은 같은 제안을 보고 답하고,
상담팀장의 ② 상담 층 고침 · ① 이름표만 고침은 그대로 된다. 합성 계정 · 합성 항목만.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain.constants import ANSWER_CODES
from foms.services.brain.proposals import Proposer, propose_create, propose_update
from foms.services.brain.store import current_object
from tests.support.brain_review_support import review_world
from tests.support.brain_support import NOW, REASON, agent_judge, values

NOT_FOUND = {"success": False, "data": None, "error": "찾을 수 없습니다."}


@pytest.fixture(autouse=True)
def _agent_judge():
    with agent_judge():
        yield


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _status(change_id):
    db_session.expire_all()
    return db_session.get(BrainChange, change_id).status


@pytest.fixture
def ids(app):
    world = review_world(db_session)
    admin = world["people"]["admin"]
    who = Proposer.user(admin.id)
    cs_q = propose_create(db_session, key="conflict/perm-api", brand="COMMON", layer="cs", item_type="conflict",
                          values=values("두 곳에 다르게 적혀 있어요", text="바깥 글과 회사 지식이 달라요"),
                          reason=REASON, proposer=who, now=NOW, known="",
                          evidence=["plan:synth#api", "about:cs/lesson/photo"])
    dr_q = propose_create(db_session, key="question/perm-api", brand="COMMON", layer="drawing", item_type="question",
                          values=values("도면 글을 고칠 곳이 있어요", text="최종본 규칙 글이 바깥 글과 달라요",
                                        visibility="team:DRAWING"),
                          reason=REASON, proposer=who, now=NOW, known="",
                          evidence=["plan:synth#api2", "about:drawing/rule/final"])
    door = current_object(db_session, "common/door")
    names = propose_update(db_session, key="common/door", base_version=door.version,
                           after={"payload": {**(door.payload or {}), "pref_label": "여닫이 문"}},
                           reason=REASON, proposer=who, now=NOW, known="")
    db_session.commit()
    return {"people": {n: u.id for n, u in world["people"].items()}, "changes": world["changes"],
            "cs_q": cs_q.id, "dr_q": dr_q.id, "names": names.id}


def _card_ids(client):
    return {c["main"]["id"] for c in client.get("/api/brain/inbox").get_json()["data"]["cards"]}


@pytest.mark.parametrize("name, key", [("cs_mgr", "cs_q"), ("dr_mgr", "dr_q")])
def test_layer_approver_cannot_see_or_decide_decide_cards_over_http(app, ids, name, key):
    client, change = _client(app, ids["people"][name]), ids[key]
    cards = _card_ids(client)
    assert change not in cards and cards  # 다른 카드는 보인다(빈 목록이 아님)
    count = client.get("/api/brain/inbox/count").get_json()["data"]["inbox"]
    assert count["cards"] == len(cards)
    page = client.get("/brain?tab=inbox").get_data(as_text=True)
    assert f'data-brain-count="inbox">{len(cards)}<' in page  # 화면 탭 수도 같은 수
    for path, body in ((f"/api/brain/proposals/{change}/apply", {"base_version": None}),
                       (f"/api/brain/proposals/{change}/apply", {"base_version": None, "edits": {"text": "고친 글"}}),
                       *((f"/api/brain/proposals/{change}/reject", {"code": code, "view_ms": 0})
                         for code in ("other", *ANSWER_CODES))):
        resp = client.post(path, json=body)
        assert resp.status_code == 404 and resp.get_json() == NOT_FOUND, (path, body)
    bulk = client.post("/api/brain/proposals/bulk-apply", json={"ids": [change]})
    assert bulk.status_code == 200 and bulk.get_json()["data"]["applied"] == []
    assert [f["id"] for f in bulk.get_json()["data"]["failed"]] == [change]
    assert _status(change) == "open"
    assert current_object(db_session, "conflict/perm-api") is None
    assert current_object(db_session, "question/perm-api") is None


def test_admin_sees_and_answers_decide_cards_and_cs_manager_keeps_names_and_content(app, ids):
    ch, people = ids["changes"], ids["people"]
    admin, cs = _client(app, people["admin"]), _client(app, people["cs_mgr"])
    assert {ids["cs_q"], ids["dr_q"]} <= _card_ids(admin)
    assert {ids["names"], ch["cs"]} <= _card_ids(cs)  # ① · ② 는 상담팀장 목록에 그대로(대조군)
    answered = admin.post(f"/api/brain/proposals/{ids['cs_q']}/reject", json={"code": "knowledge_right", "view_ms": 0})
    assert answered.status_code == 200 and answered.get_json()["data"]["code"] == "knowledge_right"
    applied = admin.post(f"/api/brain/proposals/{ids['dr_q']}/apply", json={"base_version": None})
    assert applied.status_code == 200
    names = cs.post(f"/api/brain/proposals/{ids['names']}/apply", json={"base_version": 1})
    assert names.status_code == 200  # D167 — 상담팀장 ① 승인 그대로
    content = cs.post(f"/api/brain/proposals/{ch['cs']}/reject", json={"code": "other"})
    assert content.status_code == 200  # ② 상담 층 승인자 규칙 그대로
    assert _status(ids["cs_q"]) == "rejected" and _status(ids["dr_q"]) == "applied"
    assert current_object(db_session, "common/door").payload["pref_label"] == "여닫이 문"
