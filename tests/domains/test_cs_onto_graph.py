"""단계 2 '물건 찾아 따라가기'(설계서 2026-11-12 온톨로지 5절 · 5.0 · 사장님 D196) — 이름표 찾기 · 걸린 규칙 · 묶음 칸 · 초안 길.

완료 기준: 끄면 두뇌 재료 그대로 · 긴 이름표 먼저 · 겹치면 긴 쪽 · 띄어쓰기 무시 · 다른 브랜드 · 은퇴 · 보기 범위 좁은 항목 빠짐 ·
옵션은 제품에 매이지 않음 · 걸린 규칙은 지식 id 와 이름만(금액 없음) · 가림 검사에 걸린 이름 빠짐 · 상한 · 묶음 숫자는 허용.
합성 값만(꾸민 이름 · 수).
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from db import db_session
from foms.persistence.brain.vectors import vector_metadata
from foms.services.brain.chat_settings import EMBED_FIELD, read_chat_settings
from foms.services.brain.embed_sources import run_embed
from foms.services.brain.embeddings import embedder_source
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.brain_cases import QUOTE
from foms.services.cs_agent.onto_block import MAX_CHARS, ONTO_BLOCK_HEAD, onto_block
from foms.services.cs_agent.onto_find import MAX_ITEMS, find_items, matches
from foms.services.cs_agent import onto_meaning
from foms.services.cs_agent.onto_meaning import find_by_meaning, meaning_query
from foms.services.cs_agent.onto_settings import ONTO_GRAPH_FIELD, ONTO_MEANING_FIELD
from models import SystemSetting
from tests.domains.test_cs_drafting import FakeBrain, channel, customer, result, run  # noqa: F401
from tests.support.brain_chat_support import NOW_KST, axis, chat_on, fake_embedder
from tests.support.brain_support import create, link, person
from tests.support.cs_agent_fakes import keys  # noqa: F401 — fixture

DAY = datetime.date(2026, 11, 2)
DOC = {"doc_id": "pol-door", "approved_by": "합성", "approved_at": "2026-10-20"}
PHONE = "01" + "0" + "5550" + "1234"


def rows(*pairs):
    return [(key, name, {"aliases": list(aliases)}) for key, name, *aliases in pairs]


def test_long_labels_win_and_overlaps_go_to_the_longer_one():
    table = rows(("option/1-1", "서랍"), ("option/1-2", "외부 3단 서랍", "외부서랍"), ("product_line/lahom-1", "합성장"))
    assert matches(table, ["외부3단서랍 하나랑 서랍 하나"]) == ["option/1-2", "option/1-1"]
    assert matches(table, ["외부서랍만요"]) == ["option/1-2"]  # '서랍' 은 긴 쪽 안이라 따로 치지 않는다
    assert matches(table, ["합성 장 문의"]) == ["product_line/lahom-1"]  # 띄어쓰기 무시
    assert matches(table, ["아무것도 없음"]) == []
    typed = rows(("option/1-1", "합성대 TYPE01", "타입1", "type1"), ("option/1-9", "합성대 TYPE09", "4A타입"))
    assert matches(typed, ["타입10 이랑 TYPE100 문의"]) == []  # 영문 · 숫자가 이어지면 더 긴 낱말 안이다
    assert matches(typed, ["타입1 로 할게요 type1번"]) == ["option/1-1"]
    assert matches(typed, ["14A타입"]) == []
    many = [(f"option/9-{i}", f"합성옵션{i:02d}") for i in range(12)]
    assert len(matches(rows(*many), [" ".join(n for _k, n in many)])) == MAX_ITEMS


def _products(admin):
    create(db_session, admin, "product_line/lahom-1", brand="LAHOM", name="합성장",
           payload={"price_unit": "30cm", "door_kinds": ["hinged"], "aliases": ["합성 붙박이"]})
    create(db_session, admin, "product_line/haud-7", brand="HAUD", name="하우드합성장")
    create(db_session, admin, "option/3-5", name="합성 손잡이", item_type="option",
           payload={"price_kind": "extra", "category": "합성 묶음"})
    create(db_session, admin, "option/3-9", name="합성 비밀옵션", item_type="option", visibility="admin")


@pytest.fixture
def world(app):
    admin = person(db_session, "onto_graph_admin")
    _products(admin)
    create(db_session, admin, "common/pol-door", item_type="policy", name="합성 문 정책", checked_at="2026-10-20",
           payload={**DOC, "policy_kind": "shipping"})
    link(db_session, admin, "applies_to", "common/pol-door", "product_line/lahom-1")
    db_session.commit()
    return admin


def test_find_reads_visible_items_and_their_rules(world):
    hits = find_items(db_session, ["합성 붙박이에 합성 손잡이 달 수 있나요 하우드합성장 합성 비밀옵션"], brand="LAHOM", day=DAY)
    assert [h.key for h in hits] == ["product_line/lahom-1", "option/3-5"]  # 하우드 · 관리자 범위는 빠진다
    (rule,) = hits[0].rules
    assert (rule.doc_id, rule.item_type, rule.name) == ("pol-door", "policy", "합성 문 정책")
    assert hits[1].rules == ()  # 옵션은 제품에 매여 있지 않다 — 제품 규칙이 옵션으로 넘어가지 않는다
    assert find_items(db_session, ["주문 품목만"], brand="LAHOM", day=DAY, extra=["합성장"])[0].key == "product_line/lahom-1"
    assert find_items(db_session, [""], brand="LAHOM", day=DAY) == []


def test_block_has_ids_and_names_but_no_amounts(world):
    hits = find_items(db_session, ["합성장 합성 손잡이"], brand="LAHOM", day=DAY)
    lines = onto_block(hits)
    text = "\n".join(lines)
    assert lines[0] == ONTO_BLOCK_HEAD and f"{QUOTE}합성장" in lines and "[pol-door]" in text
    assert "값 단위 30cm" in text and "문 방식 여닫이" in text and "값 방식 추가 금액" in text
    assert "원" not in text.replace("원문", "")  # 금액 칸 없음
    leaky = SimpleNamespace(key="x", item_type="option", name=f"합성 {PHONE}", payload={}, rules=())
    assert onto_block([leaky]) == []  # 가림 검사에 걸린 이름은 뺀다 — 남는 물건이 없으면 칸도 없다
    big = [SimpleNamespace(key=f"k{i}", item_type="option", name="합성" * 30, payload={}, rules=()) for i in range(40)]
    assert sum(len(line) + 1 for line in onto_block(big)) <= MAX_CHARS


def _switch(on):
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, version=1, setting_value={**st.DEFAULTS, ONTO_GRAPH_FIELD: on}))
    db_session.commit()


@pytest.fixture
def spec_world(channel):
    """초안 길용 — 지식 문서 유형이 아닌 규격 규칙(채널 준비물의 지식 문서와 맞추기 없이)."""
    admin = person(db_session, "onto_graph_spec_admin")
    _products(admin)
    create(db_session, admin, "common/spec-door", item_type="spec", name="합성 문 규격", payload={"value": 18, "unit": "mm"})
    link(db_session, admin, "applies_to", "common/spec-door", "product_line/lahom-1")
    db_session.commit()
    return channel


MEANING = {"합성장": axis(0), "붙박이": axis(0), "손잡이": axis(1), "비밀옵션": axis(1)}


@pytest.fixture
def vectors(app):
    """SQLite 벡터 표 + 회사 지식 의미 찾기 켬(시험 끝에 표를 지운다)."""
    engine = db_session.get_bind()
    vector_metadata.create_all(engine)
    chat_on(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00"})
    yield
    db_session.remove()
    vector_metadata.drop_all(engine)


def _fill_vectors():
    with embedder_source(fake_embedder(MEANING)):
        run_embed(db_session, cfg=read_chat_settings(db_session), now=NOW_KST, apply=True, sources=("brain_item",))


def test_meaning_finds_the_close_visible_item_from_masked_text_only(world, vectors, monkeypatch):
    _fill_vectors()
    calls: list = []
    with embedder_source(fake_embedder(MEANING, calls)):
        hits = find_by_meaning(db_session, ["붙박이 문의요"], brand="LAHOM", day=DAY, now=NOW_KST)
        assert [(h.key, h.by_meaning) for h in hits] == [("product_line/lahom-1", True)]  # 하우드 같은 뜻은 브랜드로 빠진다
        assert "뜻으로 찾음" in "\n".join(onto_block(hits))
        assert find_by_meaning(db_session, ["아무 상관 없는 글"], brand="LAHOM", day=DAY, now=NOW_KST) == []  # 기준 밑
        masked = find_by_meaning(db_session, [f"붙박이 {PHONE}"], brand="LAHOM", day=DAY, now=NOW_KST)
        assert [h.key for h in masked] == ["product_line/lahom-1"]  # 전화번호는 가려진 뒤 나간다
        assert find_by_meaning(db_session, ["손잡이"], brand="LAHOM", day=DAY, now=NOW_KST)[0].key == "option/3-5"
        assert meaning_query(["합성손님 님 붙박이"], customer_names=["합성손님"]) == "[이름] 님 붙박이"
        sent = len(calls)
        monkeypatch.setattr(onto_meaning, "mask", lambda text, **_kw: text)  # 가림이 놓친 경우
        assert find_by_meaning(db_session, [f"붙박이 {PHONE}"], brand="LAHOM", day=DAY, now=NOW_KST) == []
        assert len(calls) == sent  # 가림 검사에 걸린 글은 부르지도 않는다
    assert all(PHONE not in text for call in calls for text in call["texts"])
    chat_on(db_session, **{EMBED_FIELD: False, "embed_daily_cap_usd": "1.00"})
    with embedder_source(fake_embedder(MEANING)):
        assert find_by_meaning(db_session, ["붙박이 문의요"], brand="LAHOM", day=DAY, now=NOW_KST) == []  # 의미 찾기 끔


@pytest.mark.parametrize("meaning", [False, True])
def test_the_draft_falls_back_to_meaning_only_when_on(spec_world, vectors, meaning):
    channel = spec_world
    _fill_vectors()
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, version=1, setting_value={
        **st.DEFAULTS, ONTO_GRAPH_FIELD: True, ONTO_MEANING_FIELD: meaning}))
    db_session.commit()
    customer(channel, text="붙박이 문 방식이 궁금해요")  # 이름표('합성 붙박이' · '합성장')로는 못 찾는다
    brain_fn = FakeBrain(result())
    with embedder_source(fake_embedder(MEANING)):
        run(channel, brain_fn=brain_fn)
    (request,) = brain_fn.requests
    text = "\n".join(request.onto_lines)
    assert ("뜻으로 찾음" in text and f"{QUOTE}합성장" in text) is meaning
    assert bool(request.onto_lines) is meaning


@pytest.mark.parametrize("on", [False, True])
def test_the_draft_request_gets_the_block_only_when_on(spec_world, on):
    channel = spec_world
    _switch(on)
    customer(channel, text="합성 붙박이 문 방식이 궁금해요")
    brain_fn = FakeBrain(result())
    run(channel, brain_fn=brain_fn)
    (request,) = brain_fn.requests
    if on:
        text = "\n".join(request.onto_lines)
        assert "(지식 문서 밖)" in text and f"{QUOTE}합성 문 규격" in text
    else:
        assert request.onto_lines == ()
