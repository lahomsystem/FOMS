"""자료 계획의 다른 이름 · 규칙 → 제품 잇기 칸 + 제안함 ⑥(설계서 2026-11-12 온톨로지 4.2 · 사장님 D193 · D194).

다른 이름은 더하기만(이름표 고침 → ①) · 가림 검사에 걸린 말 · 이미 있는 이름 빠짐 · 항목이 승인 대기면 다음 차례 · 같은 계획
두 번 0 · ``applies_to`` 만(그 밖 종류 not_allowed) · 규칙 → 계산기 제품 링크는 ⑥ · 사장님만 한꺼번에. 합성 값만.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainLink
from foms.services.brain.apply import apply_change
from foms.services.brain.catalog_plan import catalog_plan
from foms.services.brain.decide import bulk_apply
from foms.services.brain.errors import BrainShapeError
from foms.services.brain.external import catalog_source
from foms.services.brain.inbox import inbox
from foms.services.brain.inbox_bins import BIN_NAMES, BIN_RULES, card_bin
from foms.services.brain.plan_proposals import file_plan
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from tests.domains.test_brain_catalog_plan import CATALOG, synth
from tests.support.brain_support import NOW, create, person

PHONE = "01" + "0" + "5550" + "1234"  # 합성(실행 때 만든다)


@pytest.fixture
def world(app):
    admin = person(db_session, "plan_labels_admin")
    lead = person(db_session, "plan_labels_lead", role="MANAGER", team="CS")
    with catalog_source(synth):
        file_plan(db_session, catalog_plan(CATALOG), brand="LAHOM", apply=True, now=NOW)
        for change in db_session.execute(select(BrainChange).where(BrainChange.status == "open")).scalars().all():
            apply_change(db_session, change.id, actor=admin, now=NOW)
    create(db_session, admin, "common/spec-depth", item_type="spec", name="합성 깊이 규격", payload={"value": 350, "unit": "mm"})
    db_session.commit()
    return admin, lead


def run(plan, apply=True):
    with catalog_source(synth):
        out = file_plan(db_session, {"schema": "label_link_plan/1", **plan}, brand="LAHOM", apply=apply, now=NOW)
    db_session.commit()
    return out


def opened(op):
    return db_session.execute(select(BrainChange).where(BrainChange.status == "open", BrainChange.op == op)).scalars().all()


def test_labels_add_only_clean_new_names(world):
    plan = {"labels": [
        {"key": "product_line/lahom-1", "aliases": ["합성 이름 가", f"합성 {PHONE}", "합성 제품 하나", "합성 이름 가"]},
        {"key": "option/3-5", "aliases": ["x" * 41]},  # 너무 긴 말만 — 꼴
        {"key": "product_line/lahom-404", "aliases": ["없는 항목"]}]}
    dry = run(plan, apply=False)
    assert dry["filed"] == {"update:labels": 1} and dry["skipped"] == {"shape": 1, "end_missing": 1}
    run(plan)
    (change,) = opened("update")
    assert change.fields["payload"]["after"]["aliases"] == ["합성 이름 가"]  # 전화 꼴 · 대표 이름 · 겹침 빠짐
    assert card_bin(change.op, change.item_type, change.fields, change.link_kind,
                    proposed_by=change.proposed_by) == BIN_NAMES  # 이름표만 바뀜 → ① 표
    assert run(plan)["filed_total"] == 0  # 같은 계획 두 번 0(열린 제안)


def test_rule_links_go_to_bin_six_and_only_the_owner_bulk_approves(world):
    admin, lead = world
    plan = {"links": [
        {"from": "common/spec-depth", "to": "product_line/lahom-1"},
        {"from": "common/spec-depth", "to": "option/3-5", "kind": "applies_to"},
        {"from": "common/spec-depth", "to": "product_line/lahom-1", "kind": "requires"},  # 다른 종류는 안 받는다
        {"from": "common/no-such-rule", "to": "option/3-6"}]}
    out = run(plan)
    assert out["filed"] == {"link_add:applies_to": 2}
    assert out["skipped"] == {"not_allowed": 1, "end_missing": 1}
    cards = inbox(db_session, viewer_of(admin), now=NOW)["cards"]
    ids = [c["id"] for c in cards if c["bin"] == BIN_RULES]
    assert len(ids) == 2 and all(c["main"]["bulk_ok"] for c in cards if c["bin"] == BIN_RULES)
    with pytest.raises(BrainShapeError):  # 상담팀장은 ⑥ 을 한꺼번에 못 한다(D194)
        bulk_apply(db_session, ids, actor=lead, now=NOW)
    db_session.rollback()
    with catalog_source(synth):
        assert len(bulk_apply(db_session, ids, actor=admin, now=NOW)["applied"]) == 2
    db_session.commit()
    ends = {(l.from_key, l.to_key) for l in db_session.execute(select(BrainLink).where(BrainLink.kind == "applies_to"))
            .scalars()}
    assert ends == {("common/spec-depth", "product_line/lahom-1"), ("common/spec-depth", "option/3-5")}
    assert run(plan)["filed_total"] == 0 and current_object(db_session, "common/spec-depth") is not None


def test_links_wait_for_the_product_to_be_approved(app):
    admin = person(db_session, "plan_labels_wait")
    create(db_session, admin, "common/spec-wait", item_type="spec", name="합성 규격", payload={"value": 10, "unit": "mm"})
    with catalog_source(synth):
        file_plan(db_session, catalog_plan(CATALOG), brand="LAHOM", apply=True, now=NOW)
    db_session.commit()
    out = run({"links": [{"from": "common/spec-wait", "to": "product_line/lahom-1"}],
               "labels": [{"key": "option/3-5", "aliases": ["합성 손잡이 다른 말"]}]})
    assert out["filed_total"] == 0 and out["deferred"] == {"awaiting_create": 2}  # 링크 1 + 이름표 1 — 제품이 승인 대기


def test_rule_bin_needs_the_import_proposer_and_a_catalog_end():
    ends = {"proposed_by": "import", "link_from": "common/spec", "link_to": "product_line/lahom-1"}
    assert card_bin("link_add", None, None, "applies_to", **ends) == BIN_RULES
    assert card_bin("link_add", None, None, "applies_to", **{**ends, "proposed_by": "agent:cs"}) == "content"
    assert card_bin("link_add", None, None, "applies_to", **{**ends, "link_to": "common/other"}) == "content"


def test_rule_bin_also_takes_imported_process_step_links_but_not_people_ones():
    """D202 — 옮기기 묶음의 ``at_step``(규칙 → 공정 단계)도 ⑥ 한꺼번에, 사람 · AI 제안은 ② 그대로(대조군)."""
    ends = {"proposed_by": "import", "link_from": "common/policy-1", "link_to": "process_step/install"}
    assert card_bin("link_add", None, None, "at_step", **ends) == BIN_RULES
    assert card_bin("link_add", None, None, "at_step", **{**ends, "proposed_by": "agent:cs"}) == "content"
    assert card_bin("link_remove", None, None, "at_step", **ends) == "content"  # 빼기는 한 장씩
    assert card_bin("link_add", None, None, "requires", **{**ends, "link_to": "product_line/lahom-1"}) == "content"  # D203


def test_script_reads_the_plan_from_stdin_and_prints_counts_only(world, capsys, monkeypatch):
    import io
    import json

    from tests.domains.test_brain_plan_proposals import load_script
    plan = {"schema": "label_link_plan/1", "labels": [{"key": "option/3-6", "aliases": ["합성 기본 선반 다른 말"]}]}
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(plan, ensure_ascii=False).encode("utf-8"))))
    with catalog_source(synth):
        code = load_script().run(["--plan", "-"])
    printed = capsys.readouterr().out
    out = json.loads(printed)
    assert code == 0 and out["applied"] is False and out["filed"] == {"update:labels": 1} and "다른 말" not in printed
