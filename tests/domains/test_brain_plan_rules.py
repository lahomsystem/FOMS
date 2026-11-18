"""자료 계획의 꼭 같이 · 같이 못 함 · 제작 조건 · 속성 칸(설계서 2026-11-13 온톨로지 빈 재료 채우기 2판 B · C · G — D201 · D203).

``requires`` · ``excludes`` 는 허용 짝 · 맞섬(같은 계획 · 이미 있는 링크 · 열린 제안, 어느 방향이든) · 거꾸로 같은 ``excludes`` ·
② 한 장씩 · 사실 → 제작 조건 나눔(지식 문서 항목 · 옛 사실 은퇴 · ``applies_to``) · 정책 속 문장 옮기기(만들기 → 반영 뒤 정책 고침 —
문장은 늘 한 곳에만) · 외톨이 제작 조건 0 · 속성 칸 고침(받는 칸만 · ②) · 모의 실행 쓰기 0 · 다시 돌려도 같은 결과.
합성 값만(실제 이름 · 금액 · 손님 글 없음).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject
from foms.services.brain.apply import apply_change
from foms.services.brain.catalog_plan import catalog_plan
from foms.services.brain.constants import is_doc_item
from foms.services.brain.decide import bulk_apply
from foms.services.brain.errors import BrainShapeError
from foms.services.brain.external import catalog_source
from foms.services.brain.inbox_bins import BIN_CONTENT, BIN_RULES, card_bin, change_ends
from foms.services.brain.plan_proposals import file_plan
from foms.services.brain.plan_rules import cut_sentence
from foms.services.brain.store import current_object, is_current
from tests.domains.test_brain_catalog_plan import CATALOG, synth
from tests.support.brain_support import NOW, create, link, person

DOC = {"approved_by": "합성", "approved_at": "2026-10-20", "intents": ["synth-door"], "tags": ["synth"]}
MOVED = "합성 ㄱ자 장은 여닫이 문만 돼요."
POLICY_TEXT = f"합성 정책 첫 문장이에요. {MOVED} 합성 끝 문장이에요."


@pytest.fixture
def admin(app):
    admin = person(db_session, "plan_rules_admin")
    with catalog_source(synth):
        file_plan(db_session, catalog_plan(CATALOG), brand="LAHOM", apply=True, now=NOW)
        for change in db_session.execute(select(BrainChange).where(BrainChange.status == "open")).scalars().all():
            apply_change(db_session, change.id, actor=admin, now=NOW)
    create(db_session, admin, "common/spec-depth", item_type="spec", name="합성 깊이 규격", payload={"value": 350, "unit": "mm"})
    create(db_session, admin, "common/rule-a", item_type="build_rule", name="합성 조건 가", payload={"rule_kind": "requires"})
    create(db_session, admin, "lahom/pol-door", brand="LAHOM", item_type="policy", text=POLICY_TEXT,
           checked_at="2026-10-20", payload={"doc_id": "pol-door", **DOC})
    create(db_session, admin, "lahom/f-rule", brand="LAHOM", item_type="fact", text="합성 사실 속 제작 조건 글이에요.",
           checked_at="2026-10-20", payload={"doc_id": "f-rule", **DOC})
    db_session.commit()
    return admin


def run(plan, apply=True):
    with catalog_source(synth):
        out = file_plan(db_session, {"schema": "rules_plan/1", **plan}, brand="LAHOM", apply=apply, now=NOW)
    db_session.commit()
    return out


def opened(**where):
    query = select(BrainChange).where(BrainChange.status == "open", BrainChange.proposed_by == "import")
    for name, value in where.items():
        query = query.where(getattr(BrainChange, name) == value)
    return db_session.execute(query.order_by(BrainChange.id)).scalars().all()


def approve_open(admin):
    rows = opened()
    with catalog_source(synth):
        for change in rows:
            apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    return len(rows)


def bin_of(change):
    return card_bin(change.op, change.item_type, change.fields, change.link_kind, **change_ends(change))


def imported():
    return db_session.scalar(select(func.count()).select_from(BrainChange).where(BrainChange.proposed_by == "import"))


# ── B 꼭 같이 · 같이 못 함 ──────────────────────────────────────────────
def test_constraint_links_keep_allowed_pairs_and_stay_one_card_at_a_time(admin):
    out = run({"links": [
        {"from": "common/rule-a", "to": "product_line/lahom-1", "kind": "requires", "why": "D203 합성"},
        {"from": "product_line/lahom-1", "to": "option/3-5", "kind": "excludes"},
        {"from": "option/3-6", "to": "common/spec-depth", "kind": "requires"},  # 옵션 → 규격
        {"from": "common/spec-depth", "to": "option/3-5", "kind": "requires"},  # 규격은 시작이 아니다
        {"from": "lahom/pol-door", "to": "product_line/lahom-1", "kind": "excludes"},  # 정책은 시작이 아니다
        {"from": "common/rule-a", "to": "lahom/pol-door", "kind": "requires"},  # 정책은 끝이 아니다
        {"from": "common/rule-a", "to": "option/9-9", "kind": "requires"}]})  # 없는 끝
    assert out["filed"] == {"link_add:excludes": 1, "link_add:requires": 2}
    assert out["skipped"] == {"not_allowed": 3, "end_missing": 1}
    rows = opened(op="link_add")
    assert {bin_of(c) for c in rows} == {BIN_CONTENT}  # D203 — ⑥ 에 섞이지 않는다
    assert all("D203" in c.reason for c in rows)
    with pytest.raises(BrainShapeError):  # 관리자도 한꺼번에 못 한다
        bulk_apply(db_session, [c.id for c in rows], actor=admin, now=NOW)
    db_session.rollback()
    assert approve_open(admin) == 3  # 한 장씩은 된다
    kinds = {(l.kind, l.from_key, l.to_key) for l in db_session.execute(
        select(BrainLink).where(BrainLink.kind.in_(("requires", "excludes")))).scalars()}
    assert ("excludes", "product_line/lahom-1", "option/3-5") in kinds and len(kinds) == 3


def test_opposed_and_reversed_constraints_are_not_filed(admin):
    link(db_session, admin, "requires", "common/rule-a", "option/3-5")
    link(db_session, admin, "excludes", "product_line/lahom-1", "option/3-6")
    db_session.commit()
    out = run({"links": [
        {"from": "product_line/haud-7", "to": "option/3-6", "kind": "requires"},  # 같은 계획 안 맞섬(방향 반대) — 둘 다 뺀다
        {"from": "option/3-6", "to": "product_line/haud-7", "kind": "excludes"},
        {"from": "common/rule-a", "to": "option/3-5", "kind": "excludes"},  # 이미 있는 반대 링크
        {"from": "option/3-6", "to": "product_line/lahom-1", "kind": "excludes"},  # 거꾸로 같은 '같이 못 함'
        {"from": "option/3-6", "to": "product_line/lahom-1", "kind": "requires"}]})  # 반대 방향의 맞섬
    assert out["filed_total"] == 0
    assert out["skipped"] == {"opposed_in_plan": 4, "opposed": 1}  # 같은 두 항목의 요구 · 제외가 같은 계획에 함께
    out = run({"links": [{"from": "option/3-6", "to": "product_line/lahom-1", "kind": "excludes"},
                         {"from": "product_line/haud-7", "to": "option/3-5", "kind": "excludes"}]})
    assert out["filed"] == {"link_add:excludes": 1} and out["skipped"] == {"same": 1}  # 거꾸로 있는 것은 이미 있음
    out = run({"links": [{"from": "option/3-5", "to": "product_line/haud-7", "kind": "excludes"},
                         {"from": "option/3-5", "to": "product_line/haud-7", "kind": "requires"}]})
    assert out["skipped"] == {"opposed_in_plan": 2}
    out = run({"links": [{"from": "option/3-5", "to": "product_line/haud-7", "kind": "excludes"}]})
    assert out["filed_total"] == 0 and out["skipped"] == {"open_proposal": 1}  # 거꾸로 열린 제안
    out = run({"links": [{"from": "option/3-5", "to": "product_line/haud-7", "kind": "requires"}]})
    assert out["filed_total"] == 0 and out["skipped"] == {"opposed_open": 1}  # 반대 종류 열린 제안


# ── C 제작 조건 ─────────────────────────────────────────────────────────
def test_fact_split_into_a_build_rule_keeps_the_document_and_hangs_on_products(admin):
    plan = {"items": [{"id": "f-rule", "fact_to": {"type": "build_rule", "rule_kind": "excludes",
                                                   "applies_to": ["product_line/lahom-1", "option/9-9", "common/spec-depth"]},
                       "process_step_hint": "MEASURE"}]}
    out = run(plan)
    assert out["filed"] == {"create": 1}
    assert out["skipped"] == {"retyped": 1, "rule_end_dropped": 2}  # 없는 끝 · 제품이 아닌 끝은 뺀다
    (change,) = opened(op="create")
    after = {name: entry["after"] for name, entry in change.fields.items()}
    assert (change.item_key, change.item_type, bin_of(change)) == ("lahom/f-rule-build_rule", "build_rule", BIN_CONTENT)
    assert after["payload"] == {"doc_id": "f-rule-build_rule", "rule_kind": "excludes", **DOC, "source": None}
    assert after["text"] == current_object(db_session, "lahom/f-rule").text
    assert approve_open(admin) == 1
    out = run(plan)
    assert out["filed"] == {"link_add:applies_to": 1, "retire": 1}
    assert out["skipped"].get("end_missing") == 1  # 공정 단계 항목이 없다 — 그 링크만
    assert {bin_of(c) for c in opened(op="link_add")} == {BIN_RULES}  # 제작 조건 → 제품 잇기는 ⑥
    assert approve_open(admin) == 2
    rule = current_object(db_session, "lahom/f-rule-build_rule")
    assert is_doc_item(rule.item_type, rule.payload) and current_object(db_session, "lahom/f-rule").status == "retired"
    assert run(plan)["filed_total"] == 0


def test_orphan_build_rules_are_counted_not_filed(admin):
    out = run({"items": [{"id": "f-rule", "fact_to": {"type": "build_rule", "applies_to": ["common/spec-depth"]}}],
               "new_items": [{"type": "build_rule", "key": "build_rule/new-a", "pref_label": "합성 새 조건 가",
                              "text": "합성 새 조건 글이에요.", "applies_to": ["option/3-5"]},
                             {"type": "build_rule", "key": "build_rule/new-b", "pref_label": "합성 새 조건 나"}],
               "rules": [{"policy": "lahom/pol-door", "id": "rule-door", "sentence": MOVED, "applies_to": []}]})
    assert out["filed"] == {"create": 1}  # 걸 곳이 있는 새 조건 하나만
    assert out["skipped"] == {"orphan_rule": 3, "rule_end_dropped": 1}
    assert out["deferred"] == {"awaiting_create": 1}  # 새 조건 → 옵션은 승인 뒤 다음 차례
    (change,) = opened(op="create")
    assert change.item_key == "lahom/new-a" and change.fields["payload"]["after"]["doc_id"] == "new-a"
    assert current_object(db_session, "lahom/f-rule").status == "active"  # 외톨이로 나누지 않았다


def test_policy_sentence_moves_as_one_bundle_and_lives_in_one_place(admin):
    plan = {"rules": [{"policy": "lahom/pol-door", "id": "rule-door", "sentence": MOVED, "rule_kind": "requires",
                       "applies_to": ["product_line/lahom-1"], "pref_label": "합성 문 조건", "why": "D201 합성"}]}
    out = run(plan)
    assert out["filed"] == {"create": 1} and out["deferred"] == {"awaiting_create": 2}  # 링크 · 정책 고침은 승인 뒤
    (change,) = opened(op="create")
    after = {name: entry["after"] for name, entry in change.fields.items()}
    assert (change.item_key, change.brand, after["text"], after["name"]) == ("lahom/rule-door", "LAHOM", MOVED, "합성 문 조건")
    assert after["payload"] == {"doc_id": "rule-door", "rule_kind": "requires", **DOC, "source": None}
    assert "lahom/pol-door" in change.reason and bin_of(change) == BIN_CONTENT
    assert current_object(db_session, "lahom/pol-door").text == POLICY_TEXT  # 반영 전엔 정책 그대로(문장이 사라지지 않게)
    assert approve_open(admin) == 1
    out = run(plan)
    assert out["filed"] == {"link_add:applies_to": 1, "update:move_out": 1}
    (fix,) = opened(op="update")
    assert fix.fields["text"]["after"] == "합성 정책 첫 문장이에요. 합성 끝 문장이에요."
    assert "lahom/rule-door" in fix.reason and bin_of(fix) == BIN_CONTENT
    assert run(plan)["filed_total"] == 0  # 열린 제안은 다시 넣지 않는다
    assert approve_open(admin) == 2
    holders = db_session.execute(select(BrainObject.item_key).where(
        is_current(BrainObject), BrainObject.text.contains(MOVED))).scalars().all()
    assert holders == ["lahom/rule-door"]  # 같은 문장은 한 곳에만
    again = run(plan)
    assert again["filed_total"] == 0 and again["skipped"] == {"same": 2}  # 링크 · 고침 모두 이미 됨


def test_policy_sentence_guards(admin):
    create(db_session, admin, "lahom/pol-twice", brand="LAHOM", item_type="policy", text=f"{MOVED} {MOVED}",
           checked_at="2026-10-20", payload={"doc_id": "pol-twice", **DOC})
    create(db_session, admin, "lahom/pol-only", brand="LAHOM", item_type="policy", text=MOVED,
           checked_at="2026-10-20", payload={"doc_id": "pol-only", **DOC})
    hanja = "합성 門 조건이에요."
    create(db_session, admin, "lahom/pol-hanja", brand="LAHOM", item_type="policy", text=f"합성 앞 글이에요. {hanja}",
           checked_at="2026-10-20", payload={"doc_id": "pol-hanja", **DOC})
    db_session.commit()
    ends = ["product_line/lahom-1"]
    out = run({"rules": [
        {"policy": "lahom/pol-door", "id": "r-missing", "sentence": "합성 없는 문장이에요.", "applies_to": ends},
        {"policy": "lahom/pol-twice", "id": "r-twice", "sentence": MOVED, "applies_to": ends},
        {"policy": "lahom/pol-only", "id": "r-only", "sentence": MOVED, "applies_to": ends},
        {"policy": "lahom/pol-hanja", "id": "r-hanja", "sentence": hanja, "applies_to": ends},
        {"policy": "lahom/f-rule", "id": "r-fact", "sentence": "합성 사실 속 제작 조건 글이에요.", "applies_to": ends},
        {"policy": "lahom/pol-door", "id": "R BAD", "sentence": MOVED, "applies_to": ends},
        {"policy": "lahom/pol-door", "id": "r-held", "sentence": MOVED, "applies_to": ends, "unsure": "합성"}]})
    assert out["filed_total"] == 0 and out["deferred"] == {}
    assert out["skipped"] == {"sentence_missing": 1, "sentence_twice": 1, "would_empty": 1, "gate_failed": 1,
                              "not_policy": 1, "shape": 1, "unsure": 1}


def test_cut_sentence_only_tidies_the_cut():
    assert cut_sentence("가 나 다", "나") == "가 다"
    assert cut_sentence("가\n나\n다", "나") == "가\n다"  # 그 줄 전체였다
    assert cut_sentence("가  나\n  다", "나") == "가\n  다"  # 다른 줄 들여쓰기는 그대로
    assert cut_sentence("나 가", "나") == "가"


# ── G 속성 칸 ───────────────────────────────────────────────────────────
def test_props_fill_product_fields_as_content_cards(admin):
    plan = {"props": [
        {"key": "product_line/lahom-1", "props": {"door_kinds": ["hinged"], "quote_kind": "hinge", "min_width_mm": 300,
                                                  "max_width_mm": 2400, "price_30cm": 1}},
        {"key": "lahom/pol-door", "props": {"policy_kind": "install"}},
        {"key": "option/3-5", "props": {"door_kinds": ["hinged"]}},  # 옵션 칸은 받지 않는다
        {"key": "product_line/haud-7", "props": {"quote_kind": "bogus"}},  # 고른 값 밖
        {"key": "product_line/lahom-404", "props": {"quote_kind": "hinge"}}]}
    out = run(plan)
    assert out["filed"] == {"update:props": 2}
    assert out["skipped"] == {"prop_not_allowed": 2, "shape": 1, "end_missing": 1}
    rows = opened(op="update")
    assert {bin_of(c) for c in rows} == {BIN_CONTENT}  # 이름표가 아니라 내용 칸 — ②
    assert run(plan)["skipped"]["open_proposal"] == 2
    approve_open(admin)
    product = current_object(db_session, "product_line/lahom-1").payload
    assert (product["door_kinds"], product["quote_kind"], product["min_width_mm"], product["max_width_mm"]) == (
        ["hinged"], "hinge", 300, 2400)
    assert product["price_unit"] == "30cm" and "price_30cm" not in product  # 있던 칸은 그대로 · 금액 칸은 안 들어간다
    assert current_object(db_session, "lahom/pol-door").payload["policy_kind"] == "install"
    assert run(plan)["skipped"]["same"] == 2


# ── 모의 실행 · 다시 돌리기 ─────────────────────────────────────────────
def test_dry_run_writes_nothing_and_matches_apply(admin):
    plan = {"links": [{"from": "common/rule-a", "to": "option/3-6", "kind": "excludes"}],
            "items": [{"id": "f-rule", "fact_to": {"type": "build_rule", "applies_to": ["option/3-6"]}}],
            "rules": [{"policy": "lahom/pol-door", "id": "rule-door", "sentence": MOVED, "applies_to": ["option/3-5"]}],
            "props": [{"key": "product_line/lahom-1", "props": {"quote_kind": "slide"}}]}
    before, filed_before = db_session.scalar(select(func.count()).select_from(BrainObject)), imported()
    dry = run(plan, apply=False)
    assert imported() == filed_before and db_session.scalar(select(func.count()).select_from(BrainObject)) == before
    assert dry["plan"]["rules"] == 1 and dry["plan"]["props"] == 1 and dry["filed_total"] == 4
    real = run(plan)
    assert {k: v for k, v in real.items() if k != "applied"} == {k: v for k, v in dry.items() if k != "applied"}
    assert imported() == filed_before + 4 and run(plan)["filed_total"] == 0 and imported() == filed_before + 4


def test_script_passes_rules_and_props_and_prints_counts_only(admin, capsys, monkeypatch):
    import io
    import json

    from tests.domains.test_brain_plan_proposals import load_script
    filed_before = imported()
    plan = {"schema": "rules_plan/1",
            "rules": [{"policy": "lahom/pol-door", "id": "rule-door", "sentence": MOVED, "applies_to": ["option/3-5"]}],
            "props": [{"key": "product_line/lahom-1", "props": {"quote_kind": "slide"}}]}
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(plan, ensure_ascii=False).encode("utf-8"))))
    with catalog_source(synth):
        code = load_script().run(["--plan", "-"])
    printed = capsys.readouterr().out
    out = json.loads(printed)
    assert code == 0 and out["applied"] is False and out["filed"] == {"create": 1, "update:props": 1}
    assert out["plan"]["rules"] == 1 and MOVED not in printed and imported() == filed_before
