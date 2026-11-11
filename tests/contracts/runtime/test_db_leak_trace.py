"""DB-LEAK-01: GC 가 치운 연결만 ``[DB-LEAK]`` 로 남기고, 정상 반납은 조용하다."""

from __future__ import annotations

import gc
import logging
import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool

from foms.platform import db_leak_trace


@pytest.fixture(autouse=True)
def _fresh_leak_log(caplog, monkeypatch):
    """같은 프로세스의 앞선 시험이 남긴 연결을 먼저 치우고 보고 수(최대 200)를 0 으로 — 순서와 무관하게.

    병렬 실행에서 앞 시험의 연결이 이 시험 ``gc.collect()`` 때 회수되면 그 줄이 대신 잡히고, 보고 수가 차 있으면
    이 시험의 누수는 아예 안 남는다(2026-11-11 전체 시험에서 ``checkout_at=-`` 한 줄로 실패).
    """
    gc.collect()
    caplog.clear()
    monkeypatch.setattr(db_leak_trace, "_reported", 0)


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'leak.db'}", poolclass=QueuePool)
    assert db_leak_trace.install_db_leak_trace(engine) is True
    return engine


def _in_new_thread(fn) -> None:
    # 운영은 요청마다 새 그린렛이다 — scoped_session 이 그 그린렛(여기선 스레드)에 묶인다.
    t = threading.Thread(target=fn)
    t.start()
    t.join()
    gc.collect()


def _leak_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "[DB-LEAK]" in r.getMessage()]


def test_unclosed_session_is_reported_with_checkout_site(tmp_path, caplog):
    engine = _engine(tmp_path)
    session = scoped_session(sessionmaker(bind=engine))

    def leak_without_close():
        session.execute(text("SELECT 1"))

    caplog.set_level(logging.WARNING, logger=db_leak_trace.__name__)
    _in_new_thread(leak_without_close)

    lines = _leak_lines(caplog)
    assert len(lines) == 1, lines
    assert "gc_reclaimed" in lines[0]
    assert "test_db_leak_trace.py" in lines[0] and "leak_without_close" in lines[0]
    assert engine.pool.checkedout() == 0


def test_closed_session_is_silent(tmp_path, caplog):
    engine = _engine(tmp_path)
    session = scoped_session(sessionmaker(bind=engine))

    def closes_properly():
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.remove()

    caplog.set_level(logging.WARNING, logger=db_leak_trace.__name__)
    _in_new_thread(closes_properly)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    assert _leak_lines(caplog) == []


def test_disabled_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FOMS_DB_LEAK_TRACE", "0")
    engine = create_engine(f"sqlite:///{tmp_path / 'off.db'}", poolclass=QueuePool)
    assert db_leak_trace.install_db_leak_trace(engine) is False
