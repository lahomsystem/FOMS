"""회사 지식 연결 규칙 넓힘(설계서 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 5절 — 사장님 11-27 승인).

- 되는 짝: 사실 → 제품 · 옵션(적용) · 사실 · 정책 → 규칙(자세히 풂, ``refines``) · 공통 바탕 글 → 용어(``uses``) ·
  가격 규칙 → 규격(수량 표, ``quantity_from``). 안 되는 짝(음성 대조군)은 같은 종류 · 같은 유형 안에서 고른다.
- 사람 길(제안 → 승인)로 수량 표가 들어가고, 둘째 수량 표는 연결 개수 상한(하나까지)에 걸린다.
- 바로 반영(사람 없이) 길은 수량 표 ``quantity_from`` 을 받지 않는다(:data:`.apply.AUTO_LINK_KINDS` — 7.2 '뻔한 것은 AI가 바로'의 네 종류만) —
  대조군: 사실 → 옵션 적용 · 자세히 풂 · 낱말 씀은 받는다.
- 링크 제약(고리 · 맞서는 짝 · 근거 끝)이 새 종류에서 오류 없이 돈다 · 막힐 때 안내 글은 허용 표에서 뽑는다.

합성 지식 · 합성 계정만(손님 글 · 직원 이름 · 금액 · 회사 지식 글 없음 · 네트워크 0).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain import constants as c
from foms.services.brain.apply import AUTO_LINK_KINDS, AutoLearn, apply_change
from foms.services.brain.card import item_card
from foms.services.brain.display import LINK_DISPLAY, link_pair_text, link_side_label
from foms.services.brain.errors import BrainLinkLimitError, BrainPermissionError
from foms.services.brain.link_rules import check_link_rules, creates_cycle, opposed_exists
from foms.services.brain.ontology_view import LINK_STANDARDS, ontology_type
from foms.services.brain.proposals import Proposer, propose_link
from foms.services.brain.quality import _can_link
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_link, current_object
from foms.services.cs_agent.handoff_learning_gates import AGENT
from tests.support.brain_support import NOW, agent_judge, create, link, person

DOC = {"approved_by": "합성", "approved_at": "2026-10-20"}
EVIDENCE = ["case:1", "staff:mgr-1"]
TODAY = NOW.date()

OK = [
    ("fact", "applies_to", "option"), ("fact", "applies_to", "product_line"),
    ("fact", "refines", "price_rule"), ("fact", "refines", "spec"), ("fact", "refines", "build_rule"),
    ("fact", "refines", "policy"),
    ("policy", "refines", "price_rule"), ("policy", "refines", "spec"), ("policy", "refines", "build_rule"),
    ("fact", "uses", "term"), ("policy", "uses", "term"), ("price_rule", "uses", "term"), ("spec", "uses", "term"),
    ("price_rule", "quantity_from", "spec"),
]
NOT_OK = [
    ("lesson", "refines", "price_rule"), ("fact", "refines", "situation"), ("policy", "refines", "policy"),
    ("price_rule", "uses", "policy"), ("policy", "uses", "spec"),
    ("fact", "quantity_from", "spec"), ("price_rule", "quantity_from", "term"),
]


@pytest.mark.parametrize("pair", OK, ids=lambda p: "-".join(p))
def test_widened_pairs_are_allowed(pair):
    assert c.link_allowed(*pair)


@pytest.mark.parametrize("pair", NOT_OK, ids=lambda p: "-".join(p))
def test_pairs_outside_the_widening_stay_blocked(pair):
    assert not c.link_allowed(*pair)


def test_old_meanings_are_kept_and_the_new_kind_is_everywhere():
    assert c.link_allowed("lesson", "refines", "situation") and c.link_allowed("situation", "uses", "spec")  # 예전 짝 그대로
    assert c.LINK_KINDS[-1] == "quantity_from" and c.ALLOWED_LINKS["quantity_from"] == (frozenset({"price_rule"}), frozenset({"spec"}))
    assert {"quantity_from"} <= set(LINK_DISPLAY) & set(LINK_STANDARDS) & set(c.ALLOWED_LINKS)
    assert c.cardinality("price_rule", "quantity_from") == (0, 1) and len("quantity_from") <= 16  # 잇기 종류 칸 16자
    assert c.value_problems(kind="quantity_from", check=("kind",)) == []
    assert AUTO_LINK_KINDS == frozenset({"applies_to", "at_step", "uses", "refines"})  # 7.2 — 금액 · 수량 정본 · '같이 안 돼요'는 없다
    # '이을 수 있음 / 틀이 막음' 가름은 허용 표를 그대로 탄다
    assert _can_link("price_rule", "spec") and _can_link("term", "fact") and not _can_link("lesson", "price_rule")


def test_refines_reads_by_the_card_owner_type_and_lessons_keep_their_words():
    assert link_side_label("refines", "out", "lesson") == "다듬은 것"  # 배운 점 화면의 예전 글
    assert link_side_label("refines", "in", "situation") == "다듬은 배운 점"
    assert link_side_label("refines", "out", "fact") == "자세히 푸는 규칙"
    assert link_side_label("refines", "in", "price_rule") == "자세히 푼 지식"
    assert link_side_label("quantity_from", "out", "price_rule") == "수량을 따르는 표"
    assert link_side_label("quantity_from", "in", "spec") == "이 표로 수량을 세는 가격 규칙"


def test_blocked_pair_text_lists_the_ends_that_work_now():
    text = link_pair_text("fact", "refines")
    assert text == "'사실'은 '다듬음' 연결로 규격 · 제작 조건 · 정책 · 가격 규칙에 이을 수 있어요. 이 짝은 아직 못 이어요."
    assert link_pair_text("lesson", "refines").startswith("'배운 점'은 '다듬음' 연결로 상황 · 상용구 · 말투 규칙에")
    assert link_pair_text("term", "refines").startswith("'용어'는 '다듬음' 연결을 쓰지 않아요 — ")  # 받침 없는 이름은 '는'
    assert link_pair_text("price_rule", "uses") == "'가격 규칙'은 '씀' 연결로 용어에 이을 수 있어요. 이 짝은 아직 못 이어요."
    assert link_pair_text(None, "refines") is None and link_pair_text("fact", "made_up") is None  # 부르는 쪽 기본 글


def test_blocked_pair_text_follows_the_table(monkeypatch):
    """글을 손으로 못 박지 않았다 — 좁힘이 바뀌면 안내도 따라간다."""
    monkeypatch.setitem(c.NARROW_ENDS, ("policy", "refines"), frozenset({"spec"}))
    assert link_pair_text("policy", "refines") == "'정책'은 '다듬음' 연결로 규격에 이을 수 있어요. 이 짝은 아직 못 이어요."


# ── 사람 길 · 바로 반영 길 · 링크 제약 ─────────────────────────────────────
@pytest.fixture
def world(app):
    admin = person(db_session, "link_widen_admin")

    def doc(key, item_type, name, **vals):
        payload = {"doc_id": key.rsplit("/", 1)[-1].replace("-", "_"), **DOC} if item_type in c.DOC_TYPES else {}
        create(db_session, admin, key, item_type=item_type, name=name, text=f"{name} 합성 글.", payload=payload, **vals)

    doc("common/w-price", "price_rule", "합성 통 값 규칙", checked_at="2026-10-20")
    doc("common/w-table", "spec", "합성 통 수 표")
    doc("common/w-table-b", "spec", "합성 다른 통 수 표")
    doc("common/w-fact", "fact", "합성 통 사실")
    doc("common/w-policy", "policy", "합성 통 정책")
    doc("common/w-term", "term", "합성 통 낱말")
    doc("common/w-option", "option", "합성 선반 옵션")
    db_session.commit()
    return admin


def test_quantity_table_goes_in_by_a_person_and_a_second_one_hits_the_limit(world):
    link(db_session, world, "quantity_from", "common/w-price", "common/w-table")
    db_session.commit()
    assert current_link(db_session, "quantity_from", "common/w-price", "common/w-table") is not None
    with pytest.raises(BrainLinkLimitError):
        link(db_session, world, "quantity_from", "common/w-price", "common/w-table-b")
    db_session.rollback()
    assert current_link(db_session, "quantity_from", "common/w-price", "common/w-table-b") is None
    card = item_card(db_session, viewer_of(world), "common/w-price", today=TODAY)
    assert {"kind": "quantity_from", "min": 0, "max": 1} in card["link_rules"]
    group = next(g for g in card["links"] if g["kind"] == "quantity_from")
    assert group["direction"] == "out" and group["label"] == "수량을 따르는 표"


def test_refines_and_uses_go_in_by_a_person_and_the_card_names_follow_the_owner(world):
    link(db_session, world, "refines", "common/w-fact", "common/w-price")
    link(db_session, world, "refines", "common/w-policy", "common/w-table")
    link(db_session, world, "uses", "common/w-fact", "common/w-term")
    db_session.commit()
    who = viewer_of(world)
    fact = {(g["kind"], g["direction"]): g["label"] for g in item_card(db_session, who, "common/w-fact", today=TODAY)["links"]}
    price = {(g["kind"], g["direction"]): g["label"] for g in item_card(db_session, who, "common/w-price", today=TODAY)["links"]}
    assert fact == {("refines", "out"): "자세히 푸는 규칙", ("uses", "out"): "쓰는 공통 바탕"}
    assert price == {("refines", "in"): "자세히 푼 지식"}
    detail = ontology_type(db_session, who, "fact", today=TODAY)
    phrases = {(l["kind"], l["direction"]): l["phrase"] for l in detail["links"]}
    assert phrases[("refines", "out")] == "자세히 푸는 규칙" and ("quantity_from", "out") not in phrases


@pytest.mark.parametrize("kind,start,end", [("quantity_from", "common/w-price", "common/w-table")])
def test_the_auto_path_refuses_the_quantity_table_and_a_person_still_can(world, kind, start, end):
    with agent_judge():
        change = propose_link(db_session, op="link_add", kind=kind, from_key=start, to_key=end, reason="합성",
                              proposer=Proposer.agent_named(AGENT), evidence=EVIDENCE, now=NOW)
    db_session.commit()
    with pytest.raises(BrainPermissionError):
        apply_change(db_session, change.id, actor=None, now=NOW, auto=AutoLearn(world.id))
    db_session.rollback()
    assert current_link(db_session, kind, start, end) is None
    apply_change(db_session, change.id, actor=world, now=NOW)  # 사람 승인 길은 그대로
    assert current_link(db_session, kind, start, end) is not None


def test_the_auto_path_takes_fact_applies_to_option(world):
    """대조군 — 넓힌 적용(사실 → 옵션)은 바로 반영 목록 종류라 사람 없이 들어간다."""
    with agent_judge():
        change = propose_link(db_session, op="link_add", kind="applies_to", from_key="common/w-fact",
                              to_key="common/w-option", reason="합성", proposer=Proposer.agent_named(AGENT),
                              evidence=EVIDENCE, now=NOW)
    apply_change(db_session, change.id, actor=None, now=NOW, auto=AutoLearn(world.id))
    assert current_link(db_session, "applies_to", "common/w-fact", "common/w-option") is not None


@pytest.mark.parametrize("kind,start,end", [
    ("refines", "common/w-fact", "common/w-price"), ("uses", "common/w-policy", "common/w-term")])
def test_the_auto_path_takes_refines_and_uses(world, kind, start, end):
    """7.2 — 자세히 풂 · 낱말 씀은 바로 반영 목록 종류다(뻔한지 가리는 조건 다섯은 이어 붙이기 걸음이 본다)."""
    with agent_judge():
        change = propose_link(db_session, op="link_add", kind=kind, from_key=start, to_key=end, reason="합성",
                              proposer=Proposer.agent_named(AGENT), evidence=EVIDENCE, now=NOW)
    apply_change(db_session, change.id, actor=None, now=NOW, auto=AutoLearn(world.id))
    assert current_link(db_session, kind, start, end) is not None


def test_link_rules_run_clean_on_the_new_kinds(world):
    link(db_session, world, "refines", "common/w-fact", "common/w-policy")
    db_session.commit()
    for kind, start, end, end_type in [("quantity_from", "common/w-price", "common/w-table", "spec"),
                                       ("refines", "common/w-policy", "common/w-price", "price_rule"),
                                       ("uses", "common/w-price", "common/w-term", "term")]:
        check_link_rules(db_session, current_object(db_session, start), kind, end, end_type, TODAY)
        assert not opposed_exists(db_session, kind, start, end, TODAY)
        assert not creates_cycle(db_session, kind, start, end, TODAY)
        assert kind not in c.ACYCLIC_KINDS and kind not in c.OPPOSED_KINDS


# ── 문장으로 고치기 줄 — 막힐 때 안내 글 ───────────────────────────────────
def test_a_blocked_sentence_change_line_says_why_and_what_works(app, monkeypatch):
    from tests.domains.test_brain_change_request import _start, answer_text, fake_queue, flags_on
    from tests.domains.test_brain_change_request import world as cr_world
    from tests.support.brain_chat_support import fixed
    flags_on(monkeypatch)
    fake_queue(monkeypatch)
    who = cr_world(db_session)
    client = fixed(answer_text(links=[
        {"op": "add", "kind": "applies_to", "from": "common/door", "to": "common/slide", "why": "제품끼리"},
        {"op": "add", "kind": "made_up", "from": "common/door", "to": "common/slide", "why": "모르는 종류"}]))
    view = _start(who["admin"], client=client)
    pair, unknown = (line["check"] for line in view["lines"])
    assert pair["code"] == unknown["code"] == "link_kind"
    assert pair["text"] == link_pair_text("product_line", "applies_to")
    assert pair["text"].startswith("'제품 라인'은 '적용' 연결을 쓰지 않아요 — ") and pair["text"].endswith(" 연결로 이어 주세요.")
    assert unknown["text"] == "이을 수 없는 연결 짝이에요."  # 대조군: 모르는 종류는 예전 글
