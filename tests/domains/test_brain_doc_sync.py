"""반영 때 상담 지식 문서 다시 쓰기(설계서 2026-11-02-haud-master-brain 7.5 '반영 때마다 표에서 다시 만든다' · 3.1 규칙 1) —
같은 저장점 · 그 브랜드만 · 공통은 두 브랜드 · 은퇴 · 지우기 · 판 되돌리기 · 이 반영 밖 차이면 멈춤 · 저장 실패면 반영째 되돌림 ·
[사람] · [내부] 표시 유지 · 맞추기(표 → 문서).

합성 두 브랜드 문서(:mod:`tests.domains.test_brain_import`)만 쓴다 — 실제 기준 답 · 가격 · 사람 이름 · 금액 없음.
"""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain import doc_bridge, doc_sync
from foms.services.brain.apply import apply_change
from foms.services.brain.errors import BrainDocSyncError
from foms.services.brain.proposals import Proposer, propose_delete, propose_retire, propose_update
from foms.services.brain.rollback import rollback_release
from foms.services.brain.store import current_object
from foms.services.cs_agent import knowledge as kn
from models import SecurityLog
from tests.domains.test_brain_import import docs, import_now, load_script, run_script, store_docs
from tests.support.brain_support import NOW, REASON, create, person


def _ready():
    admin = person(db_session, "ds_admin")
    store_docs(admin, docs())
    import_now(admin)
    return admin


def _edit(admin, key, after):
    row = current_object(db_session, key)
    return propose_update(db_session, key=key, base_version=row.version, after=after, reason=REASON,
                          proposer=Proposer.user(admin.id), known="")


def _versions():
    return kn.read_stored(db_session, "LAHOM").version, kn.read_stored(db_session, "HAUD").version


def _doc_item(brand, doc_id):
    return next((i for i in kn.read_stored(db_session, brand).document["items"] if i["id"] == doc_id), None)


def _equal_both():
    return all(doc_bridge.shadow_compare(db_session, b)["equal"] for b in ("LAHOM", "HAUD"))


def test_approving_a_brand_item_rewrites_only_that_brand_document(app):
    admin = _ready()
    assert _versions() == (1, 1)
    change = _edit(admin, "lahom/lahom-only", {"text": "합성 고친 사실"})
    apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    assert _versions() == (2, 1)  # 하우드 문서는 그대로
    assert kn.load_approved(db_session, "LAHOM").get("lahom-only").text == "합성 고친 사실"  # 상담 두뇌가 읽는 길
    assert kn.history(db_session, "LAHOM", limit=1)[0]["actor_user_id"] == admin.id  # 넣은 사람 = 승인한 사람
    assert _equal_both()
    audit = db_session.execute(select(SecurityLog.detail).where(SecurityLog.action == "BRAIN_APPLY")
                               .order_by(SecurityLog.id.desc())).scalars().first()
    assert audit["docs"] == {"LAHOM": 2}


def test_a_common_item_rewrites_both_documents_and_other_items_do_not(app):
    admin = _ready()
    apply_change(db_session, _edit(admin, "common/shared-hours", {"text": "합성 공통 새 안내"}).id, actor=admin, now=NOW)
    db_session.commit()
    assert _versions() == (2, 2)
    assert {_doc_item(b, "shared-hours")["text"] for b in ("LAHOM", "HAUD")} == {"합성 공통 새 안내"}
    create(db_session, admin, "line/synth", item_type="product_line")  # 지식 문서 유형이 아니다
    db_session.commit()
    assert _versions() == (2, 2) and _equal_both()


def test_retire_and_delete_follow_into_the_document(app):
    admin = _ready()
    row = current_object(db_session, "common/shared-hours")
    retire = propose_retire(db_session, key="common/shared-hours", base_version=row.version, reason=REASON,
                            proposer=Proposer.user(admin.id))
    apply_change(db_session, retire.id, actor=admin, now=NOW)
    gone = current_object(db_session, "lahom/lahom-only")
    delete = propose_delete(db_session, key="lahom/lahom-only", base_version=gone.version, reason=REASON,
                            proposer=Proposer.user(admin.id))
    apply_change(db_session, delete.id, actor=admin, now=NOW)
    db_session.commit()
    assert _doc_item("HAUD", "shared-hours")["status"] == "retired"
    assert kn.load_approved(db_session, "LAHOM").get("shared-hours") is None  # 은퇴 = 재료에서 빠짐
    assert _doc_item("LAHOM", "lahom-only") is None and _equal_both()


def test_release_rollback_rewrites_the_document_back(app):
    admin = _ready()
    before = _doc_item("LAHOM", "lahom-only")
    result = apply_change(db_session, _edit(admin, "lahom/lahom-only", {"text": "합성 고친 사실"}).id, actor=admin,
                          now=NOW)
    db_session.commit()
    rollback_release(db_session, result.release_no, "common", actor=admin, confirm_number=result.release_no, now=NOW)
    db_session.commit()
    assert _doc_item("LAHOM", "lahom-only") == before and _versions() == (3, 1) and _equal_both()


def test_a_document_written_outside_the_table_stops_the_approval(app):
    admin = _ready()
    stored = kn.read_stored(db_session, "LAHOM")
    document = copy.deepcopy(stored.document)
    next(i for i in document["items"] if i["id"] == "diff-text")["text"] = "합성 문서만 고친 정책"
    kn.save_document(db_session, "LAHOM", document, actor_user_id=admin.id, expected_version=stored.version)
    db_session.commit()
    change = _edit(admin, "lahom/lahom-only", {"text": "합성 고친 사실"})
    db_session.commit()
    with pytest.raises(BrainDocSyncError) as caught:
        apply_change(db_session, change.id, actor=admin, now=NOW)
    assert (caught.value.reason, caught.value.ids, caught.value.code) == ("drift", ("diff-text",), "BRAIN_DOC_SYNC")
    db_session.rollback()
    assert db_session.get(BrainChange, change.id).status == "open"  # 제안은 열린 채
    assert current_object(db_session, "lahom/lahom-only").version == 1 and _versions() == (2, 1)
    assert _doc_item("LAHOM", "diff-text")["text"] == "합성 문서만 고친 정책"  # 문서에만 있는 글을 덮지 않았다
    # 맞추기(표 → 문서) 뒤에는 반영이 다시 된다
    out = doc_sync.publish_documents(db_session, actor_id=admin.id, now=NOW)
    db_session.commit()
    assert out["LAHOM"]["version"] == 3 and out["LAHOM"]["diff"]["changed"] == {"diff-text": ["text"]}
    assert out["HAUD"] == {"version": 1, "diff": None}
    apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    assert _versions() == (4, 1) and _equal_both()


def test_a_failed_document_write_rolls_the_whole_approval_back(app, monkeypatch):
    admin = _ready()
    change = _edit(admin, "common/shared-hours", {"text": "합성 공통 새 안내"})
    db_session.commit()

    def conflict(*_args, **_kwargs):
        raise kn.KnowledgeConflictError(9)

    monkeypatch.setattr(doc_sync, "save_document", conflict)
    with pytest.raises(BrainDocSyncError) as caught:
        apply_change(db_session, change.id, actor=admin, now=NOW)
    assert caught.value.reason == "REVISION_CONFLICT"
    # 부르는 쪽이 되돌리기 전에도 이미 저장점이 표 쓰기를 되돌렸다 — 커밋해도 표 · 문서가 갈라지지 않는다
    db_session.commit()
    assert current_object(db_session, "common/shared-hours").version == 1
    assert db_session.get(BrainChange, change.id).status == "open" and _versions() == (1, 1) and _equal_both()


def test_spoken_and_internal_marks_survive_the_rewrite(app):
    admin = _ready()
    apply_change(db_session, _edit(admin, "lahom/lahom-only", {"text": "[내부] 합성 내부 규칙"}).id, actor=admin, now=NOW)
    apply_change(db_session, _edit(admin, "common/shared-hours", {"text": "[사람] 합성 사람 확인 안내"}).id, actor=admin,
                 now=NOW)
    db_session.commit()
    knowledge = kn.load_approved(db_session, "LAHOM")
    assert knowledge.get("lahom-only").text == "[내부] 합성 내부 규칙"
    assert knowledge.get("shared-hours").text == "[사람] 합성 사람 확인 안내"
    spoken = knowledge.spoken_texts()
    assert not any("[내부]" in t or "[사람]" in t for t in spoken) and spoken  # 숫자 허용 목록에서 빠진다


def test_a_brand_without_a_document_gets_one_only_when_it_has_items(app):
    admin = person(db_session, "ds_admin")
    create(db_session, admin, "lahom/fresh-fact", item_type="fact", brand="LAHOM",
           payload={"doc_id": "fresh-fact", "approved_by": "합성", "approved_at": "2026-10-20"})
    db_session.commit()
    assert _versions() == (1, 0)  # 하우드는 문서도 항목도 없다 — 빈 문서를 만들지 않는다
    assert [i["id"] for i in kn.read_stored(db_session, "LAHOM").document["items"]] == ["fresh-fact"]


def test_script_publish_needs_an_admin_and_makes_the_document_equal(app, capsys):
    script = load_script()
    admin = _ready()
    stored = kn.read_stored(db_session, "HAUD")
    document = copy.deepcopy(stored.document)
    document["items"] = [i for i in document["items"] if i["id"] != "haud-only"]  # 문서에서만 뺌
    kn.save_document(db_session, "HAUD", document, actor_user_id=admin.id, expected_version=stored.version)
    db_session.commit()
    assert run_script(script, capsys, "--publish")[1]["error"] == "ACTOR_REQUIRED"
    assert run_script(script, capsys, "--publish", "--apply", "--actor", "ds_admin")[1]["error"] == "APPLY_WITH_PUBLISH"
    assert _versions() == (1, 2)
    code, out = run_script(script, capsys, "--publish", "--actor", "ds_admin", "--brand", "HAUD")
    assert code == 0 and out["applied"] is True and out["publish"]["HAUD"]["diff"]["added"] == ["haud-only"]
    assert [c["equal"] for c in out["compare"]] == [True] and _versions() == (1, 3)
