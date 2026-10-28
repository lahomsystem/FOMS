"""초안 차례 선점(플랜 C3-3 · C3-1) PostgreSQL 레인 — 두 세션이 같은 손님 글을 겹쳐 집어도 줄은 하나.

SQLite 메인 레인은 DB 전체 잠금이라 두 세션이 진짜로 겹치지 않는다. 여기서는 진짜 PostgreSQL 에서 ① 앞 세션이 넣고
커밋하기 전에 뒤 세션의 '있으면 무시하고 넣기'가 고유 색인에서 기다렸다가 아무것도 넣지 않는지 ② 앞 세션이 되돌리면 뒤
세션이 집는지(음성 대조군) ③ 실패 줄 다시 집기가 겹쳐도 하나만 집는지 ④ 상태 검사 제약 · JSONB · 숫자 칸 · '올리는 중'
찾기를 본다. ``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다(레인 규칙은 ``tests/postgres/conftest.py``).
"""

from __future__ import annotations

import datetime
import threading
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foms.services.cs_agent import turns
from foms.services.cs_agent.state import KST
from models import CsAgentTurn

NOW = datetime.datetime(2026, 11, 2, 9, 0, tzinfo=KST)
CHAT = "uc-pg"


def _rows(make_session, message: str) -> int:
    with make_session() as session:
        return session.scalar(select(func.count()).select_from(CsAgentTurn).filter_by(
            chat_id=CHAT, last_user_message_id=message))


def _claim_in_thread(make_session, outcome: dict, message: str) -> threading.Thread:
    """두 번째 컨테이너의 바퀴 — 따로 연 세션으로 같은 차례를 집고 커밋한다."""

    def run() -> None:
        with make_session() as session:
            row = turns.claim_turn(session, "LAHOM", CHAT, message, now=NOW)
            outcome["second"] = None if row is None else (row.id, row.attempts)
            session.commit()

    worker = threading.Thread(target=run)
    worker.start()
    return worker


def test_overlapping_claims_wait_on_the_unique_index_and_insert_once(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    holder = make_session()
    first = turns.claim_turn(holder, "LAHOM", CHAT, "m-1", now=NOW)
    assert first is not None and first.attempts == 1  # 앞 바퀴가 넣었고 아직 커밋 전
    outcome: dict = {}
    worker = _claim_in_thread(make_session, outcome, "m-1")
    time.sleep(0.5)
    assert worker.is_alive()  # 뒤 바퀴는 고유 색인에서 앞 바퀴가 끝나기를 기다린다
    holder.commit()
    holder.close()
    worker.join(timeout=10)
    assert not worker.is_alive() and outcome["second"] is None
    assert _rows(make_session, "m-1") == 1


def test_a_rolled_back_claim_frees_the_turn(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    holder = make_session()
    assert turns.claim_turn(holder, "LAHOM", CHAT, "m-2", now=NOW) is not None
    outcome: dict = {}
    worker = _claim_in_thread(make_session, outcome, "m-2")
    time.sleep(0.5)
    assert worker.is_alive()
    holder.rollback()  # 앞 바퀴가 커밋 전에 터졌다
    holder.close()
    worker.join(timeout=10)
    assert not worker.is_alive() and outcome["second"] is not None  # 음성 대조군: 뒤 바퀴가 집는다
    assert outcome["second"][1] == 1 and _rows(make_session, "m-2") == 1


def test_overlapping_reclaims_of_a_failed_turn_pick_it_once(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    with make_session() as setup:
        row = turns.claim_turn(setup, "LAHOM", CHAT, "m-3", now=NOW)
        setup.commit()
        assert turns.mark_failed(row, error_code="send_provider_error", now=NOW) is True
        setup.commit()
    holder = make_session()
    again = turns.claim_turn(holder, "LAHOM", CHAT, "m-3", now=NOW)
    assert again is not None and again.attempts == 2
    outcome: dict = {}
    worker = _claim_in_thread(make_session, outcome, "m-3")
    time.sleep(0.5)
    assert worker.is_alive()  # 줄 잠금에서 기다린다
    holder.commit()
    holder.close()
    worker.join(timeout=10)
    assert not worker.is_alive() and outcome["second"] is None  # 다시 본 줄은 이미 '선점' — 하나만 집는다
    with make_session() as check:
        final = check.scalars(select(CsAgentTurn).filter_by(chat_id=CHAT, last_user_message_id="m-3")).one()
        assert (final.state, final.attempts, final.error_code) == ("claimed", 2, None)


def test_state_check_columns_and_stale_posting_on_postgres(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    with make_session() as session:
        session.add(CsAgentTurn(brand="LAHOM", chat_id=CHAT, last_user_message_id="m-bad", state="bogus"))
        with pytest.raises(IntegrityError):  # 상태는 여섯 가지만
            session.commit()
        session.rollback()
        row = turns.claim_turn(session, "LAHOM", CHAT, "m-4", now=NOW)
        turns.record_brain_result(row, SimpleNamespace(intent="quote", handoff=False, cost_usd=0.0123,
                                                       input_tokens=1200, latency_ms=4321))
        turns.mark_posting(row, masked_draft="합성 초안입니다", check_codes=["tone_emoji"], now=NOW)
        session.commit()
    with make_session() as session:
        found = turns.stale_posting(session, NOW + datetime.timedelta(minutes=5))
        assert [r.last_user_message_id for r in found] == ["m-4"]
        assert (found[0].check_codes, found[0].cost_usd, found[0].input_tokens, found[0].handoff) == (
            ["tone_emoji"], Decimal("0.012300"), 1200, False)
        assert turns.stale_posting(session, NOW - datetime.timedelta(minutes=5)) == []
