"""AI 가 배운 것 — 승인 없이 바로 반영된 학습을 사장님이 나중에 살펴본다(사장님 2026-11-19 '즉시 반영 · 내가 확인하고 추후 수정 및
삭제').

- 목록: ADMIN 만(그 밖은 없는 것과 같다) · 아직 안 본 것 먼저 · AI 가 넣은 글 · 고치기 앞 글 · 지금 상태.
- [맞아요]: 지식은 그대로, 봤다는 것과 누른 사람만 남는다.
- [고치기]: 곧바로 새 판(사람 승인자 · 확신 '확정') · 살펴본 것으로 남는다.
- [지우기]: 새 지식은 지우기 · 고친 지식은 앞 글로 · 이은 링크는 빼기. 그 뒤 사람이 또 고친 지식은 되돌리지 않는다.
- 화면: ``/brain?tab=learned`` 는 ADMIN 만(그 밖 404) · 길잡이 줄도 ADMIN 에게만.
합성 계정 · 합성 항목 · 합성 판정자만(네트워크 0). 손님 글 · 직원 이름 · 금액 없음.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain import learned
from foms.services.brain.apply import AUTO_ACTION, AutoLearn, apply_change
from foms.services.brain.errors import BrainPermissionError, BrainTargetError
from foms.services.brain.proposals import Proposer, propose_create, propose_link, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_link, current_object
from foms.services.graft_flags import FLAGS
from models import SecurityLog
from tests.support.brain_screen_support import people
from tests.support.brain_support import NOW, agent_judge, create

AGENT = Proposer.agent_named("cs_handoff_learning")
EVIDENCE = ["case:1", "staff:mgr-1"]
LATER = NOW + datetime.timedelta(minutes=5)
NEW_TEXT = "손님이 문 처짐 사진을 보내면 경첩 조정 안내를 먼저 한다"
OLD_RULE = "문짝 맞춤 규칙 옛 글"
RULE_TEXT = "문짝 맞춤 규칙 — 경첩 자리는 위아래 같은 간격으로 둔다"


@pytest.fixture
def world(app):
    """사람 + 반영된 항목 둘 + AI 가 바로 넣은 것 셋(새 상황 · 제작 조건 고침 · 상황 → 제품 잇기)."""
    who = people(db_session)
    admin = who["admin"]
    create(db_session, admin, "common/door", name="여닫이 문짝")
    create(db_session, admin, "common/fit", item_type="build_rule", name="문짝 맞춤 규칙", text=OLD_RULE)
    auto = AutoLearn(admin.id)
    common = dict(reason="넘긴 상담 배우기 · 근거 상담 한 곳 — 합성 까닭", proposer=AGENT, evidence=EVIDENCE, now=NOW)
    with agent_judge():
        made = propose_create(db_session, key="lahom/sit-sag", brand="LAHOM", layer="cs", item_type="situation",
                              values={"name": "합성 문 처짐 사진", "text": NEW_TEXT, "status": "active", "visibility": "all",
                                      "evidence_kind": "case"}, known="", **common)
        apply_change(db_session, made.id, actor=None, now=NOW, auto=auto)
        fixed = propose_update(db_session, key="common/fit", base_version=1, after={"text": RULE_TEXT}, known="", **common)
        apply_change(db_session, fixed.id, actor=None, now=NOW + datetime.timedelta(minutes=1), auto=auto)
        tied = propose_link(db_session, op="link_add", kind="applies_to", from_key="lahom/sit-sag", to_key="common/door",
                            **common)
        apply_change(db_session, tied.id, actor=None, now=NOW + datetime.timedelta(minutes=2), auto=auto)
    db_session.commit()
    return {"people": who, "made": made.id, "fixed": fixed.id, "tied": tied.id}


def _items(person):
    return learned.learned_list(db_session, viewer_of(person))


def _change(change_id):
    db_session.expire_all()
    return db_session.get(BrainChange, change_id)


def test_only_the_owner_sees_what_the_ai_put_in_newest_first_with_what_it_wrote(world):
    admin = world["people"]["admin"]
    assert _items(world["people"]["cs_mgr"]) is None  # 상담팀장도 못 본다
    page = _items(admin)
    assert [item["id"] for item in page["items"]] == [world["tied"], world["fixed"], world["made"]]
    assert page["counts"] == {"new": 3, "seen": 0, "line": "아직 안 본 것 3개 · 본 것 0개"}
    tied, fixed, made = page["items"]
    assert (made["kind"], made["title"], made["text"], made["state"], made["seen"]) == (
        "새 지식", "합성 문 처짐 사진", NEW_TEXT, "live", False)
    assert (fixed["kind"], fixed["text"], fixed["before"], fixed["can_fix"]) == ("고침", RULE_TEXT, OLD_RULE, True)
    assert (tied["kind"], tied["text"], tied["can_fix"]) == ("잇기", "합성 문 처짐 사진 → 여닫이 문짝", False)
    row = current_object(db_session, "lahom/sit-sag")
    assert (row.human_approver_id, _change(world["made"]).decided_action) == (None, AUTO_ACTION)


def test_seen_keeps_the_knowledge_and_records_who_looked(world):
    admin = world["people"]["admin"]
    with pytest.raises(BrainPermissionError):
        learned.mark_seen(db_session, world["made"], actor=world["people"]["cs_mgr"], now=LATER)
    learned.mark_seen(db_session, world["made"], actor=admin, now=LATER)
    db_session.commit()
    change = _change(world["made"])
    assert (change.decided_action, change.decided_by) == (learned.SEEN, admin.id)
    assert current_object(db_session, "lahom/sit-sag").text == NEW_TEXT
    page = _items(admin)
    assert (page["counts"]["new"], page["counts"]["seen"], page["items"][-1]["seen"]) == (2, 1, True)  # 본 것은 뒤로
    with pytest.raises(BrainTargetError):  # 두 번 누르지 못한다
        learned.mark_seen(db_session, world["made"], actor=admin, now=LATER)
    assert db_session.scalar(select(SecurityLog.user_id).where(SecurityLog.action == "BRAIN_LEARNED_SEEN")) == admin.id


def test_fix_puts_the_owners_words_in_at_once_as_a_confirmed_version(world):
    admin = world["people"]["admin"]
    better = "손님이 문 처짐 사진을 보내면 경첩 조정 안내 영상을 먼저 보낸다"
    out = learned.fix(db_session, world["made"], actor=admin, after={"text": better}, now=LATER)
    db_session.commit()
    row = current_object(db_session, "lahom/sit-sag")
    assert (row.text, row.version, row.human_approver_id, row.confidence, out["version"]) == (
        better, 2, admin.id, "confirmed", 2)
    assert _change(world["made"]).decided_action == learned.SEEN
    item = next(i for i in _items(admin)["items"] if i["id"] == world["made"])
    assert (item["state"], item["now"], item["seen"]) == ("changed", better, True)


def test_undo_deletes_new_knowledge_restores_an_edit_and_removes_a_link(world):
    admin = world["people"]["admin"]
    learned.undo(db_session, world["tied"], actor=admin, now=LATER)
    assert current_link(db_session, "applies_to", "lahom/sit-sag", "common/door") is None
    learned.undo(db_session, world["fixed"], actor=admin, now=LATER)
    assert current_object(db_session, "common/fit").text == OLD_RULE
    learned.undo(db_session, world["made"], actor=admin, now=LATER)
    db_session.commit()
    assert current_object(db_session, "lahom/sit-sag") is None
    assert {_change(world[name]).decided_action for name in ("tied", "fixed", "made")} == {learned.UNDONE}
    assert _items(admin)["items"] == [] and _items(admin)["counts"]["line"] == "AI 가 바로 넣은 지식이 아직 없어요."


def test_undo_never_overwrites_what_a_person_changed_afterwards(world):
    admin = world["people"]["admin"]
    mine = propose_update(db_session, key="common/fit", base_version=2, after={"text": "문짝 맞춤 규칙 사람이 고친 글"},
                          reason="합성", proposer=Proposer.user(admin.id), now=LATER)
    apply_change(db_session, mine.id, actor=admin, now=LATER)
    db_session.commit()
    with pytest.raises(BrainTargetError):
        learned.undo(db_session, world["fixed"], actor=admin, now=LATER)
    db_session.rollback()
    assert current_object(db_session, "common/fit").text == "문짝 맞춤 규칙 사람이 고친 글"
    assert _change(world["fixed"]).decided_action == AUTO_ACTION


# ── API · 화면 ───────────────────────────────────────────────────────────
def _client(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
    return client


def test_api_is_owner_only_and_answers_in_the_usual_shape(app, world):
    admin, manager = _client(app, world["people"]["admin"]), _client(app, world["people"]["cs_mgr"])
    assert manager.get("/api/brain/learned").status_code == 404
    for path in ("seen", "fix", "undo"):
        denied = manager.post(f"/api/brain/learned/{world['made']}/{path}", json={"after": {"text": "합성"}})
        assert denied.status_code == 404 and denied.get_json()["error"] == "찾을 수 없습니다."
    listed = admin.get("/api/brain/learned").get_json()
    assert listed["success"] and len(listed["data"]["items"]) == 3
    assert admin.post(f"/api/brain/learned/{world['made']}/fix", json={"after": {"valid_to": "2027-01-01"}}).status_code == 400
    done = admin.post(f"/api/brain/learned/{world['made']}/seen", json={})
    assert (done.status_code, done.get_json()["data"]["message"]) == (200, "확인했어요.")
    assert admin.post(f"/api/brain/learned/{world['made']}/seen", json={}).status_code == 409
    gone = admin.post(f"/api/brain/learned/{world['fixed']}/undo", json={})
    assert gone.status_code == 200 and _change(world["fixed"]).decided_action == learned.UNDONE


def test_the_screen_view_and_its_nav_line_are_for_the_owner_only(app, world, monkeypatch):
    monkeypatch.setenv(f"{FLAGS['brain_ui']}_ENABLED", "1")
    monkeypatch.setenv(f"{FLAGS['brain_ui']}_COHORT", "all")
    owner, manager = _client(app, world["people"]["admin"]), _client(app, world["people"]["cs_mgr"])
    page = owner.get("/brain?tab=learned")
    body = page.get_data(as_text=True)
    assert page.status_code == 200 and "data-ds-learned>" in body and 'data-learned-url="/api/brain/learned"' in body
    assert "ds-inbox-learned.js" in body and 'data-ds-nav="learned"' in body and "style=" not in body
    assert manager.get("/brain?tab=learned").status_code == 404
    inbox = manager.get("/brain?tab=inbox").get_data(as_text=True)
    assert 'data-ds-nav="learned"' not in inbox and "data-learned-url" not in inbox
