"""배우기만 · 뭐든지 다 배우기(사장님 2026-11-20 'AI 초안 끄고 배움에 모든 하루 비용 · 학습 모델은 난이도에 따라 · 뭐든지 다 배워서
자동 적용 · 다른 말은 2번 이상 나온 것 바로 수정').

초안 스위치 '배우기만'은 초안 두뇌 없이 차례 줄만 남기고(돈 상한이 0 이어도) 밤 배우기는 그대로 돈다. 어려운 상담은 가장 센
모델 · 작은 묶음, 쉬운 상담은 한 단계 아래 모델. 지금 지식과 다른 직원 답은 서로 다른 손님 둘 이상이면 그 항목을 바로 고치고
(전 → 후가 'AI 가 배운 것'에 남는다), 한 번뿐이면 엇갈림 카드로 — 카드는 AI 주 자리 상한과 상관없이 승인 대기에 보이고, 같은 말이
다른 손님에게 또 나오면 그때 고치며 카드를 닫는다. 읽는 규칙이 바뀌면 읽은 차례 표를 한 번 비운다.

준비물 · 도우미는 :mod:`tests.domains.test_cs_handoff_learning` · :mod:`tests.domains.test_cs_drafting` 것 그대로(합성 글만).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain import inbox, learned
from foms.services.brain.inbox import open_rows
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from foms.services.cs_agent import brain, brain_prompt, drafting, loop, panel as cs_panel, turns
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD, CASES_FIELD
from foms.services.cs_agent.handoff_learning_gates import MERGED_ACTION
from foms.services.cs_agent.handoff_learning_pick import EASY, HARD, hard_case, model_for, pick_batch
from tests.domains.test_cs_drafting import (  # noqa: F401 — channel 은 fixture
    FakeBrain, FakePoster, channel, customer, loop_pass, set_switch, turn,
)
from tests.domains.test_cs_drafting import run as draft_run
from tests.domains.test_cs_handoff_learning import (  # noqa: F401 — admin · two 는 fixture
    NOW, admin, ask, body, changes, handed, on, run, two,
)
from tests.support.cs_agent_fakes import FakeAnthropic, at, keys, naive  # noqa: F401 — keys 는 fixture

TARGET = "lahom/shelf-depth"
SAID = "합성 직원 답 — 선반 깊이는 400mm 로 짜 드려요"
FIXED = "합성 선반 깊이는 400mm 입니다"


def differs(ids, **fields):
    base = dict(op="differs", key=TARGET, title="합성 선반 깊이 다른 말", text="합성 선반 깊이는 400mm 로 안내했어요",
                fixed_text=FIXED, repeats=[])
    return ask(ids, **{**base, **fields})


# ── 초안 스위치 '배우기만' ───────────────────────────────────────────────
def test_learn_mode_keeps_the_turn_without_the_brain_even_when_the_daily_cap_is_gone(channel, monkeypatch):  # noqa: F811
    customer(channel)
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "0")  # 밤 배우기가 하루 돈을 다 써도 낮의 차례 모으기는 멈추지 않는다
    brain_fn, poster = FakeBrain(), FakePoster()
    summary = draft_run(channel, "learn", brain_fn=brain_fn, poster=poster,
                        ready=lambda *a, **k: pytest.fail("배우기만인데 두뇌 준비를 확인했다"))
    assert (turn().state, turn().error_code, turn().masked_draft) == ("skipped", turns.SKIP_LEARN_ONLY, None)
    assert (summary.skipped, summary.brain_calls, brain_fn.requests, poster.calls) == ({"learn_only": 1}, 0, [], [])
    assert draft_run(channel, "learn", brain_fn=brain_fn).claimed == 0  # 같은 손님 글을 두 번 집지 않는다


def test_the_loop_in_learn_mode_collects_turns_and_still_runs_the_learning_share(channel, monkeypatch):  # noqa: F811
    customer(channel)
    set_switch({"loop": "on", "draft": "learn"})
    seen = []
    monkeypatch.setattr(loop, "run_learning", lambda session, **kwargs: seen.append(1) or {"handoff_learning": {}})
    result = loop_pass(channel)
    assert (result.outcome, seen, turn().error_code) == ("ok", [1], turns.SKIP_LEARN_ONLY)
    assert turns.draft_mode(db_session) == "learn" and "learn" in turns.DRAFT_MODES and "learn" in turns.DRAFT_WORKING


def test_the_panel_switch_takes_learn_and_names_it(channel, admin):  # noqa: F811
    assert cs_panel.change_draft_mode(db_session, mode="learn", actor_user_id=admin.id, now=NOW) is True
    assert turns.draft_mode(db_session) == "learn"
    assert cs_panel.change_draft_mode(db_session, mode="learn", actor_user_id=admin.id, now=NOW) is False  # 같은 값
    with pytest.raises(ValueError):
        cs_panel.change_draft_mode(db_session, mode="learning", actor_user_id=admin.id, now=NOW)


def test_night_learning_runs_while_the_draft_switch_is_learn_only(two):
    on()
    set_switch({"loop": "on", "draft": "learn"})
    counts = run(FakeAnthropic({"proposals": [ask(two)]}))
    assert (counts["sent"], counts["filed"], counts["halted"]) == (2, 1, None)
    set_switch({"loop": "on", "draft": "off"})
    assert run(FakeAnthropic({"proposals": []}), now=at(12, 1)) == {"off": "draft_off"}  # '끔'은 배우기도 멈춘다


# ── 난이도에 따라 묶음 · 모델 ────────────────────────────────────────────
def test_hard_talks_go_to_the_strongest_model_in_a_small_batch_and_easy_ones_to_the_next(admin):
    on(**{CASES_FIELD: 6})
    easy = [handed("uc-1"), handed("uc-2")]
    hard = [handed("uc-3", reason="complaint"), handed("uc-3"), handed("uc-4", reply="합성 긴 답 " * 150)]
    client = FakeAnthropic({"proposals": []})
    first = run(client)
    assert (first["tier"], first["cases"], first["left"], client.params[0]["model"]) == (HARD, 3, 2, brain_prompt.MODEL)
    assert all(f"사례 {i} 손님 글:" in body(client) for i in hard)  # 어려운 상담의 쉬운 사례도 같은 묶음(대화를 한 번만 싣는다)
    second = run(client, now=at(11, 2, 15))
    assert (second["tier"], second["cases"], client.params[1]["model"]) == (EASY, 2, brain_prompt.MODEL_SONNET)
    assert all(f"사례 {i} 손님 글:" in body(client, 1) for i in easy)
    assert {model_for(HARD)[0], model_for(EASY)[0]} <= set(brain_prompt.PRICES)  # 값표에 있는 모델만(돈이 새지 않게)


def test_what_makes_a_case_hard_and_how_big_a_hard_batch_is():
    plain = {"chat_id": "a", "reason": "unsure", "question": "합성 질문", "reply": "합성 답", "draft": None}
    assert not hard_case(plain) and hard_case({**plain, "reason": "edited"}) and hard_case({**plain, "draft": "합성 초안"})
    assert hard_case({**plain, "reply": "가" * 800})
    cases = [{**plain, "chat_id": f"c{i}", "turn_id": i} for i in range(12)]
    assert pick_batch(cases, (), 9) == (EASY, cases[:9]) and pick_batch([], (), 9) == (EASY, [])
    tier, batch = pick_batch(cases, {"c0", "c5", "c6", "c7", "c8", "c9"}, 9)  # 손님 사진이 있는 상담은 어렵다
    assert (tier, [case["turn_id"] for case in batch]) == (HARD, [0, 5, 6, 7])  # 쉬운 묶음의 3분의 1, 적어도 넷
    busy = [{**plain, "turn_id": i} for i in range(3)]  # 한 상담에 사례 셋 — 긴 상담
    assert pick_batch(busy, (), 9)[0] == HARD


# ── 지금 지식과 다른 직원 답 ─────────────────────────────────────────────
def test_a_different_answer_given_to_two_customers_fixes_the_item_at_once_and_shows_before_and_after(admin):
    on(**{AUTO_FIELD: True})
    before = current_object(db_session, TARGET)
    old, version, grade = before.text, before.version, before.confidence
    ids = [handed("uc-5", reply=SAID), handed("uc-6", reply=SAID)]
    counts = run(FakeAnthropic({"proposals": [differs(ids)]}))
    assert (counts["applied"], counts["fixed"], counts["cards"], counts["blocked"]) == (1, 1, 0, {})
    (change,) = changes()
    assert (change.op, change.status, change.decided_action) == ("update", "applied", "auto_learn")
    assert "서로 다른 손님 2곳" in change.reason
    row = current_object(db_session, TARGET)
    assert (row.text, row.version, row.confidence) == (FIXED, version + 1, grade)  # 사람이 확정한 확신은 내리지 않는다
    (line,) = learned.learned_list(db_session, viewer_of(admin))["items"]
    assert (line["before"], line["text"], line["can_fix"], line["can_undo"]) == (old, FIXED, True, True)  # 고친 내용 표기 · 수정 가능
    assert "서로 다른 손님 2곳" in line["why"]
    learned.undo(db_session, change.id, actor=admin, now=naive(NOW))
    db_session.commit()
    assert current_object(db_session, TARGET).text == old  # 지우기 = 옛 글로


def test_a_one_off_different_answer_waits_as_a_visible_card_until_another_customer_hears_the_same(admin, monkeypatch):
    on(**{AUTO_FIELD: True})
    old = current_object(db_session, TARGET).text
    first = run(FakeAnthropic({"proposals": [differs([handed("uc-5", reply=SAID)])]}))
    assert (first["cards"], first["fixed"], first["applied"]) == (1, 0, 0) and current_object(db_session, TARGET).text == old
    (card,) = changes()
    monkeypatch.setattr(inbox, "AI_WEEKLY_CAP", 0)  # 그 층 AI 주 자리가 다 찼어도 사장님이 고를 카드는 보인다
    assert card.id in [c.id for c, _row, _end in open_rows(db_session, viewer_of(admin), naive(NOW))]
    assert inbox.inbox_counts(db_session, viewer_of(admin), naive(NOW))["ai_waiting"] == 0
    other = handed("uc-6", reply=SAID)
    client = FakeAnthropic({"proposals": [differs([other], repeats=[card.item_key, "conflict/lahom-handoff-none"])]})
    second = run(client, now=at(12, 1))
    assert f"- [{card.item_key}] 대상 [{TARGET}]: 합성 선반 깊이는 400mm 로 안내했어요" in body(client)  # 두뇌가 같은 말을 알아보게
    assert (second["fixed"], second["applied"], second["cards"]) == (1, 1, 0)
    assert current_object(db_session, TARGET).text == FIXED
    db_session.refresh(card)
    assert (card.status, card.decided_action) == ("expired", MERGED_ACTION)  # 같은 말을 모아 둔 카드는 고침에 합쳐졌다


def test_a_repeat_from_the_same_customer_or_another_item_stays_a_card(admin):
    on(**{AUTO_FIELD: True})
    run(FakeAnthropic({"proposals": [differs([handed("uc-5", reply=SAID)])]}))
    (card,) = changes()
    again = handed("uc-5", reply=SAID + " 기준이에요")  # 같은 손님에게 또 말한 것은 두 번이 아니다
    client = FakeAnthropic({"proposals": [differs([again], repeats=[card.item_key], text="합성 선반은 400mm 가 기준이라고 했어요")]})
    counts = run(client, now=at(12, 1))
    assert counts["fixed"] == 0 and current_object(db_session, TARGET).text != FIXED
    db_session.refresh(card)
    assert card.status == "open"


# ── 읽는 규칙이 바뀌면 한 번 다시 읽는다 ─────────────────────────────────
def test_a_new_reading_policy_clears_the_read_list_once(two):
    on()
    hl.mark_used(db_session, two)
    row = db_session.get(hl.SystemSetting, hl.STORE_KEY)
    row.setting_value = {key: value for key, value in row.setting_value.items() if key != "policy"}  # 옛 판이 남긴 표
    hl.flag_modified(row, "setting_value")
    db_session.commit()
    assert hl.fresh_policy(db_session) is True and hl.used_ids(db_session) == frozenset()
    hl.mark_used(db_session, two)
    assert hl.fresh_policy(db_session) is False and hl.used_ids(db_session) == frozenset(two)
    assert hl.in_window(at(11, 0, 30)) and hl.in_window(at(11, 6, 59)) and not hl.in_window(at(11, 7))
    assert drafting.SKIP_HANDOFF != turns.SKIP_LEARN_ONLY
