"""③ 질문 카드 답 한 번에 저장(설계서 2026-11-26 온톨로지 잇기 3.2 · 카드 비평 S4 · S8 · S3) — 서비스 · API · 되돌리기 · 금액 알림.

- 답 셋 모두 액션 하나(``answer_question``)가 한 트랜잭션에서: 고칠 글이 있으면 고침 제안 · 반영 → 카드 닫기(답 코드) → 카드 줄에
  사장님이 적은 글 · 그 고침 번호. 결정 시간은 카드 닫는 줄에만 실제 값으로.
- 가운데서 막히면 모두 되돌린다(기준 판 바뀜 · 카드 닫기 실패 — 고아 고침 제안 · 반쯤 바뀐 지식 없음).
- 권한: ③ 은 사장님만 — 층 승인자 · 열 수 없는 사람은 없는 카드와 같은 404, 아무것도 안 바뀐다(대조군: 사장님은 저장).
- 방금 정한 것 되돌리기가 이 길로 닫힌 카드에서도 그대로 되고, 남긴 답은 빠진다.
- 금액 알림: 견적 계산기가 원본인 가격 규칙 · 옵션에 금액 꼴 글이면 먼저 한 번 묻는다(아무것도 안 씀) — 다시 보내면 저장.
  대조군: 금액 없는 글 · 계산기가 원본이 아닌 가격 규칙.
합성 계정 · 합성 항목만(금액 꼴은 지어낸 값).
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain import question_answer as qa
from foms.services.brain.answers import ANSWER_ACTION, card_answer
from foms.services.brain.decide import reopen_decision
from foms.services.brain.errors import BrainConflictError, BrainPermissionError, BrainShapeError, BrainTargetError
from foms.services.brain.proposals import Proposer, propose_create
from foms.services.brain.store import current_object
from models import SecurityLog
from tests.support.brain_review_support import DOC, review_world
from tests.support.brain_support import NOW, REASON, agent_judge, create, link, values

LATER = NOW + datetime.timedelta(minutes=5)
SOON = LATER + datetime.timedelta(minutes=1)
DOOR = "common/door"


@pytest.fixture(autouse=True)
def _agent_judge():
    with agent_judge():
        yield


@pytest.fixture
def world(app):
    return review_world(db_session)


def _card(admin, about=DOOR, n=1):
    """③ 엇갈림 카드(합성) — 실음 칸 대상 · 근거 ``about:`` 은 밤 배우기 카드와 같은 꼴."""
    target = current_object(db_session, about)
    card = propose_create(db_session, key=f"conflict/lahom-synth-answer-{n}", brand="COMMON", layer="common",
                          item_type="conflict", reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="",
                          values=values(f"합성 엇갈림 {n}", text="승인된 규칙과 다름\n합성 바깥 글",
                                        payload={"target": about, "target_version": target.version}),
                          evidence=["plan:synth#c1", f"about:{about}"])
    db_session.commit()
    return card


def _count(model, **where):
    return int(db_session.execute(select(func.count()).select_from(model).filter_by(**where)).scalar_one())


# ── 서비스: 답 셋 ─────────────────────────────────────────────────────────
def test_knowledge_right_closes_the_card_and_keeps_the_answer_without_an_edit(world):
    admin = world["people"]["admin"]
    card = _card(admin)
    before = current_object(db_session, DOOR)
    got = qa.answer_question(db_session, card.id, actor=admin, code="knowledge_right", view_ms=4200, now=LATER)
    db_session.commit()
    assert got == {"change_id": card.id, "code": "knowledge_right", "edit": None, "saved": True}
    row = db_session.get(BrainChange, card.id)
    assert (row.status, row.reject_code, row.decided_action, row.decided_by) == ("rejected", "knowledge_right", "reject", admin.id)
    assert card_answer(row.fields) == {"code": "knowledge_right", "text": None, "edit": None, "key": DOOR}
    assert current_object(db_session, DOOR).version == before.version  # 지식 글은 그대로
    assert _count(BrainChange, action=ANSWER_ACTION) == 0
    log = db_session.query(SecurityLog).filter_by(action="BRAIN_REJECT", target_id=card.id).one()
    assert log.detail["ms"] == 4200 and log.detail["code"] == "knowledge_right"  # 결정 시간이 실제 값으로(S8)


@pytest.mark.parametrize("code, typed, expect", [
    ("outside_right", "합성 문짝은 두 짝으로 나간다", "합성 문짝은 두 짝으로 나간다"),
    ("both_right", "  벽이 약하면 한 짝으로 나간다 ", None),  # 지금 글 끝에 적은 한 줄
])
def test_outside_and_both_edit_the_knowledge_then_close_and_keep_what_the_owner_typed(world, code, typed, expect):
    admin = world["people"]["admin"]
    card = _card(admin)
    before = current_object(db_session, DOOR)
    got = qa.answer_question(db_session, card.id, actor=admin, code=code, text=typed, base_version=before.version,
                             view_ms=2600, now=LATER)
    db_session.commit()
    now_row = current_object(db_session, DOOR)
    wanted = expect or f"{before.text.rstrip()}\n{typed.strip()}"
    assert (now_row.text, now_row.version) == (wanted, before.version + 1)
    edit = db_session.get(BrainChange, got["edit"])
    assert (edit.status, edit.action, edit.decided_action, edit.proposed_by, edit.decided_by) == (
        "applied", ANSWER_ACTION, "apply", f"user:{admin.id}", admin.id)
    assert edit.reason.startswith("사장님 답 — ") and f"질문 카드 {card.id}" in edit.reason  # 어느 카드의 답인지 남는다
    row = db_session.get(BrainChange, card.id)
    assert (row.status, row.reject_code) == ("rejected", code)
    assert card_answer(row.fields) == {"code": code, "text": typed.strip(), "edit": edit.id, "key": DOOR}
    apply_log = db_session.query(SecurityLog).filter_by(action="BRAIN_APPLY", target_id=edit.id).one()
    reject_log = db_session.query(SecurityLog).filter_by(action="BRAIN_REJECT", target_id=card.id).one()
    assert "ms" not in apply_log.detail and reject_log.detail["ms"] == 2600  # 답 하나에 결정 시간 하나


def test_shapes_and_targets_are_checked_before_anything_is_written(world):
    admin, ch = world["people"]["admin"], world["changes"]
    card = _card(admin)
    door = current_object(db_session, DOOR)
    for kwargs in ({"code": "knowledge_right", "text": "글"}, {"code": "outside_right"}, {"code": "other"}):
        with pytest.raises(BrainShapeError):
            qa.answer_question(db_session, card.id, actor=admin, base_version=door.version, now=LATER, **kwargs)
    with pytest.raises(BrainConflictError):  # 화면이 본 판이 지금 판과 다르다
        qa.answer_question(db_session, card.id, actor=admin, code="outside_right", text="합성 새 글",
                           base_version=door.version + 1, now=LATER)
    with pytest.raises(BrainTargetError):  # ② 보통 제안은 ③ 질문 카드가 아니다(대조군)
        qa.answer_question(db_session, ch["cs"], actor=admin, code="knowledge_right", now=LATER)
    with pytest.raises(BrainTargetError):  # 바뀐 글이 없다
        qa.answer_question(db_session, card.id, actor=admin, code="outside_right", text=door.text,
                           base_version=door.version, now=LATER)
    db_session.rollback()
    assert db_session.get(BrainChange, card.id).status == "open" and _count(BrainChange, action=ANSWER_ACTION) == 0


def test_only_the_owner_answers_a_question_card(world):
    people = world["people"]
    card = _card(people["admin"])
    for name in ("cs_mgr", "dr_mgr"):  # 층 승인자 MANAGER 도 ③ 은 못 정한다 — 없는 카드와 같은 답
        with pytest.raises(BrainPermissionError):
            qa.answer_question(db_session, card.id, actor=people[name], code="knowledge_right", now=LATER)
    with pytest.raises(BrainPermissionError):
        qa.answer_question(db_session, 999999, actor=people["admin"], code="knowledge_right", now=LATER)
    db_session.rollback()
    assert db_session.get(BrainChange, card.id).status == "open"


# ── 방금 정한 것 되돌리기 ──────────────────────────────────────────────────
def test_reopen_undoes_an_answer_saved_in_one_go_and_drops_the_kept_answer(world):
    admin = world["people"]["admin"]
    card = _card(admin)
    before = current_object(db_session, DOOR)
    got = qa.answer_question(db_session, card.id, actor=admin, code="outside_right", text="합성 문짝은 두 짝",
                             base_version=before.version, now=LATER)
    db_session.commit()
    reopen_decision(db_session, card.id, actor=admin, undo_edit=got["edit"], now=SOON)
    db_session.commit()
    now_row = current_object(db_session, DOOR)
    assert (now_row.text or "") == (before.text or "") and now_row.version == before.version + 2  # 앞 글로
    row = db_session.get(BrainChange, card.id)
    assert row.status == "open" and card_answer(row.fields) == {}  # 남긴 답도 빠진다
    assert row.fields["payload"]["after"]["target"] == DOOR  # 카드의 다른 칸은 그대로
    plain = _card(admin, n=2)
    qa.answer_question(db_session, plain.id, actor=admin, code="knowledge_right", now=LATER)
    db_session.commit()
    reopen_decision(db_session, plain.id, actor=admin, now=SOON)  # 고침 없는 답도
    db_session.commit()
    assert db_session.get(BrainChange, plain.id).status == "open"


# ── 금액 알림(S3) ─────────────────────────────────────────────────────────
def _price(admin, key, basis):
    create(db_session, admin, key, item_type="price_rule", name="합성 손잡이 값", text="합성 손잡이 값은 계산기를 따른다",
           checked_at="2026-10-20", payload={"doc_id": key.split("/")[-1], "basis": basis, **DOC})
    db_session.commit()


def test_money_on_a_calculator_priced_rule_asks_once_then_saves(world):
    admin = world["people"]["admin"]
    _price(admin, "common/synth-calc-price", "calc")
    card = _card(admin, about="common/synth-calc-price")
    row = current_object(db_session, "common/synth-calc-price")
    text = "합성 손잡이는 개당 12,345원이다"
    asked = qa.answer_question(db_session, card.id, actor=admin, code="outside_right", text=text,
                               base_version=row.version, now=LATER)
    db_session.commit()
    assert asked == {"change_id": card.id, "saved": False, "ask": qa.ASK_MONEY, "message": qa.MONEY_ASK}
    assert db_session.get(BrainChange, card.id).status == "open" and _count(BrainChange, action=ANSWER_ACTION) == 0
    assert current_object(db_session, "common/synth-calc-price").version == row.version  # 아무것도 쓰지 않았다
    saved = qa.answer_question(db_session, card.id, actor=admin, code="outside_right", text=text,
                               base_version=row.version, money_ok=True, now=LATER)
    db_session.commit()
    assert saved["saved"] is True and current_object(db_session, "common/synth-calc-price").text == text


def test_money_alert_controls_no_money_or_not_calculator_priced(world):
    admin = world["people"]["admin"]
    _price(admin, "common/synth-calc-price", "calc")
    _price(admin, "common/synth-brain-price", "brain")
    calc, brain = _card(admin, about="common/synth-calc-price"), _card(admin, about="common/synth-brain-price", n=2)
    plain = qa.answer_question(db_session, calc.id, actor=admin, code="both_right", text="합성 손잡이는 문짝마다 하나",
                               base_version=1, now=LATER)
    other = qa.answer_question(db_session, brain.id, actor=admin, code="outside_right", text="합성 손잡이는 3만 원이다",
                               base_version=1, now=LATER)
    assert plain["saved"] is True and other["saved"] is True


def test_calculator_source_and_money_shapes(world):
    admin = world["people"]["admin"]
    create(db_session, admin, "option/synth-handle", item_type="option", name="합성 손잡이")
    create(db_session, admin, "option/synth-plain", item_type="option", name="합성 받침")
    link(db_session, admin, "value_from", "option/synth-handle", "calc:option/3:5")
    db_session.commit()
    assert qa.calc_sourced(db_session, current_object(db_session, "option/synth-handle"))  # 계산기 자리로 가는 값 링크
    assert not qa.calc_sourced(db_session, current_object(db_session, "option/synth-plain"))  # 대조군 — 링크 없음
    assert not qa.calc_sourced(db_session, current_object(db_session, DOOR))  # 제품 라인은 대상이 아니다
    for text in ("15만원", "150,000원", "3천 원", "개당 2.5만 원"):
        assert qa.MONEY_RE.search(text), text
    for text in ("원본은 계산기", "합성 원목 문짝", "12원형 손잡이", "2단 선반", "값은 계산기 원래 값"):
        assert not qa.MONEY_RE.search(text), text


# ── API: 한 트랜잭션 · 권한 ───────────────────────────────────────────────
def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def test_api_saves_in_one_call_and_hides_the_card_from_everyone_else(app, world):
    people = {n: u.id for n, u in world["people"].items()}
    card_id = _card(world["people"]["admin"]).id
    version = current_object(db_session, DOOR).version
    body = {"code": "outside_right", "text": "합성 문짝은 두 짝", "base_version": version, "view_ms": 1800}
    for name in ("cs_mgr", "viewer", "sales_mgr"):  # 권한 없는 사람은 이 동작이 거절된다 — 없는 카드와 같은 404
        resp = _client(app, people[name]).post(f"/api/brain/proposals/{card_id}/answer", json=body)
        assert resp.status_code == 404 and resp.get_json() == {"success": False, "data": None, "error": "찾을 수 없습니다."}
    db_session.expire_all()
    assert db_session.get(BrainChange, card_id).status == "open" and _count(BrainChange, action=ANSWER_ACTION) == 0
    admin = _client(app, people["admin"])
    bad = admin.post(f"/api/brain/proposals/{card_id}/answer", json={**body, "money_ok": "yes"})
    assert bad.status_code == 400 and bad.get_json()["data"]["code"] == "BRAIN_SHAPE"
    done = admin.post(f"/api/brain/proposals/{card_id}/answer", json=body)
    assert done.status_code == 200 and done.get_json()["success"] is True
    data = done.get_json()["data"]
    assert data["saved"] is True and data["code"] == "outside_right" and data["message"] == "정했어요."
    twice = admin.post(f"/api/brain/proposals/{card_id}/answer", json={"code": "knowledge_right"})
    assert twice.status_code == 409 and twice.get_json()["data"]["code"] == "BRAIN_TARGET"  # 이미 정함


def test_api_rolls_back_everything_when_closing_the_card_fails(app, world, monkeypatch):
    """S4 — 지식은 바뀌었는데 카드는 열린 반쯤 된 상태가 남지 않는다(카드 닫기에서 막힘 → 고침 제안 · 새 판 모두 없음)."""
    people = {n: u.id for n, u in world["people"].items()}
    card_id = _card(world["people"]["admin"]).id
    version = current_object(db_session, DOOR).version

    seen = []

    def broken(session, *_a, **_k):
        seen.append(current_object(session, DOOR).version)  # 닫기 직전에는 지식이 이미 바뀌어 있다(시험이 헛돌지 않게)
        raise BrainTargetError("합성 — 닫기 실패")

    monkeypatch.setattr(qa, "reject_decision", broken)
    resp = _client(app, people["admin"]).post(f"/api/brain/proposals/{card_id}/answer",
                                              json={"code": "outside_right", "text": "합성 문짝은 두 짝",
                                                    "base_version": version})
    assert resp.status_code == 409 and resp.get_json()["data"]["code"] == "BRAIN_TARGET" and seen == [version + 1]
    db_session.expire_all()
    assert current_object(db_session, DOOR).version == version
    assert _count(BrainChange, action=ANSWER_ACTION) == 0 and db_session.get(BrainChange, card_id).status == "open"
    stale = _client(app, people["admin"]).post(f"/api/brain/proposals/{card_id}/answer",
                                               json={"code": "outside_right", "text": "합성 문짝은 두 짝",
                                                     "base_version": version + 3})
    assert stale.status_code == 409 and stale.get_json()["data"] == {"code": "BRAIN_BASE_CHANGED",
                                                                     "current_version": version}
