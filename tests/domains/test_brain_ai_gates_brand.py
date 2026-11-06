"""부딪침 관문은 같은 브랜드 + 공통 지식하고만 견준다(사장님 11-06 D176 — 하우드 카드가 라홈 전용 규칙에 막히던 것).

합성 찾기 결과만(네트워크 · 실제 회사 지식 없음). 판정자는 부르면 안 되는 자리에서 부르면 시험이 떨어진다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain import ai_gates
from foms.services.datetime_kst import get_today_kst

HITS = [
    {"key": "lahom/synth-a", "name": "합성 라홈", "text": "합성 라홈 전용 규칙", "brand": "LAHOM"},
    {"key": "haud/synth-b", "name": "합성 하우드", "text": "합성 하우드 전용 규칙", "brand": "HAUD"},
    {"key": "common/synth-c", "name": "합성 공통", "text": "합성 공통 규칙", "brand": "COMMON"},
]


@pytest.fixture
def fake_search(app, monkeypatch):
    def search(_session, _viewer, _query, *, today, limit):
        return [{**hit, "confidence": ai_gates.CONFIRMED, "score": 10.0, "visibility": "all"} for hit in HITS]

    monkeypatch.setattr(ai_gates, "search_objects", search)


def related(brand):
    return ai_gates.related_knowledge(db_session, key="haud/photo-new", texts=["합성 글"], today=get_today_kst(),
                                      brand=brand)


@pytest.mark.parametrize("brand, names", [
    ("HAUD", {"합성 하우드", "합성 공통"}),
    ("LAHOM", {"합성 라홈", "합성 공통"}),
    ("COMMON", {"합성 라홈", "합성 하우드", "합성 공통"}),
    (None, {"합성 라홈", "합성 하우드", "합성 공통"}),
])
def test_related_knowledge_keeps_same_brand_and_common(fake_search, brand, names):
    assert {line.split(":", 1)[0] for line in related(brand)} == names


def test_a_brand_proposal_is_not_judged_against_another_brand_only_rule(fake_search, monkeypatch):
    only_lahom = [HITS[0]]
    monkeypatch.setattr(ai_gates, "search_objects", lambda *_a, **_k: [
        {**hit, "confidence": ai_gates.CONFIRMED, "score": 10.0, "visibility": "all"} for hit in only_lahom])

    def judge(*_a):
        raise AssertionError("다른 브랜드 전용 규칙만 있으면 판정자를 부르지 않는다")

    with ai_gates.judge_source(judge):
        result = ai_gates.conflict_gate(db_session, op="create", key="haud/photo-new", item_type="policy",
                                        texts=["합성 글"], today=get_today_kst(), brand="HAUD")
    assert result == ai_gates.PASS
    with ai_gates.judge_source(lambda *_a: True):
        assert ai_gates.conflict_gate(db_session, op="create", key="lahom/photo-new", item_type="policy",
                                      texts=["합성 글"], today=get_today_kst(), brand="LAHOM") == ai_gates.FAIL
