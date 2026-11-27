"""밤 배우기 끝 이어 붙이기의 판정 조각(설계 글 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 7.2) — 바로 넣는 조건
다섯을 하나씩 빠뜨리면 바로 넣지 않는다 · 금액 · 수량 · 꼭 같이 · 같이 안 됨은 조건이 다 맞아도 바로 넣지 않는다 · 글자 맞춤은 재는
자와 같은 이름 기준(3자 이상 · 숨은 이름 뺌 · 살아 있는 지식만)이고 가리키는 지식이 하나뿐인지 센다 · 반영 동작은 사장님 결정 ·
기준 답 끝에 사람 없이 잇지 않는다 · 예전 바로 넣는 길(상황 → 제품 '적용')은 그대로 · 지시문 · 설정 글에 한자 없음.

합성 글만(손님 글 · 직원 이름 · 금액 · 회사 지식 글 없음 · 네트워크 0).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.brain.apply import AUTO_LINK_HELD_ENDS, AUTO_LINK_KINDS, AutoLearn, apply_change
from foms.services.brain.errors import BrainPermissionError
from foms.services.brain.inbox_bins import LEARN_PROPOSERS
from foms.services.brain.proposals import Proposer, propose_link
from foms.services.brain.store import current_link
from foms.services.cs_agent import handoff_learning_link as link
from foms.services.cs_agent import handoff_learning_link_prompt as lp
from foms.services.cs_agent.handoff_learn_settings import HANDOFF_LEARN_FIELDS, LINK_CALLS_FIELD, LINK_FIELD
from foms.services.cs_agent.handoff_learning_gates import AGENT
from foms.services.cs_agent.handoff_learning_onto import file_ontology
from tests.support.brain_support import NOW, agent_judge, create, person
from tests.support.cs_agent_fakes import at

EVIDENCE = ["case:1", "case:2", "staff:mgr-1"]
HANJA = re.compile(r"[㐀-鿿豈-﫿]")


def item(item_type="fact", brand="LAHOM", visibility="all"):
    return SimpleNamespace(item_type=item_type, brand=brand, visibility=visibility)


# ── 바로 넣는 조건 다섯(7.2) ──────────────────────────────────────────────
@pytest.mark.parametrize("kind, target_type", [("applies_to", "product_line"), ("uses", "term"), ("refines", "price_rule")])
def test_all_five_conditions_met_is_the_only_way_in_without_a_person(kind, target_type):
    assert link.auto_block(kind, item(), item(target_type, "COMMON"), matched=True, unique=True) is None
    assert link.auto_block(kind, item(), item(target_type), matched=True, unique=True) is None  # 같은 브랜드
    assert link.auto_block(kind, item(), item(target_type), matched=False, unique=True) == "no_match"  # ① AI 말만
    assert link.auto_block(kind, item(), item(target_type), matched=True, unique=False) == "not_unique"  # ②
    assert link.auto_block(kind, item(), item(target_type, visibility="admin"), matched=True, unique=True) == "scope"
    assert link.auto_block(kind, item(visibility="price"), item(target_type), matched=True, unique=True) == "scope"
    assert link.auto_block(kind, item(), item(target_type, "HAUD"), matched=True, unique=True) == "brand"  # ④
    assert link.auto_block(kind, item(), None, matched=True, unique=True) == "scope"  # 바깥 자리 끝


@pytest.mark.parametrize("kind", ["value_from", "quantity_from", "requires", "excludes", "copy_in", "supersedes",
                                  "at_step"])  # 공정 단계는 사장님 11-27 답으로 뺐다 — 늘 ⑥ 칸
def test_money_quantity_and_together_links_never_go_in_without_a_person_even_when_all_else_fits(kind):
    assert link.auto_block(kind, item("build_rule"), item("product_line"), matched=True, unique=True) == "kind"  # ③
    assert kind not in AUTO_LINK_KINDS


@pytest.mark.parametrize("ends", [("template", "process_step"), ("lesson", "template"), ("owner_decision", "policy")])
def test_owner_decisions_and_template_answers_are_never_linked_without_a_person(ends):
    source, target = item(ends[0]), item(ends[1])
    assert link.auto_block("uses", source, target, matched=True, unique=True) == "owner_item"  # ⑤
    assert {"owner_decision", "template"} <= AUTO_LINK_HELD_ENDS and link.OWNER_ENDS <= AUTO_LINK_HELD_ENDS


def test_apply_refuses_an_auto_link_touching_a_template_answer_and_a_person_still_can(app):
    admin = person(db_session, "link-rules-admin")
    create(db_session, admin, "process_step/synth-measure", item_type="process_step", name="합성 실측",
           payload={"erp_stage": "MEASURE"})
    create(db_session, admin, "cs/tpl-synth", item_type="template", layer="cs", name="합성 기준 답",
           payload={"doc_id": "tpl-synth", "approved_by": "합성", "approved_at": "2026-10-20", "intents": ["hours"]})
    db_session.commit()
    with agent_judge():
        change = propose_link(db_session, op="link_add", kind="at_step", from_key="cs/tpl-synth",
                              to_key="process_step/synth-measure", reason="합성", proposer=Proposer.agent_named(AGENT),
                              evidence=EVIDENCE, now=NOW)
    db_session.commit()
    with pytest.raises(BrainPermissionError):  # 공정 단계는 바로 넣는 종류가 아니고, 끝도 기준 답이다(조건 ③ · ⑤)
        apply_change(db_session, change.id, actor=None, now=NOW, auto=AutoLearn(admin.id))
    db_session.rollback()
    assert current_link(db_session, "at_step", "cs/tpl-synth", "process_step/synth-measure") is None
    apply_change(db_session, change.id, actor=admin, now=NOW)  # 사람 승인 길은 그대로
    assert current_link(db_session, "at_step", "cs/tpl-synth", "process_step/synth-measure") is not None


def test_the_existing_situation_to_product_link_path_still_goes_in_at_once(app):
    """예전 바로 넣는 길(넘긴 상담 배우기 온톨로지 '잇기' — 상황 → 제품 '적용')은 넓힘 뒤에도 그대로 바로 들어간다."""
    admin = person(db_session, "link-rules-onto")
    create(db_session, admin, "common/synth-door", name="합성 여닫이")
    create(db_session, admin, "lahom/synth-sit", item_type="situation", layer="cs", brand="LAHOM", name="합성 문 처짐 문의",
           text="문이 처지면 경첩 조정을 안내한다")
    db_session.commit()
    idea = {"kind": "link", "key": "lahom/synth-sit", "target_key": "common/synth-door", "name": "", "text": "",
            "aliases": [], "why": "합성 까닭", "evidence_turn_ids": [7, 8]}
    cases = [{"turn_id": 7, "chat_id": "uc-1", "staff": "mgr-1"}, {"turn_id": 8, "chat_id": "uc-2", "staff": "mgr-1"}]
    with agent_judge():
        got = file_ontology(db_session, [idea], cases, now=at(11, 3), known="", auto=AutoLearn(admin.id))
    assert got == {"filed": 1, "applied": 1}
    assert current_link(db_session, "applies_to", "lahom/synth-sit", "common/synth-door") is not None


# ── 글자 맞춤 ────────────────────────────────────────────────────────────
def test_glyph_matches_count_how_many_live_items_a_name_points_to():
    owners = {"합성여닫이문": {"a"}, "합성통단위": {"b", "c"}, "합성자기이름": {"z", "d"}}
    text = "합성 여닫이문은 합성 통 단위로 재고 합성 자기 이름을 쓴다"
    assert link.glyph_matches(text, "z", owners) == {"a": True, "b": False, "c": False, "d": False}  # 자기 이름도 센다
    assert link.glyph_matches(text, "a", owners) == {"b": False, "c": False, "d": False, "z": False}  # 자기는 대상 아님
    assert link.glyph_matches("", "z", owners) == {} and link.glyph_matches(None, "z", owners) == {}


def test_label_owners_use_the_measuring_rule_names(app):
    admin = person(db_session, "link-rules-labels")
    create(db_session, admin, "common/synth-a", name="합성 가구 한 벌",
           payload={"pref_label": "합성 대표 이름", "aliases": ["합성 다른 이름", "문"], "hidden_labels": ["합성 숨은 이름"]})
    create(db_session, admin, "common/ab", item_type="term", name="갑을")  # 3자 미만
    create(db_session, admin, "common/synth-old", name="합성 은퇴 가구", status="retired")
    db_session.commit()
    owners = link.label_owners(db_session, NOW.date())
    assert {label for label, keys in owners.items() if "common/synth-a" in keys} == {"합성가구한벌", "합성대표이름", "합성다른이름"}
    assert "갑을" not in owners and not any("common/synth-old" in keys for keys in owners.values())


# ── 지시문 · 고르기 목록 · 설정 ───────────────────────────────────────────
def test_the_kind_list_schema_and_words_have_no_hanja_and_cover_the_auto_kinds():
    assert lp.schema()["properties"]["items"]["items"]["properties"]["links"]["items"]["properties"]["kind"]["enum"] == list(
        lp.KINDS)
    assert AUTO_LINK_KINDS <= set(lp.KINDS) and set(lp.KINDS) == AUTO_LINK_KINDS | {"quantity_from", "value_from",
                                                                                      "requires", "excludes", "at_step"}
    words = [lp.INSTRUCTIONS, lp.OVERRIDE, *lp.LIST_HEADS, lp.TARGET_HEAD, lp.SOURCE_HEAD, link.REASON_HEAD,
             link.GLYPH_REASON, *(f.label + f.help for f in HANDOFF_LEARN_FIELDS)]
    assert not [w for w in words if HANJA.search(w)]
    fields = {f.name: f for f in HANDOFF_LEARN_FIELDS}
    assert (fields[LINK_FIELD].label, fields[LINK_FIELD].default) == ("밤 배우기 끝에 지식 이어 붙이기", False)
    assert (fields[LINK_CALLS_FIELD].label, fields[LINK_CALLS_FIELD].default) == ("이어 붙이기 한 밤 횟수", 3)
    assert LEARN_PROPOSERS == {f"agent:{AGENT}"} and link.LEARN_AGENTS == ("agent:cs_handoff_learning", "agent:cs_photo")
