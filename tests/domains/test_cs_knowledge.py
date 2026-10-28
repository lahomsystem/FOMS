"""기준 답 · 지식 저장(플랜 C2-1) — 승인 항목만 재료 · 틀린 문서 거절 · 버전 충돌 · 되돌리기 · 수정 기록 · 브랜드 나눔 ·
관리자 스크립트(모의 실행은 쓰기 0 · 운영은 사장님 승인 표시 없이 쓰기 0).

손으로 꾸민 합성 항목만 쓴다 — 실제 기준 답 · 가격 · 정책 · 사람 이름이 없고, 금액은 일부러 가짜('1원')다. 글 표지
:data:`MARK` 는 오류 · 요약 · 감사 줄 · 스크립트 출력 어디에도 나오면 안 된다(글은 싣지 않는다).
"""

from __future__ import annotations

import copy
import datetime
import importlib.util
import json
import logging
import pathlib

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.cs_agent import knowledge as kn
from foms.services.cs_agent import knowledge_doc as kd
from models import SecurityLog, SystemSetting, SystemSettingReceipt, User

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "tools" / "ops" / "cs_agent_knowledge.py"
MARK = "보라합성표지"


def item(item_id, *, kind="template", status="approved", intents=("hours",), text=None, **extra):
    row = {"id": item_id, "kind": kind, "intents": list(intents), "status": status,
           "text": text or f"{MARK} 합성 안내 {item_id}"}
    if status == "approved":
        row.update(approved_by="synthetic-owner", approved_at="2026-10-20")
    row.update(extra)
    return row


def document(brand="LAHOM", *items):
    return {"schema_version": 1, "brand": brand, "items": list(items)}


def mixed_doc(brand="LAHOM"):
    return document(
        brand,
        item("hours-day"),
        item("hours-draft", status="draft"),
        item("hours-old", status="retired", approved_by="synthetic-owner", approved_at="2026-10-01"),
        item("booking-draft", status="draft", intents=("booking",)),
        item("fact-size", kind="fact", intents=()),
        item("price-unit", kind="price_rule", intents=(), text="합성 규칙: 한 칸 1원(가짜 값)", checked_at="2026-10-20",
             source="synthetic/rules.md"),
        item("owner-rule", kind="owner_decision", status="draft", intents=()),
    )


def admin(username="kn_admin", *, role="ADMIN", active=True):
    user = User(username=username, password=generate_password_hash("pw"), name="합성관리자", role=role,
                is_active=active)
    db_session.add(user)
    db_session.commit()
    return int(user.id)


def save(doc, *, brand="LAHOM", actor, expected):
    result = kn.save_document(db_session, brand, doc, actor_user_id=actor, expected_version=expected)
    db_session.commit()
    return result


def written():
    """지식 키의 (설정 줄, 수정 기록, 감사 줄) 수."""
    keys = [kn.knowledge_key(brand) for brand in sorted(kn.KNOWN_BRANDS)]
    return (db_session.query(SystemSetting).filter(SystemSetting.setting_key.in_(keys)).count(),
            db_session.query(SystemSettingReceipt).filter(SystemSettingReceipt.policy_id == kn.POLICY_ID).count(),
            db_session.query(SecurityLog).filter(SecurityLog.message.like("CS_AGENT_KNOWLEDGE_%")).count())


def ids(items):
    return [i.item_id for i in items]


# ── 승인 항목만 재료 ─────────────────────────────────────────────────────


def test_only_approved_items_become_material(app):
    save(mixed_doc(), actor=admin(), expected=0)
    material = kn.load_approved(db_session, "LAHOM")
    assert (material.version, material.problem) == (1, None)
    assert ids(material.items) == ["hours-day", "fact-size", "price-unit"]  # 초안 · 내림은 재료가 아니다
    assert ids(material.templates_for_intent("hours")) == ["hours-day"]
    assert material.templates_for_intent("booking") == ()  # 초안만 있는 의도는 자동 답 글이 없다
    assert material.template_intents() == ("hours",)  # 모델이 고를 수 있는 의도도 승인 문구가 있는 것뿐
    assert material.get("hours-draft") is None and material.get("owner-rule") is None
    assert ids(material.of_kind(kd.KIND_PRICE_RULE)) == ["price-unit"]
    assert material.get("price-unit").checked_at == "2026-10-20"
    assert kn.templates_for_intent(db_session, "LAHOM", "hours") == material.templates_for_intent("hours")
    assert MARK not in repr(material)  # 글은 repr 에 싣지 않는다(로그에 따라가지 않게)
    assert kn.load_approved(db_session, "HAUD") == kd.ApprovedKnowledge("HAUD", 0)  # 넣은 적 없는 브랜드는 재료 0


def test_validation_returns_the_canonical_shape():
    raw = document("LAHOM", item("hours-day", text=f"  {MARK}\r\n둘째 줄  ", tags=["night"]))
    canonical = kd.validate_document(raw, brand="LAHOM")
    row = canonical["items"][0]
    assert list(row) == list(kd.ITEM_FIELDS)
    assert row["text"] == f"{MARK}\n둘째 줄" and row["tags"] == ["night"] and row["checked_at"] is None
    assert kd.validate_document(canonical, brand="LAHOM") == canonical  # 정본은 다시 검사해도 그대로
    draft_price = document("LAHOM", item("price-draft", kind="price_rule", status="draft", intents=()))
    assert kd.validate_document(draft_price, brand="LAHOM")["items"][0]["checked_at"] is None  # 초안 가격은 날짜 없이 된다
    today = datetime.date(2026, 10, 28)  # 미래 날짜는 오늘(KST) + 1일까지만(시간대 여유)
    price = lambda day: document("LAHOM", item("price-a", kind="price_rule", intents=(), checked_at=day))  # noqa: E731
    assert kd.validate_document(price("2026-10-29"), brand="LAHOM", today=today)["items"][0]["checked_at"] == "2026-10-29"
    with pytest.raises(kd.KnowledgeSchemaError):
        kd.validate_document(price("2026-10-30"), brand="LAHOM", today=today)
    with pytest.raises(ValueError):
        kd.validate_document(raw, brand="NOPE")


INVALID = {
    "unknown top field": lambda d: d.update(note="x"),
    "schema version": lambda d: d.update(schema_version=2),
    "bool schema version": lambda d: d.update(schema_version=True),
    "other brand": lambda d: d.update(brand="HAUD"),
    "items not a list": lambda d: d.update(items={"a": 1}),
    "unknown item field": lambda d: d["items"][0].update(price=1),
    "bad id": lambda d: d["items"][0].update(id="Hours Day"),
    "duplicate id": lambda d: d["items"].append(copy.deepcopy(d["items"][0])),
    "unknown kind": lambda d: d["items"][0].update(kind="promo"),
    "unknown status": lambda d: d["items"][0].update(status="live"),
    "template without intent": lambda d: d["items"][0].update(intents=[]),
    "approved without approver": lambda d: d["items"][0].pop("approved_by"),
    "approved without date": lambda d: d["items"][0].pop("approved_at"),
    "impossible date": lambda d: d["items"][0].update(approved_at="2026-02-30"),
    "empty text": lambda d: d["items"][0].update(text="   "),
    "text too long": lambda d: d["items"][0].update(text="가" * (kd.MAX_TEXT_LEN + 1)),
    "uppercase intent": lambda d: d["items"][0].update(intents=["Hours"]),
    "duplicate tag": lambda d: d["items"][0].update(tags=["night", "night"]),
    "multi-line approver": lambda d: d["items"][0].update(approved_by="a\nb"),
    "approved price rule without checked date": lambda d: d["items"][0].update(kind="price_rule", intents=[]),
    "future checked date": lambda d: d["items"][0].update(kind="price_rule", intents=[], checked_at="2099-12-31"),
    "future approval date": lambda d: d["items"][0].update(approved_at="2099-12-31"),
    "date with time": lambda d: d["items"][0].update(approved_at="2026-10-20T10:00"),
}


@pytest.mark.parametrize("case", sorted(INVALID))
def test_invalid_documents_are_refused_and_nothing_is_written(app, case):
    actor = admin()
    doc = document("LAHOM", item("hours-day"), item("fact-ok", kind="fact", intents=()))
    INVALID[case](doc)
    with pytest.raises(kn.KnowledgeSchemaError) as caught:
        kn.save_document(db_session, "LAHOM", doc, actor_user_id=actor, expected_version=0)
    db_session.rollback()
    assert written() == (0, 0, 0)
    assert caught.value.problems and MARK not in str(caught.value)  # 자리 · 까닭만, 글은 싣지 않는다
    assert not any(problem.startswith("items[1]") for problem in caught.value.problems)  # 멀쩡한 항목은 탓하지 않는다


# ── 버전 · 수정 기록 · 되돌리기 ──────────────────────────────────────────


def test_version_conflict_is_refused_and_nothing_changes(app):
    actor = admin()
    save(document("LAHOM", item("hours-day")), actor=actor, expected=0)
    newer = document("LAHOM", item("hours-day"), item("photo", intents=("photo_intake",)))
    with pytest.raises(kn.KnowledgeConflictError) as caught:  # 낡은 버전으로 다시 넣기
        kn.save_document(db_session, "LAHOM", newer, actor_user_id=actor, expected_version=0)
    db_session.rollback()
    assert caught.value.current_version == 1 and written() == (1, 1, 1)
    assert ids(kn.load_approved(db_session, "LAHOM").items) == ["hours-day"]
    assert save(newer, actor=actor, expected=1).version == 2  # 음성 대조군: 맞는 버전이면 들어간다
    with pytest.raises(kn.KnowledgeNoChangeError):  # 같은 문서로 버전만 늘리지 않는다
        kn.save_document(db_session, "LAHOM", newer, actor_user_id=actor, expected_version=2)
    db_session.rollback()
    assert written() == (1, 2, 2)


def test_each_save_writes_one_history_row_and_one_audit_line(app):
    actor = admin()
    result = save(mixed_doc(), actor=actor, expected=0)
    receipt = db_session.query(SystemSettingReceipt).filter_by(policy_id=kn.POLICY_ID).one()
    assert (receipt.setting_key, receipt.actor_user_id, receipt.resulting_version) == ("cs_agent_knowledge_lahom", actor, 1)
    assert receipt.idempotency_key is None and str(receipt.read_receipt_id) == result.receipt_id
    canonical = kd.validate_document(mixed_doc(), brand="LAHOM")
    assert receipt.response_body["data"]["knowledge"] == canonical  # 그 버전 문서 전체가 기록에 남는다
    row = db_session.get(SystemSetting, "cs_agent_knowledge_lahom")
    assert row.version == 1 and row.setting_value == canonical
    log = db_session.query(SecurityLog).filter(SecurityLog.message.like("CS_AGENT_KNOWLEDGE_%")).one()
    assert log.user_id == actor and "version=1 approved=3 total=7" in log.message and MARK not in log.message
    assert result.diff.added == tuple(row["id"] for row in canonical["items"])
    assert result.diff.became_live == ("hours-day", "fact-size", "price-unit")
    # 되돌리기 이력이라 다른 영수증(24시간 · 오래된 줄 지울 색인)보다 길게 둔다(R6-17)
    assert receipt.expires_at - receipt.created_at > datetime.timedelta(days=5 * 365)
    assert MARK not in repr(kn.read_stored(db_session, "LAHOM"))  # 저장 문서는 repr 에 싣지 않는다(R6-18)


def test_first_insert_race_becomes_a_version_conflict(app, monkeypatch):
    actor = admin()
    save(document("LAHOM", item("hours-day")), actor=actor, expected=0)  # 다른 사람이 먼저 첫 버전을 넣었다
    real_get = db_session.get
    seen = {"locked": False}

    def get_before_the_other_insert(model, key, **kw):
        if kw.get("with_for_update") and not seen["locked"]:  # 잠글 때는 아직 줄이 없던 순간
            seen["locked"] = True
            return None
        return real_get(model, key, **kw)

    monkeypatch.setattr(db_session, "get", get_before_the_other_insert)
    with pytest.raises(kn.KnowledgeConflictError) as caught:
        kn.save_document(db_session, "LAHOM", document("LAHOM", item("photo", intents=("photo_intake",))),
                         actor_user_id=actor, expected_version=0)
    assert caught.value.current_version == 1 and caught.value.__cause__ is None  # SQL 값이 든 오류를 잇지 않는다
    assert caught.value.__suppress_context__
    db_session.rollback()
    assert written() == (1, 1, 1) and ids(kn.load_approved(db_session, "LAHOM").items) == ["hours-day"]


def test_rollback_restores_the_earlier_version_exactly(app):
    actor = admin()
    save(mixed_doc(), actor=actor, expected=0)
    first = kn.load_approved(db_session, "LAHOM")
    save(document("LAHOM", item("hours-day", text="합성 바뀐 안내"), item("photo", intents=("photo_intake",))),
         actor=actor, expected=1)
    assert ids(kn.load_approved(db_session, "LAHOM").items) == ["hours-day", "photo"]
    result = kn.rollback(db_session, "LAHOM", 1, actor_user_id=actor, expected_version=2)
    db_session.commit()
    assert (result.version, result.restored_from) == (3, 1)  # 버전은 되감지 않고 새 버전으로 쓴다
    stored = kn.read_stored(db_session, "LAHOM")
    assert stored.version == 3 and stored.document == kd.validate_document(mixed_doc(), brand="LAHOM")
    assert kn.load_approved(db_session, "LAHOM").items == first.items  # 글까지 그대로
    assert result.diff.removed == ("photo",) and result.diff.live_changed == ("hours-day",)
    entries = kn.history(db_session, "LAHOM")
    assert [e["version"] for e in entries] == [3, 2, 1] and entries[0]["restored_from"] == 1
    assert entries[0]["counts"] == kd.count_items(stored.document) and entries[0]["actor_user_id"] == actor
    log = db_session.query(SecurityLog).filter(SecurityLog.message.like("CS_AGENT_KNOWLEDGE_ROLLBACK%")).one()
    assert "version=3" in log.message and "restored_from=1" in log.message


def test_rollback_refuses_missing_history_the_same_document_and_other_brands(app):
    actor = admin()
    save(document("LAHOM", item("hours-day")), actor=actor, expected=0)
    with pytest.raises(kn.KnowledgeHistoryError):
        kn.rollback(db_session, "LAHOM", 7, actor_user_id=actor, expected_version=1)
    with pytest.raises(kn.KnowledgeNoChangeError):  # 지금 버전으로 되돌리기
        kn.rollback(db_session, "LAHOM", 1, actor_user_id=actor, expected_version=1)
    with pytest.raises(kn.KnowledgeHistoryError):  # 라홈의 버전 1 기록을 하우드로 되돌리지 않는다
        kn.rollback(db_session, "HAUD", 1, actor_user_id=actor, expected_version=0)
    db_session.rollback()
    assert written() == (1, 1, 1)


# ── 브랜드 나눔 · 망가진 값 ──────────────────────────────────────────────


def test_brands_never_mix(app, caplog):
    actor = admin()
    save(document("LAHOM", item("hours-lahom")), actor=actor, expected=0)
    save(document("HAUD", item("hours-haud")), brand="HAUD", actor=actor, expected=0)
    assert ids(kn.templates_for_intent(db_session, "HAUD", "hours")) == ["hours-haud"]
    assert ids(kn.templates_for_intent(db_session, "LAHOM", "hours")) == ["hours-lahom"]
    with pytest.raises(kn.KnowledgeSchemaError):  # 라홈 문서를 하우드 키로 넣지 않는다
        kn.save_document(db_session, "HAUD", document("LAHOM", item("x")), actor_user_id=actor, expected_version=1)
    db_session.rollback()
    planted = copy.deepcopy(db_session.get(SystemSetting, kn.knowledge_key("LAHOM")).setting_value)
    db_session.get(SystemSetting, kn.knowledge_key("HAUD")).setting_value = planted  # 손으로 옮겨 심은 라홈 문서
    db_session.commit()
    with caplog.at_level(logging.WARNING, logger=kn.__name__):
        haud = kn.load_approved(db_session, "HAUD")
    assert haud.items == () and "brand" in haud.problem  # 재료 0 — 막는 쪽으로 닫힌다
    assert any("재료를 내지 않는다" in record.getMessage() for record in caplog.records)
    assert ids(kn.load_approved(db_session, "LAHOM").items) == ["hours-lahom"]


def test_a_corrupt_stored_value_gives_no_material_and_can_be_replaced(app, caplog):
    db_session.add(SystemSetting(setting_key=kn.knowledge_key("LAHOM"), setting_value={"items": "망가짐"}))
    db_session.commit()
    with caplog.at_level(logging.WARNING, logger=kn.__name__):
        material = kn.load_approved(db_session, "LAHOM")
    assert material.items == () and material.problem and caplog.records
    result = save(document("LAHOM", item("hours-day")), actor=admin(), expected=1)  # 고친 문서는 그 버전 위에 넣는다
    assert result.version == 2 and result.diff.added == ("hours-day",)
    db_session.get(SystemSetting, kn.knowledge_key("LAHOM")).setting_value = None
    db_session.commit()
    assert kn.load_approved(db_session, "LAHOM").items == ()


def test_diff_names_ids_and_fields_only():
    before = kd.validate_document(document("LAHOM", item("a"), item("b", status="draft"), item("c")), brand="LAHOM")
    after = kd.validate_document(document("LAHOM", item("c"), item("b"), item("a", text="합성 바뀜"),
                                          item("d", status="draft")), brand="LAHOM")
    diff = kd.diff_documents(before, after)
    assert (diff.added, diff.removed, diff.reordered) == (("d",), (), True)
    assert diff.changed == {"b": ("status", "approved_by", "approved_at"), "a": ("text",)}
    assert (diff.became_live, diff.left_live, diff.live_changed) == (("b",), (), ("a",))
    assert diff.after == {"total": 4, "kinds": {"template": {"approved": 3, "draft": 1}}}
    assert MARK not in json.dumps(diff.summary(), ensure_ascii=False)
    assert not kd.diff_documents(after, copy.deepcopy(after)).has_changes()


# ── 관리자 스크립트 ──────────────────────────────────────────────────────


def load_script():
    spec = importlib.util.spec_from_file_location("cs_agent_knowledge_ut", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(script, capsys, *argv):
    code = script.run(list(argv))
    printed = capsys.readouterr().out
    assert MARK not in printed  # 글은 화면에 내지 않는다
    return code, json.loads(printed)


def doc_file(tmp_path, doc, name="knowledge.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_script_dry_run_writes_nothing_and_prints_no_text(app, tmp_path, capsys):
    script = load_script()
    code, out = run_script(script, capsys, "--brand", "LAHOM", "--file", doc_file(tmp_path, mixed_doc()))
    assert code == 0 and out["ok"] and out["applied"] is False and out["current_version"] == 0
    assert out["diff"]["added"] == [row["id"] for row in mixed_doc()["items"]]
    assert out["diff"]["after"]["kinds"]["template"] == {"approved": 1, "draft": 2, "retired": 1}
    assert out["next"].startswith("--apply --expected-version 0") and out["owner_approval_required"] is False
    assert written() == (0, 0, 0)
    bad = doc_file(tmp_path, document("LAHOM", item("Bad Id")), "bad.json")
    code, out = run_script(script, capsys, "--brand", "LAHOM", "--file", bad)
    assert (code, out["error"]) == (1, "CS_KNOWLEDGE_SCHEMA") and out["problems"]
    broken = tmp_path / "broken.json"
    broken.write_text('{"items": [' + MARK, encoding="utf-8")
    code, out = run_script(script, capsys, "--brand", "LAHOM", "--file", str(broken))
    assert (code, out["error"]) == (1, "FILE_NOT_JSON") and written() == (0, 0, 0)


def test_script_apply_needs_a_version_and_an_active_admin(app, tmp_path, capsys):
    script = load_script()
    base = ("--brand", "LAHOM", "--file", doc_file(tmp_path, mixed_doc()), "--apply")
    assert run_script(script, capsys, *base, "--actor", "kn_admin")[1]["error"] == "EXPECTED_VERSION_REQUIRED"
    assert run_script(script, capsys, *base, "--expected-version", "0")[1]["error"] == "ACTOR_REQUIRED"
    admin("kn_staff", role="STAFF")
    admin("kn_off", active=False)
    for name in ("kn_staff", "kn_off", "kn_nobody"):
        code, out = run_script(script, capsys, *base, "--expected-version", "0", "--actor", name)
        assert (code, out["error"]) == (1, "ACTOR_NOT_ADMIN")
    assert written() == (0, 0, 0)
    admin("kn_admin")
    code, out = run_script(script, capsys, *base, "--expected-version", "0", "--actor", "kn_admin")
    assert code == 0 and out["applied"] and out["version"] == 1
    code, out = run_script(script, capsys, *base, "--expected-version", "0", "--actor", "kn_admin")
    assert (code, out["error"], out["current_version"]) == (1, "REVISION_CONFLICT", 1)  # 같은 명령 두 번은 버전이 막는다
    assert written() == (1, 1, 1)


@pytest.mark.parametrize("environment", ["production", "unknown-remote", "preview"])
def test_script_refuses_to_write_outside_local_and_staging_without_owner_approval(
        app, tmp_path, capsys, monkeypatch, environment):
    script = load_script()
    monkeypatch.setattr(script, "resolve_environment", lambda: environment)
    admin("kn_admin")
    base = ("--brand", "LAHOM", "--file", doc_file(tmp_path, mixed_doc()))
    code, out = run_script(script, capsys, *base)  # 모의 실행은 읽기만 — 운영에서도 된다
    assert code == 0 and out["environment"] == environment and out["next"].endswith("--i-have-owner-approval")
    apply = ("--apply", "--expected-version", "0", "--actor", "kn_admin")
    code, out = run_script(script, capsys, *base, *apply)
    assert (code, out["error"]) == (1, "OWNER_APPROVAL_REQUIRED") and written() == (0, 0, 0)
    code, out = run_script(script, capsys, *base, *apply, "--i-have-owner-approval")
    assert code == 0 and out["applied"] and written() == (1, 1, 1)


def test_environment_detection_treats_a_remote_database_from_a_pc_as_unknown(app, tmp_path, capsys, monkeypatch):
    script = load_script()
    remote = "postgresql+psycopg://synthetic@db.example.test:5432/foms"
    detect = script.target_environment
    assert detect("local", remote) == "unknown-remote"  # 바깥 문으로 붙은 PC — 어느 서버인지 모른다
    assert detect("staging", remote) == "unknown-remote"  # PC 에 남은 FOMS_ENV 만으로는 풀지 않는다
    assert detect("local", "sqlite:///:memory:") == "local"
    assert detect("local", "postgresql+psycopg://synthetic@localhost/foms") == "unknown-remote"  # 운영 DB 로 판 굴일 수 있다
    assert detect("local", "postgresql+psycopg:///foms") == "unknown-remote"  # 집 이름 빈 주소(PGHOST 로 붙는다)
    assert detect("staging", remote, "FOMS-DEV") == "unknown-remote"  # 서비스 표지 없이 PC 에 남은 프로젝트 이름
    assert detect("staging", remote, "FOMS-DEV", "synthetic-service") == "staging"  # 스테이징 컨테이너 · railway run
    assert detect("staging", remote, "FOMS-PRODUCTION", "synthetic-service") == "production"  # 운영은 늘 운영
    assert detect("production", "sqlite:///:memory:") == "production"
    assert detect("production", remote) == "production"
    admin("kn_admin")
    doc = doc_file(tmp_path, mixed_doc())
    apply = ("--brand", "LAHOM", "--file", doc, "--apply", "--expected-version", "0", "--actor", "kn_admin")
    monkeypatch.setattr(script, "resolve_environment", lambda: "staging")
    monkeypatch.delenv("RAILWAY_PROJECT_NAME", raising=False)
    monkeypatch.delenv("RAILWAY_SERVICE_ID", raising=False)
    monkeypatch.setattr(script, "DB_URL", remote)  # PC + 바깥 DB + FOMS_ENV=staging — 표시 없이는 쓰지 않는다
    code, out = run_script(script, capsys, *apply)
    assert (code, out["environment"], out["error"]) == (1, "unknown-remote", "OWNER_APPROVAL_REQUIRED")
    assert written() == (0, 0, 0)
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", "FOMS-DEV")  # 프로젝트 이름만 남은 PC — 아직 막는다
    code, out = run_script(script, capsys, *apply)
    assert (code, out["environment"], out["error"]) == (1, "unknown-remote", "OWNER_APPROVAL_REQUIRED")
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "synthetic-service")  # 음성 대조군: 스테이징 컨테이너는 표시 없이 넣는다
    code, out = run_script(script, capsys, *apply)
    assert code == 0 and out["applied"] and out["owner_approval_required"] is False


def test_script_show_and_rollback_round_trip(app, tmp_path, capsys):
    script = load_script()
    actor = admin("kn_admin")
    save(mixed_doc(), actor=actor, expected=0)
    save(document("LAHOM", item("hours-day")), actor=actor, expected=1)
    code, out = run_script(script, capsys, "--brand", "LAHOM", "--show")
    assert code == 0 and out["version"] == 2 and [h["version"] for h in out["history"]] == [2, 1]
    assert out["counts"] == {"total": 1, "kinds": {"template": {"approved": 1}}}
    code, out = run_script(script, capsys, "--brand", "LAHOM", "--rollback", "1")
    assert code == 0 and out["applied"] is False and out["diff"]["added"] == [r["id"] for r in mixed_doc()["items"][1:]]
    assert written() == (1, 2, 2)  # 되돌리기 모의 실행도 쓰기 0
    code, out = run_script(script, capsys, "--brand", "LAHOM", "--rollback", "1", "--apply", "--expected-version", "2",
                           "--actor", "kn_admin")
    assert code == 0 and out["version"] == 3
    assert kn.read_stored(db_session, "LAHOM").document == kd.validate_document(mixed_doc(), brand="LAHOM")
    code, out = run_script(script, capsys, "--brand", "LAHOM", "--rollback", "9")
    assert (code, out["error"]) == (1, "CS_KNOWLEDGE_HISTORY")
    code, out = run_script(script, capsys, "--brand", "LAHOM", "--show", "--apply")
    assert (code, out["error"]) == (1, "APPLY_NEEDS_CHANGE")
