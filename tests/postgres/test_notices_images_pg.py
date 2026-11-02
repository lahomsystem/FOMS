"""공지 사진(설계서 2026-11-02-foms-notices §8) PostgreSQL 레인 — ``notice_02`` 마이그레이션 왕복.

내리기 → (옛 공지 한 줄) → 올리기 → 내리기 → 올리기가 모델(create_all)과 같은 칸(JSONB · NOT NULL)을 되살리고, 올릴 때 이미 있던
공지는 사진 없음(``[]``)으로 채워진다. 새 줄은 칸을 비워 넣어도 ``[]``. ``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "notice_02_notice_images.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("notice_02_notice_images", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(conn) -> dict:
    return {c["name"]: (str(c["type"]), c["nullable"]) for c in inspect(conn).get_columns("notices")}


def test_notice_02_round_trip_restores_jsonb_images_and_fills_old_rows(pg_engine):
    module = _load_migration()
    assert module.down_revision == "brain_00"
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            before = _columns(conn)
            with Operations.context(MigrationContext.configure(conn)):
                module.downgrade()
                down = _columns(conn)
                conn.execute(text("INSERT INTO notices (title) VALUES ('옛 공지')"))
                module.upgrade()
                old = conn.execute(text("SELECT images FROM notices WHERE title = '옛 공지'")).scalar()
                module.downgrade()
                module.upgrade()
            conn.execute(text("INSERT INTO notices (title) VALUES ('새 공지')"))
            new = conn.execute(text("SELECT images FROM notices WHERE title = '새 공지'")).scalar()
            after = _columns(conn)
        finally:
            trans.rollback()
    assert before["images"] == ("JSONB", False)
    assert "images" not in down
    assert old == [] and new == []
    assert after == before
