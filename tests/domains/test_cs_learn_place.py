"""넘긴 상담 배우기 — 배운 말 놓을 자리 판정(사장님 2026-11-22 '배우기를 지금 고쳐' · 설계서
``docs/specs/2026-11-22-cs-learning-placement_SPEC.md`` 6절).

판정 답 여섯 가지마다 넣기 결과 · 더함은 그 항목 글 끝에만 붙고 새 항목이 없음 · 600자를 넘으면 새 지식 · 빈 설명 칸은 후보 ·
대상에서 빠짐 · 사장님이 이미 정한 엇갈림은 다시 안 물음 · 판정을 못 하면 넣지도 카드도 없음 · 서로 다른 손님 둘 이상의 다른 말은
지금처럼 바로 고침. 합성 놓을 자리 판정자(:class:`tests.support.cs_agent_fakes.FakePlacer`)만 — 모델 길은 가짜 두뇌로(네트워크 0).
손님 글 · 직원 이름 · 금액 없음.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.brain import ai_gates, learned
from foms.services.brain.ai_gates import judge_source
from foms.services.brain.proposals import Proposer
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent import handoff_learning_gates as gates
from foms.services.cs_agent import handoff_learning_place as place
from foms.services.cs_agent import handoff_learning_route as route
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD
from foms.services.cs_agent.handoff_learning_place import placer_source
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_handoff_learning import NOW, REPLY, admin, ask, changes, handed, on  # noqa: F401 — admin 은 fixture
from tests.domains.test_cs_learn_everything import FIXED, SAID, TARGET, differs, run_clash
from tests.support.brain_support import create, no_conflict
from tests.support.cs_agent_fakes import FakeAnthropic, FakePlacer, at, clash_placer, keys, naive  # noqa: F401 — keys 는 fixture

ADDED = "합성 선반 받침은 두 줄로 넣는다"
TEXT = "합성 선반 받침은 두 줄로 넣어 드린다고 안내한다"
STUB = "common/synth-door"


def _night(proposals, placer, *, now=NOW, judge=no_conflict):
    with judge_source(judge), placer_source(placer):
        return hl.run_handoff_learning(db_session, now=now, client=FakeAnthropic({"proposals": proposals}))


def _one(**fields):
    """두 상담에서 들은 다른 말(바로 고칠 글 없음 — 놓을 자리 판정으로) — 두뇌가 짚은 항목이 늘 후보 맨 앞이다. 근거 상담이 둘이라
    되풀이 문턱(11-23 — 한 상담뿐이면 기다리는 말, :mod:`tests.domains.test_cs_learn_held`)을 넘는다."""
    said = "합성 직원 답 — 선반 받침은 두 줄로 넣어 드려요"
    return differs([handed("uc-5", reply=said), handed("uc-6", reply=said)],
                   **{"title": "합성 선반 받침", "text": TEXT, "fixed_text": "", **fields})


@pytest.fixture
def found(admin, monkeypatch):
    """찾기가 빈 설명 칸(제품) · 그 항목을 앞에 낸다(새로 만들기 안은 두뇌가 짚은 항목이 없다)."""
    create(db_session, admin, STUB, name="합성 문짝", text="합성 선반 받침 문짝 설명")
    db_session.commit()
    hits = [{"key": STUB, "name": "합성 문짝", "type": "product_line", "brand": "COMMON"},
            {"key": TARGET, "name": "shelf-depth", "type": "fact", "brand": "LAHOM"}]
    monkeypatch.setattr(ai_gates, "search_objects", lambda *_a, **_k: [
        {**hit, "confidence": ai_gates.CONFIRMED, "score": 10.0, "visibility": "all", "text": "합성"} for hit in hits])


# ── 답 여섯 가지 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("answer, count", [
    ({"verdict": "same", "target": TARGET}, "same"),
    ({"verdict": "not_rule"}, "not_rule"),
])
def test_same_and_not_rule_are_counted_and_never_filed(admin, answer, count):
    on(**{AUTO_FIELD: True})
    counts = _night([_one()], FakePlacer(answer))
    assert (counts[count], counts["filed"], counts["cards"], counts["blocked"]) == (1, 0, 0, {}) and changes() == []


def test_adds_appends_only_the_added_sentence_and_makes_no_new_item(admin):
    on(**{AUTO_FIELD: True})
    before = current_object(db_session, TARGET)
    placer = FakePlacer({"verdict": "adds", "target": TARGET, "added": ADDED})
    counts = _night([_one()], placer, judge=lambda *_a: True)  # 공용 부딪침 판정자는 늘 '부딪침'
    assert (counts["added"], counts["applied"], counts["new"], counts["cards"]) == (1, 1, 0, 0)
    (change,) = changes()
    assert (change.op, change.item_key, change.status) == ("update", TARGET, "applied")
    after = current_object(db_session, TARGET)
    assert (after.text, after.version) == (f"{before.text} {ADDED}", before.version + 1)
    assert change.gates["conflict"] == "fail"  # 결과만 적고 막지 않는다 — 같은 일을 놓을 자리 판정자가 했다
    assert "지금 지식에 더함" in change.reason
    (line,) = learned.learned_list(db_session, viewer_of(admin))["items"]
    assert (line["before"], line["text"]) == (before.text, after.text)  # 'AI 가 배운 것'의 전 → 후


@pytest.mark.parametrize("why, patch", [
    ("600자 넘음", {"MAX_TEXT": 20}),
    ("숫자 관문", {}),
])
def test_adds_that_cannot_be_appended_goes_in_as_new_knowledge(admin, monkeypatch, why, patch):
    on(**{AUTO_FIELD: True})
    for name, value in patch.items():
        monkeypatch.setattr(route, name, value)
    added = ADDED if patch else "합성 선반 받침은 37줄로 넣는다"  # 직원 답에도 지식에도 없는 숫자
    before = current_object(db_session, TARGET)
    counts = _night([_one()], FakePlacer({"verdict": "adds", "target": TARGET, "added": added}))
    assert (counts["new"], counts["added"], counts["applied"]) == (1, 0, 1), why
    (change,) = changes()
    assert change.op == "create" and current_object(db_session, change.item_key).text == TEXT
    assert current_object(db_session, TARGET).version == before.version


def test_new_contradicts_and_the_card_starts_with_the_two_clashing_phrases(admin):
    on(**{AUTO_FIELD: True})
    counts = _night([_one()], FakePlacer())
    assert (counts["new"], counts["applied"]) == (1, 1) and changes()[0].op == "create"
    again = _night([_one(text="합성 선반 받침은 한 줄만 된다고 안내한다")], clash_placer(TARGET, "깊이는 350mm", "한 줄만"),
                   now=at(12, 1))
    assert (again["cards"], again["new"]) == (1, 0)
    card = changes()[-1]
    text = card.fields["text"]["after"]
    assert text.split("\n")[:2] == [f"{gates.CLASH_HEAD}회사 지식 「깊이는 350mm」 ↔ 직원 「한 줄만」", "승인된 규칙과 다름"]
    assert gates.open_cards(db_session) == [(card.item_key, TARGET, "합성 선반 받침은 한 줄만 된다고 안내한다")]


def test_an_answer_out_of_shape_is_neither_filed_nor_a_card(admin):
    on(**{AUTO_FIELD: True})
    bad = [{"verdict": "adds", "target": TARGET, "added": ""}, {"verdict": "adds", "target": "lahom/none", "added": ADDED},
           {"verdict": "contradicts", "target": TARGET, "clash": {"knowledge": "", "staff": "합성"}},
           {"verdict": "decided", "target": TARGET}]  # 이미 정한 줄이 없는데 '이미 정함'
    for number, answer in enumerate(bad):
        counts = _night([_one()], FakePlacer(answer), now=at(11, 2, 15 * number))
        assert counts["blocked"] == {"place_unknown": 1}, answer
    assert changes() == []


# ── 사장님이 이미 정한 것 ────────────────────────────────────────────────
def test_a_clash_the_owner_already_answered_is_not_asked_again(admin):
    on(**{AUTO_FIELD: True})
    run_clash(FakeAnthropic({"proposals": [differs([handed("uc-5", reply=SAID)])]}))
    (card,) = changes()
    card.status, card.reject_code, card.decided_at = "rejected", "knowledge_right", naive(NOW)  # '회사 지식이 맞아요'
    db_session.commit()
    placer = FakePlacer(lambda request: {"verdict": "decided" if request["decided"] else "contradicts", "target": TARGET,
                                         "clash": {"knowledge": "350mm", "staff": "400mm"}})
    paraphrase = differs([handed("uc-6", reply=SAID)], text="합성 깊은 선반은 사백으로 짠다고 했다")
    counts = _night([paraphrase], placer, now=at(12, 1))
    assert (counts["decided"], counts["cards"]) == (1, 0) and len(changes()) == 1  # 카드가 다시 생기지 않는다
    (line,) = placer.requests[0]["decided"]
    assert line.startswith(f"- [{TARGET}] ") and line.endswith("→ 회사 지식이 맞아요")
    assert place.decided_lines(db_session, [TARGET], at(12, 1) + datetime.timedelta(days=31)) == []  # 30일 창 밖


# ── 빈 설명 칸 · 판정을 못 함 · 바로 고침 ────────────────────────────────
def test_stub_items_are_never_candidates_or_targets(found):
    on(**{AUTO_FIELD: True})
    placer = FakePlacer({"verdict": "contradicts", "target": STUB, "clash": {"knowledge": "합성", "staff": "합성"}})
    counts = _night([ask([handed("uc-1", reply="합성 직원 답 — 선반 받침은 두 줄")], title="합성 선반 받침", text=TEXT)], placer)
    assert [item["key"] for item in placer.requests[0]["candidates"]] == [TARGET]  # 빈 설명 칸은 후보가 아니다
    assert counts["blocked"] == {"place_unknown": 1} and changes() == []  # 후보 밖을 대상으로 고른 답
    common = dict(reason="합성", proposer=Proposer.agent_named(gates.AGENT), now=naive(NOW), known="",
                  evidence=["case:1", "staff:mgr-1"])
    assert gates._differs_card(db_session, STUB, title="합성", text=TEXT, number=1, common=common, now=NOW,
                               seen=[]) == "target"
    pointed = FakePlacer()
    again = _night([_one(key=STUB)], pointed, now=at(12, 1))  # 두뇌가 빈 설명 칸을 짚은 다른 말 — 그 칸 없이 판정
    assert again["new"] == 1 and [item["key"] for item in pointed.requests[0]["candidates"]] == [TARGET]


def test_without_a_placer_or_panel_settings_nothing_is_filed(admin):
    turn = handed("uc-1")
    case = {"turn_id": turn, "chat_id": "uc-1", "reply": REPLY, "reason": "unsure", "staff": "mgr-1"}
    with judge_source(no_conflict):
        counts = route.file_proposals(db_session, [ask([turn])], [case], now=NOW, known="", approved=[], cfg=None)
    assert counts == {"filed": 0, "place_unavailable": 1} and changes() == []


def test_two_customers_still_fix_the_item_at_once_without_asking(admin):
    on(**{AUTO_FIELD: True})
    placer = FakePlacer()
    counts = _night([differs([handed("uc-5", reply=SAID), handed("uc-6", reply=SAID)])], placer)
    assert (counts["fixed"], counts["applied"]) == (1, 1) and current_object(db_session, TARGET).text == FIXED
    assert placer.requests == []


# ── 모델 길(합성 판정자 없이 가짜 두뇌로) ─────────────────────────────────
def test_the_placement_judge_asks_sonnet_on_the_learning_line_and_reads_the_answer(admin):
    from foms.services.cs_agent.settings import read_settings
    on(**{AUTO_FIELD: True})
    answer = {"verdict": "adds", "target": TARGET, "added": ADDED, "clash": {"knowledge": "", "staff": ""}, "why": "합성"}
    client = FakeAnthropic(answer)
    got = place.place(db_session, key=TARGET, title="합성 선반 받침", text=TEXT, cfg=read_settings(db_session, log=False),
                      now=NOW, client=client)
    assert got == place.Placement("adds", TARGET, ADDED, ("", ""), "합성")
    (params,) = client.params
    assert (params["model"], params["output_config"]["effort"]) == (place.MODEL, place.EFFORT) == ("claude-sonnet-5-5", "medium")
    assert params["output_config"]["format"]["schema"] == place.SCHEMA and params["system"][0]["text"] == place.SYSTEM
    user = params["messages"][0]["content"]
    assert f"[{TARGET}] " in user and current_object(db_session, TARGET).text in user and TEXT in user
    assert user.index("[회사 지식 후보]") < user.index("[사장님이 이미 정한 것]") < user.index("[새 말]")
    assert db_session.get(hl.SystemSetting, "cs_agent_learning_spend").setting_value.get("calls", 0) >= 1
    off = FakeAnthropic(answer)
    on(**{AUTO_FIELD: True, "learning_cap_usd_panel": None})
    assert place.place(db_session, key=TARGET, title="합성", text=TEXT, cfg=read_settings(db_session, log=False), now=NOW,
                       client=off).verdict == place.UNAVAILABLE and off.params == []
