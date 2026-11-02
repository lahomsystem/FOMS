"""이웃 찾기 · 뇌 보기 바탕 점 · D105 PostgreSQL 레인 — 재귀 CTE(유효 기간 · 보기 범위) · 선 질의 · 품질 수(상관 부분 질의) ·
연결 개수 최대의 줄 잠금(같은 때 두 반영이 같은 가격 규칙에 값 정본을 하나씩 더하면 뒤 세션이 기다렸다가 상한에 막힌다).

SQLite 메인 레인과 같은 답인지 진짜 PostgreSQL 에서 본다. ``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다. 합성 항목 · 합성 계산기
정본(꾸민 수)만.
"""

from __future__ import annotations

import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from foms.persistence.brain.models import BrainLink
from foms.services.brain.apply import apply_change
from foms.services.brain.around import AroundQuery, brain_points, search_around
from foms.services.brain.errors import BrainLinkLimitError
from foms.services.brain.external import catalog_source
from foms.services.brain.proposals import Proposer, propose_link
from foms.services.brain.quality import quality_counts
from foms.services.brain.scope import viewer_of
from models import User
from tests.support.brain_screen_support import TODAY, world
from tests.support.brain_support import NOW, create, link, person, synth_catalog


def test_around_points_and_quality_filter_by_scope_and_validity_on_postgres(pg_session):
    who = {name: viewer_of(user) for name, user in world(pg_session).items()}
    admin_user = pg_session.query(User).filter_by(username="bs_admin").one()
    create(pg_session, admin_user, "common/oldfit", item_type="build_rule", name="끝난 규칙", valid_to="2026-10-31")
    link(pg_session, admin_user, "applies_to", "common/oldfit", "common/door")
    admin = search_around(pg_session, who["admin"], AroundQuery("common/door", depth=2), today=TODAY)
    cs = search_around(pg_session, who["cs_mgr"], AroundQuery("common/door", depth=2), today=TODAY)
    assert [(i["key"], i["depth"]) for i in admin["items"]] == [
        ("common/discount", 1), ("common/fit", 1), ("drawing/rule", 1), ("common/slide", 2)]  # 끝난 규칙 빠짐
    assert admin["counts"] == {"applies_to": 3, "requires": 1} and len(admin["edges"]) == 4
    assert [i["key"] for i in cs["items"]] == ["common/fit", "common/slide"] and cs["total"] == 2
    assert {k for e in cs["edges"] for k in (e["from"], e["to"])} == {"common/door", "common/fit", "common/slide"}
    limited = search_around(pg_session, who["admin"], AroundQuery("common/door", ("requires",), 2, 5), today=TODAY)
    assert limited["total"] == 0
    points = brain_points(pg_session, who["cs_mgr"], today=TODAY)
    assert points["total"] == 6 and "common/oldfit" not in {r[0] for r in points["rows"]}
    rules = {(r["type"], r["kind"]): r for r in quality_counts(pg_session, who["admin"], today=TODAY)["rules"]}
    assert rules[("price_rule", "value_from")]["items"] == 1 and rules[("price_rule", "value_from")]["missing"] == 1
    hidden = {(r["type"], r["kind"]): r for r in quality_counts(pg_session, who["cs_mgr"], today=TODAY)["rules"]}
    assert hidden[("price_rule", "value_from")]["items"] == 0  # 가격 재량 항목 수는 새지 않는다


def test_overlapping_link_adds_wait_on_the_source_row_and_hit_the_max(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    with make_session() as setup, catalog_source(synth_catalog):
        admin = person(setup, "pg_brain_limit_admin")
        create(setup, admin, "common/pglimit", item_type="price_rule", name="합성 운임 규칙", checked_at="2026-10-20",
               visibility="price", payload={"doc_id": "pglimit", "approved_by": "합성", "approved_at": "2026-10-20"})
        one = propose_link(setup, op="link_add", kind="value_from", from_key="common/pglimit", to_key="calc:product/1",
                           reason="pg", proposer=Proposer.user(admin.id), now=NOW)
        two = propose_link(setup, op="link_add", kind="value_from", from_key="common/pglimit", to_key="calc:product/7",
                           reason="pg", proposer=Proposer.user(admin.id), now=NOW)
        setup.commit()
        admin_id, one_id, two_id = admin.id, one.id, two.id
    holder = make_session()
    outcome: dict = {}

    def second() -> None:
        with make_session() as session, catalog_source(synth_catalog):
            try:
                apply_change(session, two_id, actor=session.get(User, admin_id), now=NOW)
                session.commit()
                outcome["result"] = "applied"
            except BrainLinkLimitError as exc:
                session.rollback()
                outcome["result"] = ("limit", exc.limit)

    with catalog_source(synth_catalog):
        apply_change(holder, one_id, actor=holder.get(User, admin_id), now=NOW)  # 시작 항목 줄을 잠근 채 커밋 전
    worker = threading.Thread(target=second)
    try:
        worker.start()
        time.sleep(0.5)
        waited = worker.is_alive()  # 뒤 세션은 시작 항목 줄 잠금에서 기다린다
        holder.commit()
    finally:
        holder.close()
        worker.join(timeout=10)
    assert waited and outcome["result"] == ("limit", 1)
    with make_session() as check:
        rows = check.execute(select(BrainLink.to_key).where(BrainLink.from_key == "common/pglimit",
                                                            BrainLink.superseded_at.is_(None))).scalars().all()
        assert rows == ["calc:product/1"]
