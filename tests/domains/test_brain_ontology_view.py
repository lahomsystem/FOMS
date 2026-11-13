"""온톨로지 탭 자료(설계서 2026-11-12 온톨로지 7절 · D187 · D188) — Palantir Ontology Manager 꼴, 읽기만.

왼쪽 목록(종류 · 연결 · 동작 · 능력 질문 점수)과 오른쪽 상세(속성 틀 · 채움 · 연결 · 예시)가 **보는 사람의 보기 범위로**
세는지(같은 모집단의 음성 대조군 — ADMIN 에게는 보이는 가격 재량 · 관리 항목이 CS 팀장에게는 0), 표준 이름이 모든 종류 ·
연결에 있는지, 능력 질문 점수가 물건이 생기면 오르는지. 합성 항목만.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain.constants import LINK_KINDS, TYPES
from foms.services.brain.ontology_cqs import CQS
from foms.services.brain.ontology_view import (
    LINK_STANDARDS, TYPE_STANDARDS, _coverage, ontology_summary, ontology_type,
)
from foms.services.brain.schemas import TYPE_SCHEMAS
from foms.services.brain.scope import viewer_of
from tests.support.brain_screen_support import TODAY, world


@pytest.fixture
def who(app):
    people = world(db_session)
    return {"users": people, **{name: viewer_of(user) for name, user in people.items()}}


def _types(summary):
    return {t["type"]: t["count"] for g in summary["groups"] for t in g["types"]}


def test_summary_counts_within_scope_and_names_every_type_and_link(who):
    admin, cs = ontology_summary(db_session, who["admin"], today=TODAY), ontology_summary(db_session, who["cs_mgr"], today=TODAY)
    assert set(_types(admin)) == set(TYPES)  # 바깥 정본 · 사본은 물건 종류가 아니다
    assert _types(admin)["price_rule"] == 1 and _types(cs)["price_rule"] == 0  # 가격 재량은 범위 밖 — 대조군
    assert _types(admin)["question"] == 1 and _types(cs)["question"] == 0
    links = {l["kind"]: l["count"] for l in admin["links"]}
    assert [l["kind"] for l in admin["links"]] == list(LINK_KINDS)
    assert links["applies_to"] == 3 and {l["kind"]: l["count"] for l in cs["links"]}["applies_to"] == 1
    assert links["value_from"] == 2 and admin["actions"] and any(a["agent"] for a in admin["actions"])
    assert set(TYPE_STANDARDS) == set(TYPES) and set(LINK_STANDARDS) == set(LINK_KINDS)
    assert admin["group_labels"]["external"]  # 바깥 묶음 이름도 실음(연결 끝 줄임 글)


def test_detail_lists_schema_props_with_fill_and_links_with_counts(who):
    detail = ontology_type(db_session, who["admin"], "product_line", today=TODAY)
    paths = [p["path"] for p in detail["props"]]
    assert paths == [p.path for p in TYPE_SCHEMAS["product_line"]]
    text = next(p for p in detail["props"] if p["path"] == "text")
    assert (text["filled"], text["total"], text["required"], text["standard"]) == (2, 2, "always", "skos:definition")
    door = next(p for p in detail["props"] if p["path"] == "payload.door_kinds")
    assert door["filled"] == 0 and {c["label"] for c in door["choices"]} >= {"여닫이", "슬라이딩"}
    out = {(l["direction"], l["kind"]): l for l in detail["links"]}
    assert out[("out", "value_from")]["count"] == 2 and out[("out", "value_from")]["external"]
    assert out[("in", "applies_to")]["count"] == 3  # 들어오는 수는 시작 항목을 볼 수 있는 것만
    cs = ontology_type(db_session, who["cs_mgr"], "product_line", today=TODAY)
    assert {(l["direction"], l["kind"]): l for l in cs["links"]}[("in", "applies_to")]["count"] == 1
    assert {e["key"] for e in detail["examples"]} == {"common/door", "common/slide"}
    assert ontology_type(db_session, who["admin"], "no_such_type", today=TODAY) is None
    step = ontology_type(db_session, who["admin"], "process_step", today=TODAY)
    assert {"payload.days_to_next", "payload.weekdays"} <= {p["path"] for p in step["props"]}


def test_competency_question_score_rises_when_needed_kinds_exist(who):
    before = ontology_summary(db_session, who["admin"], today=TODAY)["cq"]
    assert before["total"] == len(CQS) == 61
    erp = next(r for r in before["rows"] if any(n["erp"] for n in r["needs"]))
    assert not erp["covered"]  # ERP 주문 물건은 아직 없다(설계서 5.5 승인 대기)
    target = next(cq for cq in CQS if not any(n.startswith("erp:") for n in cq.needs))
    counts = {n: 1 for n in target.needs}
    links = {k: 1 for k in target.links}
    got = {r["id"]: r for r in _coverage(counts, links)["rows"]}
    assert got[target.cq_id]["covered"] is True  # 필요한 종류 · 연결이 다 있으면 '있음'
    missing = {k: 0 for k in target.links}
    assert got_row(counts, missing, target.cq_id)["covered"] is False  # 연결 하나라도 없으면 '모자람' — 대조군
    assert sum(r["covered"] for r in before["rows"]) == before["covered"]


def got_row(counts, links, cq_id):
    return next(r for r in _coverage(counts, links)["rows"] if r["id"] == cq_id)


def test_d204_question_table_drops_only_the_two_unfillable_links_and_keeps_the_old_demands():
    """D204 — 상담 질문 뜻으로는 채울 길이 없는 ``part_of`` · ``uses`` 만 뺐고, 빈 자리는 ``applies_to`` 로만 채웠다. 옛 요구는 그대로 남는다."""
    from foms.services.brain.ontology_cqs import D204_DROPPED, LINKS_BEFORE_D204

    now = {cq.cq_id: set(cq.links) for cq in CQS}
    assert not any(D204_DROPPED & links for links in now.values())  # 지금 표에는 두 연결이 없다
    assert set(LINKS_BEFORE_D204) == {i for i, old in LINKS_BEFORE_D204.items() if D204_DROPPED & set(old)}
    for cq_id, old in LINKS_BEFORE_D204.items():
        assert set(old) - D204_DROPPED <= now[cq_id]  # 남은 요구는 하나도 빼지 않았다
        assert now[cq_id] - set(old) <= {"applies_to"}  # 새로 든 것은 '구성 → 적용'뿐
    untouched = [cq for cq in CQS if cq.cq_id not in LINKS_BEFORE_D204]
    assert len(untouched) == 61 - len(LINKS_BEFORE_D204) and all(not (D204_DROPPED & set(cq.links)) for cq in untouched)
