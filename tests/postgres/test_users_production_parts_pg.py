"""PostgreSQL — 계정 파트 목록 ``users.production_parts``(설계서 2026-11-23 §6-1 · §15, 마이그레이션 ``prodparts_01``).

* CHECK ``ck_users_production_parts``(PG 전용) — NULL · 네 key 만 든 배열은 받고, 모르는 key · 배열 아닌 값은 막는다.
* 마이그레이션 한 칸 왕복(새 부트스트랩 DB = create_all + stamp head): downgrade 가 옛 칸을 새 칸 첫 값으로 살리고 칸 · CHECK 를
  지운다 → upgrade 가 옛 칸만 있는 행을 ``[옛 값]`` 으로 채우고 CHECK 를 다시 단다. SQLite 레인은 jsonb 함수 · CHECK 를 못 본다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 레인을 건너뛴다(conftest). 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine.url import URL

from models import User
from tests.postgres.test_migration_chain import _alembic_config, migration_chain_url  # noqa: F401 — fixture


def _insert(session, name: str, parts) -> None:
    """파트 목록만 바꿔 넣는다(옛 칸은 비움 — 옛 칸 CHECK 가 먼저 걸리지 않게). 파이썬 None 은 SQL NULL 로 가야 한다."""
    session.add(User(username=f"ppg_{name}", password="x", name=name, role="STAFF", team="PRODUCTION",
                     production_parts=parts, production_part=None))
    session.flush()


@pytest.mark.parametrize("parts", [None, ["cut"], ["cut", "edge", "assemble", "inspect"]])
def test_check_accepts_null_and_known_part_arrays(pg_session, parts):
    _insert(pg_session, f"ok{len(parts or [])}", parts)
    stored = pg_session.execute(text("SELECT production_parts IS NULL, jsonb_typeof(production_parts) FROM users "
                                     "WHERE username = :u"), {"u": f"ppg_ok{len(parts or [])}"}).one()
    assert stored == ((True, None) if parts is None else (False, "array"))  # None = SQL NULL(JSON 'null' 아님)


@pytest.mark.parametrize("parts", [["cut", "paint"], "cut", {"cut": 1}, [1]])
def test_check_rejects_unknown_parts_and_non_arrays(pg_session, parts):
    with pytest.raises(IntegrityError, match="ck_users_production_parts"):
        _insert(pg_session, "bad", parts)


def test_prodparts_01_downgrade_then_upgrade_keeps_first_part_and_refills(
    migration_chain_url: URL, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    import app  # noqa: F401  (모든 모델 모듈을 Base.metadata 에 등록)
    from db import Base

    engine = create_engine(migration_chain_url, connect_args={"client_encoding": "utf8"})
    try:
        Base.metadata.create_all(bind=engine)
        monkeypatch.setenv("DATABASE_URL", migration_chain_url.render_as_string(hide_password=False))
        config = _alembic_config()
        command.stamp(config, "head")
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (username, password, name, role, team, is_active, approval_status, "
                "password_policy_version, session_version, production_parts, production_part) VALUES "
                "('ppg_two', 'x', '김두파', 'STAFF', 'PRODUCTION', true, 'ACTIVE', 0, 0, '[\"edge\", \"inspect\"]', 'edge'),"
                "('ppg_none', 'x', '박반장', 'STAFF', 'PRODUCTION', true, 'ACTIVE', 0, 0, NULL, NULL)"))

        command.downgrade(config, "prodpart_01_handover")
        with engine.connect() as conn:
            cols = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"))}
            assert "production_parts" not in cols and "production_part" in cols
            got = dict(conn.execute(text("SELECT username, production_part FROM users WHERE username LIKE 'ppg_%'")).all())
            assert got == {"ppg_two": "edge", "ppg_none": None}
        with engine.begin() as conn:  # 옛 코드가 그사이 만든 행(옛 칸만)
            conn.execute(text(
                "INSERT INTO users (username, password, name, role, team, is_active, approval_status, "
                "password_policy_version, session_version, production_part) VALUES "
                "('ppg_old', 'x', '이조립', 'STAFF', 'PRODUCTION', true, 'ACTIVE', 0, 0, 'assemble')"))

        command.upgrade(config, "head")
        with engine.connect() as conn:
            got = dict(conn.execute(text(
                "SELECT username, production_parts FROM users WHERE username LIKE 'ppg_%'")).all())
            assert got == {"ppg_two": ["edge"], "ppg_none": None, "ppg_old": ["assemble"]}
            kinds = dict(conn.execute(text(
                "SELECT conname, contype FROM pg_constraint WHERE conname = 'ck_users_production_parts'")).all())
            assert kinds == {"ck_users_production_parts": "c"}
            data_type = conn.execute(text(
                "SELECT data_type FROM information_schema.columns WHERE table_name = 'users' "
                "AND column_name = 'production_parts'")).scalar()
            assert data_type == "jsonb"
    finally:
        engine.dispose()
