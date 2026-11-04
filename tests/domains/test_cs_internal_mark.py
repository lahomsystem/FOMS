"""손님에게 말하지 않는 회사 안 규칙 — 지식 글 [내부] 표시(사장님 D164 · master brain 설계서 7.9).

[사람] 과 같은 꼴: 두뇌 지시문 한 줄 · 초안 숫자 허용 목록에서 빼기 · 초안 검사 내부 말 · 지식 화면 표시. 값은 모두 합성.
"""

from __future__ import annotations

from db import db_session
from foms.services.cs_agent.brain_prompt import instructions, knowledge_text
from foms.services.cs_agent.checks import check_draft
from foms.services.cs_agent.knowledge_doc import INTERNAL_MARK, ApprovedKnowledge, KnowledgeItem


def _item(item_id, text, kind="policy"):
    return KnowledgeItem(item_id=item_id, kind=kind, status="approved", text=text, intents=(),
                         approved_by="synthetic-owner", approved_at="2026-10-20")


KNOWLEDGE = ApprovedKnowledge("LAHOM", 1, (
    _item("plain", "합성 안내 7,777원(가짜 값)"),
    _item("staff", "합성 지방 운임 4,321원(가짜 값) [사람]", kind="price_rule"),
    _item("inside", "합성 벌점 규칙 — 3회면 9,876원(가짜 값) [내부]"),
))


def test_spoken_texts_drop_internal_and_human_only_items():
    assert KNOWLEDGE.spoken_texts() == ("합성 안내 7,777원(가짜 값)",)  # 표시 없는 항목은 남는다(대조군)


def test_draft_with_an_internal_number_or_mark_is_stopped():
    allowed = KNOWLEDGE.spoken_texts()
    assert check_draft("안내 금액은 7,777원입니다", brand="LAHOM", allowed_numbers=allowed).ok  # 대조군
    leak = check_draft("벌점이 9,876원이라 어렵습니다", brand="LAHOM", allowed_numbers=allowed)
    assert not leak.ok
    assert "internal_words" in check_draft(f"{INTERNAL_MARK} 회사 규칙입니다", brand="LAHOM").codes
    assert check_draft("회사 규칙상 어렵습니다", brand="LAHOM").ok


def test_instructions_say_internal_items_are_for_judgement_only_and_the_mark_reaches_the_prompt():
    text = instructions("LAHOM")
    assert "[내부] 표시가 있는 항목은 손님에게 말하지 않는 회사 안 규칙" in text and "답에 쓰지 않는다" in text
    assert "[inside] (policy) 합성 벌점 규칙" in knowledge_text(KNOWLEDGE) and INTERNAL_MARK in knowledge_text(KNOWLEDGE)


def test_item_page_marks_internal_rules(app):
    from foms.services.brain.card import item_card
    from foms.services.brain.scope import viewer_of
    from tests.support.brain_support import NOW, create
    from tests.support.brain_review_support import people

    who = people(db_session)
    create(db_session, who["admin"], "cs/rule/penalty", item_type="lesson", layer="cs", name="벌점 규칙",
           text=f"합성 벌점 규칙 {INTERNAL_MARK}")
    create(db_session, who["admin"], "cs/rule/plain", item_type="lesson", layer="cs", name="보통 규칙", text="합성 규칙")
    db_session.commit()
    today = NOW.date()
    assert item_card(db_session, viewer_of(who["admin"]), "cs/rule/penalty", today=today)["item"]["internal"] is True
    assert item_card(db_session, viewer_of(who["admin"]), "cs/rule/plain", today=today)["item"]["internal"] is False
