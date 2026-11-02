"""지식 문서 → brain 표 옮기기 · 다시 만들기 · 그림자 견주기(설계서 7.5 끝 '저장 꼴' · D97 · D99) — 공통 항목 합치기 · 다시
만든 문서 = 옛 문서 · 멱등 · 문서가 바뀌면 따라감 · 관리자 스크립트(모의 실행은 쓰기 0 · 글 안 냄 · 운영 막기).

합성 두 브랜드 문서만 쓴다 — 실제 기준 답 · 가격 · 사람 이름이 없고 금액 숫자도 없다. 글 표지 :data:`MARK` 는 스크립트 출력
어디에도 나오면 안 된다.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainObject, BrainRelease
from foms.services.brain import doc_bridge, doc_import
from foms.services.brain.store import current_object
from foms.services.cs_agent import knowledge as kn
from tests.support.brain_support import NOW, person

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "brain_import_knowledge.py"
MARK = "보라합성표지"


def item(item_id, *, kind="template", status="approved", intents=("hours",), text=None, **extra):
    row = {"id": item_id, "kind": kind, "intents": list(intents), "status": status,
           "text": text or f"{MARK} 합성 안내 {item_id}"}
    if status in ("approved", "retired"):
        row.update(approved_by="synthetic-owner", approved_at="2026-10-20")
    row.update(extra)
    return row


SHARED = item("shared-hours")
DRAFT = item("draft-tpl", status="draft", intents=("booking",))
PRICE = item("price-unit", kind="price_rule", intents=(), checked_at="2026-10-20", source="synthetic/rules.md",
             tags=["fee"])


def docs():
    lahom = [SHARED, item("lahom-only", kind="fact", intents=()),
             item("diff-text", kind="policy", intents=(), text=f"{MARK} 합성 정책 라홈"), DRAFT,
             item("old-rule", status="retired"), PRICE, item("owner-rule", kind="owner_decision", status="draft",
                                                             intents=())]
    haud = [PRICE, item("diff-text", kind="policy", intents=(), text=f"{MARK} 합성 정책 하우드"), SHARED,
            item("haud-only", kind="fact", intents=(), tags=["size"]), DRAFT]
    return {"LAHOM": {"schema_version": 1, "brand": "LAHOM", "items": copy.deepcopy(lahom)},
            "HAUD": {"schema_version": 1, "brand": "HAUD", "items": copy.deepcopy(haud)}}


def store_docs(admin, documents):
    for brand, doc in documents.items():
        current = kn.read_stored(db_session, brand).version
        kn.save_document(db_session, brand, doc, actor_user_id=admin.id, expected_version=current)
    db_session.commit()


def import_now(admin, *, apply=True):
    versions, problems = doc_import.load_documents(db_session)
    assert problems == {}
    out = doc_import.run_import(db_session, versions, actor=admin, apply=apply, now=NOW)
    db_session.commit()
    return out


def written():
    return tuple(db_session.scalar(select(func.count()).select_from(model))
                 for model in (BrainObject, BrainChange, BrainRelease))


def current_keys():
    return sorted(db_session.execute(select(BrainObject.item_key).where(
        BrainObject.superseded_at.is_(None))).scalars())


def test_identical_items_become_one_common_item(app):
    admin = person(db_session, "im_admin")
    store_docs(admin, docs())
    out = import_now(admin)
    assert out["applied"] and out["create"] == 9 and out["releases"] == [0]
    assert current_keys() == ["common/draft-tpl", "common/price-unit", "common/shared-hours", "haud/diff-text",
                              "haud/haud-only", "lahom/diff-text", "lahom/lahom-only", "lahom/old-rule",
                              "lahom/owner-rule"]
    shared = current_object(db_session, "common/shared-hours")
    assert (shared.brand, shared.layer, shared.item_type, shared.status) == ("COMMON", "cs", "template", "active")
    assert shared.payload["doc_pos"] == {"HAUD": 2, "LAHOM": 0}  # 브랜드마다 문서 차례
    assert shared.evidence_kind == "import" and shared.human_approver_id is None and shared.created_by == "import"
    price = current_object(db_session, "common/price-unit")
    assert price.stale_after.isoformat() == "2026-11-03"  # 확인 날 + 14일
    assert current_object(db_session, "lahom/owner-rule").confidence == "observed"  # 승인 표시 없는 초안
    layers = db_session.execute(select(BrainRelease.number, BrainRelease.layer).order_by(BrainRelease.layer)).all()
    assert layers == [(0, "common"), (0, "cs")]  # 판 0 = 옮겨 온 판(층마다 줄)
    changes = db_session.execute(select(BrainChange.status, BrainChange.proposed_by, BrainChange.evidence)).all()
    assert {(s, p) for s, p, _e in changes} == {("applied", "import")}
    assert changes[0][2] == ["cs_agent_knowledge_haud@v1", "cs_agent_knowledge_lahom@v1"]


def test_regenerated_documents_equal_the_stored_ones(app):
    admin = person(db_session, "im_admin")
    store_docs(admin, docs())
    import_now(admin)
    for brand in ("LAHOM", "HAUD"):
        stored = kn.read_stored(db_session, brand).document
        assert doc_bridge.regenerate_document(db_session, brand) == stored  # 항목 · 칸 · 차례 모두
        compared = doc_bridge.shadow_compare(db_session, brand)
        assert compared["equal"] is True and not any(compared["diff"][k] for k in ("added", "removed", "changed"))
    # 음성 대조군: 표를 한 칸 바꾸면 견주기가 그 항목 · 칸을 잡는다(사람 반영 길로)
    from foms.services.brain.apply import apply_change
    from foms.services.brain.proposals import Proposer, propose_update
    change = propose_update(db_session, key="lahom/lahom-only", base_version=1, after={"text": "합성 고친 사실"},
                            reason="합성", proposer=Proposer.user(admin.id), known="")
    apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    compared = doc_bridge.shadow_compare(db_session, "LAHOM")
    assert compared["equal"] is False and compared["diff"]["changed"] == {"lahom-only": ["text"]}
    assert doc_bridge.shadow_compare(db_session, "HAUD")["equal"] is True


def test_import_is_idempotent(app):
    admin = person(db_session, "im_admin")
    store_docs(admin, docs())
    import_now(admin)
    before = written()
    again = import_now(admin)
    assert (again["create"], again["update"], again["delete"], again["unchanged"]) == (0, 0, 0, 9)
    assert written() == before  # 같은 문서를 다시 옮겨도 쓰기 0
    dry = import_now(admin, apply=False)
    assert dry["applied"] is False and dry["unchanged"] == 9


def test_import_follows_document_changes(app):
    admin = person(db_session, "im_admin")
    store_docs(admin, docs())
    import_now(admin)
    changed = docs()
    changed["LAHOM"]["items"][2]["text"] = changed["HAUD"]["items"][1]["text"]  # 정책이 두 브랜드에서 같아짐
    del changed["LAHOM"]["items"][1]  # 라홈만 있던 사실을 뺌
    changed["HAUD"]["items"][2]["text"] = f"{MARK} 합성 안내 하우드만 바뀜"  # 공통이던 문구가 갈라짐
    changed["HAUD"]["items"][4]["status"] = "approved"
    changed["HAUD"]["items"][4].update(approved_by="synthetic-owner", approved_at="2026-10-21")
    changed["HAUD"]["items"][3]["status"] = "retired"  # 하우드 사실을 내림 → 은퇴 제안으로
    store_docs(admin, changed)
    out = import_now(admin)
    # 라홈 문서에서 한 줄이 빠져 뒤 항목들의 문서 차례가 바뀌었다(차례도 따라간다) + 하우드 사실 내림
    assert out["keys"]["update"] == ["common/price-unit", "haud/haud-only", "lahom/old-rule", "lahom/owner-rule"]
    assert [r.status for r in db_session.execute(select(BrainObject).where(
        BrainObject.item_key == "haud/haud-only").order_by(BrainObject.version)).scalars()] == ["active", "retired"]
    assert out["keys"]["delete"] == ["common/draft-tpl", "common/shared-hours", "haud/diff-text", "lahom/diff-text",
                                     "lahom/lahom-only"]
    assert sorted(out["keys"]["create"]) == ["common/diff-text", "haud/draft-tpl", "haud/shared-hours",
                                             "lahom/draft-tpl", "lahom/shared-hours"]
    for brand in ("LAHOM", "HAUD"):
        assert doc_bridge.shadow_compare(db_session, brand)["equal"] is True
    assert len(db_session.execute(select(BrainObject).where(
        BrainObject.item_key == "common/shared-hours")).scalars().all()) == 1  # 지운 항목도 이력은 남는다


def test_import_leaves_items_made_elsewhere_alone(app):
    admin = person(db_session, "im_admin")
    store_docs(admin, docs())
    import_now(admin)
    from tests.support.brain_support import create
    create(db_session, admin, "lahom/extra", item_type="fact", brand="LAHOM",
           payload={"doc_id": "extra-fact", "approved_by": "합성", "approved_at": "2026-10-20"})
    db_session.commit()
    out = import_now(admin, apply=False)
    assert out["unmanaged"] == ["lahom/extra"] and out["delete"] == 0


# ── 관리자 스크립트 ──────────────────────────────────────────────────────
def load_script():
    spec = importlib.util.spec_from_file_location("brain_import_knowledge_ut", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(script, capsys, *argv):
    code = script.run(list(argv))
    printed = capsys.readouterr().out
    assert MARK not in printed  # 글은 화면에 내지 않는다
    return code, json.loads(printed)


def test_script_dry_run_apply_and_compare(app, capsys):
    script = load_script()
    admin = person(db_session, "im_admin")
    person(db_session, "im_staff", role="STAFF")
    store_docs(admin, docs())
    code, out = run_script(script, capsys)
    assert code == 0 and out["applied"] is False and out["import"]["create"] == 9 and written() == (0, 0, 0)
    assert out["documents"] == {"HAUD": 1, "LAHOM": 1}
    assert run_script(script, capsys, "--apply")[1]["error"] == "ACTOR_REQUIRED"
    assert run_script(script, capsys, "--apply", "--actor", "im_staff")[1]["error"] == "ACTOR_NOT_ADMIN"
    assert written() == (0, 0, 0)
    code, out = run_script(script, capsys, "--apply", "--actor", "im_admin")
    assert code == 0 and out["applied"] is True and [c["equal"] for c in out["compare"]] == [True, True]
    code, out = run_script(script, capsys, "--compare", "--brand", "HAUD")
    assert code == 0 and out["compare"][0]["brand"] == "HAUD" and out["compare"][0]["equal"] is True


@pytest.mark.parametrize("environment", ["production", "unknown-remote"])
def test_script_refuses_to_write_outside_local_and_staging_without_owner_approval(app, capsys, monkeypatch,
                                                                                  environment):
    script = load_script()
    monkeypatch.setattr(script, "resolve_environment", lambda: environment)
    admin = person(db_session, "im_admin")
    store_docs(admin, docs())
    code, out = run_script(script, capsys, "--apply", "--actor", "im_admin")
    assert (code, out["error"]) == (1, "OWNER_APPROVAL_REQUIRED") and written() == (0, 0, 0)
    code, out = run_script(script, capsys, "--apply", "--actor", "im_admin", "--i-have-owner-approval")
    assert code == 0 and out["applied"] is True
