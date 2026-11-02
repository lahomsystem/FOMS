"""온톨로지 바로잡기(설계서 7.8 · ⑤-6 · 사장님 D129) — 칸 · 링크 · 공정 단계 유형 · 제약. 음성 대조군을 같은 모집단에서 같이 센다.

다음 1 가격 규칙 근거 종류별 연결 개수 · 끝 · 다음 2 사장님 결정 틀 · ``decided_by`` · ``supersedes`` 유효 끝 · 다음 3 공정 단계 ·
``at_step`` · ``erp:stage/`` · 다음 5 옆 링크 · ``part_of`` · 다음 6 바깥 사본 링크 · 지문 · D84 합성 재현 · 다음 7 규격 · 제품 라인 ·
옵션 틀 · 다음 13 관찰 일어난 때 · 다음 14 맞서는 짝 · 고리 · 은퇴 가리킴 · 값 목록 검사 · 정책 종류(D124).
합성 항목 · 합성 계정 · 꾸민 수만(실제 금액 · 손님 글 · 직원 이름 없음).
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject
from foms.services.brain import constants as c
from foms.services.brain.apply import apply_change
from foms.services.brain.card import item_card
from foms.services.brain.copy_check import copy_mismatch, macro_refs, mismatched, text_digest, unlinked_macros
from foms.services.brain.errors import (
    BrainExternalRefError, BrainLinkLimitError, BrainLinkRuleError, BrainShapeError, BrainTargetError,
)
from foms.services.brain.inbox import similar_cases
from foms.services.brain.proposals import Proposer, propose_create, propose_link, propose_update
from foms.services.brain.quality import missing_links, off_list_counts, quality_counts
from foms.services.brain.schemas import HANDLES, MOLDINGS, QUOTE_KINDS, schema_problems
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_link, current_object
from foms.services.cs_agent import image_rules, quote_brain, quote_rules
from tests.support.brain_screen_support import TODAY
from tests.support.brain_support import NOW, REASON, create, link, person, values

DOC = {"approved_by": "합성", "approved_at": "2026-10-20"}


@pytest.fixture
def admin(app):
    return person(db_session, "d129_admin")


def _price(admin, key, basis=None, **payload):
    extra = {"basis": basis} if basis else {}
    return create(db_session, admin, key, item_type="price_rule", name="합성 값 규칙", checked_at="2026-10-20",
                  visibility="price", payload={"doc_id": key.split("/")[-1], **DOC, **extra, **payload})


def _decision(admin, key, no="D1", **vals):
    payload = {"doc_id": key.split("/")[-1], **DOC, **({"decision_no": no} if no else {})}
    return create(db_session, admin, key, item_type="owner_decision", name="합성 결정", payload=payload, **vals)


def _add(admin, kind, src, dst, **vals):
    change = propose_link(db_session, op="link_add", kind=kind, from_key=src, to_key=dst, reason=REASON,
                          proposer=Proposer.user(admin.id), now=NOW, values=vals or None)
    return apply_change(db_session, change.id, actor=admin, now=NOW)


def _proposal_refused(admin, kind, src, dst, error):
    with pytest.raises(error):
        propose_link(db_session, op="link_add", kind=kind, from_key=src, to_key=dst, reason=REASON,
                     proposer=Proposer.user(admin.id), now=NOW)


def _shape(item_type, **vals):
    return schema_problems({"status": "active", "text": "합성", **vals}, item_type)


# ── 다음 1 · 가격 규칙 근거 종류 ─────────────────────────────────────────
def test_price_rule_basis_decides_link_count_and_end():
    assert [c.cardinality("price_rule", "value_from", {"basis": b}) for b in c.PRICE_BASES] == [
        (1, 1), (0, 0), (2, 2), (1, 1)]
    assert c.cardinality("price_rule", "value_from", {}) == (0, 1)  # 근거 종류가 빈 옛 항목 — 최소 없음
    assert c.cardinality("price_rule", "value_from", {"basis": "nope"}) == (0, 1)
    assert c.cardinality("spec", "value_from", {"basis": "calc"}) == (0, 1)  # 대조군: 다른 유형은 실음 칸과 무관
    assert _shape("price_rule", checked_at="2026-10-20", payload={
        "basis": "derived", "unit": "30cm", "band_low": 1, "band_high": 9, "from_price": 1, "formula": "가 - 나",
        "stage": "extra"}) == []
    assert any(p.startswith("payload.basis") for p in _shape("price_rule", checked_at="2026-10-20",
                                                            payload={"basis": "guess"}))
    assert any(p.startswith("payload.band_low") for p in _shape("price_rule", checked_at="2026-10-20",
                                                               payload={"band_low": 9, "band_high": 1}))


def test_price_rule_links_follow_the_basis(admin):
    from foms.services.brain.external import catalog_source
    from tests.support.brain_support import setting, synth_catalog

    setting(db_session, "synthetic_fee")
    _price(admin, "common/by-calc", "calc")
    _price(admin, "common/by-setting", "setting")
    _price(admin, "common/by-brain", "brain")
    _price(admin, "common/by-diff", "derived")
    with catalog_source(synth_catalog):
        _proposal_refused(admin, "value_from", "common/by-calc", "setting:synthetic_fee", BrainLinkRuleError)
        _proposal_refused(admin, "value_from", "common/by-setting", "calc:product/1", BrainLinkRuleError)
        _proposal_refused(admin, "value_from", "common/by-brain", "calc:product/1", BrainLinkRuleError)
    link(db_session, admin, "value_from", "common/by-calc", "calc:product/1")  # 대조군: 받는 끝
    link(db_session, admin, "value_from", "common/by-setting", "setting:synthetic_fee")
    link(db_session, admin, "value_from", "common/by-diff", "calc:product/1")
    who = viewer_of(admin)
    gap = missing_links(db_session, who, {"key": "common/by-diff", "type": "price_rule",
                                          "payload": {"basis": "derived"}}, today=TODAY)
    assert gap == [{"kind": "value_from", "min": 2, "max": 2, "have": 1}]
    link(db_session, admin, "value_from", "common/by-diff", "calc:product/7")
    with catalog_source(synth_catalog):
        change = propose_link(db_session, op="link_add", kind="value_from", from_key="common/by-diff",
                              to_key="calc:option/3:5", reason=REASON, proposer=Proposer.user(admin.id), now=NOW)
        with pytest.raises(BrainLinkLimitError):  # 셋째는 반영 때 막는다(꼭 2)
            apply_change(db_session, change.id, actor=admin, now=NOW)
    rules = {(r["basis"]): r for r in quality_counts(db_session, who, today=TODAY)["rules"]
             if r["type"] == "price_rule"}
    assert rules["calc"]["missing"] == 0 and rules["derived"]["missing"] == 0 and rules["brain"]["items"] == 1


def test_empty_basis_is_not_counted_missing_but_flagged_on_the_card(admin):
    _price(admin, "common/old-rule")
    _price(admin, "common/new-rule", "calc")
    who = viewer_of(admin)
    old = item_card(db_session, who, "common/old-rule", today=TODAY)
    new = item_card(db_session, who, "common/new-rule", today=TODAY)
    assert old["missing_links"] == [] and "empty:payload.basis" in {w["code"] for w in old["warnings"]}
    assert new["missing_links"] == [{"kind": "value_from", "min": 1, "max": 1, "have": 0}]  # 대조군
    assert "empty:payload.basis" not in {w["code"] for w in new["warnings"]}
    assert old["link_rules"] == [{"kind": "value_from", "min": 0, "max": 1}]
    assert new["link_rules"] == [{"kind": "value_from", "min": 1, "max": 1}]


# ── 다음 2 · 사장님 결정 ─────────────────────────────────────────────────
def test_owner_decision_number_and_day():
    base = {"payload": {"doc_id": "d", **DOC}}
    assert _shape("owner_decision", payload={**base["payload"], "decision_no": "D129", "decided_on": "2026-11-02"}) == []
    assert _shape("owner_decision", **base) == ["payload.decision_no: 결정 번호 칸이 꼭 있어야 한다"]
    assert any("꼴" in p for p in _shape("owner_decision", payload={**base["payload"], "decision_no": "X12"}))
    assert any(p.startswith("payload.decided_on") for p in _shape(
        "owner_decision", payload={**base["payload"], "decision_no": "D1", "decided_on": "2026-13-40"}))
    assert schema_problems({"status": "draft", "text": "합성", **base}, "owner_decision") == []  # 초안은 비어도 된다
    imported = {"status": "active", "text": "합성", "evidence_kind": "import", **base}
    assert schema_problems(imported, "owner_decision") == []  # 옮긴 결정은 번호를 제안으로 채운다(카드 알림)


def test_decided_by_links_identity_items_to_decisions(admin):
    _decision(admin, "common/d1")
    _decision(admin, "common/d2", no="D2")
    create(db_session, admin, "common/depth", item_type="spec", name="합성 깊이", payload={"value": 1, "unit": "mm"})
    _add(admin, "decided_by", "common/depth", "common/d1")
    assert current_link(db_session, "decided_by", "common/depth", "common/d1") is not None
    _proposal_refused(admin, "decided_by", "common/d2", "common/d1", BrainTargetError)  # 결정 → 결정은 아님
    _proposal_refused(admin, "decided_by", "common/d1", "common/depth", BrainTargetError)  # 거꾸로


def test_supersedes_ends_the_old_item_the_day_before_the_new_decision(admin):
    _decision(admin, "common/next", valid_from="2026-11-10")
    _decision(admin, "common/now", no="D3")
    create(db_session, admin, "common/old-fit", item_type="build_rule", name="합성 옛 조건")
    create(db_session, admin, "common/old-term", item_type="term", name="합성 옛 말")
    create(db_session, admin, "common/early", item_type="term", name="합성 이른 끝", valid_to="2026-10-01")
    create(db_session, admin, "common/planned", item_type="term", name="합성 예정", valid_from="2026-12-01")
    open_change = propose_update(db_session, key="common/old-fit", base_version=1, after={"text": "합성 고침"},
                                 reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")
    _add(admin, "supersedes", "common/next", "common/old-fit")
    _add(admin, "supersedes", "common/now", "common/old-term")
    _add(admin, "supersedes", "common/now", "common/early")
    _add(admin, "supersedes", "common/next", "common/planned")  # 효력 전에 대체 — 끝 날을 찍지 않는다(시작 > 끝)
    assert current_object(db_session, "common/planned").version == 1
    fit, term, early = (current_object(db_session, k) for k in ("common/old-fit", "common/old-term", "common/early"))
    assert (fit.version, fit.valid_to) == (2, datetime.date(2026, 11, 9))  # 새 결정 유효 시작 전날
    assert (term.version, term.valid_to) == (2, TODAY)  # 시작 날이 없으면 반영 날(그날까지 맞다)
    assert (early.version, early.valid_to) == (1, datetime.date(2026, 10, 1))  # 대조군: 이미 이른 끝은 그대로
    assert fit.text == "합성 설명 합성 옛 조건" and fit.change_id is not None and fit.release_no is not None
    flagged = db_session.scalar(select(BrainChange.base_changed_at).where(BrainChange.id == open_change.id))
    assert flagged == NOW  # 그 항목 열린 제안에 '기준 판 바뀜'


def test_supersedes_and_broader_cycles_are_blocked(admin):
    _decision(admin, "common/da")
    _decision(admin, "common/db", no="D4")
    _add(admin, "supersedes", "common/da", "common/db")
    _proposal_refused(admin, "supersedes", "common/db", "common/da", BrainLinkRuleError)
    _proposal_refused(admin, "supersedes", "common/da", "common/da", BrainLinkRuleError)  # 자기 자신
    for key in ("common/t1", "common/t2", "common/t3"):
        create(db_session, admin, key, item_type="term", name="합성 " + key[-2:])
    _add(admin, "broader", "common/t1", "common/t2")
    _add(admin, "broader", "common/t2", "common/t3")
    _proposal_refused(admin, "broader", "common/t3", "common/t1", BrainLinkRuleError)  # 세 걸음 고리
    create(db_session, admin, "common/s1", item_type="spec", name="합성 규격", payload={"value": 1, "unit": "mm"})
    _proposal_refused(admin, "broader", "common/t1", "common/s1", BrainTargetError)  # 같은 유형끼리만
    _add(admin, "broader", "common/t1", "common/t3")  # 대조군: 고리 아닌 지름길은 된다
    assert current_link(db_session, "broader", "common/t1", "common/t3") is not None


# ── 다음 3 · 공정 단계 ───────────────────────────────────────────────────
def test_process_step_points_at_an_erp_stage(admin):
    assert _shape("process_step", payload={"erp_stage": "MEASURE", "step_order": 2, "aliases": ["실측 방문"]}) == []
    assert any(p.startswith("payload.erp_stage") for p in _shape("process_step", payload={"erp_stage": "NOPE"}))
    assert any(p.startswith("payload.erp_stage") for p in _shape("process_step", payload={"step_order": 1}))
    create(db_session, admin, "common/step-measure", item_type="process_step", name="실측",
           payload={"erp_stage": "MEASURE", "step_order": 2, "aliases": ["실측 방문"]})
    create(db_session, admin, "common/visit", item_type="policy", name="합성 방문 정책", checked_at="2026-10-20",
           payload={"doc_id": "visit", **DOC, "policy_kind": "install"})
    create(db_session, admin, "common/door", name="합성 문짝")
    _add(admin, "at_step", "common/visit", "common/step-measure")
    _proposal_refused(admin, "at_step", "common/door", "common/step-measure", BrainTargetError)  # 제품은 단계에 안 걸림
    _add(admin, "value_from", "common/step-measure", "erp:stage/measure")
    for ref, error in (("erp:stage/nope", BrainExternalRefError), ("erp:stage/MEASURE", BrainShapeError)):
        _proposal_refused(admin, "value_from", "common/step-measure", ref, error)
    _proposal_refused(admin, "value_from", "common/door", "erp:stage/measure", BrainTargetError)  # 공정 단계만
    change = propose_link(db_session, op="link_add", kind="value_from", from_key="common/step-measure",
                          to_key="erp:stage/drawing", reason=REASON, proposer=Proposer.user(admin.id), now=NOW)
    with pytest.raises(BrainLinkLimitError):  # ERP 단계 정본은 하나까지
        apply_change(db_session, change.id, actor=admin, now=NOW)
    card = item_card(db_session, viewer_of(admin), "common/step-measure", today=TODAY)
    chip = next(e for e in card["external"] if e["ref"] == "erp:stage/measure")
    assert chip["exists"] is True and chip["label"] == "실측" and chip["ext_type"] == c.EXT_ERP_STAGE


# ── 다음 5 · 옆 링크 ─────────────────────────────────────────────────────
def test_side_links_follow_their_pairs(admin):
    create(db_session, admin, "cs/ask-size", item_type="situation", layer="cs", name="합성 상황")
    create(db_session, admin, "cs/tpl", item_type="template", layer="cs", name="합성 기준 답",
           payload={"doc_id": "tpl", "intents": ["size"], **DOC})
    create(db_session, admin, "cs/lesson", item_type="lesson", layer="cs", name="합성 배운 점")
    create(db_session, admin, "cs/tone", item_type="tone", layer="cs", name="합성 말투")
    create(db_session, admin, "common/depth", item_type="spec", name="합성 깊이", payload={"value": 1, "unit": "mm"})
    create(db_session, admin, "common/door", name="합성 문짝")
    create(db_session, admin, "drawing/part", item_type="part_kind", layer="drawing", name="합성 조각")
    allowed = (("uses", "cs/ask-size", "common/depth"), ("answers", "cs/tpl", "cs/ask-size"),
               ("refines", "cs/lesson", "cs/tone"), ("part_of", "drawing/part", "common/door"))
    for kind, src, dst in allowed:
        _add(admin, kind, src, dst)
        assert current_link(db_session, kind, src, dst) is not None
    for kind, src, dst in (("uses", "cs/ask-size", "common/door"), ("answers", "cs/ask-size", "cs/tpl"),
                           ("refines", "cs/tone", "cs/lesson"), ("applies_to", "drawing/part", "common/door")):
        _proposal_refused(admin, kind, src, dst, BrainTargetError)  # 거꾸로 · 짝 밖 · applies_to 에서 옮긴 짝


def test_old_part_kind_applies_to_links_stay_readable_and_removable(admin):
    create(db_session, admin, "common/door", name="합성 문짝")
    create(db_session, admin, "drawing/part", item_type="part_kind", layer="drawing", name="합성 조각")
    db_session.add(BrainLink(kind="applies_to", from_key="drawing/part", to_key="common/door", version=1,
                             confidence="confirmed", recorded_at=NOW, created_by="import"))  # 짝 표가 바뀌기 전 줄
    db_session.flush()
    card = item_card(db_session, viewer_of(admin), "common/door", today=TODAY)
    assert any(g["kind"] == "applies_to" and g["count"] == 1 for g in card["links"])  # 읽기는 그대로
    old = current_link(db_session, "applies_to", "drawing/part", "common/door")
    removal = propose_link(db_session, op="link_remove", kind="applies_to", from_key="drawing/part",
                           to_key="common/door", reason=REASON, proposer=Proposer.user(admin.id), now=NOW,
                           base_version=old.version)
    apply_change(db_session, removal.id, actor=admin, now=NOW)
    assert current_link(db_session, "applies_to", "drawing/part", "common/door") is None


# ── 다음 6 · 바깥 사본 ───────────────────────────────────────────────────
def test_copy_in_points_at_external_copies_with_digest_only(admin):
    create(db_session, admin, "common/depth", item_type="spec", name="합성 깊이", payload={"value": 1, "unit": "mm"})
    digest = text_digest("합성   매크로 글\n")
    assert digest == text_digest("합성 매크로 글") and len(digest) == 64  # 띄어쓰기만 다르면 같은 지문
    _add(admin, "copy_in", "common/depth", "macro:m100", payload={"seen_digest": digest, "checked_at": "2026-11-01"})
    for ref in ("store:prod-1#size", "screen:cs/settings", "form:quote-sheet"):
        _add(admin, "copy_in", "common/depth", ref)
    for bad in ({"text": "사본 글 통째"}, {"seen_digest": "합성 글"}, {"checked_at": "어제"}):
        with pytest.raises(BrainShapeError):
            propose_link(db_session, op="link_add", kind="copy_in", from_key="common/depth", to_key="macro:m200",
                         reason=REASON, proposer=Proposer.user(admin.id), now=NOW, values={"payload": bad})
    for bad_ref in ("store:prod-1", "macro:", "macro:M1"):
        _proposal_refused(admin, "copy_in", "common/depth", bad_ref, BrainShapeError)
    chips = {e["ref"]: e for e in item_card(db_session, viewer_of(admin), "common/depth", today=TODAY)["external"]}
    assert chips["macro:m100"]["copy_ref"] is True and chips["macro:m100"]["checked_at"] == "2026-11-01"
    assert "seen_digest" not in chips["macro:m100"]
    assert macro_refs(db_session, TODAY) == {"macro:m100"}
    assert unlinked_macros(["m100", "M300", "m200"], macro_refs(db_session, TODAY)) == ["m200", "m300"]


def test_d84_style_mismatches_are_caught_with_synthetic_values():
    """D84 네 건 꼴(운임 표 · 실측비 · 실측 뒤 기간 · 기본 몰딩)을 꾸민 수 · 말로 재현 — 넷 다 잡고, 맞는 사본은 통과."""
    cases = [
        ((11, 22, 33), "합성 운임 가 11 · 나 25 · 다 33"),  # 표 한 칸이 다름
        ((7,), "합성 실측비 5"),  # 값이 다름
        ((5, 7), "실측 뒤 3~4일 안에 합성 안내"),  # 기간이 다름
        (("기본 몰딩",), "합성 상품은 몰딩 선택"),  # 고른 값 이름이 없음
    ]
    assert all(mismatched(pointed, text) for pointed, text in cases)
    assert copy_mismatch((11, 22, 33), cases[0][1]) == {"extra": ["25"], "missing": ["22"]}
    assert copy_mismatch(("기본 몰딩",), cases[3][1]) == {"extra": [], "missing": ["기본 몰딩"]}
    good = [((11, 22, 33), "합성 운임 가 11 · 나 22 · 다 33"), ((7,), "합성 실측비 7"),
            ((5, 7), "실측 뒤 5~7일 안에 합성 안내"), (("기본 몰딩",), "합성 상품은 기본 몰딩 포함"),
            ((1500,), "합성 최소 1,500mm")]
    assert not any(mismatched(pointed, text) for pointed, text in good)  # 대조군(쉼표 숫자도 같은 값)


# ── 다음 7 · 규격 · 제품 라인 · 옵션 틀 ───────────────────────────────────
def test_spec_product_line_and_option_fields():
    assert _shape("spec", payload={"value": 2, "unit": "통", "basis": "wall_incl"}) == []
    assert all(_shape("spec", payload={"value": 1, "unit": u}) == [] for u in ("일", "통", "자"))
    assert any(p.startswith("payload.basis") for p in _shape("spec", payload={"value": 1, "unit": "mm", "basis": "x"}))
    line = {"quote_kind": "slide", "price_unit": "30cm", "molding_default": "molding", "handle_default": "push",
            "min_width_mm": 600, "max_width_mm": 5000}
    assert _shape("product_line", payload=line) == []
    assert any(p.startswith("payload.min_width_mm") for p in _shape(
        "product_line", payload={**line, "min_width_mm": 6000}))
    assert any(p.startswith("payload.quote_kind") for p in _shape("product_line", payload={"quote_kind": "sideways"}))
    assert _shape("option", payload={"price_kind": "extra", "unit": "개", "category": "손잡이",
                                     "door_kinds": ["hinged"]}) == []
    assert any(p.startswith("payload.door_kinds") for p in _shape("option", payload={"door_kinds": ["round"]}))
    # 상담 쪽 정본 값과 같은 목록('모름' 뺌)
    assert QUOTE_KINDS == quote_rules.RULES
    assert set(MOLDINGS) == set(image_rules.MOLDINGS) - {"unknown"}
    assert set(HANDLES) == set(quote_brain.HANDLES) - {"unknown"}


def test_policy_kind_and_promotion_needs_an_end():
    doc = {"doc_id": "p", **DOC}
    assert _shape("policy", checked_at="2026-10-20", payload={**doc, "policy_kind": "shipping"}) == []
    assert _shape("policy", checked_at="2026-10-20", valid_to="2026-12-31",
                  payload={**doc, "policy_kind": "promotion"}) == []
    assert "valid_to: 판촉 정책은 유효 끝이 꼭 있어야 한다(D124)" in _shape(
        "policy", checked_at="2026-10-20", payload={**doc, "policy_kind": "promotion"})
    assert any(p.startswith("payload.policy_kind") for p in _shape("policy", payload={**doc, "policy_kind": "sale"}))


# ── 다음 13 · 관찰 일어난 때 ─────────────────────────────────────────────
def test_observations_carry_the_source_time(admin):
    assert _shape("case", payload={"occurred_at": "2026-10-03T21:30:00+09:00"}) == []
    assert any(p.startswith("payload.occurred_at") for p in _shape("case", payload={"occurred_at": "어제 저녁"}))
    assert any(p.startswith("payload") for p in _shape("photo_observation", payload={"photo": "x"}))  # 닫힌 틀
    create(db_session, admin, "common/door", name="합성 문짝")
    create(db_session, admin, "obs/a", item_type="case", name="합성 사례 하나",
           payload={"occurred_at": "2026-09-30T23:30:00+00:00"})  # 한국 10-01 08:30
    create(db_session, admin, "obs/b", item_type="image_read", name="합성 그림 읽기")  # 원본 시각 모름 — 줄 쓴 날
    for key in ("obs/a", "obs/b"):
        _add(admin, "evidence_of", key, "common/door")
    found = similar_cases(db_session, viewer_of(admin), ["common/door"])["common/door"]
    assert found == {"count": 2, "first": "2026-10-01", "last": "2026-11-02"}


# ── 다음 14 · 제약 ───────────────────────────────────────────────────────
def test_requires_and_excludes_cannot_share_a_pair(admin):
    create(db_session, admin, "common/fit", item_type="build_rule", name="합성 조건")
    create(db_session, admin, "common/door", name="합성 문짝")
    create(db_session, admin, "common/slide", name="합성 미닫이")
    _add(admin, "requires", "common/fit", "common/door")
    _proposal_refused(admin, "excludes", "common/fit", "common/door", BrainLinkRuleError)
    _add(admin, "excludes", "common/fit", "common/slide")  # 대조군: 다른 짝은 된다
    _add(admin, "requires", "common/door", "common/slide")
    _proposal_refused(admin, "excludes", "common/slide", "common/door", BrainLinkRuleError)  # 거꾸로 짝도 맞선다


def test_links_to_retired_items_warn_on_the_card_and_in_counts(admin):
    from foms.services.brain.proposals import propose_retire

    create(db_session, admin, "common/fit", item_type="build_rule", name="합성 조건")
    create(db_session, admin, "common/door", name="합성 문짝")
    create(db_session, admin, "common/slide", name="합성 미닫이")
    _add(admin, "applies_to", "common/fit", "common/door")
    _add(admin, "applies_to", "common/fit", "common/slide")
    who = viewer_of(admin)
    assert quality_counts(db_session, who, today=TODAY)["retired_links"] == 0  # 대조군
    retire = propose_retire(db_session, key="common/slide", base_version=1, reason=REASON,
                            proposer=Proposer.user(admin.id), now=NOW)
    apply_change(db_session, retire.id, actor=admin, now=NOW)
    card = item_card(db_session, who, "common/fit", today=TODAY)
    assert [w["key"] for w in card["warnings"] if w["code"].startswith("retired_target:")] == ["common/slide"]
    assert quality_counts(db_session, who, today=TODAY)["retired_links"] == 1


def test_value_lists_are_checked_in_one_place(admin):
    assert c.value_problems(item_type="spec", brand="COMMON", kind="uses", status="active") == []
    bad = c.value_problems(item_type="widget", brand="ACME", kind="likes", status="gone")
    assert [p.split(":")[0] for p in bad] == ["item_type", "brand", "kind", "status"]
    with pytest.raises(BrainShapeError):
        propose_create(db_session, key="common/x", brand="ACME", layer="common", item_type="spec",
                       values=values("합성", payload={"value": 1, "unit": "mm"}), reason=REASON,
                       proposer=Proposer.user(admin.id), now=NOW, known="")
    create(db_session, admin, "common/door", name="합성 문짝")
    with pytest.raises(BrainShapeError):
        propose_link(db_session, op="link_add", kind="likes", from_key="common/door", to_key="calc:product/1",
                     reason=REASON, proposer=Proposer.user(admin.id), now=NOW)
    assert off_list_counts(db_session) == {"item_type": 0, "brand": 0, "status": 0, "kind": 0}  # 대조군
    db_session.add(BrainObject(item_key="common/raw", version=1, brand="COMMON", layer="common", item_type="widget",
                               name="합성", status="active", confidence="confirmed", visibility="all",
                               created_by="user:1", recorded_at=NOW))  # 반영 동작 밖에서 쓴 줄
    db_session.add(BrainLink(kind="likes", from_key="common/door", to_key="common/raw", version=1,
                             confidence="confirmed", recorded_at=NOW, created_by="user:1"))
    db_session.flush()
    assert off_list_counts(db_session) == {"item_type": 1, "brand": 0, "status": 0, "kind": 1}
    assert db_session.scalar(select(BrainObject.item_type).where(BrainObject.item_key == "common/raw")) == "widget"
