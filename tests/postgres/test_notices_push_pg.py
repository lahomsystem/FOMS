"""공지 폰 알림(설계서 2026-11-02-foms-notices §7) PostgreSQL 레인 — 선점 한 번 · 마이그레이션 왕복.

① 웹과 SIDEFX 가 같은 공지를 동시에 선점(``UPDATE ... WHERE push_sent_at IS NULL``)해도 뒤 세션은 앞 세션 커밋을 기다렸다가
0 줄 — 한 번만 보낸다. 앞 세션이 되돌리면 뒤 세션이 집는다(음성 대조군).
② ``notice_01`` 내리기 → 올리기 → 내리기 → 올리기가 모델(create_all)과 같은 칸 · FK 를 되살리고, 올릴 때 이미 있던 공지는
``push_sent_at`` 이 채워진다(배포 직후 옛 공지가 한꺼번에 울리지 않는다). ``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다.
"""
from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, inspect, text
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.notices.push import _claim
from models import Notice

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "notice_01_notice_push.py"


def _committed_notice(make_session) -> int:
    session = make_session()
    try:
        notice = Notice(title="PG 선점 공지", body="", audience_staff_all=True)
        session.add(notice)
        session.commit()
        return int(notice.id)
    finally:
        session.close()


def _drop(make_session, notice_id: int) -> None:
    session = make_session()
    try:
        session.execute(delete(Notice).where(Notice.id == notice_id))
        session.commit()
    finally:
        session.close()


def _claim_in_thread(make_session, notice_id: int, outcome: dict) -> threading.Thread:
    def run() -> None:
        session = make_session()
        try:
            outcome["second"] = _claim(session, notice_id, now_utc_naive())
            session.commit()
        finally:
            session.close()

    worker = threading.Thread(target=run)
    worker.start()
    return worker


def test_two_claims_at_once_send_once(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    notice_id = _committed_notice(make_session)
    try:
        holder = make_session()
        assert _claim(holder, notice_id, now_utc_naive()) is True
        outcome: dict = {}
        worker = _claim_in_thread(make_session, notice_id, outcome)
        time.sleep(0.3)
        assert "second" not in outcome  # 앞 세션 커밋을 기다린다
        holder.commit()
        holder.close()
        worker.join(timeout=10)
        assert outcome["second"] is False
    finally:
        _drop(make_session, notice_id)


def test_rolled_back_claim_lets_the_next_one_send(pg_engine):
    make_session = sessionmaker(bind=pg_engine)
    notice_id = _committed_notice(make_session)
    try:
        holder = make_session()
        assert _claim(holder, notice_id, now_utc_naive()) is True
        outcome: dict = {}
        worker = _claim_in_thread(make_session, notice_id, outcome)
        time.sleep(0.3)
        holder.rollback()  # 음성 대조군: 앞 사람이 되돌리면 뒤 사람이 집는다
        holder.close()
        worker.join(timeout=10)
        assert outcome["second"] is True
    finally:
        _drop(make_session, notice_id)


def _load_migration():
    spec = importlib.util.spec_from_file_location("notice_01_pg", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shape(conn):
    found = inspect(conn)
    notices = {c["name"]: (str(c["type"]), c["nullable"]) for c in found.get_columns("notices")}
    acks = {c["name"]: (str(c["type"]), c["nullable"]) for c in found.get_columns("notice_acks")}
    fks = {
        (fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
        for fk in found.get_foreign_keys("notice_acks")
    }
    return notices, acks, fks


def test_the_migration_round_trip_restores_shape_and_fills_old_notices(pg_engine):
    module = _load_migration()
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            before = _shape(conn)
            with Operations.context(MigrationContext.configure(conn)):
                module.downgrade()
                down = _shape(conn)
                conn.execute(text("INSERT INTO notices (title) VALUES ('옛 공지')"))
                module.upgrade()
                filled = conn.execute(text("SELECT push_sent_at FROM notices WHERE title = '옛 공지'")).scalar()
                module.downgrade()
                module.upgrade()
            after = _shape(conn)
        finally:
            trans.rollback()
    assert "push_sent_at" in before[0] and "notification_id" in before[1]
    assert (module.FK_NAME, ("notification_id",), "notifications", "SET NULL") in before[2]
    assert "push_sent_at" not in down[0] and "notification_id" not in down[1]
    assert not {fk for fk in down[2] if fk[0] == module.FK_NAME}
    assert filled is not None
    assert after == before
