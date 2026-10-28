"""CS 감시 루프(플랜 C1-3) PostgreSQL 레인 — 대표 잠금 · 아침 보고 한 번(두 컨테이너가 겹칠 때).

SQLite 메인 레인은 advisory lock 대신 프로세스 안 잠금을 쓰고 ``FOR UPDATE`` 를 무시한다. 여기서는 진짜 PostgreSQL 에서
① 바퀴의 ``pg_try_advisory_lock`` 이 다른 연결(두 번째 컨테이너)을 막고, 바퀴가 터져도 풀리며 ② 기록 줄을 쥔 첫 바퀴가
커밋할 때까지 두 번째 바퀴가 ``FOR UPDATE`` 에서 기다렸다가 이미 낸 아침 보고를 다시 내지 않는지 본다.
``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다(레인 규칙은 ``tests/postgres/conftest.py``).
"""

from __future__ import annotations

import datetime
import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from foms.services.cs_agent import loop, report
from foms.services.cs_agent.state import KST
from models import ChannelInboundEventLog, CsAgentMessage, Notification, NotificationUserState, SystemSetting, User
from tests.support.cs_agent_fakes import FakeReader, at, chat_snap, derived, entity, weekdays_only


def _try_lock(conn) -> bool:
    return bool(conn.execute(text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": loop.LEADER_LOCK_KEY}).scalar())


def test_leader_lock_blocks_another_connection_and_releases_even_on_error(pg_engine):
    with loop.leader_lock(pg_engine) as first:
        assert first is True
        with loop.leader_lock(pg_engine) as second:
            assert second is False  # 두 번째 컨테이너의 바퀴는 건너뛴다
        with pg_engine.connect() as other:
            assert _try_lock(other) is False  # 일 세션이 커밋해도 바퀴 내내 쥔다
    with pytest.raises(RuntimeError):
        with loop.leader_lock(pg_engine) as got:
            assert got is True
            raise RuntimeError("바퀴가 터졌다")
    with pg_engine.connect() as other:  # 음성 대조군: 풀린 뒤엔 누구나 잡는다
        assert _try_lock(other) is True
        other.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": loop.LEADER_LOCK_KEY})
        other.commit()


def test_overlapping_container_waits_on_the_state_row_and_sends_no_second_report(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    now = datetime.datetime(2026, 11, 2, 8, 0, tzinfo=KST)
    with make_session() as setup:
        report._ensure_state_row(setup)
        before = setup.query(Notification).filter_by(notification_type=report.NOTIFY_MORNING_REPORT).count()
    holder = make_session()
    holder.get(SystemSetting, report.STATE_KEY, with_for_update=True)  # 첫 컨테이너가 기록 줄을 쥐었다
    outcome: dict = {}

    def second_container() -> None:
        with make_session() as session:
            outcome["published"] = report.publish(
                session, states=[], missing=[], checks={"LAHOM": "ok", "HAUD": "ok"}, watch_missing_inbound=False,
                now=now, is_business_day=lambda _day: True)

    worker = threading.Thread(target=second_container)
    worker.start()
    time.sleep(0.5)
    assert worker.is_alive()  # FOR UPDATE 에서 기다린다
    row = holder.get(SystemSetting, report.STATE_KEY)
    row.setting_value = {"report_date": "2026-11-02"}  # 첫 컨테이너가 보고를 냈다고 적고 커밋
    holder.commit()
    holder.close()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert outcome["published"].report_sent is False
    with make_session() as check:
        assert check.query(Notification).filter_by(notification_type=report.NOTIFY_MORNING_REPORT).count() == before


def test_a_full_pass_on_postgres_ingests_reconciles_and_reports_once(pg_engine):
    """있으면 무시하고 넣기(ON CONFLICT) · 기록 줄 FOR UPDATE · 알림 수신자 펼침(FK)을 진짜 PostgreSQL 에서 한 바퀴.

    같은 모듈의 앞 시험이 기록 줄에 11-02 보고를 적어 두었다(레인은 모듈마다 비운다) — 그래서 다음 운영일(11-03)로 돈다.
    """
    make_session = sessionmaker(bind=pg_engine)
    with make_session() as session:
        session.add(User(username="cs_pg_admin", password="x", name="관리자", role="ADMIN", is_active=True))
        session.add(ChannelInboundEventLog(
            id=1, dedupe_key="msg_message_1", payload_hash="0" * 64, chat_type="message", source_chat_id="uc-1",
            status="user_chat_handled",
            raw_payload={"event": "push", "type": "message", "entity": entity("m1", at(3, 9), text="합성 문의")}))
        session.commit()
        api = {"uc-1": [derived("m1", at(3, 9), text="합성 문의"), derived("m2", at(3, 9, 5), text="합성 덧글")]}
        sent = []
        for minute in (10, 25):
            reader = FakeReader([chat_snap("uc-1", at(3, 9, 5))], api)
            result = loop.run_pass(session, now=at(3, 9, minute), reader=reader, is_business_day=weekdays_only)
            assert result.outcome == loop.OUTCOME_OK
            sent.append(result.report_sent)
        assert sent == [True, False]
        assert session.query(CsAgentMessage).count() == 2  # 수신 기록 1 + 채널톡 보정 1, 두 번째 바퀴는 겹치지 않음
        reports = session.query(Notification).filter_by(notification_type=report.NOTIFY_MORNING_REPORT).all()
        assert len(reports) == 1 and "[라홈] 3일+ 0 · 약속 넘김 0 · 답 필요 1" in reports[0].message
        assert session.query(NotificationUserState).filter_by(notification_id=reports[0].id).count() == 1
        assert session.get(SystemSetting, report.STATE_KEY).setting_value["report_date"] == "2026-11-03"
