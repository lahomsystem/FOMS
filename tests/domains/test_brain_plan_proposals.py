"""자료 계획 → 열린 제안(설계서 7.8 '자료(제안)' · 사장님 D130) — 모의 실행은 쓰기 0 · 넣은 수 · 다시 돌리면 0 · 보류 묶음 ·
못 찾은 계산기 이름 · 승인 뒤 다음 차례 링크 · 옮기기 묶음은 AI 주 상한 · 4주 닫힘 밖 · 출력에 글 없음 · 옮기기가 계획 항목을
지우지 않음.

합성 항목 · 합성 계산기(:data:`tests.support.brain_support.SYNTH_CATALOG`) · 합성 계획만 쓴다(실제 이름 · 금액 · 손님 글 없음).
글 표지 :data:`MARK` 는 스크립트 출력 어디에도 나오면 안 된다.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain import doc_import
from foms.services.brain.apply import apply_change
from foms.services.brain.constants import AI_WEEKLY_CAP
from foms.services.brain.decide import expire_ai_proposals
from foms.services.brain.external import catalog_source
from foms.services.brain.inbox import inbox
from foms.services.brain.labels import alias_keys
from foms.services.brain.plan_proposals import file_plan
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from tests.support.brain_support import NOW, create, person, synth_catalog

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "brain_plan_proposals.py"
MARK = "보라합성표지"
DOC = {"approved_by": "합성", "approved_at": "2026-10-20"}
OPTION = "calc:option/<합성 옵션 묶음>:<합성 손잡이>"  # 합성 계산기에 이름이 똑같은 옵션 하나
NO_OPTION = "calc:option/<합성 옵션  묶음>:<합성 손잡이>"  # 띄어쓰기 하나 다름 — 못 찾음


def _labels(item_id, **extra):
    return {"id": item_id, "pref_label": f"{MARK} {item_id}", "aliases": [f"{MARK} {item_id} 별명"], "hidden_labels": [],
            **extra}


def plan():
    split = {"basis": "calc", "value_from_hint": [OPTION, NO_OPTION], "split_into": [
        {"id": "p-split-a", "pref_label": f"{MARK} 가", "basis": "calc", "value_from_hint": [OPTION]},
        {"id": "p-split-b", "pref_label": f"{MARK} 나", "basis": "calc", "value_from_hint": [NO_OPTION]},
        {"id": "p-split-c", "pref_label": f"{MARK} 다", "basis": "brain", "value_from_hint": [], "unsure": "합성"}]}
    return {
        "schema": "synth_data_plan/1",
        "items": [
            _labels("p-calc", kind="price_rule", price_rule={"basis": "calc", "value_from_hint": [OPTION]},
                    copy_hint=["form:synth-table"]),
            _labels("p-split", kind="price_rule", price_rule=split),
            _labels("p-held", kind="price_rule", price_rule={"basis": "calc", "value_from_hint": [OPTION],
                                                             "waiting": "합성"}),
            _labels("f-spec", kind="fact", fact_to={"type": "spec", "why": "합성"}),
            _labels("f-step", kind="fact", fact_to={"type": "process_step", "why": "합성"}, process_step_hint="MEASURE"),
            _labels("f-brand", kind="fact", fact_to={"type": "brand", "why": "합성"}),
            _labels("pol", kind="policy", process_step_hint="RECEIVED", decided="D5 합성"),
            _labels("dec", kind="owner_decision", decision_no="D5"),
            _labels("tpl", kind="template", process_step_hint="RECEIVED", decided="D99"),
            _labels("held", kind="policy", waiting="합성"),
            _labels("gone", kind="policy"),
        ],
        "new_items": [
            {"type": "process_step", "key": "process_step/MEASURE", "erp": "erp:stage/MEASURE",
             "pref_label": f"{MARK} 실측", "aliases": [f"{MARK} 방문"], "why": "D117 합성"},
            {"type": "process_step", "key": "process_step/RECEIVED", "erp": "erp:stage/RECEIVED",
             "pref_label": f"{MARK} 접수", "aliases": []},
            {"type": "spec", "key": "spec/synth-limit", "pref_label": f"{MARK} 한도",
             "value_from_hint": ["setting:cs_quote_rules#hinge_min_mm"]},
            {"type": "spec", "key": "spec/synth-held", "pref_label": f"{MARK} 보류", "unsure": "합성", "waiting": "합성"},
            {"type": "term", "key": "term/synth-word", "pref_label": f"{MARK} 낱말", "aliases": [f"{MARK} 다른 낱말"]},
            {"type": "price_rule", "key": "price_rule/p-new", "pref_label": f"{MARK} 새 값", "aliases": [f"{MARK} 새 별명"],
             "basis": "calc", "value_from_hint": [OPTION], "copy_hint": ["form:synth-table"], "parent_hint": "p-split",
             "decided": "D5 합성"},
        ],
        "conflicts": [
            {"about": ["p-calc"], "summary": f"{MARK} 합성 엇갈림", "resolved_by": None, "action": "conflict_item"},
            {"about": ["pol", "gone"], "summary": f"{MARK} 합성 글 고침", "resolved_by": "D5", "action": "edit_text"},
        ],
    }


@pytest.fixture
def admin(app):
    admin = person(db_session, "plan_admin")
    price = {"item_type": "price_rule", "checked_at": "2026-10-20"}
    for doc_id in ("p-calc", "p-split", "p-held"):
        create(db_session, admin, f"lahom/{doc_id}", brand="LAHOM", payload={"doc_id": doc_id, **DOC}, **price)
    create(db_session, admin, "common/f-spec", item_type="fact", payload={"doc_id": "f-spec", **DOC})
    for doc_id in ("f-step", "f-brand"):
        create(db_session, admin, f"lahom/{doc_id}", brand="LAHOM", item_type="fact", payload={"doc_id": doc_id, **DOC})
    for doc_id in ("pol", "held"):
        create(db_session, admin, f"lahom/{doc_id}", brand="LAHOM", item_type="policy", payload={"doc_id": doc_id, **DOC})
    create(db_session, admin, "lahom/dec", brand="LAHOM", item_type="owner_decision",
           payload={"doc_id": "dec", "decision_no": "D5", **DOC})
    create(db_session, admin, "lahom/tpl", brand="LAHOM", item_type="template", layer="cs",
           payload={"doc_id": "tpl", "intents": ["hours"], **DOC})
    db_session.commit()
    return admin


def run_plan(document=None, *, apply=True, now=NOW):
    with catalog_source(synth_catalog):
        out = file_plan(db_session, document or plan(), brand="LAHOM", apply=apply, now=now)
    db_session.commit()
    return out


def changes():
    """계획이 넣은 제안 수(합성 항목을 만든 사람 제안은 빼고)."""
    return db_session.scalar(select(func.count()).select_from(BrainChange).where(BrainChange.proposed_by == "import"))


def approve_all(admin):
    ids = db_session.execute(select(BrainChange.id).where(BrainChange.status == "open")
                             .order_by(BrainChange.id)).scalars().all()
    with catalog_source(synth_catalog):
        for change_id in ids:
            apply_change(db_session, change_id, actor=admin, now=NOW)
    db_session.commit()
    return len(ids)


def test_dry_run_files_nothing_and_counts_like_apply(admin):
    dry = run_plan(apply=False)
    assert changes() == 0 and dry["applied"] is False and dry["filed_total"] == 20
    real = run_plan()
    assert changes() == 20 and {k: v for k, v in real.items() if k != "applied"} == {
        k: v for k, v in dry.items() if k != "applied"}


def test_apply_files_expected_proposals_then_nothing_twice(admin):
    out = run_plan()
    assert out["filed"] == {"create": 10, "link_add:copy_in": 1, "link_add:decided_by": 1, "update": 8}
    assert out["deferred"] == {"awaiting_create": 13, "basis_pending": 1}
    assert out["skipped"] == {
        "decision_missing": 1, "item_missing": 2, "ref_unresolved": 1, "retype_brand": 1, "retype_process_step": 1,
        "retyped": 1, "unsure": 2, "waiting": 3}
    assert out["unresolved_refs"] == ["lahom/p-split-b"]  # 못 찾은 계산기 이름은 항목 키만
    rows = db_session.execute(select(BrainChange).where(BrainChange.status == "open")).scalars().all()
    assert len(rows) == 20 and {(c.proposed_by, c.action) for c in rows} == {("import", "import")}
    assert all(current_object(db_session, k) is None for k in ("lahom/p-split-a", "process_step/measure"))  # 반영 없음
    held = [c for c in rows if c.item_key == "lahom/p-held"]
    assert [sorted(c.fields["payload"]["after"]) for c in held] == [
        ["aliases", "approved_at", "approved_by", "doc_id", "pref_label"]]  # 보류 묶음(근거 종류)은 빠지고 이름표만
    again = run_plan()
    assert again["filed_total"] == 0 and changes() == 20 and again["deferred"] == out["deferred"]


def test_deferred_links_and_retire_follow_on_a_later_run(admin):
    run_plan()
    assert approve_all(admin) == 20
    out = run_plan()
    assert out["filed"] == {"link_add:about": 2, "link_add:at_step": 3, "link_add:copy_in": 1, "link_add:decided_by": 1,
                            "link_add:value_from": 6, "retire": 1}
    assert out["deferred"] == {} and out["unresolved_refs"] == ["lahom/p-split-b"]
    retire = db_session.execute(select(BrainChange).where(BrainChange.op == "retire")).scalar_one()
    assert retire.item_key == "common/f-spec" and "common/f-spec-spec" in retire.reason and MARK not in retire.reason
    assert approve_all(admin) == 14 and run_plan()["filed_total"] == 0
    new = current_object(db_session, "lahom/p-new")  # 새 가격 규칙 — 부모 힌트에서 보기 범위, 다른 이름은 실음 칸
    assert (new.item_type, new.payload["doc_id"], new.payload["aliases"]) == ("price_rule", "p-new", [f"{MARK} 새 별명"])
    spec = current_object(db_session, "common/f-spec-spec")
    assert spec.item_type == "spec" and spec.text == current_object(db_session, "common/f-spec").text
    assert current_object(db_session, "common/f-spec").status == "retired"
    child = current_object(db_session, "lahom/p-split-a")
    assert (child.item_type, child.status, child.payload["basis"], child.evidence_kind) == (
        "price_rule", "active", "calc", "document")
    assert current_object(db_session, "process_step/measure").payload["erp_stage"] == "MEASURE"
    assert "lahom/p-calc" in alias_keys(db_session, f"{MARK} p-calc 별명")  # 가격 규칙 다른 이름도 찾기에 든다


def test_import_rerun_leaves_plan_created_document_items(admin):
    run_plan()
    approve_all(admin)
    planned = doc_import.plan_import(db_session, {})
    assert "lahom/p-split-a" in planned.unmanaged
    assert "lahom/p-split-a" not in [row.item_key for row in planned.deletes]


def test_import_proposals_are_not_capped_and_do_not_expire(admin):
    for n in range(AI_WEEKLY_CAP + 5):
        create(db_session, admin, f"lahom/bulk-{n:02d}", brand="LAHOM", item_type="policy",
               payload={"doc_id": f"bulk-{n:02d}", **DOC})
    db_session.commit()
    document = {"items": [_labels(f"bulk-{n:02d}", kind="policy") for n in range(AI_WEEKLY_CAP + 5)]}
    assert run_plan(document)["filed"] == {"update": AI_WEEKLY_CAP + 5}
    later = NOW + datetime.timedelta(days=40)
    cards = inbox(db_session, viewer_of(admin), now=later)["cards"]
    assert len([c for c in cards if c["key"].startswith("lahom/bulk-")]) == AI_WEEKLY_CAP + 5
    assert expire_ai_proposals(db_session, now=later) == 0
    assert db_session.scalar(select(func.count()).select_from(BrainChange).where(BrainChange.status == "open")) == (
        AI_WEEKLY_CAP + 5)


def test_bad_plan_shape_is_refused_without_text(admin):
    from foms.services.brain.errors import BrainShapeError

    with pytest.raises(BrainShapeError) as caught:
        file_plan(db_session, {"items": [{"pref_label": MARK}]}, brand="LAHOM", apply=False, now=NOW)
    assert MARK not in str(caught.value) and changes() == 0


# ── 관리자 스크립트 ──────────────────────────────────────────────────────
def load_script():
    spec = importlib.util.spec_from_file_location("brain_plan_proposals_ut", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(script, capsys, *argv):
    with catalog_source(synth_catalog):
        code = script.run(list(argv))
    printed = capsys.readouterr().out
    assert MARK not in printed and "합성 엇갈림" not in printed  # 글 · 이름은 화면에 내지 않는다
    return code, json.loads(printed)


def test_script_dry_run_then_apply_prints_counts_only(admin, capsys, tmp_path):
    script = load_script()
    path = tmp_path / "synth_plan.json"
    path.write_text(json.dumps(plan(), ensure_ascii=False), encoding="utf-8")
    code, out = run_script(script, capsys, "--plan", str(path))
    assert code == 0 and out["applied"] is False and out["filed_total"] == 20 and changes() == 0
    code, out = run_script(script, capsys, "--plan", str(path), "--apply")
    assert code == 0 and out["applied"] is True and changes() == 20
    evidence = db_session.execute(select(BrainChange.evidence).where(BrainChange.proposed_by == "import")).scalars().first()
    assert evidence[0].startswith("plan:synth_data_plan#")
    code, out = run_script(script, capsys, "--plan", str(tmp_path / "none.json"))
    assert (code, out["error"]) == (1, "PLAN_UNREADABLE")


@pytest.mark.parametrize("environment", ["production", "unknown-remote"])
def test_script_refuses_remote_apply_without_owner_approval(admin, capsys, monkeypatch, tmp_path, environment):
    script = load_script()
    monkeypatch.setattr(script, "resolve_environment", lambda: environment)
    path = tmp_path / "synth_plan.json"
    path.write_text(json.dumps(plan(), ensure_ascii=False), encoding="utf-8")
    code, out = run_script(script, capsys, "--plan", str(path), "--apply")
    assert (code, out["error"]) == (1, "OWNER_APPROVAL_REQUIRED") and changes() == 0
    code, out = run_script(script, capsys, "--plan", str(path))  # 모의 실행은 막지 않는다(쓰기 0)
    assert code == 0 and changes() == 0
    assert db_session.scalar(select(func.count()).select_from(BrainObject)) == 10  # 합성 항목 그대로


def test_plan_text_goes_into_new_items_and_withdraw_refiles_only_undecided(admin):
    """계획의 ``text`` 는 새 항목 글로 들어간다 · 거두기는 이 계획이 넣고 아직 결정 안 된 제안만 닫고(결정된 것 · 다른 근거는 그대로),
    다시 넣으면 고친 글로 들어간다."""
    from foms.services.brain.plan_proposals import withdraw_open

    first = plan()
    run_plan(first)
    decided = db_session.execute(select(BrainChange).where(BrainChange.proposed_by == "import", BrainChange.op == "update")
                                 .order_by(BrainChange.id)).scalars().first()
    with catalog_source(synth_catalog):
        apply_change(db_session, decided.id, actor=admin, now=NOW)
    db_session.commit()
    open_before = db_session.scalar(select(func.count()).select_from(BrainChange).where(
        BrainChange.proposed_by == "import", BrainChange.status == "open"))

    second = plan()
    second["new_items"][4]["text"] = f"{MARK} 낱말 뜻 글"
    second["items"][1]["price_rule"]["split_into"][0]["text"] = f"{MARK} 가 나눔 글"
    assert withdraw_open(db_session, source="other_plan", now=NOW) == 0  # 다른 근거 대조군
    withdrawn = withdraw_open(db_session, source="synth_data_plan", now=NOW)
    db_session.commit()
    assert withdrawn == open_before
    assert db_session.get(BrainChange, decided.id).status == "applied"  # 결정된 것은 그대로
    assert db_session.scalar(select(func.count()).select_from(BrainChange).where(
        BrainChange.status == "expired", BrainChange.decided_action == "withdraw")) == withdrawn

    again = run_plan(second)
    assert again["filed_total"] >= open_before  # 반영된 고침이 풀어 준 링크가 더 들어갈 수 있다
    keys = db_session.execute(select(BrainChange.op, BrainChange.item_key, BrainChange.link_kind, BrainChange.link_to)
                              .where(BrainChange.status == "open")).all()
    assert len(keys) == len(set(keys))  # 같은 제안이 둘 열리지 않는다
    texts = {c.item_key: (c.fields or {}).get("text", {}).get("after") for c in db_session.execute(
        select(BrainChange).where(BrainChange.status == "open", BrainChange.op == "create")).scalars()}
    assert texts["term/synth-word"] == f"{MARK} 낱말 뜻 글"
    assert texts["lahom/p-split-a"] == f"{MARK} 가 나눔 글"
    assert texts["spec/synth-limit"] == f"{MARK} 한도"  # 글이 없으면 대표 이름(규격)


def test_text_fix_files_a_text_edit_once_and_skips_same_text(admin):
    """``text_fix`` 는 승인된 글의 고침을 고침 제안 '글' 칸으로 싣는다(D147 맞춤법만) — 지금 글과 같으면 싣지 않고,
    다시 돌려도 같은 제안이 둘 열리지 않는다."""
    from foms.services.brain.store import current_object, values_of

    document = plan()
    document["items"][6].update(text_fix=f"{MARK} 고친 글", text_fix_why="D147 — 합성 맞춤법만")  # pol
    document["items"][8]["text_fix"] = values_of(current_object(db_session, "lahom/tpl"))["text"]  # 대조군: 같은 글
    run_plan(document)
    rows = db_session.execute(select(BrainChange).where(BrainChange.proposed_by == "import", BrainChange.op == "update",
                                                         BrainChange.status == "open")).scalars().all()
    fixed = [c for c in rows if c.item_key == "lahom/pol"]
    assert len(fixed) == 1 and fixed[0].fields["text"]["after"] == f"{MARK} 고친 글"
    assert "payload" in fixed[0].fields and "맞춤법 · 뜻을 고쳐요" in fixed[0].reason and "D147" in fixed[0].reason
    assert not any("text" in (c.fields or {}) for c in rows if c.item_key == "lahom/tpl")  # 같은 글은 싣지 않는다
    before = changes()
    run_plan(document)
    assert changes() == before  # 다시 돌려도 그대로


def test_price_creates_carry_their_calculator_place_and_reasons_read_as_sentences(admin):
    """새 가격 규칙 만들기 제안은 근거에 계산기 자리를 함께 싣는다(카드가 '지금 값' 한 줄 — 설계서 7.9 ② 문장 카드).
    못 찾은 이름(띄어쓰기 다름)은 싣지 않는다. 까닭은 사람이 읽는 문장 + 사장님 결정 번호."""
    run_plan()
    rows = {c.item_key: c for c in db_session.execute(select(BrainChange).where(
        BrainChange.proposed_by == "import", BrainChange.op == "create")).scalars()}
    split_a, split_b = rows["lahom/p-split-a"], rows["lahom/p-split-b"]
    assert [e for e in split_a.evidence if e.startswith("calc:")] == [e for e in split_a.evidence[1:]]
    assert len(split_a.evidence) == 2 and split_a.evidence[1].startswith("calc:option/")
    assert split_b.evidence == split_b.evidence[:1]  # 못 찾은 자리는 안 싣는다(대조군)
    assert split_a.reason.startswith("한 글에 여러 값이 섞여 있어서 값마다 나눠요 (자료 정리 · 사장님 결정 D115")
    assert "채움" not in " ".join(c.reason for c in rows.values()) and "자료 계획 —" not in split_a.reason
