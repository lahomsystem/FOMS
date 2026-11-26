"""회사 지식 새는 곳 막기 — 찾기 · 바로 반영 쪽(설계서 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 4.1).

- 가. 놓을 자리 후보의 낱말 찾기 글에 한글 이름 · 다른 이름이 든다 — 이름표로만 맞는 항목이 후보에 들고(전 · 후), 이름표만
  바뀌어도 새 판이라 낱말 기억이 다시 나눈다.
- 나. '깊이 줄임'의 '깊이'처럼 부사로 읽힌 치수 이름씨를 남긴다 — 그 꼴만 늘고 다른 글의 낱말 · 순위는 그대로(전 · 후 견주기).
- 마. 바로 반영(사람 없이) 길은 정한 잇기 종류만 잇는다 — 지금 학습이 바로 넣는 종류(상황 → 제품 '적용')는 목록 안, 그 밖은
  권한 오류. 사람 승인 길은 그대로.

합성 글만(손님 글 · 직원 이름 · 금액 · 회사 지식 글 없음 · 네트워크 0).
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.brain import ai_gates, word_search
from foms.services.brain.apply import AUTO_LINK_KINDS, AutoLearn, apply_change
from foms.services.brain.errors import BrainPermissionError
from foms.services.brain.proposals import Proposer, propose_link, propose_update
from foms.services.brain.store import current_link, current_object
from foms.services.cs_agent import photo_learning
from foms.services.cs_agent.handoff_learning_gates import AGENT
from tests.domains.test_brain_word_search import DOCS
from tests.support.brain_support import NOW, agent_judge, create, person

EVIDENCE = ["case:1", "staff:mgr-1"]


# ── 가. 후보 찾기 글에 한글 이름 · 다른 이름 ──────────────────────────────
LABELED, DECOY = "lahom/synth-term-crown", "lahom/synth-term-ask"
QUERY = ["크라운 몰딩 문의", "크라운 몰딩 문의가 오면"]
TERM = dict(item_type="term", layer="common", brand="LAHOM")


@pytest.fixture
def terms(app):
    """이름 · 글에는 물은 낱말이 없고 이름표에만 있는 항목 + 글에 물은 낱말 하나가 있는 항목(낱말 찾기가 빈 목록이 아니게 —
    빈 목록이면 예전 글자 찾기로 넘어가 견주기가 흐려진다)."""
    word_search._reset_for_tests()
    admin = person(db_session, "leak_stop_admin")
    create(db_session, admin, LABELED, name="합성 마감 낱말", text="벽과 천장 사이를 덮는 판이다",
           payload={"pref_label": "천장 몰딩", "aliases": ["크라운 몰딩"]}, **TERM)
    create(db_session, admin, DECOY, name="상담 시간", text="문의는 평일 낮에 받는다", **TERM)
    db_session.commit()
    return admin


def _words():
    found = ai_gates.related_items(db_session, key=None, texts=QUERY, today=NOW.date(), brand="LAHOM", limit=6, words=True)
    return [item["key"] for item in found]


def test_word_text_adds_the_korean_name_and_other_names_and_keeps_unlabeled_items_as_before(terms):
    row, plain = current_object(db_session, LABELED), current_object(db_session, DECOY)
    assert ai_gates.word_text(row) == "합성 마감 낱말 천장 몰딩 크라운 몰딩 벽과 천장 사이를 덮는 판이다"
    assert ai_gates.word_text(plain) == f"{plain.name} {plain.text}"  # 이름표 없는 항목은 예전 글 그대로


def test_an_item_matched_only_by_its_labels_becomes_a_candidate(terms, monkeypatch):
    with monkeypatch.context() as before:  # 대조군 — 예전 글(이름 + 글)이면 후보에 못 든다
        before.setattr(ai_gates, "word_text", lambda r: f"{r.name or ''} {r.text or ''}")
        assert _words() == [DECOY]
    word_search._reset_for_tests()  # 같은 판의 낱말 기억을 비운다(배포 뒤 새 프로세스와 같다)
    assert _words()[0] == LABELED and DECOY in _words()


def test_a_label_only_change_is_a_new_version_so_the_token_memory_reads_it_again(terms):
    _words()
    plain = current_object(db_session, DECOY)
    assert "크라운" not in word_search._CACHE[(DECOY, plain.version)]  # 이 판의 낱말은 기억돼 있다
    change = propose_update(db_session, key=DECOY, base_version=plain.version, after={"payload": {"aliases": ["크라운 문의"]}},
                            reason="합성 이름표만 고침", proposer=Proposer.user(terms.id), now=NOW)
    apply_change(db_session, change.id, actor=terms, now=NOW)
    db_session.commit()
    assert current_object(db_session, DECOY).version == plain.version + 1  # 이름표만 바뀌어도 새 판(반영 동작이 늘 새 판 줄)
    _words()
    assert "크라운" in word_search._CACHE[(DECOY, plain.version + 1)]  # 새 판은 다시 나눈다(옛 기억을 쓰지 않는다)


# ── 나. 부사로 읽힌 치수 이름씨 ───────────────────────────────────────────
CUT_DOCS = [*DOCS[:3], ("synth/cut", "깊이 줄임 선반 깊이를 줄이면 통마다 따로 셉니다"),
            ("synth/lift", "높이 낮춤 상부장 높이를 낮추면 문을 다시 짭니다")]
#: 견줄 글 — 다른 부사 · 이름씨로 읽힌 '깊이' · 그 꼴 없는 글, 끝 줄만 '깊이'가 정말 부사로 쓰인 글(낱말 하나가 는다 — 찾기엔 해 없음).
OTHER = ["문을 꼭 닫아 주세요", "아주 빨리 보내 드려요", "선반 깊이는 깊이 조정 없이 짭니다", "깊이를 줄여 드려요", "많이 깊어요",
         "경첩이 삐걱거리면 기름칠해 드립니다", "도면은 실측 뒤 사흘 안에 보내 드립니다", "문을 깊이 넣어요"]
QUERIES = ["경첩에서 삐걱거리는 소리가 나면 기름칠을 해요", "도면이 언제 보내지나요 실측하고 사흘이면 되나요",
           "깊이 줄여 주세요", "높이 낮춤 문의"]


def _both(monkeypatch, work):
    """같은 일을 고친 뒤 · 고치기 전(목록을 비운 예전 규칙)으로 — 낱말 기억은 그때마다 비운다."""
    word_search._reset_for_tests()
    after = work()
    with monkeypatch.context() as old:
        old.setattr(word_search, "NOUN_ADVERBS", frozenset())
        word_search._reset_for_tests()
        before = work()
    word_search._reset_for_tests()
    return before, after


def test_a_dimension_noun_read_as_an_adverb_is_kept(monkeypatch):
    """재현 — '깊이 줄임'의 '깊이'는 뒤에 낱말이 바로 붙어 부사로 읽혀 빠졌다(예전 ['줄', '이'])."""
    before, after = _both(monkeypatch, lambda: [word_search.tokens("깊이 줄임"), word_search.tokens("높이 낮춤")])
    assert before == [["줄", "이"], ["낮추"]]
    assert after == [["깊이", "줄", "이"], ["높이", "낮추"]]


def test_only_those_forms_are_added_and_other_texts_split_the_same(monkeypatch):
    before, after = _both(monkeypatch, lambda: [word_search.tokens(text) for text in OTHER])
    for text, old, new in zip(OTHER, before, after):  # 늘어난 것은 그 꼴뿐, 나머지 낱말 · 차례는 그대로
        assert [t for t in new if t not in word_search.NOUN_ADVERBS] == [t for t in old if t not in word_search.NOUN_ADVERBS], text
    assert [text for text, old, new in zip(OTHER, before, after) if old != new] == ["문을 깊이 넣어요"]
    assert after[-1] == ["문", "깊이", "넣"] and before[-1] == ["문", "넣"]
    assert not {"꼭", "아주", "빨리", "많이", "없이"} & {t for got in after for t in got}  # 다른 부사는 그대로 버린다


def test_the_query_now_finds_its_item_and_other_queries_rank_the_same(monkeypatch):
    before, after = _both(monkeypatch, lambda: [word_search.rank(q, CUT_DOCS, limit=5) for q in [*QUERIES, "깊이 줄임 되나요"]])
    assert before[-1] == [] and after[-1][:1] == ["synth/cut"]  # 고친 것
    assert before[:-1] == after[:-1]  # 다른 질의의 순위는 그대로(대조군)


# ── 마. 바로 반영 길의 잇기 종류 허용 목록 ─────────────────────────────────
@pytest.fixture
def ends(app):
    admin = person(db_session, "leak_stop_link_admin")
    create(db_session, admin, "common/synth-door", name="합성 여닫이")
    create(db_session, admin, "common/synth-door-wide", name="합성 문짝 묶음")
    create(db_session, admin, "lahom/synth-sit", item_type="situation", layer="cs", brand="LAHOM", name="합성 문 처짐 문의",
           text="문이 처지면 경첩 조정을 안내한다")
    db_session.commit()
    return admin


def test_the_kinds_learning_links_without_a_person_are_the_first_list(ends):
    """처음 값 = 지금 학습이 바로 넣는 종류 — 넘긴 상담 배우기의 온톨로지 '잇기'(사진 학습 넣기 길의 ``link`` 갈래)."""
    idea = {"kind": "link", "key": "lahom/synth-sit", "target_key": "common/synth-door"}
    with agent_judge():
        code, make = photo_learning._filer(db_session, idea, key="lahom/synth-unused", reason="합성", evidence=EVIDENCE,
                                           now=NOW.replace(tzinfo=datetime.timezone.utc), known="", agent_name=AGENT)
        change = make()
    assert AUTO_LINK_KINDS == frozenset({"applies_to"})
    assert code is None and change.link_kind in AUTO_LINK_KINDS
    apply_change(db_session, change.id, actor=None, now=NOW, auto=AutoLearn(ends.id))
    assert current_link(db_session, "applies_to", "lahom/synth-sit", "common/synth-door") is not None


def test_a_kind_outside_the_list_is_refused_without_a_person_and_still_goes_in_with_one(ends):
    with agent_judge():
        change = propose_link(db_session, op="link_add", kind="broader", from_key="common/synth-door",
                              to_key="common/synth-door-wide", reason="합성", proposer=Proposer.agent_named(AGENT),
                              evidence=EVIDENCE, now=NOW)
    db_session.commit()
    assert "broader" not in AUTO_LINK_KINDS
    with pytest.raises(BrainPermissionError):
        apply_change(db_session, change.id, actor=None, now=NOW, auto=AutoLearn(ends.id))
    db_session.rollback()
    assert current_link(db_session, "broader", "common/synth-door", "common/synth-door-wide") is None
    apply_change(db_session, change.id, actor=ends, now=NOW)  # 사람 승인 길은 그대로
    assert current_link(db_session, "broader", "common/synth-door", "common/synth-door-wide") is not None
