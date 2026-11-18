"""문장으로 채우기 안내(설계서 2026-11-18-brain-sentence-change 5절 3판) — 능력 질문의 모자란 재료 → 쉬운 말 한 줄 표.

- 표가 시험지(:data:`CQS`)의 모든 회사 지식 재료(ERP 밖)를 덮는다 · 채울 수 있나는 분석기가 만들 수 있는 유형
  (:data:`CREATE_TYPES`)과 같다 · 못 채우는 것(가격 규칙 · 사장님 결정 · 기준 답 문구)은 "이 칸으로 못 채워요 — <어디서>" 이고
  예시가 없다 · 글은 쉬운 한글(한자 · 개발자 말 · 금액 없음).
- :func:`fill_hint` — 표에 있는 번호만(모르는 번호 · 빈 값 · 너무 긴 값은 None) · 질문 글은 표의 일반화한 질문 · ERP 재료는 빼고 ·
  모자란 것은 보는 사람의 보기 범위로 센다(같은 모집단의 대조군 — 재료를 넣으면 그 줄이 빠진다).
합성 계정 · 합성 항목만(:func:`fill_world` — 시험지 화면 시험도 쓴다).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from db import db_session
from foms.services.brain.change_request_hints import (
    FILL_ID_MAX, LINK_HINTS, TYPE_HINTS, fill_hint, fill_kinds, hint_for,
)
from foms.services.brain.change_request_model import CREATE_TYPES
from foms.services.brain.ontology_cqs import CQS, ERP_NEEDS
from foms.services.brain.scope import viewer_of
from tests.support.brain_screen_support import TODAY, world
from tests.support.brain_support import create

HANJA = re.compile(r"[一-鿿㐀-䶿]")
DEV_WORDS = re.compile(r"[a-z]+_[a-z]+|requires|excludes|applies|build|policy|\bkey\b|\bid\b", re.I)
MONEY = re.compile(r"\d\s*(원|만|천)|₩")


def fill_world(session: Any) -> dict[str, Any]:
    """시험지 화면 world + 정책 · 상황 · 사실 하나씩 — 같은 모집단 안에 네 갈래 줄이 생긴다(관리자 보기).

    - 다 있음(D03 · S13 · X01 · X02) · ERP 재료만 모자람(P09) · 못 채우는 것만 모자람(S14 — 사장님 결정, X04 — 사장님 결정 + ERP)
      → 채우기 길 없음.
    - 채울 수 있는 것이 모자람(E01 — 규격 · 옵션, E09 — 사실은 있고 사장님 결정 · 정한 결정이 모자람) → 채우기 길.
    """
    who = world(session)
    admin = who["admin"]
    doc = {"approved_by": "합성", "approved_at": "2026-10-20"}  # 지식 문서 유형(정책 · 사실)은 승인 칸이 있어야 한다
    create(session, admin, "common/policy/as", item_type="policy", name="합성 보증 정책", text="합성 정책 글.",
           payload={"doc_id": "as_policy", **doc})
    create(session, admin, "cs/situation/beam", item_type="situation", layer="cs", name="합성 보 있는 집", text="합성 상황 글.")
    create(session, admin, "common/fact/room", item_type="fact", name="합성 쇼룸 사실", text="합성 사실 글.",
           payload={"doc_id": "room_fact", **doc})
    session.commit()
    return who


@pytest.fixture
def people(app):
    return fill_world(db_session)


def _cq_kinds() -> tuple[set[str], set[str]]:
    types = {n for cq in CQS for n in cq.needs if n not in ERP_NEEDS}
    links = {k for cq in CQS for k in cq.links}
    return types, links


# ── 표 ──────────────────────────────────────────────────────────────────
def test_table_covers_every_knowledge_gap_the_test_sheet_can_show():
    types, links = _cq_kinds()
    assert types <= set(TYPE_HINTS) and links <= set(LINK_HINTS)
    assert {"build_rule", "situation", "spec", "term", "policy", "fact"} <= types  # 사장님이 본 빨간 표시들
    assert {"requires", "excludes", "at_step", "applies_to", "broader", "decided_by"} <= links


def test_fillable_follows_what_the_analyser_can_make():
    kinds = fill_kinds()
    for item_type in TYPE_HINTS:
        got = hint_for(item_type=item_type)
        assert got["fillable"] is (item_type in CREATE_TYPES), item_type
        assert (item_type in kinds["types"]) is got["fillable"], item_type
    for name in ("price_rule", "owner_decision", "template"):  # 설계서 12절 — 이 길로 만들지 않는 것
        got = hint_for(item_type=name)
        assert got["fillable"] is False and got["example"] is None
        assert "이 칸으로 못 채워요 — " in got["gap"], name
    assert kinds["links"] == sorted(LINK_HINTS) and all(hint_for(kind=k)["fillable"] for k in LINK_HINTS)
    unknown = hint_for(kind="uses")  # 표 밖 — 화면 이름으로 짧게, 채우기 아님
    assert unknown == {"gap": "씀 — 모자라요", "example": None, "fillable": False}


def test_words_are_plain_korean_without_amounts():
    for name, hint in [*TYPE_HINTS.items(), *LINK_HINTS.items()]:
        for text in filter(None, (hint.gap, hint.example)):
            assert not HANJA.search(text) and not DEV_WORDS.search(text) and not MONEY.search(text), (name, text)
            assert "요" in text, (name, text)  # '-어요' 말투
        if hint.example is not None:
            assert len(hint.example) <= 40 and "—" not in hint.example, name  # 한 줄짜리 짧은 예
            assert "없어요 — " in hint.gap and hint.gap.endswith(("주세요", "이어요)")), name


# ── 질문 하나의 안내 ────────────────────────────────────────────────────
def test_fill_hint_reads_the_table_question_and_skips_erp(people):
    admin = viewer_of(people["admin"])
    got = fill_hint(db_session, admin, "E01", today=TODAY)
    assert got["id"] == "E01" and got["question"] == next(cq.question for cq in CQS if cq.cq_id == "E01")
    assert [g["gap"] for g in got["gaps"]] == [TYPE_HINTS["spec"].gap, TYPE_HINTS["option"].gap]
    assert got["example"] == TYPE_HINTS["spec"].example
    erp = fill_hint(db_session, admin, "P09", today=TODAY)  # ERP 재료만 모자람 — 회사 지식으로 채울 것 없음
    assert erp["gaps"] == [] and erp["example"] is None
    only_owner = fill_hint(db_session, admin, "S14", today=TODAY)  # 못 채우는 것만 — 정직하게, 예시 없음
    assert [g["fillable"] for g in only_owner["gaps"]] == [False] and only_owner["example"] is None
    assert only_owner["gaps"][0]["gap"].startswith("사장님 결정은 이 칸으로 못 채워요 — ")
    mixed = fill_hint(db_session, admin, "E09", today=TODAY)  # 못 채움(사장님 결정) + 채움(정한 결정 잇기)
    assert [g["fillable"] for g in mixed["gaps"]] == [False, True] and mixed["example"] == LINK_HINTS["decided_by"].example


def test_fill_hint_counts_within_the_viewers_scope(people):
    admin, cs = viewer_of(people["admin"]), viewer_of(people["cs_mgr"])
    # 가격 재량 규칙은 관리자만 본다 — 같은 질문(E06)이 CS 팀장에게는 '가격 규칙은 못 채워요' 한 줄이 더 있다(대조군)
    assert TYPE_HINTS["price_rule"].gap not in [g["gap"] for g in fill_hint(db_session, admin, "E06", today=TODAY)["gaps"]]
    assert TYPE_HINTS["price_rule"].gap in [g["gap"] for g in fill_hint(db_session, cs, "E06", today=TODAY)["gaps"]]
    before = fill_hint(db_session, admin, "E08", today=TODAY)["gaps"]
    create(db_session, people["admin"], "common/term/ja", item_type="term", name="합성 자 용어", text="합성 용어 글.")
    db_session.commit()
    assert [g["gap"] for g in before] == [TYPE_HINTS["term"].gap]
    assert fill_hint(db_session, admin, "E08", today=TODAY)["gaps"] == []  # 넣으면 그 줄이 빠진다


@pytest.mark.parametrize("raw", ["", None, "ZZ9", "e01", "E01 ", "E01" + "x" * FILL_ID_MAX, "<b>E01</b>", "../E01"])
def test_fill_hint_takes_only_ids_in_the_table(people, raw):
    got = fill_hint(db_session, viewer_of(people["admin"]), raw, today=TODAY)
    assert got is None or (raw == "E01 " and got["id"] == "E01")
