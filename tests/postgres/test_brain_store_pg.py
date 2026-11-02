"""master brain 표 PostgreSQL 레인 — 부분 유일 색인 · pg_trgm 색인과 비슷함 찾기 · 재귀 CTE 이웃 · 반영 줄 잠금 · 옮기기 왕복.

SQLite 메인 레인은 DB 전체 잠금이고 pg_trgm 이 없다. 여기서는 진짜 PostgreSQL 에서 ① '지금 판 하나' 부분 유일 색인이
막는지(지난 판은 대조군) ② 이름 · 글 trgm 색인이 지금 줄만 담아 있는지와 ``%`` 비슷함 찾기 ③ 재귀 CTE 이웃이 걸음 · 범위대로
도는지 ④ 같은 기준 판 제안 둘을 두 세션이 겹쳐 반영하면 뒤 세션이 줄 잠금에서 기다렸다가 기준 판 충돌로 멈추는지 ⑤ 지식
문서(JSONB)를 옮겨 다시 만든 문서가 같은지를 본다. ``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다(레인 규칙은
``tests/postgres/conftest.py``). 합성 항목만 — 금액 · 손님 글 · 직원 이름 없음.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foms.persistence.brain.models import BrainObject
from foms.services.brain import doc_bridge, doc_import
from foms.services.brain.apply import apply_change
from foms.services.brain.errors import BrainConflictError
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.read import neighbours, search
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from foms.services.cs_agent import knowledge as kn
from models import User
from tests.support.brain_support import NOW, create, link, person


def _raw(key, version, superseded=None, *, name="term", body=None):
    return BrainObject(item_key=key, version=version, brand="COMMON", layer="common", item_type="term", name=name,
                       text=body, status="active", confidence="confirmed", visibility="all", created_by="user:1",
                       recorded_at=NOW, superseded_at=superseded)


def test_partial_unique_index_allows_one_current_version_per_key(pg_session):
    pg_session.add_all([_raw("common/term", 1, superseded=NOW), _raw("common/term", 2)])  # 대조군: 지난 판 + 지금 판
    pg_session.flush()
    savepoint = pg_session.begin_nested()
    pg_session.add(_raw("common/term", 3))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    savepoint.rollback()
    defs = dict(pg_session.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'brain_objects'")).all())
    assert "WHERE (superseded_at IS NULL)" in defs["uq_brain_objects_current_key"]
    assert "WHERE" not in defs["uq_brain_objects_key_version"]


def test_trgm_indexes_and_similarity_search(pg_session):
    defs = dict(pg_session.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'brain_objects'")).all())
    for name, column in (("ix_brain_objects_name_trgm", "name"), ("ix_brain_objects_text_trgm", "text")):
        assert f"gin ({column} gin_trgm_ops) WHERE (superseded_at IS NULL)" in defs[name]
    admin = person(pg_session, "pg_brain_admin")
    create(pg_session, admin, "common/door", name="hinged door panel")
    create(pg_session, admin, "common/shelf", name="open shelf unit", visibility="admin")
    create(pg_session, admin, "common/rail", name="ceiling rail")
    staff = viewer_of(person(pg_session, "pg_brain_staff", role="STAFF", team="CS"))
    typo = search(pg_session, viewer_of(admin), "hinged door panle")  # 부분 일치는 아니고 비슷함(%)으로만 닿는다
    assert [i["key"] for i in typo["items"]] == ["common/door"] and typo["total"] == 1
    assert search(pg_session, viewer_of(admin), "shelf")["total"] == 1  # 대조군: 관리 항목은 ADMIN 에게 있다
    assert search(pg_session, staff, "shelf") == {"items": [], "total": 0}


def test_search_predicates_can_use_the_partial_trgm_indexes(pg_session):
    """찾기 술어(지금 줄 + 이름 · 글 ILIKE · 이름 비슷함)가 trgm 색인을 탈 수 있는지 — 지금 줄을 수천 개 채워 통계를 낸 뒤 순차 · 단순
    색인 읽기를 끄고 계획을 본다(빈 표면 플래너가 아무 색인이나 통째로 읽는다)."""
    rows = [{"item_key": f"common/term-{n}", "version": 1, "brand": "COMMON", "layer": "common", "item_type": "term",
             "name": f"synthetic shelf {n}", "text": f"synthetic rail note {n}", "status": "active",
             "confidence": "confirmed", "visibility": "all", "created_by": "user:1", "recorded_at": NOW}
            for n in range(5000)]
    pg_session.execute(insert(BrainObject), rows)
    # 새 줄은 GIN 대기 목록에 쌓여 있어 비용이 부풀어 보인다(운영은 autovacuum 이 비운다) — 비우고 통계를 낸다
    pg_session.execute(text("SELECT gin_clean_pending_list('ix_brain_objects_name_trgm'), "
                            "gin_clean_pending_list('ix_brain_objects_text_trgm')"))
    pg_session.execute(text("ANALYZE brain_objects"))
    pg_session.execute(text("SET LOCAL enable_seqscan = off"))
    pg_session.execute(text("SET LOCAL enable_indexscan = off"))
    plan = " | ".join(pg_session.execute(text(
        "EXPLAIN SELECT id FROM brain_objects WHERE superseded_at IS NULL "
        "AND (name ILIKE :p OR text ILIKE :p OR name % :q)"), {"p": "%door%", "q": "door"}).scalars())
    assert "ix_brain_objects_name_trgm" in plan and "ix_brain_objects_text_trgm" in plan
    assert "Seq Scan" not in plan


def test_neighbours_recursive_cte_on_postgres(pg_session):
    admin = person(pg_session, "pg_brain_admin")
    create(pg_session, admin, "common/door")
    create(pg_session, admin, "common/slide")
    create(pg_session, admin, "common/fit", item_type="build_rule")
    create(pg_session, admin, "drawing/rule", item_type="drawing_rule", layer="drawing", visibility="team:DRAWING")
    link(pg_session, admin, "applies_to", "common/fit", "common/door")
    link(pg_session, admin, "applies_to", "drawing/rule", "common/door")
    link(pg_session, admin, "applies_to", "drawing/rule", "common/slide")
    link(pg_session, admin, "value_from", "common/door", "calc:product/1")
    got = neighbours(pg_session, viewer_of(admin), "common/slide", depth=2)
    assert [(i["key"], i["depth"]) for i in got["items"]] == [("drawing/rule", 1), ("common/door", 2)]
    assert got["total"] == 2 and got["counts"] == {"applies_to": 2}  # 맞춤 규칙은 3걸음 · 계산기 자리는 항목 아님
    assert neighbours(pg_session, viewer_of(admin), "common/door", depth=1)["total"] == 2
    cs = viewer_of(person(pg_session, "pg_brain_cs", role="STAFF", team="CS"))
    assert neighbours(pg_session, cs, "common/slide", depth=2)["total"] == 0  # 숨긴 항목을 지나가지 않는다


def test_overlapping_applies_on_the_same_base_wait_and_then_conflict(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    with make_session() as setup:
        admin = person(setup, "pg_brain_lock_admin")
        create(setup, admin, "common/door")
        one = propose_update(setup, key="common/door", base_version=1, after={"text": "first"}, reason="pg",
                             proposer=Proposer.user(admin.id), known="")
        two = propose_update(setup, key="common/door", base_version=1, after={"text": "second"}, reason="pg",
                             proposer=Proposer.user(admin.id), known="")
        setup.commit()
        admin_id, one_id, two_id = admin.id, one.id, two.id
    holder = make_session()
    holder_admin = holder.get(User, admin_id)
    apply_change(holder, one_id, actor=holder_admin, now=NOW)  # 앞 세션이 지금 줄을 잠근 채 커밋 전
    outcome: dict = {}

    def second() -> None:
        with make_session() as session:
            try:
                apply_change(session, two_id, actor=session.get(User, admin_id), now=NOW)
                session.commit()
                outcome["result"] = "applied"
            except BrainConflictError as exc:
                session.rollback()
                outcome["result"] = ("conflict", exc.current_version)

    worker = threading.Thread(target=second)
    try:
        worker.start()
        time.sleep(0.5)
        waited = worker.is_alive()  # 뒤 세션은 줄 잠금에서 기다린다
        holder.commit()
    finally:
        holder.close()  # 단언이 먼저 떨어져도 잠금을 풀어 뒤 세션이 멈춰 있지 않게
        worker.join(timeout=10)
    assert waited and outcome["result"] == ("conflict", 2)
    with make_session() as check:
        rows = check.execute(select(BrainObject.version, BrainObject.text, BrainObject.superseded_at.is_(None))
                             .where(BrainObject.item_key == "common/door").order_by(BrainObject.version)).all()
        assert rows == [(1, "합성 설명 door", False), (2, "first", True)]


def test_import_round_trip_on_jsonb(pg_session):
    admin = person(pg_session, "pg_brain_import_admin")
    shared = {"id": "shared", "kind": "template", "intents": ["hours"], "text": "synthetic shared answer",
              "status": "approved", "approved_by": "synthetic-owner", "approved_at": "2026-10-20"}
    only = {"id": "only", "kind": "fact", "intents": [], "text": "synthetic lahom fact", "status": "draft"}
    for brand, items in (("LAHOM", [only, shared]), ("HAUD", [shared])):
        kn.save_document(pg_session, brand, {"schema_version": 1, "brand": brand, "items": items},
                         actor_user_id=admin.id, expected_version=0)
    versions, problems = doc_import.load_documents(pg_session)
    assert problems == {}
    out = doc_import.run_import(pg_session, versions, actor=admin, apply=True, now=NOW)
    assert out["create"] == 2 and current_object(pg_session, "common/shared").brand == "COMMON"
    for brand in ("LAHOM", "HAUD"):
        assert doc_bridge.shadow_compare(pg_session, brand)["equal"] is True
    assert doc_import.run_import(pg_session, versions, actor=admin, apply=False)["unchanged"] == 2
