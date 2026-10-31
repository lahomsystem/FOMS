"""[보내기](플랜 C10-3) PostgreSQL 레인 — 두 사람이 동시에 눌러도 '보내는 중'은 하나 · 보낸 글을 상태 표 '답'으로 · 마이그레이션 왕복.

SQLite 메인 레인은 DB 전체 잠금이라 두 세션이 진짜로 겹치지 않는다. 여기서는 진짜 PostgreSQL 에서 ① 두 세션이 같은 차례를 읽고
(둘 다 앞 확인을 지남) '보내는 중' 조건부 쓰기를 겹쳐 해도 뒤 세션은 앞 세션 커밋을 기다렸다가 0 줄 — 한 사람만 채널톡을 부른다
② 앞 세션이 되돌리면 뒤 세션이 집는다(음성 대조군) ③ 웹훅이 먼저 우리 봇 글로 넣은 줄도 '답'으로 고친다 ④ ``csagent_04``
내리기 → 올리기가 모델(create_all)과 같은 칸 · 제약 · 색인을 되살리는지 본다. ``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다.
"""

from __future__ import annotations

import datetime
import importlib.util
import threading
import time
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import sessionmaker

from foms.services.cs_agent import send_record, turns
from foms.services.cs_agent.state import KST
from foms.services.cs_agent.state_store import SOURCE_WEBHOOK, store_messages
from foms.services.cs_agent.channel_read import DerivedMessage
from models import CsAgentChat, CsAgentMessage, CsAgentTurn

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "csagent_04_turn_send_state.py"
NOW = datetime.datetime(2026, 11, 2, 9, 0, tzinfo=KST)
CHAT = "uc-pg-send"


def _posted(make_session, message: str) -> int:
    """메모를 올린 차례(테스트마다 다른 손님 글 — 모듈 안에서는 줄이 남는다)."""
    with make_session() as session:
        row = turns.claim_turn(session, "LAHOM", CHAT, message, now=NOW)
        turns.mark_posting(row, masked_draft="합성 초안", now=NOW)
        turns.mark_posted(row, memo_message_id="memo-1", now=NOW)
        session.commit()
        return row.id


def _start_in_thread(make_session, turn_id: int, outcome: dict) -> threading.Thread:
    """두 번째 직원의 [보내기] — 따로 연 세션으로 같은 차례를 읽고(앞 확인 통과) '보내는 중'을 쓴다."""

    def run() -> None:
        with make_session() as session:
            row = session.get(CsAgentTurn, turn_id)
            outcome["second"] = send_record.start_sending(session, row, user_id=2, click_ms=None, now=NOW)
            session.commit()

    worker = threading.Thread(target=run)
    worker.start()
    return worker


def test_two_people_pressing_at_once_start_one_send(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    turn_id = _posted(make_session, "m-1")
    holder = make_session()
    row = holder.get(CsAgentTurn, turn_id)
    assert send_record.start_sending(holder, row, user_id=1, click_ms=900, now=NOW) is True  # 앞 사람, 아직 커밋 전
    outcome: dict = {}
    worker = _start_in_thread(make_session, turn_id, outcome)
    time.sleep(0.5)
    assert worker.is_alive()  # 뒤 사람은 줄 잠금에서 앞 사람이 끝나기를 기다린다
    holder.commit()
    worker.join(timeout=10)
    holder.close()
    assert outcome["second"] is False  # 앞 사람이 '보내는 중' — 뒤 사람은 채널톡을 부르지 않는다
    with make_session() as session:
        stored = session.execute(select(CsAgentTurn.send_state, CsAgentTurn.sent_by_user_id, CsAgentTurn.click_ms)
                                 .where(CsAgentTurn.id == turn_id)).one()
    assert tuple(stored) == ("sending", 1, 900)


def test_if_the_first_press_rolls_back_the_second_one_starts(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    turn_id = _posted(make_session, "m-2")
    holder = make_session()
    assert send_record.start_sending(holder, holder.get(CsAgentTurn, turn_id), user_id=1, click_ms=None, now=NOW)
    outcome: dict = {}
    worker = _start_in_thread(make_session, turn_id, outcome)
    time.sleep(0.3)
    holder.rollback()  # 음성 대조군: 앞 사람이 되돌리면 뒤 사람이 집는다
    worker.join(timeout=10)
    holder.close()
    assert outcome["second"] is True


def test_a_bot_row_ingested_first_is_turned_into_an_answer(pg_session):
    created = datetime.datetime(2026, 11, 2, 0, 1, tzinfo=datetime.timezone.utc)
    bot = DerivedMessage(chat_id=CHAT, message_id="sent-1", channel_id="201824", brand="LAHOM", person_type="bot",
                         created_at=created)
    store_messages(pg_session, [bot], source=SOURCE_WEBHOOK, now=NOW.replace(tzinfo=None))  # 웹훅이 먼저(봇 글)
    send_record.record_answer(pg_session, brand="LAHOM", chat_id=CHAT, message_id="sent-1", sent_at=created, now=NOW)
    pg_session.flush()
    person = pg_session.execute(select(CsAgentMessage.person_type).where(CsAgentMessage.message_id == "sent-1")).scalar()
    chat = pg_session.execute(select(CsAgentChat.last_answer_message_id).where(CsAgentChat.chat_id == CHAT)).scalar()
    assert (person, chat) == ("manager", "sent-1")


def _load_migration():
    spec = importlib.util.spec_from_file_location("csagent_04_pg", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shape(conn):
    found = inspect(conn)
    columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in found.get_columns("cs_agent_turns")}
    checks = {c["name"] for c in found.get_check_constraints("cs_agent_turns")}
    indexes = {i["name"]: tuple(i["column_names"]) for i in found.get_indexes("cs_agent_turns")}
    default = conn.execute(text("SELECT column_default FROM information_schema.columns WHERE table_name = "
                                "'cs_agent_turns' AND column_name = 'rewrite_count'")).scalar()
    return columns, checks, indexes, default


def test_the_migration_round_trip_restores_the_create_all_shape(pg_engine):
    module = _load_migration()
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            before = _shape(conn)
            with Operations.context(MigrationContext.configure(conn)):
                module.downgrade()
                down = _shape(conn)
                module.upgrade()
            after = _shape(conn)
        finally:
            trans.rollback()
    assert module.SEND_STATE_CHECK in before[1] and "send_state" in before[0] and before[3] == "0"
    assert "send_state" not in down[0] and module.SEND_STATE_CHECK not in down[1]
    assert not {name for name, _ in module.INDEXES} & set(down[2])
    assert after == before
