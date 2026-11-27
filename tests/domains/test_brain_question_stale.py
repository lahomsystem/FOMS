"""③ 질문 카드 — 카드가 생긴 뒤 다루는 지식이 바뀌었나(``about.changed_since`` — 결함 2026-11-27) 서버 시험.

- 판정 둘: 카드 실음 칸에 대상 · 그때 판(``payload.target_version`` — 밤 배우기 카드 꼴)이 있으면 판 견줌, 없으면(계획 파일 카드
  꼴) 카드 생긴 시각 < 지금 판 기록 시각. 둘 다 카드 뒤 대상 고침 → 참, 그대로 → 거짓(대조군).
- 대상이 사라지면 카드 응답 · 답 저장 모두 오류 없이(다루는 지식 칸이 빠지고, '회사 지식이 맞아요'는 그대로 닫힌다).
- 한 번에 저장은 바뀐 뒤 답도 막지 않고 응답에 ``changed_since`` 를 싣는다(화면이 지금 글을 보고 고친 답).
- 속 칸(기록 시각)은 화면 응답에 나가지 않는다.
합성 계정 · 합성 항목만.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.brain import question_answer as qa
from foms.services.brain.about_fresh import RECORDED, about_changed
from foms.services.brain.apply import apply_change
from foms.services.brain.inbox import inbox
from foms.services.brain.proposals import Proposer, propose_create, propose_delete, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from tests.support.brain_review_support import review_world
from tests.support.brain_support import NOW, REASON, agent_judge, values

DOOR = "common/door"
LATER = NOW + datetime.timedelta(minutes=5)
SOON = LATER + datetime.timedelta(minutes=5)


@pytest.fixture(autouse=True)
def _agent_judge():
    with agent_judge():
        yield


@pytest.fixture
def admin(app):
    return review_world(db_session)["people"]["admin"]


def _card(admin, *, with_version: bool, n: int = 1):
    """엇갈림 카드(합성) — ``with_version`` 이면 밤 배우기 꼴(실음 칸 대상 · 그때 판), 아니면 계획 파일 꼴(근거만)."""
    target = current_object(db_session, DOOR)
    payload = {"target": DOOR, "target_version": target.version} if with_version else {"plan_action": "conflict"}
    card = propose_create(db_session, key=f"conflict/lahom-synth-stale-{n}", brand="COMMON", layer="common",
                          item_type="conflict", reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="",
                          values=values(f"합성 엇갈림 {n}", text="승인된 규칙과 다름\n합성 바깥 글", payload=payload),
                          evidence=["plan:synth#c1", f"about:{DOOR}"])
    db_session.commit()
    return card


def _edit_door(admin, text: str, when: datetime.datetime):
    door = current_object(db_session, DOOR)
    edit = propose_update(db_session, key=DOOR, base_version=door.version, after={"text": text}, reason=REASON,
                          proposer=Proposer.user(admin.id), now=when, known="")
    apply_change(db_session, edit.id, actor=admin, now=when)
    db_session.commit()


def _about(admin, card) -> list[dict]:
    got = inbox(db_session, viewer_of(admin), now=SOON)["cards"]
    return next(c for c in got if c["main"]["id"] == card.id)["main"]["about"]


@pytest.mark.parametrize("with_version", [True, False])
def test_changed_since_is_false_until_the_knowledge_is_edited_after_the_card(admin, with_version):
    card = _card(admin, with_version=with_version)
    before = _about(admin, card)
    assert [a["changed_since"] for a in before] == [False]  # 그대로 — 대조군
    assert RECORDED not in before[0]  # 속 칸은 화면에 나가지 않는다
    _edit_door(admin, "합성 문짝은 두 짝으로 나간다", LATER)
    after = _about(admin, card)
    assert [(a["key"], a["text"], a["changed_since"]) for a in after] == [(DOOR, "합성 문짝은 두 짝으로 나간다", True)]


def test_stored_version_wins_over_the_clock_and_the_clock_is_strict(admin):
    card = _card(admin, with_version=True)
    door = current_object(db_session, DOOR)
    item = {"key": DOOR, "version": door.version, RECORDED: NOW + datetime.timedelta(days=1)}
    assert about_changed(card, item) is False  # 판이 같으면 시각이 뒤여도 안 바뀜
    assert about_changed(card, {**item, "version": door.version + 1}) is True
    plain = _card(admin, with_version=False, n=2)
    assert about_changed(plain, {"key": DOOR, "version": 1, RECORDED: NOW}) is False  # 같은 시각은 안 바뀜
    assert about_changed(plain, {"key": DOOR, "version": 1, RECORDED: None}) is False
    assert about_changed(card, {"key": "common/other", "version": 9, RECORDED: LATER}) is True  # 다른 대상이면 시각으로


def test_gone_knowledge_drops_the_about_without_errors(admin):
    card = _card(admin, with_version=True)
    door = current_object(db_session, DOOR)
    gone = propose_delete(db_session, key=DOOR, base_version=door.version, reason=REASON, proposer=Proposer.user(admin.id),
                          now=LATER)
    apply_change(db_session, gone.id, actor=admin, now=LATER)
    db_session.commit()
    assert current_object(db_session, DOOR) is None
    assert _about(admin, card) == []
    got = qa.answer_question(db_session, card.id, actor=admin, code="knowledge_right", now=SOON)
    db_session.commit()
    assert got["saved"] is True and got["changed_since"] is False


def test_answer_after_a_later_edit_is_saved_and_says_so(admin):
    card = _card(admin, with_version=True)
    _edit_door(admin, "합성 문짝은 세 짝으로 나간다", LATER)
    door = current_object(db_session, DOOR)
    got = qa.answer_question(db_session, card.id, actor=admin, code="outside_right", text="합성 문짝은 네 짝으로 나간다",
                             base_version=door.version, now=SOON)
    db_session.commit()
    assert got["saved"] is True and got["changed_since"] is True  # 막지 않는다 — 사실만 싣는다
    assert current_object(db_session, DOOR).text == "합성 문짝은 네 짝으로 나간다"
    fresh = _card(admin, with_version=True, n=3)  # 지금 판으로 만든 카드 — 대조군
    plain = qa.answer_question(db_session, fresh.id, actor=admin, code="knowledge_right", now=SOON)
    db_session.commit()
    assert plain["changed_since"] is False
