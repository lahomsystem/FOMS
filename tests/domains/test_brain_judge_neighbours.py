"""판정자에게 한 걸음 이웃(설계 글 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 7.4 · 차례 9).

- 줄 꼴: 나가는 쪽 이름 → 유형 '이름'(단위) · 수량 표 · 낱말 끝은 앞 한 문장 · 계산기는 '값은 견적 계산기(옵션 '이름')' — 금액 없음.
- 거름: 지금 판 · 유효 잇기만, 끝은 반영 · 모두가 보는 지식만(관리 글 · 은퇴 · 가림 걸린 이름은 뺌), 이웃 5개 · 300자 상한.
- 조회는 후보 묶음에 한 번(후보 수와 상관없이 같은 질의 수).
- 놓을 자리 · 엇갈림 판정자: 지시문 한 줄, 후보 줄 바로 아래 '이어진 것', **잇기가 없으면 요청 글이 예전과 글자까지 같다**.
합성 항목 · 합성 계산기만(꾸민 이름 · 꾸민 수 — 손님 글 · 직원 이름 · 실제 금액 없음).
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import event

from db import db_session
from foms.services.brain import judge_neighbours as jn
from foms.services.brain.ai_gates import judge_source
from foms.services.brain.external import catalog_source
from foms.services.cs_agent import handoff_learning_judge as judge
from foms.services.cs_agent import handoff_learning_place as place
from tests.support.brain_support import SYNTH_CATALOG, create, link, person

TODAY = datetime.date(2026, 11, 2)
NOW = datetime.datetime(2026, 11, 2, 1, 0, tzinfo=datetime.timezone.utc)
RULE = "common/synth-rule"
DOC = {"approved_by": "합성", "approved_at": "2026-10-20"}  # 가격 규칙 지식 문서 꼴(승인 칸)
OPTION_PRICE = str(SYNTH_CATALOG.option_categories[0]["options"][0]["price"])


@pytest.fixture
def admin(app):
    return person(db_session, "judge_neighbours_admin")


@pytest.fixture
def linked(admin):
    """가격 규칙 하나 → 옵션(적용) · 규격 표(수량) · 용어(씀) · 계산기 옵션(값). 커밋한다."""
    create(db_session, admin, RULE, item_type="price_rule", name="합성 통 값 규칙", text="합성 통 하나 값은 계산기를 따른다.",
           checked_at="2026-11-01", payload={"doc_id": "synth-rule", **DOC, "unit": "통"})
    create(db_session, admin, "common/synth-option", item_type="option", name="합성 맞춤 옵션", text="합성 옵션 설명",
           payload={"unit": "통"})
    create(db_session, admin, "common/synth-table", item_type="spec", name="합성 통 수 표",
           text="합성 가로 길이마다 통 수를 정한 표다. 둘째 문장은 싣지 않는다.")
    create(db_session, admin, "common/synth-word", item_type="term", name="합성 반통", text="합성 반통은 한 통 값으로 센다! 덧말.")
    for kind, to in (("applies_to", "common/synth-option"), ("quantity_from", "common/synth-table"),
                     ("uses", "common/synth-word"), ("value_from", "calc:option/3:5")):
        link(db_session, admin, kind, RULE, to)
    db_session.commit()
    return admin


def _lines(owners, **kw):
    with catalog_source(lambda: SYNTH_CATALOG):
        return jn.neighbour_lines(db_session, owners, today=TODAY, **kw)


def test_line_names_kind_unit_gist_and_calculator_name_without_amounts(linked):
    line = _lines({RULE: "price_rule"})[RULE]
    assert line == (jn.HEAD + "값은 견적 계산기(옵션 '합성 옵션 묶음 > 합성 손잡이') · "
                    "수량을 따르는 표 → 규격 '합성 통 수 표' — 합성 가로 길이마다 통 수를 정한 표다. · "
                    "쓰는 공통 바탕 → 용어 '합성 반통' — 합성 반통은 한 통 값으로 센다! · "
                    "적용 대상 → 옵션 '합성 맞춤 옵션'(단위 통)")
    assert OPTION_PRICE not in line and "원" not in line  # 계산기 금액은 싣지 않는다
    assert len(line) <= jn.LINE_CHARS


def test_only_live_visible_ends_and_none_without_links(linked):
    create(db_session, linked, "common/synth-alone", item_type="fact", name="합성 홀로", text="합성 홀로 사실.",
           checked_at="2026-11-01", payload={"doc_id": "synth-alone", **DOC})
    create(db_session, linked, "common/synth-held", item_type="option", name="합성 관리 옵션", visibility="admin")
    create(db_session, linked, "common/synth-gone", item_type="option", name="합성 은퇴 옵션", status="retired")
    for to in ("common/synth-held", "common/synth-gone"):
        link(db_session, linked, "applies_to", RULE, to)
    db_session.commit()
    got = _lines({RULE: "price_rule", "common/synth-alone": "fact", "no/such": None})
    assert list(got) == [RULE]  # 잇기 없는 후보 · 없는 키는 줄이 없다
    assert "합성 관리 옵션" not in got[RULE] and "합성 은퇴 옵션" not in got[RULE]
    assert _lines({}) == {} and _lines({"common/synth-alone": "fact"}) == {}


def test_caps_neighbours_and_chars(linked, monkeypatch):
    for i in range(4):
        create(db_session, linked, f"common/synth-extra-{i}", item_type="option", name=f"합성 더 옵션 {chr(0xAC00 + i)}")
        link(db_session, linked, "applies_to", RULE, f"common/synth-extra-{i}")
    db_session.commit()
    line = _lines({RULE: "price_rule"})[RULE]
    assert line.count(" · ") == jn.MAX_NEIGHBOURS - 1  # 8개 중 5개
    monkeypatch.setattr(jn, "LINE_CHARS", 80)
    short = _lines({RULE: "price_rule"})[RULE]
    assert len(short) <= 80 and short.startswith(jn.HEAD + "값은 견적 계산기")  # 넘는 조각은 뺀다(중간에서 자르지 않는다)


def test_one_lookup_for_the_whole_batch(linked):
    other = "common/synth-rule-two"
    create(db_session, linked, other, item_type="price_rule", name="합성 둘째 규칙", text="합성 둘째.", checked_at="2026-11-01",
           payload={"doc_id": "synth-rule-two", **DOC})
    link(db_session, linked, "applies_to", other, "common/synth-option")
    db_session.commit()
    seen: list[str] = []

    def count(_conn, _cursor, statement, *_a):
        seen.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        one = len((_lines({RULE: "price_rule"}), seen)[1])
        seen.clear()
        many = len((_lines({RULE: "price_rule", other: "price_rule", **{f"x/{i}": None for i in range(6)}}), seen)[1])
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert 2 <= many == one <= 3  # 잇기 한 번 · 끝 지식 한 번(계산기 정본은 끼운 합성 목록)


def test_first_sentence():
    assert jn.first_sentence("첫 문장. 둘째.") == "첫 문장."
    assert jn.first_sentence("마침표 없는 글") == "마침표 없는 글"
    assert len(jn.first_sentence("가" * 300)) == jn.GIST_CHARS


# ── 판정자 ───────────────────────────────────────────────────────────────
def _old_user_text(request):
    """바꾸기 전 놓을 자리 요청 글(그대로 옮김) — 잇기가 없으면 새 글과 글자까지 같아야 한다."""
    flat = place._flat
    items = [f"[{item['key']}] {flat(item['name'])}: {flat(item['text'])[:place.CANDIDATE_CHARS]}"
             for item in request["candidates"]]
    return "\n".join(["[회사 지식 후보](키는 대괄호 안 · 이름: 지금 글)", *(items or ["(없음)"]), "",
                      "[사장님이 이미 정한 것](엇갈림 카드 대상 키 · 그때 직원 말 → 사장님 답, 사장님이 글을 적었으면 그 글)",
                      *(request["decided"] or ["(없음)"]), "", "[새 말]", f"{request['title']}: {request['text']}", "",
                      "새 말을 회사 지식의 어디에 놓을까?"])


REQUEST = {"candidates": [{"key": "a/one", "name": "합성 하나", "type": "fact", "text": "합성 하나 글"},
                          {"key": "a/two", "name": "합성 둘", "type": "fact", "text": "합성 둘 글"}],
           "decided": [], "held": [], "title": "합성 새 말", "text": "합성 새 말 글"}


def test_placement_request_is_unchanged_without_links_and_line_sits_under_its_candidate():
    assert place.user_text(REQUEST) == _old_user_text(REQUEST) == place.user_text({**REQUEST, "neighbours": {}})
    lines = place.user_text({**REQUEST, "neighbours": {"a/one": jn.HEAD + "적용 대상 → 옵션 '합성'"}}).split("\n")
    assert lines[1:4] == ["[a/one] 합성 하나: 합성 하나 글", jn.HEAD + "적용 대상 → 옵션 '합성'", "[a/two] 합성 둘: 합성 둘 글"]
    for system in (place.SYSTEM, judge.SYSTEM):
        assert judge.NEIGHBOURS_NOTE in system
    assert judge.NEIGHBOURS_NOTE == "후보 아래 '이어진 것'은 그 지식이 기대는 다른 지식이다 — 값 · 수량 · 낱말 뜻은 거기서 온다."
    assert jn.HEAD.strip().startswith("↳ 이어진 것")


def test_place_sends_the_neighbour_line_with_one_lookup(linked, monkeypatch):
    items = [{"key": RULE, "name": "합성 통 값 규칙", "type": "price_rule", "text": "합성 통 하나 값은 계산기를 따른다."},
             {"key": "common/synth-table", "name": "합성 통 수 표", "type": "spec", "text": "합성 표 글"}]
    monkeypatch.setattr(place, "related_items", lambda *_a, **_k: items)
    seen = []
    with catalog_source(lambda: SYNTH_CATALOG), place.placer_source(lambda _s, req: seen.append(req) or {"verdict": "new"}):
        assert place.place(db_session, key=RULE, title="합성", text="합성 새 말", cfg=None, now=NOW, vector=None).verdict == "new"
    (request,) = seen
    assert list(request["neighbours"]) == [RULE]
    text = place.user_text(request).split("\n")
    assert text[2] == request["neighbours"][RULE] and text[2].startswith(jn.HEAD)


def test_differs_judge_sees_neighbours_and_same_text_without_links(linked, monkeypatch):
    entries = [(RULE, "price_rule", "합성 통 값 규칙: 합성 글"), ("common/synth-word", "term", "합성 반통: 합성 낱말 글")]
    monkeypatch.setattr(judge, "related_entries", lambda *_a, **_k: entries)
    with catalog_source(lambda: SYNTH_CATALOG):
        joined, extra = judge.known_text(db_session, target_key=RULE, title="합성", text="합성", today=TODAY)
    near = _lines({RULE: "price_rule"})[RULE]
    assert joined.split("\n") == ["합성 통 값 규칙: 합성 글", near, "합성 반통: 합성 낱말 글"] and extra == len(near) + 1
    monkeypatch.setattr(judge, "related_entries", lambda *_a, **_k: [entries[1]])
    plain, none = judge.known_text(db_session, target_key=RULE, title="합성", text="합성", today=TODAY)
    assert (plain, none) == ("합성 반통: 합성 낱말 글", 0)  # 잇기가 없으면 예전 글 그대로
    got = []
    with judge_source(lambda _s, known, _said: got.append(known) or False):
        assert judge.differs_verdict(db_session, target_key=RULE, title="합성", text="합성", cfg=None, now=NOW) == judge.ADDS
    assert got == ["합성 반통: 합성 낱말 글"]
