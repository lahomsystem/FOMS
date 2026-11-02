"""회사 지식 물어보기 PostgreSQL 레인(설계서 10절 · ⑤-5 · D105 · D106 · D114) — SQLite 메인 레인과 같은 답인지 진짜
PostgreSQL(pg_trgm 단어 비슷함 · JSONB · 저장점 쓰인 횟수 · 층별 AI 자리 · pgvector)에서 본다.

- 답하는 길: 보기 범위 안 후보만(음성 대조군 — 같은 질문 · 볼 수 없는 사람) · 가림 · 근거 키 확인.
- 틀림 신고 둘 → 엇갈림 제안(이름 있는 에이전트 액션) · '확인 필요'.
- 쓰인 횟수 줄 넣기 · 더하기(저장점) · 다른 이름 찾기 · 층별 AI 주 자리.
- 의미 찾기 ``<=>`` — **pgvector 확장이 있을 때만**(CI PG 레인 이미지 postgres:17 에는 없어 건너뛴다 — 운영 · 스테이징은 0.8.2).
``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다. 합성 지식 · 가짜 모델 · 가짜 벡터만.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from foms.persistence.brain.models import BrainChange, BrainUsage
from foms.services.brain.chat_answer import ask
from foms.services.brain.chat_log import record_feedback
from foms.services.brain.chat_reports import reported_keys
from foms.services.brain.chat_settings import EMBED_FIELD, read_chat_settings
from foms.services.brain.chat_tools import search_objects
from foms.services.brain.embed_sources import run_embed
from foms.services.brain.embeddings import embedder_source, nearest, query_vector
from foms.services.brain.scope import viewer_of
from foms.services.brain.usage import count_reads, usage_of
from tests.support.brain_chat_support import NOW_KST, axis, candidates_of, chat_on, chat_world, fake_embedder, fixed, reply

ROOT = Path(__file__).resolve().parents[2]
TODAY = NOW_KST.date()
NOW_UTC = NOW_KST.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def _ask(session, user, question, client):
    out = ask(session, user, question, client=client, now=NOW_KST)
    session.commit()
    return out


def test_answer_path_filters_scope_and_masks_on_postgres(pg_session):
    people = chat_world(pg_session, stage="leads")
    question = "재량 할인 폭과 슬라이딩 깊이 알려 주세요 010-2345-6789"
    hidden = fixed(reply(answer="재량 할인 폭은 합성 비밀 규칙입니다.", evidence_ids=["common/discount"], unknown=False))
    out = _ask(pg_session, people["sales_mgr"], question, hidden)
    sent = json.dumps(hidden.calls, ensure_ascii=False)
    assert "재량 할인 폭은" not in sent and "2345" not in sent and out["unknown"] is True
    seen = fixed(reply(answer="합성 규격 650mm 입니다.", evidence_ids=["common/sliding"], unknown=False))
    ok = _ask(pg_session, people["admin"], question, seen)
    keys = {c["key"] for c in candidates_of(seen.calls[0])["usable"]}
    assert {"common/discount", "common/sliding"} <= keys and ok["unknown"] is False  # 대조군: ADMIN 은 본다
    assert usage_of(pg_session, ["common/sliding"]) == {"common/sliding": 1}


def test_wrong_reports_raise_a_conflict_proposal_on_postgres(pg_session):
    people = chat_world(pg_session)
    for name in ("admin", "admin2"):
        row = _ask(pg_session, people[name], "슬라이딩 깊이는?",
                   fixed(reply(answer="합성 규격 650mm", evidence_ids=["common/sliding"], unknown=False)))
        record_feedback(pg_session, question_id=row["id"], asker_id=people[name].id, feedback="wrong",
                        note="깊이 값이 달라요", now_utc=NOW_UTC)
        pg_session.commit()
    change = pg_session.execute(select(BrainChange).where(BrainChange.action == "report_conflict")).scalar_one()
    assert change.item_type == "conflict" and change.gates["evidence"] == "pass"
    assert reported_keys(pg_session, ["common/sliding"]) == {"common/sliding"}


def test_usage_upsert_alias_search_and_trgm_on_postgres(pg_session):
    people = chat_world(pg_session)
    count_reads(pg_session, ["common/hinge"], "chatbot", now=NOW_UTC)
    count_reads(pg_session, ["common/hinge", "common/sliding"], "cs_brain", now=NOW_UTC)
    count_reads(pg_session, ["common/hinge"], "chatbot", now=NOW_UTC)
    pg_session.commit()
    rows = pg_session.execute(select(BrainUsage.item_key, BrainUsage.reader, BrainUsage.count)
                              .order_by(BrainUsage.item_key, BrainUsage.reader)).all()
    assert rows == [("common/hinge", "chatbot", 2), ("common/hinge", "cs_brain", 1), ("common/sliding", "cs_brain", 1)]
    who = viewer_of(people["admin"])
    assert search_objects(pg_session, who, "벽장 짜는 법", today=TODAY)[0]["key"] == "common/term-builtin"
    assert search_objects(pg_session, who, "슬라이딩 깊이는?", today=TODAY)[0]["key"] == "common/sliding"  # word_similarity 질의


def _vector_ready(session) -> bool:
    return bool(session.execute(text("SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'")).scalar())


def test_vector_search_uses_pgvector_exact_distance(pg_session):
    if not _vector_ready(pg_session):
        pytest.skip("pgvector 확장이 이 PostgreSQL 에 없다(CI PG 레인 이미지 postgres:17) — 운영 · 스테이징은 0.8.2 있음")
    spec = importlib.util.spec_from_file_location("brain_02_pg", ROOT / "migrations/versions/brain_02_chat_usage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pg_session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    for statement in module.EMBED_DDL:
        pg_session.execute(text(statement))
    pg_session.commit()
    try:
        people = chat_world(pg_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00"})
        table = {"깊이": axis(0), "치수": axis(0), "재단": axis(3), "여유분": axis(3)}
        cfg = read_chat_settings(pg_session)
        with embedder_source(fake_embedder(table)):
            done = run_embed(pg_session, cfg=cfg, now=NOW_KST, apply=True)["brain_item"]
            vector = query_vector(pg_session, "여유분 얼마나", cfg=cfg, now=NOW_KST)
        assert done["embedded"] >= 5
        dr = nearest(pg_session, viewer_of(people["dr_mgr"]), vector, today=TODAY, limit=3)
        cs = nearest(pg_session, viewer_of(people["cs_mgr"]), vector, today=TODAY, limit=3)
        assert dr[0][0] == "drawing/bom" and dr[0][1] == pytest.approx(1.0, abs=1e-3)
        assert "drawing/bom" not in [k for k, _s in cs]  # 보기 범위는 순위 앞에(SQL)
        stored = pg_session.execute(text("SELECT count(*) FROM brain_embeddings WHERE source_key = 'common/discount'"))
        assert stored.scalar() == 0  # 가격 재량 항목은 넣지 않는다
    finally:
        pg_session.rollback()
        pg_session.execute(text("DROP TABLE IF EXISTS brain_embeddings"))
        pg_session.commit()


def test_ai_weekly_slots_group_by_layer_on_postgres(pg_session):
    from foms.services.brain.inbox import ai_week

    people = chat_world(pg_session)
    week = ai_week(pg_session, NOW_UTC, viewer_of(people["cs_mgr"]))
    assert week["layers"] == {"cs": {"used": 0, "left": 20}} and week["cap"] == 20
    assert pg_session.scalar(select(func.count()).select_from(BrainChange).where(
        BrainChange.action == "report_conflict")) == 0
    chat_on(pg_session, stage="all")
