"""전사 지식 온톨로지 점검 '지금' 항목(⑤-5) — 챗봇 · 벡터 · 이웃 · 수가 같이 읽는 거르기와 이음새.

1. 기본 읽기 거르기 하나 — 초안 · 은퇴 · 유효 시작 전 · 대체된 항목은 챗봇 후보 · 찾기 · 이웃 · 수 · 벡터에서 빠지고, 카드는 표시를 단다.
2. SKOS 이름표(대표 · 다른 · 숨은 · 위 낱말)가 용어 밖(제품 라인 · 옵션 · 정책)에도 있고 찾기 · 벡터 글이 쓴다.
3. ``about`` 링크 — 열린 엇갈림이 그 항목을 '확인 필요'로(지식 표 · 카드 · 챗봇). 근거 관문은 사람 수.
5. 옮길 때 보기 범위 좁히기(``basic-account`` → 관리) · 계좌 같은 번호는 벡터로 보내지 않음.
6. 점검 평가 질문 여섯 + 말 바뀜(제주 · 도서산간)이 실행되는 시험.
합성 지식 · 합성 계정 · 가짜 모델 · 가짜 벡터만.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.vectors import brain_embeddings, vector_metadata
from foms.services.brain.around import AroundQuery, search_around
from foms.services.brain.browse import TableQuery, search_grouped, table_page
from foms.services.brain.card import item_card
from foms.services.brain.chat_retrieve import retrieve
from foms.services.brain.chat_settings import EMBED_FIELD, read_chat_settings
from foms.services.brain.chat_tools import search_objects
from foms.services.brain.constants import SCOPE_ADMIN, SCOPE_ALL
from foms.services.brain.doc_bridge import IMPORT_SCOPE_OVERRIDES, doc_values, import_visibility
from foms.services.brain.doc_import import desired_items, plan_import
from foms.services.brain.embed_sources import run_embed
from foms.services.brain.embeddings import account_like, doc_text, embedder_source, nearest
from foms.services.brain.eval_set import run_eval
from foms.services.brain.read import count_items
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from foms.services.cs_agent.knowledge_doc import KIND_OWNER_DECISION
from tests.support.brain_chat_eval_set import audit_questions, seed, seed_audit
from tests.support.brain_chat_support import NOW_KST, axis, chat_world, fake_embedder
from tests.support.brain_support import create, link, person

TODAY = NOW_KST.date()


@pytest.fixture
def people(app):
    who = chat_world(db_session)
    admin = who["admin"]
    create(db_session, admin, "common/sliding-draft", item_type="spec", name="슬라이딩 초안 깊이", status="draft",
           text="슬라이딩 깊이 초안 합성", payload={"value": 700, "unit": "mm"})
    create(db_session, admin, "common/sliding-next", item_type="spec", name="슬라이딩 다음 깊이",
           text="슬라이딩 깊이 다음 해 합성", valid_from="2027-01-01", payload={"value": 680, "unit": "mm"})
    create(db_session, admin, "common/sliding-old", item_type="spec", name="슬라이딩 옛 깊이",
           text="슬라이딩 깊이 옛 합성", payload={"value": 600, "unit": "mm"})
    create(db_session, admin, "common/sliding-decision", item_type="owner_decision", name="슬라이딩 깊이 결정",
           text="슬라이딩 깊이를 새로 정한 합성 결정", evidence_ref="원장 합성",
           payload={"doc_id": "sliding-decision", "approved_by": "합성", "approved_at": "2026-10-30",
                    "decision_no": "D1"})
    link(db_session, admin, "supersedes", "common/sliding-decision", "common/sliding-old")
    db_session.commit()
    return who


HIDDEN = {"common/sliding-draft", "common/sliding-next", "common/sliding-old"}


# ── 1. 기본 읽기 거르기 하나 ─────────────────────────────────────────────
def test_one_default_read_filter_for_chat_search_around_counts_and_vectors(people):
    who = viewer_of(people["admin"])
    chat = {c.key for c in retrieve(db_session, who, "슬라이딩 깊이", today=TODAY).candidates}
    assert "common/sliding" in chat and "common/sliding-decision" in chat and not (chat & HIDDEN)
    assert not ({h["key"] for h in search_objects(db_session, who, "슬라이딩 깊이", today=TODAY)} & HIDDEN)
    screen = {i["key"] for g in search_grouped(db_session, who, "슬라이딩", today=TODAY)["groups"] for i in g["items"]}
    assert "common/sliding" in screen and not (screen & HIDDEN)
    assert count_items(db_session, who, today=TODAY)["types"]["spec"] == 1  # 수도 같은 거르기
    around = search_around(db_session, who, AroundQuery("common/sliding-decision"), today=TODAY)
    assert around["items"] == [] and around["total"] == 0  # 대체된 앞 항목으로는 닿지 않는다
    table = {r["key"] for r in table_page(db_session, who, TableQuery("spec", status="draft"), today=TODAY)["rows"]}
    assert table == {"common/sliding-draft"}  # 지식 표에서 상태로 고르면 보인다(대조군)
    vector_metadata.create_all(db_session.get_bind())
    try:
        from tests.support.brain_chat_support import chat_on
        chat_on(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00"})
        with embedder_source(fake_embedder({"슬라이딩": axis(0)})):
            run_embed(db_session, cfg=read_chat_settings(db_session), now=NOW_KST, apply=True)
        stored = set(db_session.execute(select(brain_embeddings.c.source_key).where(
            brain_embeddings.c.source_kind == "brain_item")).scalars())
        assert "common/sliding-draft" not in stored  # 초안은 넣지도 않는다
        near = {k for k, _s in nearest(db_session, who, axis(0), today=TODAY, limit=10)}
        assert "common/sliding" in near and not (near & HIDDEN)  # 넣었어도(다음 해 · 대체) 읽을 때 같은 거르기
    finally:
        db_session.remove()
        vector_metadata.drop_all(db_session.get_bind())


def test_cards_still_open_and_show_effect_badges(people, app):
    who = viewer_of(people["admin"])
    old = item_card(db_session, who, "common/sliding-old", today=TODAY)
    nxt = item_card(db_session, who, "common/sliding-next", today=TODAY)
    draft = item_card(db_session, who, "common/sliding-draft", today=TODAY)
    assert old["effect"] == {"effective": False, "not_yet": False, "superseded_by": ["common/sliding-decision"],
                             "status": "active"}
    assert nxt["effect"]["not_yet"] is True and draft["effect"]["effective"] is False
    assert item_card(db_session, who, "common/sliding", today=TODAY)["effect"]["effective"] is True  # 대조군
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = people["admin"].id
    html = client.get("/brain/items/common/sliding-old").get_data(as_text=True)
    assert 'data-brain-superseded-by="common/sliding-decision"' in html


# ── 2. SKOS 이름표 ───────────────────────────────────────────────────────
def test_pref_alt_hidden_labels_on_policy_product_and_option(people):
    admin = people["admin"]
    create(db_session, admin, "common/policy-remote", item_type="policy", name="remote-fee", text="먼 곳 운임 합성 정책",
           checked_at="2026-10-30", payload={"doc_id": "remote-fee", "approved_by": "합성", "approved_at": "2026-10-30",
                                             "pref_label": "도서산간 운임", "aliases": ["섬 운임"],
                                             "hidden_labels": ["도서 산간"]})
    create(db_session, admin, "common/door-line", item_type="product_line", name="여닫이 문짝 라인", text="합성 제품",
           payload={"aliases": ["스윙도어"], "hidden_labels": ["스윙 도아"]})
    db_session.commit()
    who = viewer_of(admin)
    for query, key in (("섬 운임 알려 줘", "common/policy-remote"), ("도서산간 운임 얼마", "common/policy-remote"),
                       ("스윙 도아 되나요", "common/door-line"), ("스윙도어 라인", "common/door-line")):
        assert search_objects(db_session, who, query, today=TODAY)[0]["key"] == key, query
    found = retrieve(db_session, who, "섬 운임 알려 줘", today=TODAY)
    assert found.candidates[0].name == "도서산간 운임"  # 대표 이름으로 보인다
    body = doc_text(current_object(db_session, "common/policy-remote"))
    assert body.startswith("도서산간 운임\nremote-fee") and "섬 운임" in body and "도서 산간" in body


# ── 3. about 링크 · 열린 엇갈림 ──────────────────────────────────────────
def test_open_conflict_about_an_item_marks_it_needs_check(people):
    admin = people["admin"]
    create(db_session, admin, "conflict/hinge", item_type="conflict", name="경첩 엇갈림", text="매크로와 값이 다름 합성",
           confidence="observed", visibility="all")
    link(db_session, admin, "about", "conflict/hinge", "common/hinge")
    db_session.commit()
    who = viewer_of(admin)
    card = item_card(db_session, who, "common/hinge", today=TODAY)
    assert card["open_conflicts"] == 1 and card["item"]["needs_check"] is True
    rows = {r["key"]: r for r in table_page(db_session, who, TableQuery("build_rule", check="needs_check"),
                                            today=TODAY)["rows"]}
    assert "common/hinge" in rows
    found = {c.key: c for c in retrieve(db_session, who, "여닫이 경첩 조건", today=TODAY).candidates}
    assert found["common/hinge"].usable is False and found["common/hinge"].why == "conflict"
    assert item_card(db_session, who, "common/sliding", today=TODAY)["open_conflicts"] == 0  # 대조군


# ── 5. 옮길 때 보기 범위 좁히기 · 계좌 번호 ──────────────────────────────
def test_import_scope_override_and_account_numbers_never_embedded(app):
    admin = person(db_session, "sc_admin")
    assert IMPORT_SCOPE_OVERRIDES == {"basic-account": SCOPE_ALL}  # 사장님 11-02 — 내부 모두(정해 두는 틀은 그대로)
    assert import_visibility("basic-account") == SCOPE_ALL and import_visibility("other") == SCOPE_ALL
    item = {"id": "basic-account", "kind": KIND_OWNER_DECISION, "intents": [], "text": "합성 입금 안내",
            "status": "approved", "approved_by": "합성", "approved_at": "2026-10-30", "checked_at": None, "source": None,
            "tags": []}
    assert doc_values(item, item_type="owner_decision", positions={"LAHOM": 0}, evidence_ref="합성")["visibility"] == "all"
    create(db_session, admin, "lahom/basic-account", item_type="owner_decision", brand="LAHOM",
           name="basic-account", text="합성 입금 안내", evidence_ref="합성",
           payload={"doc_id": "basic-account", "approved_by": "합성", "approved_at": "2026-10-30", "decision_no": "D2"})
    db_session.commit()
    docs = {"LAHOM": {"schema_version": 1, "brand": "LAHOM", "items": [item]}}
    plan = plan_import(db_session, desired_items(docs))
    updates = {wanted.key: after for wanted, _row, after in plan.updates}
    assert "visibility" not in updates.get("lahom/basic-account", {})  # 이미 '내부 모두' — 범위를 바꾸지 않는다
    from foms.services.brain import doc_bridge
    doc_bridge.IMPORT_SCOPE_OVERRIDES["basic-account"] = SCOPE_ADMIN  # 틀은 그대로 — 좁히기로 바꾸면 옮긴 줄도 맞춘다
    try:
        narrowed = {w.key: a for w, _r, a in plan_import(db_session, desired_items(docs)).updates}
        assert narrowed["lahom/basic-account"]["visibility"] == SCOPE_ADMIN
    finally:
        doc_bridge.IMPORT_SCOPE_OVERRIDES["basic-account"] = SCOPE_ALL
    row = current_object(db_session, "lahom/basic-account")
    row.visibility = "all"  # 좁히기 전 꼴로 — 계좌 글이 들어 있어도 벡터 글이 되지 않는다
    row.text = "입금 계좌 110-123-456789"
    assert account_like(row.text) and doc_text(row) is None
    db_session.rollback()


# ── 6. 점검 평가 질문 여섯 + 말 바뀜 ─────────────────────────────────────
def test_audit_competency_and_synonym_questions_are_executable(app):
    admin = person(db_session, "ax_admin")
    seed(db_session, admin)
    seed_audit(db_session, admin)
    who = viewer_of(admin)
    qs = audit_questions()
    assert len(qs) == 9 and {q.qid for q in qs} >= {"x01", "x02", "x03", "x04", "x05", "x06", "x07", "s01", "s02"}

    def recall(question):
        keys = [c.key for c in retrieve(db_session, who, question.q, today=TODAY).usable]
        return {"unknown": not keys, "evidence": keys}

    score = run_eval(qs, recall)
    assert score.hit == 9 and score.passed, score.as_dict()
    later = retrieve(db_session, who, "옛 몰딩 기준은?", today=TODAY)
    assert "eval/old-molding" not in {c.key for c in later.candidates}  # D83 이 대체한 앞 항목은 읽지 않는다
    assert "eval/d83" in {c.key for c in later.usable}
    copies = {c.key: c.copies for c in retrieve(db_session, who, "슬라이딩 깊이 값을 베끼는 매크로는?", today=TODAY).usable}
    assert copies["eval/sliding"] == ["매크로 깊이 안내"]  # 사본 목록이 두뇌 후보에 간다
