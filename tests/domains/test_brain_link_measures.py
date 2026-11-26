"""재는 자(설계서 2026-11-26 온톨로지 잇기 3.1 · 8절) — 읽기만 하는 잇기 수 · 실제 쓰임 순 정렬.

- 잇기 없는 살아 있는 지식 수 · 비율: 반영 상태만(초안은 뺌), 볼 수 없는 끝으로 가는 잇기는 세지 않는다(도면팀만 보는 규칙의
  잇기는 CS 팀장에게 '잇기 없음' — 같은 모집단의 대조군).
- 글이 다른 지식 이름(이름 · 다른 이름)을 말하는데 안 이어진 짝: 이을 수 있음 / 틀이 막음, 이미 이어진 짝 · 3자 미만 이름은 뺀다.
- 새 지식이 생긴 날 이어진 비율(최근 30일): 다음 날 이어진 것 · 창 밖 옛 지식은 세지 않는다.
- 잇기 뒤 글이 바뀐 끝 항목 수: 잇기 뒤 고친 항목만(잇기 없는 항목을 고친 것은 대조군).
- 온톨로지 능력 질문 응답의 ``linked_pct`` · 품질 수 API 의 ``linking`` 칸.
- 쓰인 횟수 정렬: 판 줄 칸(아무도 올리지 않음)이 아니라 따로 센 합으로 — 세기 전 순서가 대조군.

합성 항목만(이름 · 글은 지어낸 것).
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.persistence.brain.models import BrainLink
from foms.services.brain.apply import apply_change
from foms.services.brain.ontology_view import _coverage, ontology_summary, ontology_type
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.quality import MIN_MENTION, link_measures, linked_share, mention_pairs, quality_counts
from foms.services.brain.scope import viewer_of
from foms.services.brain.usage import READER_CS, count_reads
from foms.services.cs_agent.onto_find import RULE_TYPES, _rules
from foms.services.cs_agent.onto_follow import _linked
from tests.support.brain_support import NOW, REASON, create, link, person

TODAY = datetime.date(2026, 11, 3)  # NOW(11-02 한국 10시) 다음 날
NEXT_DAY = NOW + datetime.timedelta(days=1)


@pytest.fixture
def who(app):
    admin = person(db_session, "lm_admin")
    cs_mgr = person(db_session, "lm_cs_mgr", role="MANAGER", team="CS")
    create(db_session, admin, "common/m-door", name="합성 큰 문짝", text="합성 설명 하나")
    create(db_session, admin, "common/m-slide", name="합성 미닫이", text="합성 설명 둘", payload={"aliases": ["합성 옆문"]})
    create(db_session, admin, "common/m-short", name="짝짝", text="합성 설명 셋")
    create(db_session, admin, "common/m-rule-a", item_type="build_rule", name="합성 규칙 가", text="합성큰 문짝은 여닫이만")
    create(db_session, admin, "common/m-rule-b", item_type="build_rule", name="합성 규칙 나", text="합성 미닫이는 짝짝 둘")
    create(db_session, admin, "common/m-rule-c", item_type="build_rule", name="합성 규칙 다", text="합성 옆문 쪽")
    create(db_session, admin, "common/m-word", item_type="term", name="합성 낱말", text="합성 큰 문짝을 부르는 말")
    create(db_session, admin, "common/m-draw", item_type="drawing_rule", layer="drawing", name="합성 도면 규칙",
           text="합성 설명 넷", visibility="team:DRAWING")
    create(db_session, admin, "common/m-late", name="합성 늦은 것", text="합성 설명 다섯")
    create(db_session, admin, "common/m-late-rule", item_type="build_rule", name="합성 규칙 라", text="합성 설명 여섯")
    create(db_session, admin, "common/m-old", name="합성 옛 것", text="합성 설명 일곱", now=NOW - datetime.timedelta(days=40))
    create(db_session, admin, "common/m-draft", item_type="build_rule", name="합성 초안", text="합성 큰 문짝", status="draft")
    link(db_session, admin, "applies_to", "common/m-rule-a", "common/m-door")
    link(db_session, admin, "applies_to", "common/m-draw", "common/m-slide")
    link(db_session, admin, "applies_to", "common/m-late-rule", "common/m-short", now=NEXT_DAY)
    later = NOW + datetime.timedelta(hours=2)
    for key, text in (("common/m-door", "합성 설명 고침"), ("common/m-rule-b", "합성 미닫이는 짝짝 셋")):
        # 잇기 뒤 고친 항목 · 잇기 없는 항목 고침(대조군)
        fix = propose_update(db_session, key=key, base_version=1, after={"text": text}, reason=REASON,
                             proposer=Proposer.user(admin.id), now=later, known="")
        apply_change(db_session, fix.id, actor=admin, now=later)
    db_session.commit()
    return {"admin": viewer_of(admin), "cs_mgr": viewer_of(cs_mgr)}


def test_unlinked_counts_only_active_items_and_links_whose_ends_the_viewer_sees(who):
    admin = link_measures(db_session, who["admin"], today=TODAY)
    assert (admin["alive"], admin["unlinked"], admin["unlinked_pct"]) == (11, 5, 45)  # 초안은 살아 있는 지식이 아니다
    cs = link_measures(db_session, who["cs_mgr"], today=TODAY)
    assert (cs["alive"], cs["unlinked"], cs["unlinked_pct"]) == (10, 6, 60)  # 미닫이의 잇기는 도면팀 규칙에서 온다
    assert linked_share(db_session, who["admin"], today=TODAY) == {"alive": 11, "linked": 6, "pct": 55}
    assert linked_share(db_session, who["cs_mgr"], today=TODAY) == {"alive": 10, "linked": 4, "pct": 40}


def test_name_mentions_without_a_link_split_into_open_and_blocked(who):
    # 규칙 나 → 미닫이(이름) · 규칙 다 → 미닫이(다른 이름)는 이을 수 있음, 낱말 → 큰 문짝은 틀이 막음.
    # 규칙 가 → 큰 문짝은 이미 이어짐, '짝짝'은 3자 미만, 초안이 말한 이름은 세지 않는다.
    assert link_measures(db_session, who["admin"], today=TODAY)["mention_pairs"] == {"open": 2, "blocked": 1}


def test_mention_pairs_ignore_spacing_self_names_and_short_names():
    def row(key, item_type, name, text, payload=None):
        return type("Row", (), {"item_key": key, "item_type": item_type, "name": name, "text": text, "payload": payload})

    rows = [row("a", "product_line", "합성 붙박이장", "합성 붙박이장 설명"), row("b", "build_rule", "합성 규칙", "합성붙박이 장은 짝"),
            row("c", "term", "짝", "합성 규칙 쓰는 곳"), row("d", "build_rule", "합성 다른 규칙", "합성 붙박이장 · 합성 붙박이장")]
    assert MIN_MENTION == 3
    got = mention_pairs(rows, tied={frozenset(("a", "d"))})
    assert got == {"open": 1, "blocked": 1}  # b→a 이을 수 있음 · c→b(낱말 → 제작 조건) 틀이 막음 · '짝'은 짧음 · a↔d 이어짐


def test_same_day_link_rate_in_the_last_30_days(who):
    admin = link_measures(db_session, who["admin"], today=TODAY)["same_day"]
    assert admin == {"days": 30, "new": 10, "linked": 4, "pct": 40}  # 옛 것(40일 전)은 창 밖 · 다음 날 이은 둘은 안 셈
    cs = link_measures(db_session, who["cs_mgr"], today=TODAY)["same_day"]
    assert cs == {"days": 30, "new": 9, "linked": 2, "pct": 22}


def test_items_changed_after_their_link_are_counted(who):
    assert link_measures(db_session, who["admin"], today=TODAY)["changed_after_link"] == 1  # 큰 문짝만(규칙 나는 잇기 없음)


def test_quality_api_and_ontology_carry_the_new_fields_without_touching_old_ones(who, app):
    counts = quality_counts(db_session, who["admin"], today=TODAY)
    assert {"rules", "missing_total", "over_total", "retired_links", "off_list"} <= set(counts)
    assert counts["linking"] == link_measures(db_session, who["admin"], today=TODAY)
    summary = ontology_summary(db_session, who["admin"], today=TODAY)
    assert summary["cq"]["linked_pct"] == 55 and {"rows", "covered", "total"} <= set(summary["cq"])
    assert ontology_summary(db_session, who["admin"], today=TODAY, erp=True)["cq"]["linked_pct"] == 55
    assert _coverage({}, {})["linked_pct"] is None  # 셀 것이 없으면 값 없음
    before = db_session.query(BrainLink).count()
    link_measures(db_session, who["cs_mgr"], today=TODAY)
    assert db_session.query(BrainLink).count() == before  # 읽기만


def test_rules_sort_by_real_usage_not_the_dead_column(app):
    admin = person(db_session, "lm_usage_admin")
    create(db_session, admin, "product_line/lm-1", brand="LAHOM", name="합성 쓰임 장")
    for key in ("common/lm-spec-a", "common/lm-spec-b"):
        create(db_session, admin, key, item_type="spec", name=f"합성 규격 {key[-1]}", payload={"value": 18, "unit": "mm"})
        link(db_session, admin, "applies_to", key, "product_line/lm-1")
    db_session.commit()
    day = datetime.date(2026, 11, 2)
    viewer = viewer_of(admin)

    def order():
        found = [r.key for r in _rules(db_session, ["product_line/lm-1"], "LAHOM", day)["product_line/lm-1"]]
        followed = [r.key for _end, r in _linked(db_session, "applies_to", ["product_line/lm-1"], near=BrainLink.to_key,
                                                 far=BrainLink.from_key, types=RULE_TYPES, brand="LAHOM", day=day)]
        examples = [e["key"] for e in ontology_type(db_session, viewer, "spec", today=day)["examples"]]
        return found, followed, examples

    assert order() == (["common/lm-spec-a", "common/lm-spec-b"],) * 3  # 세기 전 — 키 순(대조군)
    for _ in range(3):
        count_reads(db_session, ["common/lm-spec-b"], READER_CS, now=NOW)
    db_session.commit()
    assert order() == (["common/lm-spec-b", "common/lm-spec-a"],) * 3
    used = _rules(db_session, ["product_line/lm-1"], "LAHOM", day)["product_line/lm-1"][0]
    assert used.usage == 3
