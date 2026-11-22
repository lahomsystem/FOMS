"""넘긴 상담 배우기 — 두뇌의 고치기 안도 놓을 자리 판정으로 · 후보 찾기에 뜻 찾기(설계서
``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 2.1 · 2.2 · 7절).

- 고치기(``update``) 안: 판정 답 여섯 가지마다 넣기 결과. 공용 부딪침 판정자가 늘 '부딪침'이어도 그것만으로는 카드가 생기지
  않는다(첫 밤 카드 19장 가운데 13장이 이 옛 길에서 나왔다).
- 후보: 벡터를 주면 글자가 안 겹치는 항목도 후보에 든다. 벡터가 없으면 지금과 같다. 바로 반영한 항목은 그 자리에서 벡터가
  생기고, 벡터를 못 만들어도 배우기는 계속된다.

합성 놓을 자리 판정자(:class:`tests.support.cs_agent_fakes.FakePlacer`) · 가짜 벡터만(네트워크 0). 손님 글 · 직원 이름 · 금액 없음.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.vectors import vector_metadata
from foms.services.brain import ai_gates
from foms.services.brain import embeddings as emb
from foms.services.brain.ai_gates import judge_source
from foms.services.brain.apply import apply_change
from foms.services.brain.chat_settings import EMBED_FIELD, read_chat_settings
from foms.services.brain.proposals import Proposer, propose_retire
from foms.services.brain.embed_sources import run_embed
from foms.services.brain.embeddings import EmbedUnavailable, embedder_source
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent import handoff_learning_gates as gates
from foms.services.cs_agent import handoff_learning_place as place
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD
from foms.services.cs_agent.handoff_learning_place import placer_source
from models import CsAgentLearnHeld
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_handoff_learning import NOW, admin, ask, changes, handed, on  # noqa: F401 — admin 은 fixture
from tests.domains.test_cs_learn_everything import SAID as DIFFERENT, differs, run_clash
from tests.support.brain_chat_support import axis, chat_on, fake_embedder
from tests.support.brain_support import NOW as BRAIN_NOW
from tests.support.brain_support import REASON, create, no_conflict
from tests.support.cs_agent_fakes import FakeAnthropic, FakePlacer, at, clash_placer, keys, naive  # noqa: F401 — keys 는 fixture

TARGET = "lahom/shelf-depth"
SAID = "합성 직원 답 — 선반 깊이는 350mm 이고 받침은 두 줄로 넣어 드려요"
UPDATED = "합성 선반 깊이는 350mm 이고 선반 받침은 두 줄로 넣어 드립니다"  # 지금 글 + 덧붙인 문장(두뇌의 고치기 안 꼴)
ADDED = "선반 받침은 두 줄로 넣는다"
LATER = at(12, 1)
QUIET = "lahom/synth-quiet-rail"
MEANING = {"저소음": axis(5), "조용히": axis(5)}  # 가짜 뜻 — 두 낱말은 같은 방향(글자는 안 겹친다)


def _clash(*_args) -> bool:
    """공용 부딪침 판정자 — 늘 '부딪침'(옛 길이면 카드가 생겼을 자리)."""
    return True


def _night(proposals, placer, *, now=LATER, judge=_clash):
    with judge_source(judge), placer_source(placer):
        return hl.run_handoff_learning(db_session, now=now, client=FakeAnthropic({"proposals": proposals}))


def _update(**fields):
    """두 상담에서 들은 고치기 안 — 되풀이 문턱을 넘는다."""
    ids = [handed("uc-5", reply=SAID), handed("uc-6", reply=SAID)]
    return ask(ids, **{"op": "update", "key": TARGET, "title": "합성 선반 깊이", "text": UPDATED, **fields})


def _owner_answered():
    """그 항목에 대해 사장님이 '회사 지식이 맞아요'로 닫은 엇갈림 카드 한 장(지난밤)."""
    run_clash(FakeAnthropic({"proposals": [differs([handed("uc-4", reply=DIFFERENT)])]}))
    (card,) = changes()
    card.status, card.reject_code, card.decided_at = "rejected", "knowledge_right", naive(NOW)
    db_session.commit()


# ── 고치기 안 — 답 여섯 가지 ─────────────────────────────────────────────
@pytest.mark.parametrize("answer, count", [
    ({"verdict": "same", "target": TARGET}, "same"),
    ({"verdict": "not_rule"}, "not_rule"),
    ({"verdict": "decided", "target": TARGET}, "decided"),
])
def test_an_update_the_placer_drops_is_never_filed_nor_a_card(admin, answer, count):
    on(**{AUTO_FIELD: True})
    if answer["verdict"] == "decided":
        _owner_answered()
    before, made = current_object(db_session, TARGET), len(changes())
    placer = FakePlacer(answer)
    counts = _night([_update()], placer)
    assert (counts[count], counts["filed"], counts["cards"], counts["blocked"]) == (1, 0, 0, {})
    assert len(changes()) == made and current_object(db_session, TARGET).version == before.version
    (request,) = placer.requests
    assert request["candidates"][0]["key"] == TARGET and request["text"] == UPDATED  # 짚은 항목이 후보 맨 앞


def test_an_update_that_adds_appends_only_the_new_sentence_although_the_shared_judge_says_clash(admin):
    on(**{AUTO_FIELD: True})
    before = current_object(db_session, TARGET)
    counts = _night([_update()], FakePlacer({"verdict": "adds", "target": TARGET, "added": ADDED}))
    assert (counts["added"], counts["applied"], counts["new"], counts["cards"], counts["blocked"]) == (1, 1, 0, 0, {})
    (change,) = changes()
    assert (change.op, change.item_key, change.status) == ("update", TARGET, "applied")
    assert current_object(db_session, TARGET).text == f"{before.text} {ADDED}"  # 두뇌가 다시 쓴 글이 아니라 더한 문장만
    assert change.gates["conflict"] == "fail"  # 공용 판정 결과는 적히기만 한다 — 카드가 아니다


def test_an_update_the_placer_calls_new_goes_in_as_new_knowledge_and_no_card(admin):
    on(**{AUTO_FIELD: True})
    before = current_object(db_session, TARGET)
    counts = _night([_update()], FakePlacer())
    assert (counts["new"], counts["applied"], counts["cards"], counts["blocked"]) == (1, 1, 0, {})
    (change,) = changes()
    assert change.op == "create" and current_object(db_session, change.item_key).text == UPDATED
    assert current_object(db_session, TARGET).version == before.version


def test_only_an_update_the_placer_calls_contradicts_becomes_a_card_with_the_two_phrases(admin):
    on(**{AUTO_FIELD: True})
    before = current_object(db_session, TARGET)
    counts = _night([_update()], clash_placer(TARGET, "깊이는 350mm", "받침은 두 줄"))
    assert (counts["cards"], counts["filed"], counts["applied"]) == (1, 0, 0)
    (card,) = changes()
    assert card.item_type == "conflict" and card.fields["payload"]["after"]["target"] == TARGET
    assert card.fields["text"]["after"].split("\n")[:2] == [
        f"{gates.CLASH_HEAD}회사 지식 「깊이는 350mm」 ↔ 직원 「받침은 두 줄」", "승인된 규칙과 다름"]
    assert current_object(db_session, TARGET).version == before.version


def test_an_update_of_a_missing_or_retired_item_keeps_the_target_code_without_asking(admin):
    old = create(db_session, admin, "lahom/synth-old", item_type="situation", layer="cs", brand="LAHOM", name="옛 상황",
                 text="합성 옛 상황 설명")
    retire = propose_retire(db_session, key=old.item_key, base_version=old.version, reason=REASON,
                            proposer=Proposer.user(admin.id), now=BRAIN_NOW)
    apply_change(db_session, retire.id, actor=admin, now=BRAIN_NOW)
    db_session.commit()
    on(**{AUTO_FIELD: True})
    placer = FakePlacer()
    counts = _night([_update(key="lahom/none"), _update(key=old.item_key)], placer)
    assert (counts["blocked"], counts["filed"], placer.requests) == ({"target": 2}, 0, [])


# ── 지금 글을 품은 고치기 글 — 통째로 새 항목 · 기다리는 말이 되지 않는다 ─────────────
def _wrapping(chats=("uc-5", "uc-6")):
    """짚은 항목의 지금 글을 그대로 품고 한 문장을 덧붙인 고치기 안(첫 밤 옛 길 카드 13장의 꼴)."""
    whole = f"{current_object(db_session, TARGET).text} {ADDED}"
    ids = [handed(chat, reply=SAID) for chat in chats]
    return ask(ids, op="update", key=TARGET, title="합성 선반 깊이", text=whole), whole


def test_a_rewrite_holding_the_current_text_is_never_made_into_a_new_item_whole(admin):
    on(**{AUTO_FIELD: True})
    before, made = current_object(db_session, TARGET), len(changes())
    proposal, _whole = _wrapping()
    counts = _night([proposal], FakePlacer())  # 판정자가 '새 지식'이라 해도 — 그 글은 지금 글을 품는다
    assert (counts["blocked"], counts["filed"], counts["new"], counts["cards"]) == ({"place_unknown": 1}, 0, 0, 0)
    assert len(changes()) == made and current_object(db_session, TARGET).version == before.version


def test_a_rewrite_from_one_chat_waits_as_its_added_sentence_only(admin):
    on(**{AUTO_FIELD: True})
    before = current_object(db_session, TARGET)
    proposal, whole = _wrapping(chats=("uc-5",))
    counts = _night([proposal], FakePlacer({"verdict": "adds", "target": TARGET, "added": ADDED}))
    assert (counts["held"], counts["filed"], counts["cards"]) == (1, 0, 0)
    (row,) = db_session.scalars(select(CsAgentLearnHeld)).all()
    assert row.text == ADDED and row.text != whole  # 더한 문장만 기다린다(지금 글은 이미 지식이다)
    assert current_object(db_session, TARGET).version == before.version


# ── 뜻 찾기 후보 ─────────────────────────────────────────────────────────
@pytest.fixture
def vec(admin):
    """회사 지식 물어보기 '의미 찾기' 켬 + SQLite 벡터 표(시험 끝에 지운다)."""
    engine = db_session.get_bind()
    vector_metadata.create_all(engine)
    chat_on(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00"})
    yield admin
    db_session.remove()
    vector_metadata.drop_all(engine)


def test_a_vector_brings_in_a_candidate_with_no_shared_words_and_no_vector_keeps_todays_list(vec):
    create(db_session, vec, QUIET, item_type="situation", layer="cs", brand="LAHOM", name="저소음 레일",
           text="서랍 레일은 저소음 부품을 씁니다")
    db_session.commit()
    title, text = "닫힘 소리", "문짝이 조용히 닫히게 해 드린다"
    with embedder_source(fake_embedder(MEANING)):
        run_embed(db_session, cfg=read_chat_settings(db_session), now=NOW, apply=True, sources=("brain_item",))
        vector = place.learned_vector(db_session, title=title, text=text, now=NOW)
    assert vector is not None
    common = dict(key=None, texts=[title, text], today=NOW.date(), brand="LAHOM")
    plain = ai_gates.related_items(db_session, **common)
    assert QUIET not in [item["key"] for item in plain]  # 글자로는 못 찾는다
    assert ai_gates.related_items(db_session, **common, vector=None) == plain  # 벡터가 없으면 지금과 같다
    meant = ai_gates.related_items(db_session, **common, vector=vector)
    assert QUIET in [item["key"] for item in meant]
    placer = FakePlacer({"verdict": "same", "target": QUIET})
    with embedder_source(fake_embedder(MEANING)), placer_source(placer):  # 벡터를 안 주면 판정자가 배운 말로 만든다
        got = place.place(db_session, key=None, title=title, text=text, cfg=None, now=NOW)
    assert got.verdict == "same" and QUIET in [item["key"] for item in placer.requests[0]["candidates"]]


def test_the_learned_vector_is_none_when_meaning_search_is_off_or_fails_and_never_raises(vec):
    title, text = "닫힘 소리", "문짝이 조용히 닫히게 해 드린다"
    with embedder_source(fake_embedder(MEANING, fail=EmbedUnavailable("timeout"))):
        assert place.learned_vector(db_session, title=title, text=text, now=NOW) is None
    chat_on(db_session, **{EMBED_FIELD: False, "embed_daily_cap_usd": "1.00"})
    calls = []
    with embedder_source(fake_embedder(MEANING, calls)):
        assert place.learned_vector(db_session, title=title, text=text, now=NOW) is None
    assert calls == []  # 꺼져 있으면 부르지도 않는다(돈 0)


def test_an_item_the_night_applies_gets_its_vector_at_once_and_a_failure_does_not_stop_learning(vec):
    on(**{AUTO_FIELD: True})
    calls = []
    with embedder_source(fake_embedder(MEANING, calls)):
        counts = _night([_update()], FakePlacer({"verdict": "adds", "target": TARGET, "added": ADDED}), judge=no_conflict)
    assert counts["applied"] == 1
    row = current_object(db_session, TARGET)
    assert emb.stored(db_session, emb.SOURCE_ITEM)[TARGET][0] == row.version  # 같은 밤 뒤 바퀴가 뜻으로 찾는다
    assert [call["input_type"] for call in calls] == ["query", "document"]  # 판정용 한 번 + 반영한 항목 한 번
    with embedder_source(fake_embedder(MEANING, fail=EmbedUnavailable("timeout"))):
        again = _night([ask([handed("uc-7"), handed("uc-8")])], FakePlacer(), now=at(13, 1), judge=no_conflict)
    assert (again["applied"], again["new"]) == (1, 1)  # 벡터를 못 만들어도 글자 찾기로 판정하고 넣는다
    made = [c for c in changes() if c.op == "create"][-1]
    assert made.item_key not in emb.stored(db_session, emb.SOURCE_ITEM)
