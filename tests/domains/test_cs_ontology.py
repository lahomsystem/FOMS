"""바꿔 묻기 대응(사장님 11-11 '온톨로지화해야 다양한 변형에 대응') — 세 칸(처음 끔) · 숫자 같은 값 · 다른 말 · 용어 · 규격 싣기 ·
같은 뜻이면 답하기. 끄면 예전 그대로(같은 바이트)인지도 본다.

합성 회사 지식 항목 · 합성 초안만(네트워크 0). 손님 글 · 금액 원본 없음.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.persistence.brain.models import BrainObject
from foms.services.cs_agent import brain_prompt as bp
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.brain_instructions import INSTRUCTIONS
from foms.services.cs_agent.checks import check_draft
from foms.services.cs_agent.knowledge_doc import ApprovedKnowledge, KnowledgeItem
from foms.services.cs_agent.onto_settings import ONTO_FIELDS, OntoFlags, onto_flags
from foms.services.cs_agent.ontology import Ontology, OntoItem, load_ontology, with_ontology
from foms.services.cs_agent.ontology_text import EXTRA_HEAD, OLD_HEAD, OLD_RULE, ONTO_HEAD, ONTO_RULE
from models import SystemSetting
from tests.domains.test_cs_photo_read import PHONE

KNOWN = ("제작 기간은 약 2주 걸려요. 선반 깊이는 350mm 예요. 보증은 1년이에요. 상판 18mm 는 15만 원이에요.",)
CUSTOMER = ["가로 1200 짜리로 하고 싶어요, 예산은 20만 원이요, 3주 안에 되나요"]
TODAY = datetime.date(2026, 11, 11)


def codes(text, *, on):
    extra = {"same_values": True, "customer_texts": CUSTOMER} if on else {}
    return [p.code for p in check_draft(text, brand="LAHOM", medium="native", allowed_numbers=KNOWN, **extra).problems]


# ── 숫자 같은 값 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "제작은 2주일 정도 걸려요.", "제작은 14일 정도 걸려요.", "선반 깊이는 35cm 예요.", "선반 깊이 0.35m 예요.",
    "보증은 12개월이에요.", "가로 1200mm 로 맞춰 드려요.",
])
def test_same_values_pass_only_when_switched_on(text):
    assert codes(text, on=False) == ["number_not_allowed"]  # 끔 — 예전처럼 글자 그대로만
    assert codes(text, on=True) == []


@pytest.mark.parametrize("text", [
    "20만 원이에요.",  # 손님 예산 금액 — 손님 글에서 가져오지 않는다(D164)
    "3주 걸려요.",  # 손님이 말한 기간 — 약속이 된다
    "10일이면 돼요.",  # 2주(14일)와 다른 값
    "상판은 16만 원이에요.",  # 지식에 없는 금액
])
def test_amounts_periods_and_other_values_stay_blocked(text):
    assert codes(text, on=True) == ["number_not_allowed"]


# ── 다른 말 · 용어 · 규격 싣기 · 같은 뜻이면 답하기(프롬프트) ─────────────
def knowledge(onto=None):
    item = KnowledgeItem(item_id="fact-depth", kind="fact", intents=(), text="선반 깊이는 350mm 예요.", status="approved")
    return ApprovedKnowledge("LAHOM", 3, (item,), None, onto)


def test_switched_off_the_prompt_is_byte_for_byte_the_old_one():
    old = bp.knowledge_text(knowledge())
    assert old.splitlines()[0] == OLD_HEAD and EXTRA_HEAD not in old
    assert bp.knowledge_text(knowledge(Ontology(OntoFlags()))) == old
    assert OLD_RULE in INSTRUCTIONS  # 바꿔 낄 8번 글이 지시문에 그대로 있어야 한다(지시문을 고치면 이 시험이 알린다)
    assert bp.instructions("LAHOM") == bp.instructions("LAHOM", knowledge=knowledge())
    assert knowledge().same_values() is False and knowledge().spoken_texts() == ("선반 깊이는 350mm 예요.",)


def test_labels_and_rule_reach_the_prompt_when_switched_on():
    onto = Ontology(OntoFlags(numbers=True, labels=True, prompt=True), {"fact-depth": ("선반 폭", "안쪽 깊이")},
                    (OntoItem("term-shelf", "용어", "선반", "벽에 다는 판이에요. 두께 18mm.", ("시렁",)),))
    text = bp.knowledge_text(knowledge(onto))
    lines = text.splitlines()
    assert lines[0] == ONTO_HEAD and lines[2].strip() == "다른 말: 선반 폭 · 안쪽 깊이"
    assert EXTRA_HEAD in lines and "[onto:term-shelf] (용어) 선반 — 벽에 다는 판이에요. 두께 18mm. (다른 말: 시렁)" in lines
    rules = bp.instructions("LAHOM", knowledge=knowledge(onto))
    assert ONTO_RULE in rules and OLD_RULE not in rules
    assert "두께 18mm" in " ".join(knowledge(onto).spoken_texts()) and knowledge(onto).same_values() is True
    assert bp.evidence_choices(knowledge(onto)) == ("fact-depth",)  # 덧붙인 항목은 근거 id 로 고르지 않는다


# ── 회사 지식 표에서 읽기 ─────────────────────────────────────────────────
def brain_row(key, item_type, name, text, *, payload=None, brand="LAHOM", status="active", visibility="all",
              superseded=False, valid_to=None):
    db_session.add(BrainObject(item_key=key, version=1, brand=brand, layer="common", item_type=item_type, name=name,
                               text=text, status=status, visibility=visibility, payload=payload or {},
                               confidence="confirmed", created_by="import", valid_to=valid_to,
                               superseded_at=datetime.datetime(2026, 11, 1) if superseded else None))


def test_load_reads_only_current_active_public_items_and_drops_risky_labels(app):
    brain_row("fact.depth", "fact", "선반 깊이", "선반 깊이는 350mm",
              payload={"doc_id": "fact-depth", "aliases": ["안쪽 깊이", PHONE, "x" * 60]})
    brain_row("term.shelf", "term", "선반", "벽에 다는 판", payload={"aliases": ["시렁"]})
    brain_row("spec.top", "spec", "상판 두께", "상판은 18mm", brand="COMMON")
    brain_row("spec.secret", "spec", "원가", "[내부] 원가 표")
    brain_row("term.admin", "term", "관리 용어", "관리자만", visibility="admin")
    brain_row("term.old", "term", "옛 말", "옛 글", superseded=True)
    brain_row("term.draft", "term", "초안 말", "초안 글", status="draft")
    brain_row("term.ended", "term", "끝난 말", "끝난 글", valid_to=datetime.date(2026, 10, 1))
    brain_row("term.haud", "term", "하우드 말", "하우드 글", brand="HAUD")
    db_session.commit()
    onto = load_ontology(db_session, "LAHOM", OntoFlags(labels=True), today=TODAY)
    assert dict(onto.aliases) == {"fact-depth": ("선반 깊이", "안쪽 깊이")}  # 전화 꼴 · 너무 긴 이름표는 뺀다
    assert [(i.key, i.kind, i.name, i.aliases) for i in onto.extra] == [
        ("spec.top", "규격", "상판 두께", ()), ("term.shelf", "용어", "선반", ("시렁",))]
    assert load_ontology(db_session, "LAHOM", OntoFlags(numbers=True), today=TODAY).extra == ()  # '싣기' 끔


def test_with_ontology_follows_the_three_panel_switches(app):
    base = knowledge()
    assert with_ontology(db_session, base) is base  # 처음 값 — 모두 끔
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={
        **st.DEFAULTS, "onto_numbers_enabled": True, "onto_prompt_enabled": True}))
    db_session.commit()
    got = with_ontology(db_session, base)
    assert got.onto.flags == OntoFlags(numbers=True, labels=False, prompt=True) and got.onto.extra == ()
    assert [f.default for f in ONTO_FIELDS] == [False] * 7  # 넷째 = 주문 확인해 답하기(5.6) · 다섯째 = 물건 찾아 따라가기(5절) · 여섯째 = 뜻으로도 물건 찾기(D197) · 일곱째 = 뜻으로도 비슷한 상담(D197 ③)
    assert onto_flags({"onto_labels_enabled": "yes"}) == OntoFlags()  # 참일 때만 켬
