"""master brain 저장 · 반영 동작(설계서 2026-11-02-haud-master-brain 4 ~ 7.5 · D97) — 허용 짝 · 지금 판 하나 · 기준 판 충돌 ·
사장님 몫 권한 · 은퇴 · 지우기 · 되돌리기 제안 · 글 관문 · 판 번호 · 마이그레이션.

합성 항목 · 합성 계정만 쓴다(금액 · 손님 글 · 직원 이름 없음).
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, func, select
from sqlalchemy.exc import IntegrityError

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject, BrainRelease
from foms.services.brain import constants as c
from foms.services.brain.apply import apply_change, reject_change
from foms.services.brain.errors import (
    BrainConflictError, BrainGateError, BrainPermissionError, BrainShapeError, BrainTargetError,
)
from foms.services.brain.proposals import (
    Proposer, propose_create, propose_delete, propose_link, propose_retire, propose_rollback, propose_update,
)
from foms.services.brain.releases import release_number
from foms.services.brain.store import current_object
from models import SecurityLog
from tests.support.brain_support import NOW, REASON, create, link, person, values

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "brain_00_master_brain_tables.py"


def rows(key):
    return db_session.execute(select(BrainObject).where(BrainObject.item_key == key)
                              .order_by(BrainObject.version)).scalars().all()


def current_count(key):
    return db_session.scalar(select(func.count()).select_from(BrainObject).where(
        BrainObject.item_key == key, BrainObject.superseded_at.is_(None)))


# ── 허용 짝 ──────────────────────────────────────────────────────────────
def test_allowed_pairs_follow_the_spec_table():
    assert c.link_allowed("build_rule", "applies_to", "product_line")
    assert c.link_allowed("part_kind", "applies_to", "product_line")  # 8절 — 어느 제품이 어느 조각을
    assert c.link_allowed("price_rule", "value_from", c.EXT_CALCULATOR)
    assert c.link_allowed("owner_decision", "supersedes", "policy")
    assert c.link_allowed("case", "evidence_of", "template")
    assert not c.link_allowed("product_line", "applies_to", "build_rule")  # 방향이 거꾸로
    assert not c.link_allowed("template", "supersedes", "policy")  # 앞 항목을 대체하는 것은 사장님 결정만
    assert not c.link_allowed("case", "evidence_of", "case")  # 관찰은 정체 항목의 근거로만
    assert not any(c.link_allowed(f, "caused_by", t) for f in c.TYPES for t in c.TYPES)  # 판 3 전 — 짝 0
    assert set(c.ALLOWED_LINKS) == set(c.LINK_KINDS) and len(c.LINK_KINDS) == 9
    assert all(set(layers) <= set(c.LAYERS) for layers in c.TYPE_LAYERS.values())
    assert set(c.TYPE_LAYERS) == set(c.TYPES) == set(c.TYPE_GRADES)


def test_link_outside_the_allowed_pairs_is_refused(app):
    admin = person(db_session, "br_admin")
    create(db_session, admin, "common/door", item_type="product_line")
    create(db_session, admin, "common/fit", item_type="build_rule")
    with pytest.raises(BrainTargetError):
        propose_link(db_session, op="link_add", kind="applies_to", from_key="common/door", to_key="common/fit",
                     reason=REASON, proposer=Proposer.user(admin.id))
    with pytest.raises(BrainTargetError):  # 없는 끝
        propose_link(db_session, op="link_add", kind="applies_to", from_key="common/fit", to_key="common/none",
                     reason=REASON, proposer=Proposer.user(admin.id))
    link(db_session, admin, "applies_to", "common/fit", "common/door")
    link(db_session, admin, "value_from", "common/door", "calc:product/7")  # 바깥 정본 자리
    assert db_session.scalar(select(func.count()).select_from(BrainLink).where(
        BrainLink.superseded_at.is_(None))) == 2


def test_types_and_layers_are_checked_on_create(app):
    admin = person(db_session, "br_admin")
    with pytest.raises(BrainShapeError):  # 상담 유형을 공통 층에
        create(db_session, admin, "common/tpl", item_type="situation", layer="common")
    with pytest.raises(BrainShapeError):  # 코드에 없는 유형
        create(db_session, admin, "common/x", item_type="widget")
    with pytest.raises(BrainShapeError):
        create(db_session, admin, "common/y", visibility="team:NOPE")
    assert db_session.scalar(select(func.count()).select_from(BrainObject)) == 0


# ── 지금 판은 하나 ────────────────────────────────────────────────────────
def _raw(key, version, superseded=None):
    return BrainObject(item_key=key, version=version, brand="COMMON", layer="common", item_type="term", name="합성",
                       status="active", confidence="confirmed", visibility="all", created_by="user:1",
                       recorded_at=NOW, superseded_at=superseded)


def test_partial_unique_index_allows_one_current_version_per_key(app):
    db_session.add_all([_raw("common/term", 1, superseded=NOW), _raw("common/term", 2)])  # 대조군: 지난 판 + 지금 판
    db_session.commit()
    db_session.add(_raw("common/term", 3))  # 지금 판 둘째
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert current_count("common/term") == 1


def test_update_appends_a_version_and_closes_the_old_one(app):
    admin = person(db_session, "br_admin")
    first = create(db_session, admin, "common/door")
    change = propose_update(db_session, key="common/door", base_version=1, after={"text": "합성 새 설명"},
                            reason=REASON, proposer=Proposer.user(admin.id), known="")
    assert change.fields == {"text": {"before": "합성 설명 door", "after": "합성 새 설명"}}
    result = apply_change(db_session, change.id, actor=admin, now=NOW + datetime.timedelta(minutes=5))
    db_session.commit()
    history = rows("common/door")
    assert [r.version for r in history] == [1, 2] and result.version == 2
    assert history[0].id == first.id and history[0].superseded_at is not None and history[1].superseded_at is None
    assert history[1].human_approver_id == admin.id and history[1].change_id == change.id
    assert current_count("common/door") == 1
    stored = db_session.get(BrainChange, change.id)
    assert (stored.status, stored.decided_by, stored.result_version) == ("applied", admin.id, 2)


# ── 기준 판 충돌 ──────────────────────────────────────────────────────────
def test_second_proposal_on_the_same_base_is_refused_after_the_first_applies(app):
    admin = person(db_session, "br_admin")
    create(db_session, admin, "common/door")
    one = propose_update(db_session, key="common/door", base_version=1, after={"text": "합성 하나"}, reason=REASON,
                         proposer=Proposer.user(admin.id), known="")
    two = propose_update(db_session, key="common/door", base_version=1, after={"text": "합성 둘"}, reason=REASON,
                         proposer=Proposer.user(admin.id), known="")
    apply_change(db_session, one.id, actor=admin, now=NOW)
    with pytest.raises(BrainConflictError) as caught:
        apply_change(db_session, two.id, actor=admin, now=NOW)
    assert caught.value.current_version == 2
    db_session.commit()
    assert [r.version for r in rows("common/door")] == [1, 2]
    assert current_object(db_session, "common/door").text == "합성 하나"
    assert db_session.get(BrainChange, two.id).status == "open"  # 제안은 열린 채(다시 만들기)
    with pytest.raises(BrainConflictError):  # 지금 판이 아닌 기준으로는 제안도 못 만든다
        propose_update(db_session, key="common/door", base_version=1, after={"text": "합성 셋"}, reason=REASON,
                       proposer=Proposer.user(admin.id), known="")


# ── 권한 ─────────────────────────────────────────────────────────────────
def _proposal(actor, key, item_type, layer, **vals):
    return propose_create(db_session, key=key, brand="LAHOM", layer=layer, item_type=item_type,
                          values=values(key.split("/")[-1], **vals), reason=REASON, proposer=Proposer.user(actor.id),
                          known="")


def test_owner_only_types_and_common_retire_need_admin(app):
    admin = person(db_session, "br_admin")
    cs_manager = person(db_session, "br_cs_mgr", role="MANAGER", team="CS")
    drawing_manager = person(db_session, "br_dr_mgr", role="MANAGER", team="DRAWING")
    staff = person(db_session, "br_staff", role="STAFF", team="CS")
    template = _proposal(cs_manager, "lahom/tpl", "template", "cs",
                         payload={"doc_id": "tpl", "intents": ["hours"], "approved_by": "합성", "approved_at": "2026-10-20"})
    price = _proposal(cs_manager, "lahom/price", "price_rule", "common", checked_at="2026-10-20",
                      payload={"doc_id": "price", "approved_by": "합성", "approved_at": "2026-10-20"})
    for actor in (staff, drawing_manager):  # 같은 층 승인자가 아니다
        with pytest.raises(BrainPermissionError):
            apply_change(db_session, template.id, actor=actor, now=NOW)
    apply_change(db_session, template.id, actor=cs_manager, now=NOW)  # 상담 층 승인자(CS 팀 MANAGER)
    with pytest.raises(BrainPermissionError):  # 가격 규칙은 사장님 몫
        apply_change(db_session, price.id, actor=cs_manager, now=NOW)
    apply_change(db_session, price.id, actor=admin, now=NOW)
    fact = create(db_session, admin, "common/fact", item_type="term")
    retire = propose_retire(db_session, key="common/fact", base_version=fact.version, reason=REASON,
                            proposer=Proposer.user(cs_manager.id))
    with pytest.raises(BrainPermissionError):  # 공통 바탕 은퇴는 사장님 몫
        apply_change(db_session, retire.id, actor=cs_manager, now=NOW)
    db_session.commit()
    assert current_object(db_session, "lahom/tpl").human_approver_id == cs_manager.id
    assert current_object(db_session, "lahom/price").human_approver_id == admin.id
    assert current_object(db_session, "common/fact").status == "active"


def test_agents_inactive_accounts_and_partners_cannot_apply(app):
    admin = person(db_session, "br_admin")
    agent = person(db_session, "ai-brain-agent", role="VIEWER", active=False)  # 시스템 계정 꼴(로그인 못 함)
    off_admin = person(db_session, "br_off", role="ADMIN", active=False)
    partner = person(db_session, "br_partner", role="PARTNER", partner_org_id=99)
    change = _proposal(admin, "lahom/sit", "situation", "cs")
    for actor in (agent, off_admin, partner, None):
        with pytest.raises(BrainPermissionError):
            apply_change(db_session, change.id, actor=actor, now=NOW)
    assert apply_change(db_session, change.id, actor=admin, now=NOW).version == 1


# ── 은퇴 · 지우기 · 되돌리기 · 거절 ───────────────────────────────────────
def test_retire_goes_through_the_apply_action_and_keeps_history(app):
    admin = person(db_session, "br_admin")
    create(db_session, admin, "common/door")
    change = propose_retire(db_session, key="common/door", base_version=1, reason=REASON,
                            proposer=Proposer.agent_named("cs_agent"))
    assert change.grade == c.GRADE_B and change.status == "open"
    assert current_object(db_session, "common/door").status == "active"  # 제안만으로는 아무것도 안 바뀐다
    apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    assert [(r.version, r.status) for r in rows("common/door")] == [(1, "active"), (2, "retired")]
    with pytest.raises(BrainTargetError):  # 이미 은퇴
        propose_retire(db_session, key="common/door", base_version=2, reason=REASON, proposer=Proposer.user(admin.id))


def test_delete_closes_the_item_and_its_links_but_keeps_history(app):
    admin = person(db_session, "br_admin")
    create(db_session, admin, "common/door")
    create(db_session, admin, "common/fit", item_type="build_rule")
    link(db_session, admin, "applies_to", "common/fit", "common/door")
    change = propose_delete(db_session, key="common/door", base_version=1, reason=REASON,
                            proposer=Proposer.user(admin.id))
    result = apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    assert result.version is None and current_object(db_session, "common/door") is None
    assert len(rows("common/door")) == 1  # 이력은 남는다
    assert db_session.scalar(select(func.count()).select_from(BrainLink).where(BrainLink.superseded_at.is_(None))) == 0


def test_single_item_rollback_is_the_old_value_as_a_new_proposal(app):
    admin = person(db_session, "br_admin")
    create(db_session, admin, "common/door")
    first = propose_update(db_session, key="common/door", base_version=1, after={"text": "합성 바뀜", "name": "문짝"},
                           reason=REASON, proposer=Proposer.user(admin.id), known="")
    apply_change(db_session, first.id, actor=admin, now=NOW)
    back = propose_rollback(db_session, key="common/door", to_version=1, reason=REASON,
                            proposer=Proposer.user(admin.id))
    assert (back.op, back.status, back.base_version, back.rollback_of_version) == ("update", "open", 2, 1)
    assert set(back.fields) == {"name", "text"}
    assert current_object(db_session, "common/door").version == 2  # 되돌리기도 반영 전에는 그대로
    apply_change(db_session, back.id, actor=admin, now=NOW)
    db_session.commit()
    latest = current_object(db_session, "common/door")
    assert (latest.version, latest.name, latest.text) == (3, "door", "합성 설명 door")


def test_reject_records_the_reason_code(app):
    admin = person(db_session, "br_admin")
    change = _proposal(admin, "lahom/sit", "situation", "cs")
    with pytest.raises(BrainShapeError):
        reject_change(db_session, change.id, actor=admin, code="because")
    reject_change(db_session, change.id, actor=admin, code="one_customer", now=NOW)
    db_session.commit()
    stored = db_session.get(BrainChange, change.id)
    assert (stored.status, stored.reject_code, stored.decided_by) == ("rejected", "one_customer", admin.id)
    with pytest.raises(BrainTargetError):  # 닫힌 제안은 반영하지 않는다
        apply_change(db_session, change.id, actor=admin, now=NOW)
    assert db_session.scalar(select(func.count()).select_from(SecurityLog).where(
        SecurityLog.action == "BRAIN_REJECT")) == 1


# ── 글 관문 ──────────────────────────────────────────────────────────────
def test_agent_proposals_must_pass_the_text_gates(app):
    person(db_session, "br_admin")
    agent = Proposer.agent_named("cs_agent")
    hanja = "합성 " + chr(0x6728) + " 설명"  # 한자 한 글자
    for text in (hanja, "합성 길이 35 넘음"):  # 승인 지식에 없는 숫자
        with pytest.raises(BrainGateError):
            propose_create(db_session, key="lahom/sit", brand="LAHOM", layer="cs", item_type="situation",
                           values=values("sit", text=text), reason=REASON, proposer=agent, known="합성 길이 20")
    ok = propose_create(db_session, key="lahom/sit", brand="LAHOM", layer="cs", item_type="situation",
                        values=values("sit", text="합성 길이 20 안쪽"), reason=REASON, proposer=agent,
                        known="합성 길이 20")
    assert ok.gates["numbers"] == "pass" and ok.gates["hanja"] == "pass" and ok.gates["mask"] == "pass"
    person_made = propose_create(db_session, key="lahom/sit2", brand="LAHOM", layer="cs", item_type="situation",
                                 values=values("sit2", text=hanja), reason=REASON, proposer=Proposer.user(1), known="")
    assert person_made.gates["hanja"] == "fail"  # 사람 제안은 남기고 승인자가 본다


# ── 판 번호 ──────────────────────────────────────────────────────────────
def test_releases_import_zero_then_one_number_per_day(app):
    day = datetime.date(2026, 11, 2)
    assert release_number(db_session, day=day, as_import=True) == 0
    assert release_number(db_session, day=day, as_import=False) == 1
    admin = person(db_session, "br_admin")
    create(db_session, admin, "common/a")
    create(db_session, admin, "lahom/b", item_type="situation", layer="cs", brand="LAHOM")
    create(db_session, admin, "common/c", now=NOW + datetime.timedelta(days=1))
    db_session.commit()
    got = db_session.execute(select(BrainRelease.number, BrainRelease.layer, BrainRelease.day, BrainRelease.counts)
                             .order_by(BrainRelease.number, BrainRelease.layer)).all()
    assert [(n, layer, d.isoformat(), counts) for n, layer, d, counts in got] == [
        (1, "common", "2026-11-02", {"create": 1}), (1, "cs", "2026-11-02", {"create": 1}),
        (2, "common", "2026-11-03", {"create": 1})]
    assert current_object(db_session, "common/c").release_no == 2


# ── 마이그레이션 ─────────────────────────────────────────────────────────
def test_brain_00_matches_the_models_and_is_the_single_head():
    spec = importlib.util.spec_from_file_location("brain_00_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.down_revision) == ("brain_00", "notice_01")
    source = MIGRATION.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source
    assert module.OBJECT_STATUSES == c.OBJECT_STATUSES and module.CONFIDENCES == c.CONFIDENCES
    assert module.LAYERS == c.LAYERS and module.CHANGE_OPS == (*c.OBJECT_OPS, *c.LINK_OPS)
    from db import Base
    for name, columns in module.COLUMNS.items():
        table = Base.metadata.tables[name]
        assert [col.name for col in table.columns] == ["id", *(n for n, *_ in columns)], name
        for col_name, type_, nullable, _default in columns:
            column = table.c[col_name]
            assert column.nullable is nullable, (name, col_name)
            assert getattr(column.type, "length", None) == getattr(type_, "length", None), (name, col_name)
        checks = {k.name: str(k.sqltext) for k in table.constraints if isinstance(k, CheckConstraint)}
        assert checks == {n: module.in_check(col, vals) for n, col, vals in module.CHECKS[name]}, name
        indexes = {i.name: i for i in table.indexes if not i.name.endswith("_trgm")}
        assert set(indexes) == {n for n, *_ in module.INDEXES[name]}, name
        for index_name, cols, unique, current_only in module.INDEXES[name]:
            index = indexes[index_name]
            assert tuple(col.name for col in index.columns) == cols and index.unique is unique, index_name
            where = index.dialect_options["postgresql"]["where"]
            assert (str(where) if where is not None else None) == (module.CURRENT if current_only else None)
    trgm = {i.name for i in Base.metadata.tables["brain_objects"].indexes if i.name.endswith("_trgm")}
    assert trgm == {n for n, _ in module.TRGM_INDEXES}
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert script.get_heads() == ["brain_00"]
