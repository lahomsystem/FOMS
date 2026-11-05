"""온톨로지 바로잡기(설계서 7.8) — 지식 문서와 오가는 쪽: brain 만의 칸 · 제작 조건 지식 문서 종류(다음 9) · 옮긴 결정 번호.

- 가격 규칙 · 사장님 결정의 brain 만의 칸(근거 종류 · 결정 번호 …)은 옮기기를 다시 돌려도 남고(사람이 고친 판은 옮기기가
  손대지 않는다 — 3.1 규칙 1), 다시 만든 지식 문서로 나가지 않는다(다시 만든 문서 = 옛 문서).
- 제작 조건(``build_rule``)이 지식 문서 종류가 되어 상담 견적 검사가 읽는다 — 안 맞으면 사람에게 넘길 까닭만(값은 그대로).
  문서 id 가 없는 brain 만의 제작 조건은 문서로 나가지 않고 옮기기가 건드리지 않는다.
합성 두 브랜드 문서 · 합성 계정만(금액 숫자 없음).
"""

from __future__ import annotations

import copy

from db import db_session
from foms.services.brain import doc_bridge, doc_import
from foms.services.brain.apply import apply_change
from foms.services.brain.card import item_card
from foms.services.brain.constants import DOC_TYPES, is_doc_item
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from foms.services.cs_agent import knowledge as kn
from foms.services.cs_agent import knowledge_doc as kd
from foms.services.cs_agent import quote_calc as qc
from tests.support.brain_screen_support import TODAY
from tests.support.brain_support import NOW, REASON, create, person
from tests.support.cs_quote_support import MOLD, ask, evaluate, space


def item(item_id, *, kind, text=None, **extra):
    row = {"id": item_id, "kind": kind, "intents": [], "status": "approved", "text": text or f"합성 글 {item_id}",
           "approved_by": "synthetic-owner", "approved_at": "2026-10-20"}
    row.update(extra)
    return row


def docs(rule_text=f"합성 조건 글\n검사: product={MOLD['id']} max_width=3000"):
    rows = [item("unit-fee", kind="price_rule", checked_at="2026-10-20"), item("decide-one", kind="owner_decision"),
            item("fit-rule", kind="build_rule", text=rule_text)]
    return {brand: {"schema_version": 1, "brand": brand, "items": copy.deepcopy(rows)} for brand in ("LAHOM", "HAUD")}


def store(admin, documents):
    for brand, doc in documents.items():
        current = kn.read_stored(db_session, brand).version
        kn.save_document(db_session, brand, doc, actor_user_id=admin.id, expected_version=current)
    db_session.commit()


def import_now(admin):
    versions, problems = doc_import.load_documents(db_session)
    assert problems == {}
    out = doc_import.run_import(db_session, versions, actor=admin, apply=True, now=NOW)
    db_session.commit()
    return out


def test_build_rule_is_a_knowledge_doc_kind_read_by_the_quote_check():
    assert kd.KIND_BUILD_RULE in kd.KINDS and qc.KIND_BUILD_RULE == kd.KIND_BUILD_RULE
    doc = kd.validate_document(docs()["LAHOM"], brand="LAHOM")
    approved = kd.approved_items(doc)
    rules = qc.build_rules(approved)
    assert [r.item_id for r in rules] == ["fit-rule"] and rules[0].max_width == 3000
    over = evaluate(ask(space(width=3600)), rules=rules)
    assert (over.status, over.code, over.allowed) == (qc.STATUS_HUMAN, qc.HUMAN_RULE, ())  # 사람에게 넘길 까닭만
    within = evaluate(ask(space(width=2400)), rules=rules)
    assert within.status == qc.STATUS_OK and within.allowed == evaluate(ask(space(width=2400))).allowed  # 값은 그대로
    other = evaluate(ask(space(width=3600)), rules=qc.build_rules(kd.approved_items(kd.validate_document(
        docs(rule_text="합성 조건\n검사: product=999999 max_width=3000")["LAHOM"], brand="LAHOM"))))
    assert other.status != qc.STATUS_HUMAN or other.code != qc.HUMAN_RULE  # 대조군: 다른 제품 규칙은 안 걸린다


def test_brain_only_fields_survive_reimport_and_never_reach_the_document(app):
    admin = person(db_session, "d129_doc_admin")
    store(admin, docs())
    out = import_now(admin)
    assert out["create"] == 3 and current_object(db_session, "common/fit-rule").item_type == "build_rule"
    stored = {b: kn.read_stored(db_session, b).document for b in ("LAHOM", "HAUD")}
    price = current_object(db_session, "common/unit-fee")
    change = propose_update(db_session, key="common/unit-fee", base_version=price.version, reason=REASON,
                            after={"payload": {**price.payload, "basis": "brain", "stage": "extra", "unit": "회"}},
                            proposer=Proposer.user(admin.id), now=NOW, known="")
    apply_change(db_session, change.id, actor=admin, now=NOW)
    decision = current_object(db_session, "common/decide-one")
    change = propose_update(db_session, key="common/decide-one", base_version=decision.version, reason=REASON,
                            after={"payload": {**decision.payload, "decision_no": "D7", "decided_on": "2026-10-20"}},
                            proposer=Proposer.user(admin.id), now=NOW, known="")
    apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    for brand in ("LAHOM", "HAUD"):
        assert doc_bridge.regenerate_document(db_session, brand) == stored[brand]  # brain 만의 칸은 문서로 안 나간다
    changed = docs()
    for brand in changed:
        changed[brand]["items"][0]["text"] = "합성 글 고친 규칙"
    store(admin, changed)
    again = import_now(admin)  # 사람이 고친 판은 문서 값으로 되돌리지 않는다(표가 정본 — 3.1 규칙 1)
    assert again["protected"] == ["common/unit-fee"] and again["update"] == 0
    unit_fee = current_object(db_session, "common/unit-fee")
    assert unit_fee.text != "합성 글 고친 규칙"
    payload = unit_fee.payload
    assert (payload["basis"], payload["stage"], payload["unit"]) == ("brain", "extra", "회")  # brain 만의 칸 그대로
    assert current_object(db_session, "common/decide-one").payload["decision_no"] == "D7"
    from foms.services.brain.doc_sync import publish_documents
    publish_documents(db_session, actor_id=admin.id, now=NOW)  # 맞추기(표 → 문서) — brain 만의 칸은 문서로 안 나간다
    db_session.commit()
    for brand in ("LAHOM", "HAUD"):
        assert kn.read_stored(db_session, brand).document == stored[brand]
        assert doc_bridge.shadow_compare(db_session, brand)["equal"] is True


def test_imported_decision_without_number_is_flagged_not_blocked(app):
    admin = person(db_session, "d129_doc_admin")
    store(admin, docs())
    import_now(admin)
    decision = current_object(db_session, "common/decide-one")
    assert decision.status == "active" and "decision_no" not in decision.payload  # 옮기기는 막히지 않는다
    card = item_card(db_session, viewer_of(admin), "common/decide-one", today=TODAY)
    assert "empty:payload.decision_no" in {w["code"] for w in card["warnings"]}
    fixed = propose_update(db_session, key="common/decide-one", base_version=decision.version, reason=REASON,
                           after={"text": "합성 고친 결정 글"}, proposer=Proposer.user(admin.id), now=NOW, known="")
    apply_change(db_session, fixed.id, actor=admin, now=NOW)  # 옮긴 결정은 번호 없이도 고칠 수 있다
    numbered = current_object(db_session, "common/decide-one")
    change = propose_update(db_session, key="common/decide-one", base_version=numbered.version, reason=REASON,
                            after={"payload": {**numbered.payload, "decision_no": "D8"}},
                            proposer=Proposer.user(admin.id), now=NOW, known="")
    apply_change(db_session, change.id, actor=admin, now=NOW)
    card = item_card(db_session, viewer_of(admin), "common/decide-one", today=TODAY)
    assert "empty:payload.decision_no" not in {w["code"] for w in card["warnings"]}  # 대조군


def test_brain_only_build_rules_stay_out_of_the_document(app):
    admin = person(db_session, "d129_doc_admin")
    store(admin, docs())
    import_now(admin)
    create(db_session, admin, "common/brain-fit", item_type="build_rule", name="합성 brain 조건",
           payload={"rule_kind": "limit"})
    db_session.commit()
    assert "build_rule" in DOC_TYPES and not is_doc_item("build_rule", {"rule_kind": "limit"})
    assert is_doc_item("build_rule", {"doc_id": "fit-rule"}) and is_doc_item("policy", {})
    for brand in ("LAHOM", "HAUD"):
        assert doc_bridge.shadow_compare(db_session, brand)["equal"] is True  # brain 만의 조건은 문서 밖
    dry = doc_import.run_import(db_session, doc_import.load_documents(db_session)[0], actor=admin, apply=False, now=NOW)
    assert dry["unmanaged"] == [] and dry["delete"] == 0 and dry["unchanged"] == 3  # 옮기기가 건드리지 않는다
