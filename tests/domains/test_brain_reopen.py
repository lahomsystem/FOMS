"""방금 정한 것 되돌리기(사장님 2026-11-20 '잘못 선택했는데 고치려면?' · 상담 원장 D275) — 서비스 · API · 화면 스크립트.

- 내가 하루 안에 거절한 제안만 다시 열린다(대조군: 남이 거절한 것 · 하루 지난 것 · 열린 것 · 승인한 것은 대상 오류).
- ③ 질문 답으로 넣은 지식 고침은 앞 글로 되돌리고 연다. 그 지식이 뒤에 또 바뀌었으면 아무것도 하지 않는다.
- 화면: 거절 칩 · 질문 답 바로 뒤 [되돌리기] 한 줄 — 누르면 ``…/reopen`` 을 한 번 보내고 줄이 사라진다.

합성 자료만(금액 · 손님 글 · 직원 이름 없음).
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain.decide import REOPEN_WINDOW, apply_decision, reject_decision, reopen_decision
from foms.services.brain.errors import BrainPermissionError, BrainTargetError
from foms.services.brain.inbox import inbox
from foms.services.brain.proposals import Proposer, propose_create, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from models import SecurityLog
from tests.domains.test_brain_ds_inbox_js import NODE, _run, page  # noqa: F401 — page 는 fixture
from tests.domains.test_brain_fix_inbox_js import _card
from tests.support.brain_review_support import review_world
from tests.support.brain_support import NOW, REASON, agent_judge, values

LATER = NOW + datetime.timedelta(minutes=5)
SOON = LATER + datetime.timedelta(minutes=1)


@pytest.fixture(autouse=True)
def _agent_judge():
    with agent_judge():
        yield


@pytest.fixture
def world(app):
    return review_world(db_session)


def _question(admin, about_key="common/door"):
    return propose_create(db_session, key="conflict/lahom-synth-reopen", brand="COMMON", layer="common", item_type="conflict",
                          values=values("문짝 안내가 두 곳에 다르게 적혀 있어요", text="바깥 글은 이렇게 적혀 있어요"),
                          reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="",
                          evidence=["plan:synth#c1", f"about:{about_key}"])


def _ids(admin):
    return {c["main"]["id"] for c in inbox(db_session, viewer_of(admin), now=SOON)["cards"]}


# ── 서비스 ────────────────────────────────────────────────────────────────
def test_my_fresh_rejection_opens_again_and_leaves_an_audit_line(world):
    admin, change_id = world["people"]["admin"], world["changes"]["cs"]
    reject_decision(db_session, change_id, actor=admin, code="other", now=LATER)
    db_session.commit()
    assert change_id not in _ids(admin)
    reopen_decision(db_session, change_id, actor=admin, now=SOON)
    db_session.commit()
    row = db_session.get(BrainChange, change_id)
    assert (row.status, row.reject_code, row.decided_by, row.decided_at, row.decided_action) == ("open", None, None, None, None)
    assert row.base_changed_at is None and change_id in _ids(admin)  # 지식이 그대로면 '기준 판 바뀜' 표시도 없다
    log = db_session.query(SecurityLog).filter_by(action="BRAIN_REOPEN", target_id=change_id).one()
    assert log.user_id == admin.id and log.detail == {"code": "other", "action": "reopen"}
    reject_decision(db_session, change_id, actor=admin, code="other", now=SOON)  # 다시 연 것은 다시 정할 수 있다
    assert db_session.get(BrainChange, change_id).status == "rejected"


def test_only_my_own_rejection_inside_the_window_and_only_rejections(world):
    people, ch = world["people"], world["changes"]
    admin, cs_mgr = people["admin"], people["cs_mgr"]
    reject_decision(db_session, ch["cs"], actor=cs_mgr, code="other", now=LATER)
    db_session.commit()
    with pytest.raises(BrainTargetError):  # 남이 거절한 것 — 사장님이어도 '방금 내가 정한 것'이 아니다
        reopen_decision(db_session, ch["cs"], actor=admin, now=SOON)
    with pytest.raises(BrainTargetError):  # 하루 지남
        reopen_decision(db_session, ch["cs"], actor=cs_mgr, now=LATER + REOPEN_WINDOW + datetime.timedelta(seconds=1))
    with pytest.raises(BrainTargetError):  # 열린 제안(대조군)
        reopen_decision(db_session, ch["drawing"], actor=admin, now=SOON)
    with pytest.raises(BrainPermissionError):  # 결정할 수 없는 사람 · 없는 제안은 같은 답
        reopen_decision(db_session, ch["price"], actor=cs_mgr, now=SOON)
    with pytest.raises(BrainPermissionError):
        reopen_decision(db_session, 999999, actor=admin, now=SOON)
    apply_decision(db_session, ch["price"], actor=admin, base_version=1, now=LATER,
                   confirm={"field": "text", "value": "지역별 운임 새 기준"})
    with pytest.raises(BrainTargetError):  # 승인한 것은 이 길로 되돌리지 않는다
        reopen_decision(db_session, ch["price"], actor=admin, now=SOON)
    assert db_session.get(BrainChange, ch["cs"]).status == "rejected"
    reopen_decision(db_session, ch["cs"], actor=cs_mgr, now=LATER + REOPEN_WINDOW)  # 하루 꼭 채운 때까지는 된다
    assert db_session.get(BrainChange, ch["cs"]).status == "open"


def test_a_rejection_reopened_after_the_knowledge_moved_is_marked_stale(world):
    admin, ch = world["people"]["admin"], world["changes"]
    reject_decision(db_session, ch["cs"], actor=admin, code="other", now=LATER)
    other = propose_update(db_session, key="cs/lesson/photo", base_version=1, after={"text": "사진부터 받는다"},
                           reason=REASON, proposer=Proposer.user(admin.id), now=LATER, known="")
    apply_decision(db_session, other.id, actor=admin, base_version=1, now=LATER, confirm={"field": "text", "value": "사진부터 받는다"})
    reopen_decision(db_session, ch["cs"], actor=admin, now=SOON)
    assert db_session.get(BrainChange, ch["cs"]).base_changed_at == SOON  # 거절해 둔 동안 지식이 바뀌었다


def _answer(admin, code, new_text=None):
    """③ 질문 카드에 답한다 — 화면이 부르는 차례 그대로(고침 제안 → 승인 → 질문을 그 까닭으로 닫음). (질문, 고침 번호)."""
    q = _question(admin)
    door, edit_id = current_object(db_session, "common/door"), None
    if new_text is not None:
        edit = propose_update(db_session, key="common/door", base_version=door.version, after={"text": new_text},
                              reason="사장님 답 — 바깥 글이 맞아요", proposer=Proposer.user(admin.id), now=LATER, known="")
        apply_decision(db_session, edit.id, actor=admin, base_version=door.version, now=LATER,
                       confirm={"field": "text", "value": new_text})
        edit_id = edit.id
    reject_decision(db_session, q.id, actor=admin, code=code, now=LATER)
    db_session.commit()
    return q, edit_id


def test_knowledge_right_answer_comes_back_to_the_decide_bin(world):
    admin = world["people"]["admin"]
    q, _edit = _answer(admin, "knowledge_right")
    reopen_decision(db_session, q.id, actor=admin, now=SOON)
    db_session.commit()
    card = next(c for c in inbox(db_session, viewer_of(admin), now=SOON)["cards"] if c["main"]["id"] == q.id)
    assert card["bin"] == "decide" and card["main"]["about"][0]["key"] == "common/door"


def test_outside_right_answer_rolls_the_knowledge_back_then_opens_the_question(world):
    admin = world["people"]["admin"]
    before = current_object(db_session, "common/door")
    q, edit_id = _answer(admin, "outside_right", "실측 뒤 두 주 안")
    assert current_object(db_session, "common/door").text == "실측 뒤 두 주 안"
    reopen_decision(db_session, q.id, actor=admin, undo_edit=edit_id, now=SOON)
    db_session.commit()
    now_row = current_object(db_session, "common/door")
    assert (now_row.text or "") == (before.text or "") and now_row.version == before.version + 2  # 앞 글로 — 판은 새로 쌓인다
    back = db_session.get(BrainChange, now_row.change_id)
    assert (back.decided_action, back.rollback_of_version, back.decided_by) == ("reopen", before.version, admin.id)
    assert db_session.get(BrainChange, q.id).status == "open"
    log = db_session.query(SecurityLog).filter_by(action="BRAIN_REOPEN", target_id=q.id).one()
    assert log.detail == {"code": "outside_right", "action": "reopen", "undone_by": back.id}


def test_an_edit_changed_again_or_not_mine_blocks_the_whole_undo(world):
    people = world["people"]
    admin = people["admin"]
    q, edit_id = _answer(admin, "outside_right", "실측 뒤 두 주 안")
    with pytest.raises(BrainTargetError):  # 내 고침이 아닌 번호(대조군 — 열린 남의 제안)
        reopen_decision(db_session, q.id, actor=admin, undo_edit=world["changes"]["cs"], now=SOON)
    door = current_object(db_session, "common/door")
    again = propose_update(db_session, key="common/door", base_version=door.version, after={"text": "실측 뒤 세 주 안"},
                           reason=REASON, proposer=Proposer.user(admin.id), now=SOON, known="")
    apply_decision(db_session, again.id, actor=admin, base_version=door.version, now=SOON,
                   confirm={"field": "text", "value": "실측 뒤 세 주 안"})
    db_session.commit()
    with pytest.raises(BrainTargetError):  # 그 뒤에 또 바뀐 지식 — 뒤 고침을 덮지 않는다
        reopen_decision(db_session, q.id, actor=admin, undo_edit=edit_id, now=SOON)
    db_session.rollback()
    assert db_session.get(BrainChange, q.id).status == "rejected"  # 질문도 열리지 않는다
    assert current_object(db_session, "common/door").text == "실측 뒤 세 주 안"


# ── API ───────────────────────────────────────────────────────────────────
def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def test_api_reopens_for_the_decider_and_hides_from_everyone_else(app, world):
    people, ch = world["people"], world["changes"]
    people, ch = {n: u.id for n, u in people.items()}, dict(ch)
    cs = _client(app, people["cs_mgr"])
    assert cs.post(f"/api/brain/proposals/{ch['cs']}/reject", json={"code": "other", "view_ms": 0}).status_code == 200
    viewer = _client(app, people["viewer"]).post(f"/api/brain/proposals/{ch['cs']}/reopen", json={})
    hidden = cs.post(f"/api/brain/proposals/{ch['price']}/reopen", json={})  # 볼 수 없는 제안
    assert viewer.status_code == hidden.status_code == 404
    bad = cs.post(f"/api/brain/proposals/{ch['cs']}/reopen", json={"undo_edit": "x"})
    assert bad.status_code == 400 and bad.get_json()["data"]["code"] == "BRAIN_SHAPE"
    done = cs.post(f"/api/brain/proposals/{ch['cs']}/reopen", json={})
    assert done.status_code == 200
    assert done.get_json()["data"] == {"message": "되돌렸어요 — 다시 정해 주세요.", "change_id": ch["cs"]}
    twice = cs.post(f"/api/brain/proposals/{ch['cs']}/reopen", json={})
    assert twice.status_code == 409 and twice.get_json()["data"]["code"] == "BRAIN_TARGET"
    db_session.expire_all()
    assert db_session.get(BrainChange, ch["cs"]).status == "open"


# ── 화면 ──────────────────────────────────────────────────────────────────
UNDO = """
  const line = api.q('[data-ds-inbox-undo]');
  const look = () => ({ shown: api.shown(line), text: api.text(line.querySelector('[data-ds-inbox-undo-text]')),
                        status: api.text(api.q('[data-ds-inbox-status]')) });"""
#: 고침 제안(POST /api/brain/proposals)에 제안 번호를 돌려주는 가짜 fetch — 바탕 가짜는 번호를 주지 않는다.
WITH_IDS = """
  const plain = fetch;
  fetch = async function (url, init) {
    const res = await plain(url, init);
    if (init && init.method === 'POST' && url === '/api/brain/proposals') {
      return { status: 200, json: async () => ({ success: true, data: { change_id: 777 } }) };
    }
    return res;
  };"""


def _question_card(n: int) -> dict:
    card = _card(n, "decide")
    card["main"]["about"] = [{"key": "common/door", "title": "여닫이 문짝", "text": "옛 글", "version": 3}]
    return card


@NODE
def test_reject_chip_offers_one_undo_line_and_the_button_reopens(page, tmp_path):
    body = UNDO + """
      const before = look();
      const one = api.q('[data-ds-inbox-cards] [data-card-id="c1"]');
      await api.click(one.querySelector('[data-ds-act="reject"]'));
      await api.click(one.querySelector('[data-reject-code]'));
      const offered = look();
      const sent = api.posts.length;
      await api.click(line.querySelector('[data-ds-inbox-undo-do]'));
      const after = look();
      return { before: before, offered: offered, after: after, posts: api.posts.slice(sent) };"""
    got = _run(page("/brain?tab=inbox&bin=content"), body, cards=[_card(1, "content")], search="?tab=inbox&bin=content",
               tmp=tmp_path)
    assert got["before"]["shown"] is False
    assert got["offered"]["shown"] is True and got["offered"]["text"] == "방금 정한 것 「지식 1」"
    assert got["posts"] == [{"url": "/api/brain/proposals/10/reopen", "body": {}}]
    assert got["after"]["shown"] is False and got["after"]["status"] == "했어요."  # 가짜 서버의 끝난 말


@NODE
def test_question_answers_offer_undo_with_the_edit_they_made(page, tmp_path):
    body = UNDO + """
      const box = api.q('[data-ds-inbox-cards] [data-card-id="c1"]');
      await api.click(box.querySelector('[data-ds-answer="outside"]'));
      box.querySelector('[data-ds-answer-text="outside"]').value = '새 글';
      await api.click(box.querySelector('[data-ds-answer="outside-save"]'));
      const offered = look();
      const sent = api.posts.length;
      await api.click(line.querySelector('[data-ds-inbox-undo-do]'));
      const edited = api.posts.slice(sent);
      await api.click(api.q('[data-ds-inbox-cards] [data-card-id="c1"] [data-ds-answer="knowledge"]'));
      const plain = look();
      const from = api.posts.length;
      await api.click(line.querySelector('[data-ds-inbox-undo-do]'));
      return { offered: offered, edited: edited, plain: plain, last: api.posts.slice(from), end: look() };"""
    got = _run(page("/brain?tab=inbox&bin=decide"), body, cards=[_question_card(1)], search="?tab=inbox&bin=decide",
               before=WITH_IDS, tmp=tmp_path)
    assert got["offered"] == {"shown": True, "text": "방금 정한 것 「지식 1」", "status": "정했어요 — 바깥 글이 맞아요."}
    assert got["edited"] == [{"url": "/api/brain/proposals/10/reopen", "body": {"undo_edit": 777}}]
    assert got["plain"]["status"] == "정했어요 — 회사 지식이 맞아요." and got["plain"]["shown"] is True
    assert got["last"] == [{"url": "/api/brain/proposals/10/reopen", "body": {}}]  # 지식을 안 고친 답은 고침 번호 없이
    assert got["end"]["shown"] is False
