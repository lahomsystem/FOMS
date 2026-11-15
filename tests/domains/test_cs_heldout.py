"""시험용으로 떼어 둔 상담(사용자 결정 D219) — 비율 칸 · 상담 단위 결정 규칙 · 차례를 만들 때 한 번 적기 · 배우기 길 모두에서 빠짐 ·
평가 '지난 상담' 묶음에 잡힘 · 0 이면 예전 그대로.

합성 상담 id · 합성 가린 글만(전화 꼴 숫자 · 금액 · 이름 없음). 두뇌 · 채널톡은 :mod:`tests.domains.test_cs_drafting` 의 가짜.
시각은 2026-11 KST(11-02 월요일).
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import event, select

from db import db_session, engine
from foms.services.ai_staff import evals
from foms.persistence.brain.vectors import vector_metadata
from foms.services.brain import embed_sources
from foms.services.cs_agent import (
    case_material, handoff_learning, heldout, photo_desc, photo_learning, turns, weekly_fix,
)
from foms.services.cs_agent import settings as st
from models import CsAgentTurn, CsAgentTurnPhoto, SystemSetting
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.support.cs_agent_fakes import at, keys, naive  # noqa: F401 — keys 는 fixture

NOW = at(2, 9)
QUESTION = "합성 선반 깊이가 어떻게 되나요"
REPLY = "합성 직원 답 — 선반 깊이는 규격표대로 안내드려요"
CHATS = tuple(f"uc-syn-{n}" for n in range(1000))


def first_chat(predicate) -> str:
    """합성 상담 id 가운데 조건에 맞는 첫 것(규칙이 결정적이라 늘 같은 것)."""
    return next(chat for chat in CHATS if predicate(chat))


def claim(chat: str, message: str, percent: int, now=NOW) -> CsAgentTurn:
    row = turns.claim_turn(db_session, "LAHOM", chat, message, now=now, held_out_percent=percent)
    db_session.commit()
    return row


def panel(**extra):
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, version=1, setting_value={**st.DEFAULTS, **extra}))
    db_session.commit()


# ── 칸 · 규칙 ────────────────────────────────────────────────────────────
def test_the_panel_field_starts_at_ten_percent_and_bad_values_mean_zero(app):
    field = st.FIELD_BY_NAME[heldout.HELD_OUT_FIELD]
    assert (field.kind, field.default, field.low, field.high, field.unit) == (st.KIND_INT, 10, 0, 100, "%")
    assert heldout.held_out_percent(st.read_settings(db_session)) == 10
    for bad in (True, "10", 10.5, None, -3):
        assert heldout.held_out_percent({heldout.HELD_OUT_FIELD: bad}) == 0
    assert heldout.held_out_percent({heldout.HELD_OUT_FIELD: 250}) == 100
    assert st.check_value(field, 101) == (False, None) and st.check_value(field, 0) == (True, 0)


@pytest.mark.parametrize("percent,low,high", [(0, 0, 0), (10, 70, 130), (100, 1000, 1000)])
def test_the_rule_holds_about_the_set_share_of_chats(percent, low, high):
    held = sum(heldout.rule_holds("LAHOM", chat, percent) for chat in CHATS)
    assert low <= held <= high


def test_the_same_chat_always_gets_the_same_answer_and_the_brand_is_part_of_it():
    first = [heldout.chat_bucket("LAHOM", chat) for chat in CHATS]
    assert first == [heldout.chat_bucket("LAHOM", chat) for chat in CHATS]
    assert all(0 <= bucket < 100 for bucket in first)
    assert first != [heldout.chat_bucket("HAUD", chat) for chat in CHATS]
    for chat in CHATS[:50]:  # 비율이 커지면 떼어 둔 상담은 그대로 떼어 둔 채 더해질 뿐이다
        assert not heldout.rule_holds("LAHOM", chat, 10) or heldout.rule_holds("LAHOM", chat, 20)


# ── 차례를 만들 때 한 번 ─────────────────────────────────────────────────
def test_percent_zero_is_todays_claim_and_reads_nothing_more(app):
    statements: list[str] = []

    def keep(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", keep)
    try:
        old = turns.claim_turn(db_session, "LAHOM", "uc-a", "m-1", now=NOW)
        zero = turns.claim_turn(db_session, "LAHOM", "uc-b", "m-1", now=NOW, held_out_percent=0)
        on = turns.claim_turn(db_session, "LAHOM", "uc-c", "m-1", now=NOW, held_out_percent=10)
    finally:
        event.remove(engine, "before_cursor_execute", keep)
    db_session.commit()
    assert (old.held_out, zero.held_out) == (False, False)
    assert on.held_out is heldout.rule_holds("LAHOM", "uc-c", 10)
    assert len(statements) == 2 + 2 + 3  # 넣기 + 다시 읽기 — 켠 때만 그 상담의 첫 차례를 한 번 더 읽는다


def test_a_new_chat_follows_the_rule_and_its_later_turns_follow_the_first_turn(app):
    low = [c for c in CHATS if heldout.chat_bucket("LAHOM", c) < 10]
    high = [c for c in CHATS if heldout.chat_bucket("LAHOM", c) >= 10]
    assert claim(low[0], "m-1", 10).held_out is True and claim(low[0], "m-2", 10).held_out is True
    assert claim(high[0], "m-1", 10).held_out is False and claim(high[0], "m-2", 10).held_out is False
    assert claim(high[1], "m-1", 100).held_out is True
    assert claim(high[1], "m-2", 10).held_out is True  # 비율을 낮춰도 이어지는 상담은 시험 쪽 그대로
    assert claim(low[1], "m-1", 0).held_out is False
    assert claim(low[1], "m-2", 100).held_out is False  # 비율을 올려도 이어지는 상담은 배우기 쪽 그대로


def test_old_turns_are_never_changed_and_their_chat_stays_learning(app):
    db_session.add(CsAgentTurn(brand="LAHOM", chat_id="uc-old", last_user_message_id="m-0", state="posted",
                               created_at=naive(at(1, 9)), updated_at=naive(at(1, 9))))
    db_session.commit()
    assert claim("uc-old", "m-1", 100).held_out is False
    rows = db_session.execute(select(CsAgentTurn.last_user_message_id, CsAgentTurn.held_out)
                              .where(CsAgentTurn.chat_id == "uc-old").order_by(CsAgentTurn.id)).all()
    assert [tuple(r) for r in rows] == [("m-0", False), ("m-1", False)]


def test_a_reclaimed_failed_turn_keeps_its_value(app):
    row = claim("uc-retry", "m-1", 100)
    assert row.held_out is True
    assert turns.mark_failed(row, error_code="brain_unavailable", now=NOW)
    db_session.commit()
    again = claim("uc-retry", "m-1", 0, now=NOW + datetime.timedelta(minutes=5))
    assert (again.id, again.attempts, again.held_out) == (row.id, 2, True)


# ── 초안 바퀴 — 응대는 똑같고 줄에만 적힌다 ──────────────────────────────
@pytest.mark.parametrize("percent", [0, 100])
def test_the_draft_pass_writes_the_value_and_answers_the_same(channel, percent):
    from tests.domains.test_cs_drafting import DRAFT, FakeBrain, customer, result, run, turn

    panel(**{heldout.HELD_OUT_FIELD: percent})
    customer(channel)
    brain_fn = FakeBrain(result())
    run(channel, brain_fn=brain_fn)
    row = turn("uc-1")
    assert row.held_out is (percent == 100)
    assert (row.state, len(brain_fn.requests), DRAFT in (row.masked_draft or "")) == ("stored", 1, True)


def test_without_a_panel_row_the_draft_pass_uses_ten_percent(channel):
    from tests.domains.test_cs_drafting import FakeBrain, customer, result, run, turn

    customer(channel)
    run(channel, brain_fn=FakeBrain(result()))
    assert turn("uc-1").held_out is heldout.rule_holds("LAHOM", "uc-1", heldout.HELD_OUT_DEFAULT)


# ── 배우기 길 모두에서 빠지고 시험 묶음에만 잡힌다 ──────────────────────────
def finished(chat: str, percent: int) -> int:
    """규칙으로 만든 차례를 '고쳐 보냄 · 직원 답 · 까닭 · 사진(설명 전)'까지 채운다 — 모든 배우기 길의 고르기 조건에 맞게."""
    row = claim(chat, "m-1", percent)
    row.state, row.outcome, row.intent = "posted", "edited", "spec"
    row.masked_question, row.staff_reply_masked, row.masked_context = QUESTION, REPLY, "[손님] 합성 앞 말"
    row.edit_reason, row.edit_detail_masked = "wrong_fact", "합성 까닭 — 깊이를 틀렸다"
    row.sent_by_user_id, row.desk_manager_id, row.sent_at = 1, "mgr-1", naive(NOW)
    row.updated_at = naive(NOW)
    db_session.add(CsAgentTurnPhoto(turn_id=row.id, seq=1, storage_key=f"cs-agent/edit-photos/{row.id}/p1.jpg",
                                    content_type="image/jpeg", bytes=1000, width=1600, height=1200,
                                    sha256="a" * 64, no_personal=True, desc_state="pending", uploaded_by=1,
                                    created_at=naive(NOW)))
    db_session.commit()
    return row.id


@pytest.fixture
def vectors(app):
    """SQLite 벡터 표(사례 벡터 길이 읽는다 — 시험 끝에 지운다)."""
    bind = db_session.get_bind()
    vector_metadata.create_all(bind)
    yield
    db_session.remove()
    vector_metadata.drop_all(bind)


def test_every_learning_path_skips_a_held_turn_and_the_eval_set_takes_it(vectors):
    learn = finished("uc-learn", 0)
    held = finished("uc-held", 100)
    since = naive(NOW - datetime.timedelta(days=7))
    picked = {
        "사례 고르기": [r.id for r in case_material._py_cases(db_session, "LAHOM", QUESTION, 10)],
        "뜻 사례 고르기 조건": list(db_session.scalars(select(CsAgentTurn.id).where(*case_material._usable("LAHOM")))),
        "사례 벡터": [int(key) for key, _hash, _body in embed_sources.case_todo(db_session, 10)],
        "넘김 · 고친 글 배우기": [r.id for r in handoff_learning._turn_rows(db_session, since, edits=True)],
        "사진 배우기": [r.id for r in photo_learning._turn_rows(db_session, since)],
        "주간 고침 안": [r.id for r in weekly_fix._turn_rows(db_session, since)],
        "사진 설명 뽑기": [db_session.get(CsAgentTurnPhoto, pid).turn_id
                       for pid in photo_desc._pending_ids(db_session, 10)],
    }
    assert {name: ids for name, ids in picked.items() if ids != [learn]} == {}
    past = evals._past_cases(db_session, 10, naive(NOW + datetime.timedelta(hours=1)))
    assert [(case.turn_id, case.staff_reply) for case in past] == [(held, REPLY)]


def test_with_percent_zero_every_learning_path_sees_both_turns_as_before(app):
    first, second = finished("uc-a", 0), finished("uc-b", 0)
    since = naive(NOW - datetime.timedelta(days=7))
    assert sorted(r.id for r in weekly_fix._turn_rows(db_session, since)) == [first, second]
    assert sorted(r.id for r in photo_learning._turn_rows(db_session, since)) == [first, second]
    assert len(photo_desc._pending_ids(db_session, 10)) == 2
    assert evals._past_cases(db_session, 10, naive(NOW + datetime.timedelta(hours=1))) == ()
