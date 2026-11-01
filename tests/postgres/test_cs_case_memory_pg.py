"""사례 기억(플랜 C10-4) PostgreSQL 레인 — pg_trgm 비슷한 사례 고르기 · 마이그레이션 왕복 · 사례 조건부 쓰기.

SQLite 메인 레인은 파이썬 비슷함(:func:`~foms.services.cs_agent.case_material.trigram_similarity`)으로 같은 셈을 흉내 낸다.
여기서는 진짜 PostgreSQL 에서 ① ``similar_cases`` 가 pg_trgm(``%`` · ``similarity``) 길로 같은 브랜드 비슷한 사례만 비슷한 것부터
고르고 파이썬 셈과 같은 값 · 같은 순서인지(한국어 글) ② ``%`` 질의가 ``ix_cs_agent_turns_question_trgm`` GIN 색인을 탈 수 있는지
③ ``csagent_03`` 내리기 → 올리기가 모델(create_all)과 같은 칸 · 제약 · 색인을 되살리는지 ④ 사례 쓰기가 사례 칸이 빈 줄에만
쓰이는지(두 번째는 :class:`~foms.services.cs_agent.turns.TurnConflict`)를 본다. ``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다.
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, select, text

from foms.services.cs_agent import case_material, turns
from foms.services.cs_agent.channel_read import DerivedMessage
from foms.services.cs_agent.drafting_read import ChatLine
from foms.services.cs_agent.state import KST
from models import CsAgentTurn

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "csagent_03_turn_case_memory.py"
NOW = datetime.datetime(2026, 11, 2, 9, 0, tzinfo=KST)
QUERY = "주황고래손님표지 선반 깊이 문의드려요"


def _case(session, chat, question, *, brand="LAHOM", outcome="direct", held_out=False):
    session.add(CsAgentTurn(brand=brand, chat_id=chat, last_user_message_id=f"m-{chat}", state="stored", attempts=1,
                            masked_question=question, staff_reply_masked=f"합성 답 {chat}", outcome=outcome,
                            held_out=held_out))
    session.flush()


def _lines(text_value):
    meta = DerivedMessage("uc-pg", "m-q", "201824", "LAHOM", "user", NOW.astimezone(datetime.timezone.utc))
    return [ChatLine(meta, text_value)]


def test_similar_cases_use_pg_trgm_and_match_the_python_fallback(pg_session):
    hangul = pg_session.execute(text("SELECT show_trgm(:probe)"), {"probe": case_material.TRGM_PROBE}).scalar()
    ctype = pg_session.execute(text("SELECT datctype FROM pg_database WHERE datname = current_database()")).scalar()
    assert hangul, f"이 레인은 한글을 글자로 보는 지역 설정이 전제다(en_US.UTF-8 · ko_KR 등) — 지금 {ctype}"  # R14-2
    _case(pg_session, "c-1", "선반 깊이 문의드려요")  # 비슷함 0.57
    _case(pg_session, "c-2", "선반 깊이 문의")  # 0.36
    _case(pg_session, "c-3", "주황고래손님표지 선반 깊이 문의드려요 합성")  # 0.88
    _case(pg_session, "c-low", "선반 깊이가 얼마인가요")  # 0.17 — 문턱(0.2) 아래, 두 길 모두 뺀다
    for chat, extra in (("c-haud", {"brand": "HAUD"}), ("c-held", {"held_out": True}),
                        ("c-copied", {"outcome": "copied"})):
        _case(pg_session, chat, "선반 깊이 문의드려요", **extra)
    _case(pg_session, "c-far", "배송 일정이 궁금합니다")
    found = case_material.similar_cases(pg_session, "LAHOM", _lines(QUERY))
    assert [answer for _, answer in found] == ["합성 답 c-3", "합성 답 c-1", "합성 답 c-2"]
    assert case_material._py_cases(pg_session, "LAHOM", QUERY, 5) == [(q, a) for q, a in found]  # 같은 셈 · 같은 순서
    for question in ("선반 깊이 문의드려요", "선반 깊이가 얼마인가요", "[이름] 선반 문의"):  # 한국어 글 셈이 같다
        score = pg_session.execute(text("SELECT similarity(:a, :b)"), {"a": question, "b": QUERY}).scalar()
        assert round(score, 6) == round(case_material.trigram_similarity(question, QUERY), 6), question
    threshold = pg_session.execute(text("SHOW pg_trgm.similarity_threshold")).scalar()
    assert float(threshold) == case_material.CASE_MIN_SIMILARITY  # 이 트랜잭션만(set_config 의 is_local)


def test_the_percent_query_can_use_the_gin_index(pg_session):
    for number in range(40):
        _case(pg_session, f"c-{number}", f"합성 문의 {number} 번째 글입니다")
    pg_session.execute(text("ANALYZE cs_agent_turns"))
    pg_session.execute(text("SET LOCAL enable_seqscan = off"))
    connection = pg_session.connection()
    compiled = case_material._pg_statement("LAHOM", QUERY, 5).compile(  # 앱과 같은 SQL(IN 목록만 펼침)
        dialect=connection.dialect, compile_kwargs={"render_postcompile": True})

    def plan() -> str:
        return "\n".join(row[0] for row in connection.exec_driver_sql("EXPLAIN " + str(compiled), compiled.params))

    # 작은 표에선 브랜드 btree 가 먼저 뽑힌다 — 잴 때만 빼고(트랜잭션째 되돌린다) GIN 이 쓰이는지 본다.
    pg_session.execute(text("DROP INDEX ix_cs_agent_turns_brand_created"))
    assert "ix_cs_agent_turns_question_trgm" in plan()
    pg_session.execute(text("DROP INDEX ix_cs_agent_turns_question_trgm"))  # 음성 대조군: 색인을 빼면 못 쓴다
    assert "ix_cs_agent_turns_question_trgm" not in plan()


def _load_migration():
    spec = importlib.util.spec_from_file_location("csagent_03_pg", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shape(conn):
    found = inspect(conn)
    columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in found.get_columns("cs_agent_turns")}
    checks = {c["name"] for c in found.get_check_constraints("cs_agent_turns")}
    index = conn.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_cs_agent_turns_question_trgm'")
                         ).scalar()
    return columns, checks, index


def test_the_migration_round_trip_restores_the_create_all_shape(pg_engine):
    module = _load_migration()
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            before = _shape(conn)
            assert "gin_trgm_ops" in before[2] and module.OUTCOME_CHECK in before[1]
            with Operations.context(MigrationContext.configure(conn)):
                module.downgrade()
                down = _shape(conn)
                module.upgrade()
            after = _shape(conn)
        finally:
            trans.rollback()
    assert down[2] is None and "outcome" not in down[0] and module.OUTCOME_CHECK not in down[1]
    assert after == before


def test_a_case_is_written_once_on_postgres(pg_session):
    row = turns.claim_turn(pg_session, "LAHOM", "uc-pg", "m-1", now=NOW)
    turns.mark_stored(row, masked_draft="합성 초안", now=NOW)
    case = {"masked_question": "합성 질문", "outcome": "direct", "edit_ratio": None, "desk_manager_id": "mgr-pg"}
    turns.record_staff_reply(row, "합성 직원 답", case=case, now=NOW)
    pg_session.flush()
    with pytest.raises(turns.TurnConflict):  # 사례 칸이 이미 찼다 — 다른 쪽이 다시 붙이지 못한다
        turns.record_staff_reply(row, "다른 합성 답", case={**case, "outcome": "copied"}, now=NOW)
    stored = pg_session.execute(select(CsAgentTurn.outcome, CsAgentTurn.staff_reply_masked,
                                       CsAgentTurn.held_out)).one()
    assert tuple(stored) == ("direct", "합성 직원 답", False)
